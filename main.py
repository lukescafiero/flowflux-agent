from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from openai import OpenAI
from supabase import create_client
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

load_dotenv()

app = FastAPI()
# --- BEGIN RAW CORS MIDDLEWARE ---
ALLOW_ORIGINS = {
    "https://www.flowfluxmedia.com",
    "https://flowfluxmedia.com",
    "https://flowfluxmedia.squarespace.com",
}

@app.middleware("http")
async def raw_cors(request, call_next):
    origin = request.headers.get("origin", "")
    allowed = origin and (origin in ALLOW_ORIGINS or origin.endswith(".squarespace.com"))

    # Handle preflight early
    if request.method == "OPTIONS":
        req_headers = request.headers.get("access-control-request-headers", "content-type, authorization")
        headers = {
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": req_headers,
            "Access-Control-Max-Age": "86400",
        }
        if allowed:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Vary"] = "Origin"
            headers["Access-Control-Allow-Credentials"] = "true"
        else:
            headers["Access-Control-Allow-Origin"] = "*"
        return Response(status_code=204, headers=headers)

    # Normal requests
    response = await call_next(request)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"
    return response
# --- END RAW CORS MIDDLEWARE ---




# Catch-all preflight so OPTIONS never 400s, and force CORS headers
from fastapi import Request

from fastapi import Request
from starlette.responses import Response

WHITELIST = {
    "https://www.flowfluxmedia.com",
    "https://flowfluxmedia.com",
    # keep preview if you use it:
    "https://flowfluxmedia.squarespace.com",
}

@app.options("/{rest_of_path:path}")
async def preflight_ok(rest_of_path: str, request: Request):
    origin = request.headers.get("origin", "")
    # allow if in whitelist (simple check)
    allow_origin = origin if origin in WHITELIST or origin.endswith(".squarespace.com") else "*"

    # If you need cookies/auth across origins, set credentials True and DO NOT use "*"
    allow_credentials = "true" if allow_origin != "*" else "false"

    req_headers = request.headers.get("access-control-request-headers", "content-type, authorization")

    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": allow_origin,
            "Vary": "Origin",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": req_headers,
            "Access-Control-Max-Age": "86400",
            "Access-Control-Allow-Credentials": allow_credentials,
        },
    )









# Define the request model
class ChatRequest(BaseModel):
    message: str
    phone: str | None = None
    name: str | None = None
    
# Connect to APIs
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
twilio = TwilioClient(os.getenv("TWILIO_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

@app.post("/chat")
async def chat(payload: ChatRequest):
    user_msg = payload.message


    # Save inbound message
    supabase.table("messages").insert({
        "direction": "inbound",
        "channel": "chat",
        "content": user_msg
    }).execute()

    # Generate response
    completion = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are Flow Flux AI, a friendly sales agent who qualifies leads and books consultations."},
            {"role": "user", "content": user_msg}
        ]
    )
    reply = completion.choices[0].message.content

    # Save outbound message
    supabase.table("messages").insert({
        "direction": "outbound",
        "channel": "chat",
        "content": reply
    }).execute()

    return {"reply": reply}
