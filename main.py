from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from supabase import create_client
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

load_dotenv()
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.flowfluxmedia.com",
        "https://flowfluxmedia.com",
        "https://flowfluxmedia.squarespace.com",
    ],
    allow_origin_regex=r"https://.*\.squarespace\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.middleware.cors import CORSMiddleware
import os

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
