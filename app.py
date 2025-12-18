from dotenv import load_dotenv
load_dotenv()

import os
import time
import uuid
import threading
import hashlib
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
        print("WhatsApp send error:", e)

# -------------------------------------------------
# PAYNOW HASH (MANDATORY)
# -------------------------------------------------
def generate_paynow_hash(values: dict) -> str:
    s = ""
    for k in sorted(values.keys()):
        s += str(values[k])
    s += PAYNOW_KEY
    return hashlib.sha512(s.encode()).hexdigest().upper()

# -------------------------------------------------
# PAYNOW CREATE (ECOCASH)
# -------------------------------------------------
def create_paynow_payment(uid, ecocash_phone):
    ref = f"ORDER-{uuid.uuid4().hex[:10]}"

    payload = {
        "id": PAYNOW_ID,
        "reference": ref,
        "amount": "2.00",
        "additionalinfo": "Dating Match Unlock",
        "returnurl": RETURN_URL,
        "resulturl": RESULT_URL,
        "authemail": "payments@example.com",
        "phone": ecocash_phone,
        "method": "ecocash"
    }

    payload["hash"] = generate_paynow_hash(payload)

    try:
        r = requests.post(PAYNOW_URL, data=payload, timeout=20)
    except Exception as e:
        print("Paynow request failed:", e)
        return None

    poll_url = None
    pay_url = None

    for line in r.text.splitlines():
        if line.lower().startswith("pollurl="):
            poll_url = line.split("=", 1)[1]
        if line.lower().startswith("browserurl="):
            pay_url = line.split("=", 1)[1]

    if not poll_url or not pay_url:
        print("Invalid Paynow response:", r.text)
        return None

    db_manager.create_payment(uid, ref, poll_url)
    return pay_url

# -------------------------------------------------
# PAYMENT POLLING
# -------------------------------------------------
def poll_payments():
    while True:
        for p in db_manager.get_pending_payments():
            try:
                r = requests.get(p["poll_url"], timeout=15)
                if "paid" in r.text.lower():
                    db_manager.mark_payment_paid(p["id"])
                    db_manager.activate_user(p["user_id"])

                    phone = db_manager.get_user_phone(p["user_id"])
                    matches = db_manager.get_matches(p["user_id"])

                    msg = "✅ *Payment Confirmed!*\n\n📞 Contact details:\n\n"
                    for m in matches:
                        msg += f"{m['name']} — {m['contact_phone']}\n"

                    send_whatsapp_message(phone, msg)
            except:
                pass
        time.sleep(20)

def start_payment_polling():
    threading.Thread(target=poll_payments, daemon=True).start()

# -------------------------------------------------
# PAYNOW RETURN
# -------------------------------------------------
@app.get("/paynow/return")
def paynow_return():
    return PlainTextResponse(
        "✅ Payment completed.\n\nPlease return to WhatsApp.",
        status_code=200
    )

# -------------------------------------------------
# PAYNOW RESULT
# -------------------------------------------------
@app.post("/paynow/result")
async def paynow_result(request: Request):
    data = dict(await request.form())
    print("Paynow RESULT:", data)
    return PlainTextResponse("OK")

# -------------------------------------------------
# WEBHOOK
# -------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and auth != f"Bearer {GREEN_API_AUTH_TOKEN}":
        raise HTTPException(status_code=401)

    payload = await request.json()
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    phone = payload["senderData"]["chatId"].split("@")[0]
    msg = payload["messageData"].get("textMessageData", {}).get("textMessage", "").strip()

    reply = handle_message(phone, msg)
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status": "ok"})

# -------------------------------------------------
# CHAT HANDLER (FULL FLOW)
# -------------------------------------------------
def handle_message(phone, text):
    msg = text.lower().strip()

    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_new_user(phone)

    uid = user["id"]
    state = user["chat_state"]

    # EXIT ALWAYS WORKS
    if msg == "exit":
        db_manager.reset_chat_state(uid)
        return "🔄 Chat restarted."

    # UNPAID → VIEW MATCHES
    if not user["is_paid"]:
        if state is None:
            db_manager.set_chat_state(uid, "AWAITING_ECOCASH")
            return (
                "🔒 To unlock contact details, pay $2 via EcoCash.\n\n"
                "📞 Please enter your EcoCash phone number.\n\n"
                "Type EXIT to cancel."
            )

        if state == "AWAITING_ECOCASH":
            if not msg.isdigit():
                return "❌ Invalid number. Please enter your EcoCash phone number."

            link = create_paynow_payment(uid, msg)
            if not link:
                return "❌ Payment initiation failed. Try again later."

            db_manager.set_chat_state(uid, "PAYMENT_PENDING")
            return (
                "💳 EcoCash payment initiated.\n\n"
                "📲 Please check your phone and enter your EcoCash PIN.\n\n"
                f"{link}\n\n"
                "⏳ Waiting for confirmation..."
            )

        if state == "PAYMENT_PENDING":
            return "⏳ Waiting for EcoCash confirmation..."

    return "OK"
