from dotenv import load_dotenv
load_dotenv()

import os
import time
import hashlib
import requests
import json

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

# -------------------------------------------------
# STARTUP: AUTO-CREATE TABLES
# -------------------------------------------------
@app.on_event("startup")
def startup_event():
    """
    Runs automatically when Railway container starts.
    Ensures MySQL tables exist.
    """
    try:
        db_manager.init_db()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        raise e

# -------------------------------------------------
# GREEN API SEND MESSAGE
# -------------------------------------------------
def send_whatsapp_message(to_chat_id: str, message_text: str):
    if not ID_INSTANCE or not API_TOKEN_INSTANCE:
        print("❌ Green API credentials missing")
        return None

    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {
        "chatId": f"{to_chat_id}@c.us",
        "message": message_text
    }

    try:
        res = requests.post(url, json=payload, timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        print(f"❌ Green API send error: {e}")
        return None

# -------------------------------------------------
# WEBHOOK VERIFICATION
# -------------------------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge, status_code=200)

    raise HTTPException(status_code=403, detail="Verification failed")

# -------------------------------------------------
# INCOMING MESSAGES
# -------------------------------------------------
@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    auth_header = request.headers.get("Authorization")

    if GREEN_API_AUTH_TOKEN and auth_header != GREEN_API_AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()

    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"}, status_code=200)

    sender = payload.get("senderData", {})
    message = payload.get("messageData", {}).get("textMessageData", {})

    raw_chat_id = sender.get("chatId", "")
    phone = raw_chat_id.split("@")[0]
    text = message.get("textMessage", "").strip()

    if not phone or not text:
        return JSONResponse({"status": "no-text"}, status_code=200)

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)

    return JSONResponse({"status": "processed"}, status_code=200)

# -------------------------------------------------
# CHAT LOGIC
# -------------------------------------------------
def handle_message(phone: str, text: str) -> str:
    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if state == "START":
        db_manager.update_chat_state(uid, "GET_NAME")
        return "Welcome ❤️ What is your name?"

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
        if text.capitalize() not in ["Male", "Female", "Other"]:
            return "Please enter Male, Female, or Other."
        db_manager.update_profile_field(uid, "gender", text.capitalize())
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Which city are you in?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_MOTIVE")
        return "What are you looking for? (Soulmate / Casual / Sugar)"

    if state == "GET_MOTIVE":
        if text.capitalize() not in ["Soulmate", "Casual", "Sugar"]:
            return "Please enter Soulmate, Casual, or Sugar."
        db_manager.update_profile_field(uid, "motive", text.capitalize())
        db_manager.update_chat_state(uid, "AWAITING_PAYMENT")
        return initiate_payment(uid)

    if state == "AWAITING_PAYMENT":
        return "💰 Please complete your EcoCash payment to continue."

    if state == "ACTIVE_SEARCH":
        profile = db_manager.get_user_profile(uid)
        match = db_manager.find_potential_matches(uid, profile["location"])

        if match:
            return (
                "🔥 Match Found!\n"
                f"Name: {match['match_name']}\n"
                f"Age: {match['match_age']}\n"
                f"Motive: {match['match_motive']}\n"
                f"Contact: +{match['match_phone']}"
            )

        return "No matches yet. Please try again later."

    return "Please restart the chat."

# -------------------------------------------------
# PAYNOW PAYMENT
# -------------------------------------------------
def initiate_payment(user_id: int) -> str:
    reference = f"SUB-{user_id}-{int(time.time())}"
    amount = "5.00"

    auth_string = f"{PAYNOW_ID}{reference}{amount}{PAYNOW_KEY}"
    hash_val = hashlib.sha512(auth_string.encode()).hexdigest()

    payload = {
        "id": PAYNOW_ID,
        "reference": reference,
        "amount": amount,
        "additionalinfo": "Dating subscription",
        "returnurl": f"{BASE_URL}/paid",
        "resulturl": f"{BASE_URL}/paynow/ipn",
        "status": "Message",
        "hash": hash_val,
    }

    res = requests.post(PAYNOW_INIT_URL, data=payload)

    if "pollurl=" not in res.text:
        return "❌ Payment failed."

    poll_url = res.text.split("pollurl=")[-1]
    db_manager.create_transaction(user_id, reference, poll_url, amount)

    return f"💰 Pay here: {poll_url}"

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
            db_manager.activate_subscription(tx["user_id"])

    return PlainTextResponse("OK", status_code=200)

# -------------------------------------------------
# LOCAL DEV ONLY
# -------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=True,
    )
