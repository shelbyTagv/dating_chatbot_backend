from dotenv import load_dotenv
load_dotenv()

import os
import time
import hashlib
import requests

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

import db_manager
from init_db import init_db

# -------------------------------------------------
# App Init
# -------------------------------------------------
app = FastAPI()
init_db()

# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------

# Paynow
PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")

# Green API
GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_WEBHOOK_SECRET = os.getenv("GREEN_API_WEBHOOK_SECRET")

# -------------------------------------------------
# Green API Send Message
# -------------------------------------------------
def send_whatsapp_message(phone: str, message: str):
    if not ID_INSTANCE or not API_TOKEN_INSTANCE:
        print("❌ Green API credentials missing")
        return

    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"

    payload = {
        "chatId": f"{phone}@c.us",
        "message": message
    }

    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print(f"✅ Sent message to {phone}")
    except Exception as e:
        print(f"❌ Failed to send message: {e}")

# -------------------------------------------------
# Webhook (Green API ONLY)
# -------------------------------------------------
@app.post("/webhook")
async def webhook(request: Request):

    # Optional security check
    secret = request.headers.get("Authorization")
    if GREEN_API_WEBHOOK_SECRET and secret != GREEN_API_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()

    # Only handle incoming text messages
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return PlainTextResponse("IGNORED", status_code=200)

    sender = payload.get("senderData", {})
    message = payload.get("messageData", {})

    raw_chat_id = sender.get("chatId", "")
    phone = raw_chat_id.replace("@c.us", "")

    text_data = message.get("textMessageData", {})
    text = text_data.get("textMessage", "").strip()

    if not phone or not text:
        return PlainTextResponse("NO_TEXT", status_code=200)

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)

    return PlainTextResponse("OK", status_code=200)

# -------------------------------------------------
# Chat Logic
# -------------------------------------------------
def handle_message(phone: str, text: str) -> str:
    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if state == "START":
        db_manager.update_chat_state(uid, "GET_NAME")
        return "❤️ Welcome! What is your name?"

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
        gender = text.capitalize()
        if gender not in ["Male", "Female", "Other"]:
            return "Please reply with Male, Female, or Other."
        db_manager.update_profile_field(uid, "gender", gender)
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Which city are you in?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_MOTIVE")
        return "What are you looking for? (Soulmate / Casual / Sugar)"

    if state == "GET_MOTIVE":
        motive = text.capitalize()
        if motive not in ["Soulmate", "Casual", "Sugar"]:
            return "Choose: Soulmate, Casual, or Sugar."
        db_manager.update_profile_field(uid, "motive", motive)
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

    return "Please restart the conversation."

# -------------------------------------------------
# Paynow Payment
# -------------------------------------------------
def initiate_payment(user_id: int) -> str:
    if not PAYNOW_ID or not PAYNOW_KEY or not BASE_URL:
        return "❌ Payment not configured."

    reference = f"SUB-{user_id}-{int(time.time())}"
    amount = "5.00"

    hash_string = f"{PAYNOW_ID}{reference}{amount}{PAYNOW_KEY}"
    hash_val = hashlib.sha512(hash_string.encode()).hexdigest()

    payload = {
        "id": PAYNOW_ID,
        "reference": reference,
        "amount": amount,
        "additionalinfo": "Dating Subscription",
        "returnurl": f"{BASE_URL}/paid",
        "resulturl": f"{BASE_URL}/paynow/ipn",
        "status": "Message",
        "hash": hash_val
    }

    r = requests.post(PAYNOW_INIT_URL, data=payload, timeout=30)

    if r.status_code != 200 or "pollurl=" not in r.text:
        return "❌ Payment failed. Try again."

    poll_url = r.text.split("pollurl=")[-1]
    db_manager.create_transaction(user_id, reference, poll_url, amount)

    return f"💳 Pay using EcoCash: {poll_url}"

# -------------------------------------------------
# Paynow IPN
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
# Local Dev
# -------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
