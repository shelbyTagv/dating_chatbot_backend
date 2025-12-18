from dotenv import load_dotenv
load_dotenv()

import os
import time
import uuid
import threading
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import db_manager

app = FastAPI()

# -------------------------------------------------
# ENV
# -------------------------------------------------
GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")

PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
PAYNOW_URL = "https://www.paynow.co.zw/interface/initiatetransaction"

RETURN_URL = os.getenv("PAYNOW_RETURN_URL")
RESULT_URL = os.getenv("PAYNOW_RESULT_URL")

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()
    start_payment_polling()

# -------------------------------------------------
# WHATSAPP SEND
# -------------------------------------------------
def send_whatsapp_message(phone, text):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    try:
        requests.post(
            url,
            json={"chatId": f"{phone}@c.us", "message": text},
            timeout=15
        )
    except Exception as e:
        print("WhatsApp send failed:", e)

# -------------------------------------------------
# PAYNOW CREATE (ECOCASH ONLY)
# -------------------------------------------------
def create_paynow_payment(uid, phone):
    ref = f"ORDER-{uuid.uuid4().hex[:10]}"

    payload = {
        "id": PAYNOW_ID,
        "reference": ref,
        "amount": "2.00",
        "additionalinfo": "Dating Match Unlock",
        "returnurl": RETURN_URL,
        "resulturl": RESULT_URL,
        "authemail": "payments@example.com",
        "phone": phone,
        "method": "ecocash"
    }

    try:
        r = requests.post(PAYNOW_URL, data=payload, timeout=20)
    except Exception as e:
        print("Paynow request error:", e)
        return None

    if r.status_code != 200:
        print("Paynow HTTP error:", r.status_code, r.text)
        return None

    poll_url = None
    pay_url = None

    for line in r.text.splitlines():
        if line.lower().startswith("pollurl="):
            poll_url = line.split("=", 1)[1]
        if line.lower().startswith("browserurl="):
            pay_url = line.split("=", 1)[1]

    if not poll_url or not pay_url:
        print("Paynow response invalid:", r.text)
        return None

    db_manager.create_payment(uid, ref, poll_url)
    return pay_url

# -------------------------------------------------
# PAYMENT POLLING (BACKGROUND THREAD)
# -------------------------------------------------
def poll_payments():
    while True:
        unpaid = db_manager.get_pending_payments()
        for p in unpaid:
            try:
                r = requests.get(p["poll_url"], timeout=15)
                if "paid" in r.text.lower():
                    db_manager.mark_payment_paid(p["id"])
                    db_manager.activate_user(p["user_id"])

                    phone = db_manager.get_user_phone(p["user_id"])
                    matches = db_manager.get_matches(p["user_id"])

                    reply = "✅ *Payment Confirmed!*\n\n📞 Contact details:\n\n"
                    for m in matches:
                        reply += f"{m['name']} — {m['contact_phone']}\n"

                    send_whatsapp_message(phone, reply)
            except Exception as e:
                print("Polling error:", e)

        time.sleep(20)

def start_payment_polling():
    t = threading.Thread(target=poll_payments, daemon=True)
    t.start()

# -------------------------------------------------
# PAYNOW RETURN (USER REDIRECT)
# -------------------------------------------------
@app.get("/paynow/return")
def paynow_return():
    return PlainTextResponse(
        "✅ Payment received.\n\nPlease return to WhatsApp to continue.",
        status_code=200
    )

# -------------------------------------------------
# PAYNOW RESULT (SERVER CALLBACK)
# -------------------------------------------------
@app.post("/paynow/result")
async def paynow_result(request: Request):
    data = await request.form()
    payload = dict(data)
    print("Paynow RESULT callback:", payload)
    return PlainTextResponse("OK", status_code=200)

# -------------------------------------------------
# WEBHOOK (GREEN API)
# -------------------------------------------------
@app.get("/webhook")
async def verify():
    return PlainTextResponse("OK")

@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and auth != f"Bearer {GREEN_API_AUTH_TOKEN}":
        raise HTTPException(status_code=401)

    payload = await request.json()
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    sender = payload.get("senderData", {})
    phone = sender.get("chatId", "").split("@")[0]

    msg = payload.get("messageData", {})
    text = (
        msg.get("textMessageData", {}).get("textMessage")
        or msg.get("extendedTextMessageData", {}).get("text")
        or ""
    ).strip()

    if not phone or not text:
        return JSONResponse({"status": "empty"})

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status": "processed"})

# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------
def handle_message(phone, text):
    msg = text.lower().strip()

    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_new_user(phone)

    uid = user["id"]
    db_manager.ensure_profile(uid)
    state = user.get("chat_state")

    if state == "PAY":
        if msg == "pay":
            link = create_paynow_payment(uid, phone)
            if not link:
                return "❌ Payment initiation failed. Please try again later."
            return f"💳 Pay via EcoCash:\n{link}\n\n⏳ Waiting for confirmation..."
        return "💰 Reply *PAY* to unlock contact details."

    # Placeholder for your existing flow
    return "OK"
