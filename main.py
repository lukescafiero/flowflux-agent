# ============================================================
# 🧩 Core Imports
# ============================================================
import os
import asyncio
from typing import Optional, List

# ============================================================
# ⚙️ Environment & Config
# ============================================================
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# ============================================================
# 🚀 FastAPI & Middleware
# ============================================================
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter

# ============================================================
# 🌐 External Clients
# ============================================================
from openai import OpenAI
from supabase import create_client, Client

# ============================================================
# 🧱 Data Models
# ============================================================
from pydantic import BaseModel, EmailStr
from notifications import notify_lead_from_row

# ============================================================
# 🔐 Environment Variables
# ============================================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE")  # legacy name supported
    or os.getenv("SUPABASE_ANON_KEY")
)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ============================================================
# 🧠 Initialize Supabase
# ============================================================
supabase: Client | None = None
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[info] Supabase client initialized")
    else:
        print("[WARN] Supabase URL/key missing; Supabase disabled.")
except Exception as e:
    print(f"[ERROR] Supabase init failed: {e}")
    raise

# ============================================================
# 🧠 Initialize OpenAI
# ============================================================
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
if not OPENAI_API_KEY:
    print("[WARN] OpenAI API key missing: set OPENAI_API_KEY")

# ============================================================
# 🚀 FastAPI app
# ============================================================
app = FastAPI()

# ============================================================
# 🔐 CORS
# ============================================================
origins = [
    "https://www.flowfluxmedia.com",
    "https://flowfluxmedia.com",
    "https://flowfluxmedia.squarespace.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8010",
    "http://127.0.0.1:8010",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Trigger-Preflight"],
)

# ============================================================
# 🩺 Health & Diag
# ============================================================
@app.get("/ping")
def ping():
    return {"ok": True}

diag = APIRouter()

@diag.get("/routes")
def list_routes():
    return [r.path for r in app.routes]

try:
    import importlib.metadata as md
except Exception:
    md = None

def _ver(name: str) -> str:
    if md is None: return "n/a"
    try:
        return md.version(name)
    except Exception:
        return "n/a"

@diag.get("/version")
def version():
    return {
        "ok": True,
        "packages": {
            "python": _ver("python"),
            "fastapi": _ver("fastapi"),
            "pydantic": _ver("pydantic"),
            "supabase": _ver("supabase"),
            "httpx": _ver("httpx"),
            "openai": _ver("openai"),
            "uvicorn": _ver("uvicorn"),
        },
        "config": {
            "has_supabase": bool(SUPABASE_URL and SUPABASE_KEY),
            "has_openai_key": bool(OPENAI_API_KEY),
            "allowed_origins": origins,
        },
    }

app.include_router(diag, prefix="/diag")

@app.on_event("startup")
async def _show_routes_startup():
    print("[startup] routes:", [r.path for r in app.routes])

# ============================================================
# 🌐 Helpers
# ============================================================
def _client_ip(request: Request) -> str:
    return (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )

def _domain_from_request(request: Request) -> str:
    return request.headers.get("origin") or request.headers.get("referer") or "unknown"

# ============================================================
# 🧾 Input Models
# ============================================================
class LeadIn(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None
    city: Optional[str] = None
    project_description: Optional[str] = None
    budget_range: Optional[str] = None
    timeline: Optional[str] = None
    service_type: Optional[str] = None
    source: Optional[str] = None

    first_message: Optional[str] = None
    page_url: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    domain: Optional[str] = None
    note: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None

# ============================================================
# 🧲 Lead endpoint
# ============================================================
@app.post("/lead")
async def create_lead(body: LeadIn, request: Request):
    if not supabase:
        return JSONResponse({"ok": False, "error": "server_not_configured"}, status_code=500)

    if not body.name.strip() or not body.phone.strip():
        return JSONResponse({"ok": False, "error": "name_or_phone_missing"}, status_code=400)

    ua = request.headers.get("user-agent", "")[:500]
    ip = _client_ip(request)[:100]

    row = {
        "name": body.name.strip(),
        "phone": body.phone.strip(),
        "email": (body.email or None),
        "city": (body.city or None),
        "project_description": (body.project_description or None),
        "budget_range": (body.budget_range or None),
        "timeline": (body.timeline or None),
        "service_type": (body.service_type or None),
        "source": (body.source or None),

        "first_message": (body.first_message or "").strip(),
        "page_url": (body.page_url or "").strip(),
        "user_agent": ua,
        "ip": ip,
        "utm_source": body.utm_source,
        "utm_medium": body.utm_medium,
        "utm_campaign": body.utm_campaign,
        "domain": (body.domain or _domain_from_request(request)),
        "note": (body.note or ""),
    }

    try:
        res = supabase.table("leads").insert(row).execute()
        try:
            notify_lead_from_row(row)
        except Exception as e:
            print("[notify error]", e)

        new_id = None
        try:
            if hasattr(res, "data") and isinstance(res.data, list) and res.data:
                new_id = res.data[0].get("id")
        except Exception:
            pass

        return JSONResponse({"ok": True, "id": new_id}, status_code=201)

    except Exception as e:
        print("[lead insert error]", e)
        return JSONResponse({"ok": False, "error": "db_insert_failed"}, status_code=500)

# ============================================================
# 💬 Chat endpoint (with session memory)
# ============================================================
@app.post("/chat")
async def chat(payload: ChatRequest):
    if not openai_client or not supabase:
        return JSONResponse({"error": "server_config_missing"}, status_code=500)

    user_msg = (payload.message or "").strip()
    if not user_msg:
        return JSONResponse({"error": "empty_message"}, status_code=400)

    session_id = payload.session_id or "anon"
    name = (payload.name or None)
    phone = (payload.phone or None)

    # Save inbound (best effort)
    try:
        supabase.table("messages").insert({
            "direction": "inbound",
            "channel": "chat",
            "content": user_msg,
            "session_id": session_id,
            "name": name,
            "phone": phone,
        }).execute()
    except Exception as e:
        print("Supabase inbound error:", e)

    # Build short history for memory (last 10 messages for this session)
    history: List[dict] = []
    try:
        q = (
            supabase.table("messages")
            .select("direction,content,created_at")
            .eq("session_id", session_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        rows = list(reversed(q.data or []))  # oldest first
        for r in rows:
            role = "assistant" if r.get("direction") == "outbound" else "user"
            content = r.get("content") or ""
            if content:
                history.append({"role": role, "content": content})
    except Exception as e:
        print("Supabase history error:", e)

    # System prompt with lightweight lead memory
    system_prompt = (
        "You are Flow Flux AI, a friendly sales agent who qualifies leads and books consultations. "
        "Politely collect: name, phone, email, city, project description, budget range, and timeline. "
        "If some are known from context, don't ask again; confirm and move on. "
        "Keep replies concise and helpful."
    )
    messages = [{"role": "system", "content": system_prompt}] + history + [
        {"role": "user", "content": user_msg}
    ]

    # Generate response with a firm timeout using thread offload
    try:
        completion = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    max_tokens=200,
                )
            ),
            timeout=15
        )
        reply = completion.choices[0].message.content
    except asyncio.TimeoutError:
        return JSONResponse({"error": "ai_timeout"}, status_code=504)
    except Exception as e:
        print("OpenAI error:", e)
        return JSONResponse({"error": "ai_generation_failed"}, status_code=502)

    # Save outbound (best effort)
    try:
        supabase.table("messages").insert({
            "direction": "outbound",
            "channel": "chat",
            "content": reply,
            "session_id": session_id,
            "name": name,
            "phone": phone,
        }).execute()
    except Exception as e:
        print("Supabase outbound error:", e)

    return {"reply": reply}
