# flowflux-agent/notifications.py
import os
import json
import ssl
import smtplib
import urllib.request

# ---------- Config ----------
ENV = os.getenv("ENV", "dev").lower()              # dev | prod
NOTIFY_CHANNELS = os.getenv("NOTIFY_CHANNELS", "slack").split(",")

# Slack
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Email (optional)
EMAIL_TO   = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
SMTP_HOST  = os.getenv("SMTP_HOST", "smtp.gmail.com")  # set if you use email
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER  = os.getenv("SMTP_USER")
SMTP_PASS  = os.getenv("SMTP_PASS")

# ---------- Providers ----------
def _send_slack(text: str):
    if not SLACK_WEBHOOK_URL:
        print("[notify] Slack not configured"); return
    body = json.dumps({"text": text}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            _ = r.read()
    except Exception as e:
        print("[notify] Slack error:", e)

def _send_email(subject: str, body: str):
    if not all([EMAIL_TO, EMAIL_FROM, SMTP_HOST, SMTP_USER, SMTP_PASS]):
        print("[notify] Email not configured"); return
    msg = f"From: {EMAIL_FROM}\r\nTo: {EMAIL_TO}\r\nSubject: {subject}\r\n\r\n{body}"
    ctx = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASS)
            s.sendmail(EMAIL_FROM, [EMAIL_TO], msg)
    except Exception as e:
        print("[notify] Email error:", e)

# ---------- Helpers ----------
def _fmt_phone(p: str) -> str:
    d = "".join(ch for ch in (p or "") if ch.isdigit())
    if len(d) == 11 and d[0] == "1": d = d[1:]
    return f"({d[0:3]}) {d[3:6]}-{d[6:10]}" if len(d) == 10 else (p or "")

# ---------- Public API ----------
def notify_lead_from_row(row: dict):
    """
    Call this with the same 'row' dict you inserted into Supabase.
    Keys it uses (all optional): name, phone, domain, note, first_message,
    page_url, utm_source, utm_medium, utm_campaign
    """
    name  = (row.get("name") or "(no name)").strip()
    phone = _fmt_phone(row.get("phone", ""))
    domain = row.get("domain") or "unknown"
    note = (row.get("note") or row.get("first_message") or "").strip()
    page_url = row.get("page_url") or ""

    utm_bits = []
    for k in ("utm_source", "utm_medium", "utm_campaign"):
        v = row.get(k)
        if v: utm_bits.append(f"{k}={v}")
    utm = ", ".join(utm_bits)

    prefix = "" if ENV == "prod" else "[DEV] "
    text = (
        f"{prefix}🚀 *NEW LEAD*\n"
        f"*Name:* {name}\n"
        f"*Phone:* {phone}\n"
        f"*Site:* {domain}\n"
        + (f"*From:* {page_url}\n" if page_url else "")
        + (f"*UTM:* {utm}\n" if utm else "")
        + (f"*Note:* {note[:300]}" if note else "")
    )

    channels = [c.strip().lower() for c in NOTIFY_CHANNELS if c.strip()]
    for ch in channels:
        if ch == "slack":
            _send_slack(text)
        elif ch == "email":
            _send_email("NEW LEAD 🚀", text)
        elif ch == "sms":
            # left unimplemented on purpose
            print("[notify] SMS channel selected but not configured")
        else:
            print(f"[notify] Unknown channel: {ch}")
