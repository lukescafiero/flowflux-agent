from fastapi import FastAPI, Request
from starlette.responses import Response
from openai import OpenAI
from supabase import create_client
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient
from typing import Optional
from fastapi.responses import JSONResponse
import asyncio
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# --- Add near your other env setup (you already have load_dotenv) ---
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)

# --- Pydantic model for lead input ---
class LeadIn(BaseModel):
    name: str
    phone: str
    first_message: Optional[str] = None
    page_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

# --- Small helper for client IP ---
def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for","").split(",")[0].strip()
            or (request.client.host if request.client else ""))

# --- Lead endpoint (no Twilio) ---
@app.post("/lead")
async def create_lead(body: LeadIn, request: Request):
    ua = request.headers.get("user-agent", "")
    ip = _client_ip(request)

    row = {
        "name": body.name.strip(),
        "phone": body.phone.strip(),
        "first_message": (body.first_message or "").strip(),
        "page_url": (body.page_url or "").strip(),
        "user_agent": ua[:500],
        "ip": ip[:100],
        "utm_source": body.utm_source,
        "utm_medium": body.utm_medium,
        "utm_campaign": body.utm_campaign,
    }

    try:
        supabase.table("leads").insert(row).execute()
        return {"ok": True}
    except Exception as e:
        # Log server-side; return clean error to client
        print("[lead insert error]", e)
        return JSONResponse({"ok": False, "error": "db_insert_failed"}, status_code=500)

app = FastAPI()


origins = [
    "https://www.flowfluxmedia.com",
    "https://flowfluxmedia.com",
    "https://flowfluxmedia.squarespace.com",  # optional preview domain
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],   # include OPTIONS for preflight
    allow_headers=["Content-Type", "Authorization", "X-Trigger-Preflight"],
)

# Optional: simple GET that avoids preflight (handy for quick checks)
@app.get("/ping")
def ping():
    return {"ok": True}


class ChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None
    name: Optional[str] = None


@app.post("/chat")
async def chat(payload: ChatRequest):
    user_msg = payload.message

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")

    if not OPENAI_API_KEY or not SUPABASE_URL or not SUPABASE_KEY:
        return JSONResponse({"error": "Server config missing env vars"}, status_code=500)

    openai = OpenAI(api_key=OPENAI_API_KEY, timeout=10)
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)

    # Save inbound
    try:
        sb.table("messages").insert({
            "direction": "inbound", "channel": "chat", "content": user_msg
        }).execute()
    except Exception as e:
        print("Supabase inbound error:", e)

    # Generate response with timeout
    try:
        completion = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are Flow Flux AI, a friendly sales agent who qualifies leads and books consultations."},
                        {"role": "user", "content": user_msg},
                    ],
                    max_tokens=150,
                )
            ),
            timeout=15
        )
        reply = completion.choices[0].message.content
    except asyncio.TimeoutError:
        print("OpenAI call timed out")
        return JSONResponse({"error": "AI timed out, try again"}, status_code=504)
    except Exception as e:
        print("OpenAI error:", e)
        return JSONResponse({"error": "AI generation failed"}, status_code=502)

    # Save outbound
    try:
        sb.table("messages").insert({
            "direction": "outbound", "channel": "chat", "content": reply
        }).execute()
    except Exception as e:
        print("Supabase outbound error:", e)

    return {"reply": reply}

