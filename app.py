from dotenv import load_dotenv
load_dotenv()

import os
import time
import hashlib
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import db_manager

app = FastAPI()

# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------
GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")

PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")
PAYMENT_AMOUNT = "2.00"

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()

# -------------------------------------------------
# SEND WHATSAPP MESSAGE
# -------------------------------------------------
def send_whatsapp_message(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    requests.post(url, json=payload, timeout=15)

# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------
INTENT_MAP = {
    "1": "sugar mummy",
    "2": "sugar daddy",
    "3": "benten",
    "4": "girlfriend",
    "5": "boyfriend",
    "6": "1 night stand",
    "7": "just vibes",
    "8": "friend",
}

AGE_MAP = {
    "1": (18, 25),
    "2": (26, 30),
    "3": (31, 35),
    "4": (36, 40),
    "5": (41, 50),
    "6": (50, 99),
}

def infer_gender(intent):
    if intent in ["girlfriend", "sugar mummy"]:
        return "female"
    if intent in ["boyfriend", "benten", "sugar daddy"]:
        return "male"
    return "any"

# -------------------------------------------------
# WEBHOOK VERIFY
# -------------------------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    return PlainTextResponse("OK")

# -------------------------------------------------
# INCOMING WEBHOOK (WORKING FORMAT)
# -------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and (not auth or auth.replace("Bearer ", "") != GREEN_API_AUTH_TOKEN):
        raise HTTPException(status_code=401)

    payload = await request.json()
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    sender = payload.get("senderData", {})
    message_data = payload.get("messageData", {})

    raw_chat_id = sender.get("chatId", "")
    phone = raw_chat_id.split("@")[0]

    text = ""
    if "textMessageData" in message_data:
        text = message_data["textMessageData"].get("textMessage", "").strip()
    elif "extendedTextMessageData" in message_data:
        text = message_data["extendedTextMessageData"].get("text", "").strip()

    if not phone or not text:
        return JSONResponse({"status": "no-text"})

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status": "processed"})

# -------------------------------------------------
# CHAT LOGIC (NEW FLOW, WORKING)
# -------------------------------------------------
def handle_message(phone: str, text: str) -> str:
    msg = text.strip()
    msg_l = msg.lower()

    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if msg_l == "exit":
        db_manager.reset_user(uid)
        return "❌ Conversation ended.\nType HELLO to start again."

    if state == "NEW":
        db_manager.update_chat_state(uid, "WELCOME")
        return (
            "Welcome to Shelby Date Connections ❤️\n\n"
            "1️⃣ Fill in your details & preferences\n"
            "2️⃣ View 2 matches\n"
            "3️⃣ Pay $2 to unlock contacts\n"
            "4️⃣ Your privacy is our concern\n\n"
            "Type HELLO to start or EXIT anytime."
        )

    if state == "WELCOME":
        if msg_l != "hello":
            return "Please type HELLO to continue."
        db_manager.update_chat_state(uid, "GET_INTENT")
        return (
            "What are you looking for?\n\n"
            "1️⃣ Sugar mummy\n"
            "2️⃣ Sugar daddy\n"
            "3️⃣ Benten\n"
            "4️⃣ Girlfriend\n"
            "5️⃣ Boyfriend\n"
            "6️⃣ 1 night stand\n"
            "7️⃣ Just vibes\n"
            "8️⃣ Friend"
        )

    if state == "GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent:
            return "Please reply with a number (1–8)."
        db_manager.update_profile_field(uid, "intent", intent)
        db_manager.update_profile_field(uid, "preferred_gender", infer_gender(intent))
        db_manager.update_chat_state(uid, "GET_AGE_RANGE")
        return (
            "Preferred age range:\n\n"
            "1️⃣ 18-25\n"
            "2️⃣ 26-30\n"
            "3️⃣ 31-35\n"
            "4️⃣ 36-40\n"
            "5️⃣ 41-50\n"
            "6️⃣ 50+"
        )

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r:
            return "Choose a valid age range (1–6)."
        db_manager.update_profile_field(uid, "age_min", r[0])
        db_manager.update_profile_field(uid, "age_max", r[1])
        db_manager.update_chat_state(uid, "GET_NAME")
        return "Your name?"

    if state == "GET_NAME":
        db_manager.update_profile_field(uid, "name", msg)
        db_manager.update_chat_state(uid, "GET_AGE")
        return "Your age?"

    if state == "GET_AGE":
        if not msg.isdigit():
            return "Please enter a valid age."
        db_manager.update_profile_field(uid, "age", int(msg))
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Your location?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", msg)
        db_manager.update_chat_state(uid, "GET_PHONE")
        return "Your phone number?"

    if state == "GET_PHONE":
        db_manager.update_profile_field(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)

        if not matches:
            return "No matches found yet. Try again later."

        preview = "🔥 Top Matches:\n\n"
        for m in matches:
            preview += f"{m['name']} ({m['age']}) – {m['location']} [{m['intent']}]\n"

        db_manager.update_chat_state(uid, "PAY")
        return preview + "\n💳 Pay $2 to unlock contacts."

    if state == "PAY":
        reference = f"PAY-{uid}-{int(time.time())}"
        auth_string = f"{PAYNOW_ID}{reference}{PAYMENT_AMOUNT}Unlock{BASE_URL}/paid{BASE_URL}/paynow/ipn{PAYNOW_KEY}"
        hash_val = hashlib.sha512(auth_string.encode()).hexdigest().upper()

        res = requests.post(
            PAYNOW_INIT_URL,
            data={
                "id": PAYNOW_ID,
                "reference": reference,
                "amount": PAYMENT_AMOUNT,
                "additionalinfo": "Unlock",
                "returnurl": f"{BASE_URL}/paid",
                "resulturl": f"{BASE_URL}/paynow/ipn",
                "status": "Message",
                "hash": hash_val,
            },
            timeout=15,
        )

        poll_url = res.text.split("pollurl=")[-1].strip()
        db_manager.create_transaction(uid, reference, poll_url, PAYMENT_AMOUNT)
        return f"👉 Pay here:\n{poll_url}"

    return "Type EXIT to restart."

# -------------------------------------------------
# PAYNOW IPN
# -------------------------------------------------
@app.post("/paynow/ipn")
async def paynow_ipn(request: Request):
    data = await request.form()
    reference = data.get("reference")
    status = data.get("status")

    if status and status.lower() == "paid":
        tx = db_manager.get_transaction_by_reference(reference)
        if tx:
            db_manager.mark_transaction_paid(tx["id"])
            db_manager.unlock_full_profiles(tx["user_id"])

    return PlainTextResponse("OK")
