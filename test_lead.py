# test_lead.py
import json, urllib.request

URL = "http://127.0.0.1:8000/lead"  # change to your deployed URL if you prefer

body = {
    "name": "Alex Tester",
    "phone": "7075559999",
    "first_message": "Testing Slack alerts from local server",
    "page_url": "https://flowfluxmedia.com",
    "utm_source": "localtest",
    "utm_medium": "cli",
    "utm_campaign": "slack-verify",
    "domain": "flowfluxmedia.com",
    "note": "Confirming Slack notifications work properly."
}

req = urllib.request.Request(
    URL,
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(req, timeout=10) as r:
    print("Status:", r.status)
    print("Body:", r.read().decode())
