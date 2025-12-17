from dotenv import load_dotenv
load_dotenv()

import os, time, hashlib, requests
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

PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")
PAYMENT_AMOUNT = "2.00"

# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()

# -------------------------------------------------
def send_whatsapp_message(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    requests.post(url, json=payload, timeout=10)

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
@app.get("/webhook")
async def verify():
    return PlainTextResponse("OK")

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
    message = payload.get("messageData", {})
    phone = sender.get("chatId", "").split("@")[0]

    text = ""
    if "textMessageData" in message:
        text = message["textMessageData"].get("textMessage", "")
    elif "extendedTextMessageData" in message:
        text = message["extendedTextMessageData"].get("text", "")

    if not phone or not text:
        return JSONResponse({"status": "no-text"})

    reply = handle_message(phone, text.strip())
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status": "ok"})

# -------------------------------------------------
def handle_message(phone: str, text: str) -> str:
    msg = text.lower()
    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if msg == "exit":
        db_manager.reset_user(uid)
        return "❌ Conversation ended.\nType HELLO to start again."

    if state == "NEW":
        db_manager.update_chat_state(uid, "WELCOME")
        return (
            "Welcome to Shelby Date Connections ❤️\n\n"
            "1️⃣ Fill your preferences\n"
            "2️⃣ View matches\n"
            "3️⃣ Pay $2 to unlock contacts\n\n"
            "Type HELLO to begin."
        )

    if state == "WELCOME":
        if msg != "hello":
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
        intent = INTENT_MAP.get(text)
        if not intent:
            return "Reply with a number (1–8)."
        db_manager.update_profile_field(uid, "intent", intent)
        db_manager.update_gender(uid, infer_gender(intent))
        db_manager.update_chat_state(uid, "GET_AGE_RANGE")
        return "Preferred age range:\n1️⃣18-25\n2️⃣26-30\n3️⃣31-35\n4️⃣36-40\n5️⃣41-50\n6️⃣50+"

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(text)
        if not r:
            return "Choose 1–6."
        db_manager.update_profile_field(uid, "age_min", r[0])
        db_manager.update_profile_field(uid, "age_max", r[1])
        db_manager.update_chat_state(uid, "GET_NAME")
        return "Your name?"

    if state == "GET_NAME":
        db_manager.update_profile_field(uid, "name", text)
        db_manager.update_chat_state(uid, "GET_AGE")
        return "Your age?"

    if state == "GET_AGE":
        if not text.isdigit():
            return "Enter a valid age."
        db_manager.update_profile_field(uid, "age", int(text))
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Your location?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_PHONE")
        return "Your phone number?"

    if state == "GET_PHONE":
        db_manager.update_profile_field(uid, "contact_phone", text)
        matches = db_manager.get_matches(uid)
        if not matches:
            return "No matches yet. Try again later."

        msg = "🔥 Top Matches:\n\n"
        for m in matches:
            msg += f"{m['name']} ({m['age']}) – {m['location']} [{m['intent']}]\n"

        db_manager.update_chat_state(uid, "PAY")
        return msg + "\n💳 Pay $2 to unlock contacts."

    if state == "PAY":
        ref = f"PAY-{uid}-{int(time.time())}"
        raw = f"{PAYNOW_ID}{ref}{PAYMENT_AMOUNT}Unlock{BASE_URL}/paid{BASE_URL}/paynow/ipn{PAYNOW_KEY}"
        hash_val = hashlib.sha512(raw.encode()).hexdigest().upper()

        res = requests.post(PAYNOW_INIT_URL, data={
            "id": PAYNOW_ID,
            "reference": ref,
            "amount": PAYMENT_AMOUNT,
            "additionalinfo": "Unlock",
            "returnurl": f"{BASE_URL}/paid",
            "resulturl": f"{BASE_URL}/paynow/ipn",
            "status": "Message",
            "hash": hash_val
        })

        poll = res.text.split("pollurl=")[-1].strip()
        db_manager.create_transaction(uid, ref, poll, PAYMENT_AMOUNT)
        return f"👉 Pay here:\n{poll}"

    return "Type EXIT to restart."

# -------------------------------------------------
@app.post("/paynow/ipn")
async def ipn(request: Request):
    data = await request.form()
    ref = data.get("reference")
    status = data.get("status", "").lower()

    if status == "paid":
        db_manager.mark_transaction_paid(ref)

    return PlainTextResponse("OK")
