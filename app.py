from dotenv import load_dotenv
load_dotenv()

import os
import time
import hashlib
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import db_manager

# -------------------------------------------------
# App Initialization
# -------------------------------------------------
app = FastAPI()

# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------
PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")
GREEN_API_URL = "https://api.greenapi.com"

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
PAYMENT_AMOUNT = "2.00"

RELATIONSHIP_TYPES = [
    "Friends",
    "Sugar mummy",
    "Sugar daddy",
    "Soulmate",
    "One night stand",
    "Money deals"
]

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup_event():
    db_manager.init_db()

# -------------------------------------------------
# SEND WHATSAPP MESSAGE
# -------------------------------------------------
def send_whatsapp_message(to_chat_id: str, message_text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {"chatId": f"{to_chat_id}@c.us", "message": message_text}
    requests.post(url, json=payload, timeout=10)

# -------------------------------------------------
# WEBHOOK VERIFY
# -------------------------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403)

# -------------------------------------------------
# INCOMING WEBHOOK
# -------------------------------------------------
@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    auth_header = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and (not auth_header or auth_header.replace("Bearer ", "") != GREEN_API_AUTH_TOKEN):
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
# CHAT LOGIC
# -------------------------------------------------
def handle_message(phone: str, text: str) -> str:
    text_clean = text.strip().lower()
    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if text_clean == "exit":
        db_manager.reset_user(uid)
        return "❌ Conversation ended. Type HELLO to start again."

    if state == "NEW":
        db_manager.update_chat_state(uid, "AWAITING_HELLO")
        return (
            "👋 Welcome! Type HELLO to start.\n"
            "Privacy: your data is safe and only shared after payment."
        )

    if state == "AWAITING_HELLO":
        if text_clean != "hello":
            return "Please type HELLO to start or EXIT to cancel."
        db_manager.update_chat_state(uid, "GET_NAME")
        return "What is your name?"

    if state == "GET_NAME":
        db_manager.update_profile_field(uid, "name", text)
        db_manager.update_chat_state(uid, "GET_AGE")
        return "How old are you?"

    if state == "GET_AGE":
        if not text.isdigit():
            return "Please enter a valid age."
        db_manager.update_profile_field(uid, "age", int(text))
        db_manager.update_chat_state(uid, "GET_GENDER")
        return "Gender? (Male / Female / Other)"

    if state == "GET_GENDER":
        db_manager.update_profile_field(uid, "gender", text.capitalize())
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Which city are you in?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_RELATIONSHIP_TYPE")
        return "Preferred relationship type:\n" + "\n".join(f"- {r}" for r in RELATIONSHIP_TYPES)

    if state == "GET_RELATIONSHIP_TYPE":
        if text.capitalize() not in RELATIONSHIP_TYPES:
            return "Please choose one of the listed options."
        db_manager.update_profile_field(uid, "relationship_type", text.capitalize())
        db_manager.update_chat_state(uid, "GET_PREFERRED_PERSON")
        return "Describe your preferred type of person."

    if state == "GET_PREFERRED_PERSON":
        db_manager.update_profile_field(uid, "preferred_person", text)
        db_manager.update_chat_state(uid, "GET_PHONE")
        return "Please enter your phone number."

    if state == "GET_PHONE":
        db_manager.update_profile_field(uid, "contact_phone", text)
        db_manager.update_chat_state(uid, "PREVIEW_MATCHES")
        return preview_matches(uid)

    if state == "AWAITING_PAYMENT":
        return "💳 Please complete the $2 payment to unlock full profiles."

    return "Type EXIT to restart."

# -------------------------------------------------
# AI MATCH PREVIEW
# -------------------------------------------------
def preview_matches(user_id: int) -> str:
    matches = db_manager.ai_match_preview(user_id)
    if not matches:
        return "No matches yet. Please try again tomorrow as more users join."

    msg = "🔥 Potential Matches:\n\n"
    for m in matches:
        msg += f"- {m['name']} ({m['location']}) — {m['relationship_type']}\n"

    msg += "\n💳 Pay $2 to unlock full profiles."
    db_manager.update_chat_state(user_id, "AWAITING_PAYMENT")
    msg += "\n\n" + initiate_payment(user_id)
    return msg

# -------------------------------------------------
# PAYNOW INIT
# -------------------------------------------------
def initiate_payment(user_id: int) -> str:
    reference = f"PAY-{user_id}-{int(time.time())}"
    auth_string = f"{PAYNOW_ID}{reference}{PAYMENT_AMOUNT}Match Unlock{BASE_URL}/paid{BASE_URL}/paynow/ipnMessage{PAYNOW_KEY}"
    hash_val = hashlib.sha512(auth_string.encode()).hexdigest().upper()

    payload = {
        "id": PAYNOW_ID,
        "reference": reference,
        "amount": PAYMENT_AMOUNT,
        "additionalinfo": "Match Unlock",
        "returnurl": f"{BASE_URL}/paid",
        "resulturl": f"{BASE_URL}/paynow/ipn",
        "status": "Message",
        "hash": hash_val
    }

    res = requests.post(PAYNOW_INIT_URL, data=payload, timeout=15)
    if "pollurl=" not in res.text.lower():
        db_manager.reset_user(user_id)
        return "❌ Payment failed. Type HELLO to start again."

    poll_url = res.text.split("pollurl=")[-1].strip()
    db_manager.create_transaction(user_id, reference, poll_url, PAYMENT_AMOUNT)
    return f"\n👉 Pay here:\n{poll_url}"

# -------------------------------------------------
# PAYNOW IPN
# -------------------------------------------------
@app.post("/paynow/ipn")
async def paynow_ipn(request: Request):
    data = await request.form()
    reference = data.get("reference")
    status = data.get("status")
    if status == "Paid":
        tx = db_manager.get_transaction_by_reference(reference)
        if tx:
            db_manager.mark_transaction_paid(tx["id"])
            db_manager.unlock_full_profiles(tx["user_id"])
    return PlainTextResponse("OK")
