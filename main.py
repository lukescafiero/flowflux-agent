from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from supabase import create_client
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
import asyncio
import os


# --- env + clients ---
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE = os.getenv("SUPABASE_SERVICE_ROLE")

supabase = None
if SUPABASE_URL and SUPABASE_SERVICE_ROLE:
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE)
else:
    print("[WARN] Supabase not configured: set SUPABASE_URL and SUPABASE_SERVICE_ROLE")

# --- FastAPI app (DEFINE THIS BEFORE ROUTES) ---
app = FastAPI()

# --- CORS ---
origins = [
    "https://www.flowfluxmedia.com",
    "https://flowfluxmedia.com",
    "https://flowfluxmedia.squarespace.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET","POST","OPTIONS"],
    allow_headers=["Content-Type","Authorization","X-Trigger-Preflight"],
)

# --- quick health ---
@app.get("/ping")
def ping():
    return {"ok": True}

# --- Lead capture model + utils ---
class LeadIn(BaseModel):
    name: str
    phone: str
    first_message: Optional[str] = None
    page_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

def _client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for","").split(",")[0].strip()
            or (request.client.host if request.client else ""))

# --- Lead endpoint (MUST be after app is defined) ---
@app.post("/lead")
async def create_lead(body: LeadIn, request: Request):
    if not supabase:
        return JSONResponse({"ok": False, "error": "server_not_configured"}, status_code=500)

    ua = request.headers.get("user-agent","")
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
        print("[lead insert error]", e)
        return JSONResponse({"ok": False, "error": "db_insert_failed"}, status_code=500)





class ChatRequest(BaseModel):
    message: str
    phone: Optional[str] = None
    name: Optional[str] = None


@app.post("/chat")
async def chat(payload: ChatRequest):
    user_msg = payload.message

    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY or not supabase:
        return JSONResponse({"error": "Server config missing env vars"}, status_code=500)

    openai = OpenAI(api_key=OPENAI_API_KEY)  # no constructor timeout

    # Save inbound
    try:
        supabase.table("messages").insert({
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
        return JSONResponse({"error": "AI timed out, try again"}, status_code=504)
    except Exception as e:
        print("OpenAI error:", e)
        return JSONResponse({"error": "AI generation failed"}, status_code=502)

    # Save outbound
    try:
        supabase.table("messages").insert({
            "direction": "outbound", "channel": "chat", "content": reply
        }).execute()
    except Exception as e:
        print("Supabase outbound error:", e)

    return {"reply": reply}


   

