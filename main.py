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

