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


# TEMP: open it up to prove CORS works
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # temp
    allow_methods=["*"],       # temp
    allow_headers=["*"],       # temp
    allow_credentials=False,   # must be False with "*"
    max_age=86400,
)

# Catch-all preflight so OPTIONS never 400s, and force CORS headers
from fastapi import Request

@app.options("/{rest_of_path:path}")
async def preflight_ok(rest_of_path: str, request: Request):
    origin = request.headers.get("origin", "*")
    req_headers = request.headers.get("access-control-request-headers", "content-type, authorization")
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin": origin,
            "Vary": "Origin",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": req_headers,
            "Access-Control-Max-Age": "86400",
        },
    )






FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")  # set to your site later

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],  # during testing you can use "*"
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
