from fastapi import FastAPI, Request
from openai import OpenAI
from supabase import create_client
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from twilio.rest import Client as TwilioClient

load_dotenv()
app = FastAPI()
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
