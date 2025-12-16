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
# App
# -------------------------------------------------
app = FastAPI()

PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")

# -------------------------------------------------
# WhatsApp Webhook
# -------------------------------------------------
@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    try:
        payload = await request.json()
        phone = payload["from"]
        text = payload["text"].strip()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    reply = handle_message(phone, text)
    return JSONResponse(content={"reply": reply})

# -------------------------------------------------
# Chat Logic
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
        db_manager.update_profile_field(uid, "gender", text.capitalize())
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Which city are you in?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_MOTIVE")
        return "What are you looking for? (Soulmate / Casual / Sugar)"

    if state == "GET_MOTIVE":
        db_manager.update_profile_field(uid, "motive", text)
        db_manager.update_chat_state(uid, "AWAITING_PAYMENT")
        return initiate_payment(uid)

    if state == "AWAITING_PAYMENT":
        return "💰 Please complete your EcoCash payment to continue."

    if state == "ACTIVE_SEARCH":
        match = db_manager.find_match(uid, user.get("motive"))
        if match:
            return (
                "🔥 Match Found!\n"
                f"Name: {match['name']}\n"
                f"Age: {match['age']}\n"
                f"Location: {match['location']}"
            )
        return "No matches yet. Please check again later."

    return "Something went wrong. Please restart."

# -------------------------------------------------
# Paynow Payment Initiation
# -------------------------------------------------
def initiate_payment(user_id: int) -> str:
    if not PAYNOW_ID or not PAYNOW_KEY or not BASE_URL:
        return "❌ Payment system not configured. Contact support."

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

    response = requests.post(PAYNOW_INIT_URL, data=payload, timeout=30)

    if response.status_code != 200 or "pollurl=" not in response.text:
        return "❌ Payment initiation failed. Try again later."

    poll_url = response.text.split("pollurl=")[-1]
    db_manager.create_transaction(user_id, reference, poll_url, amount)

    return "💰 Payment initiated. Please confirm on EcoCash."

# -------------------------------------------------
# Paynow IPN (Instant Confirmation)
# -------------------------------------------------
@app.post("/paynow/ipn")
async def paynow_ipn(request: Request):
    data = await request.form()

    reference = data.get("reference")
    status = data.get("status")

    if not reference or not status:
        return PlainTextResponse("Invalid IPN", status_code=400)

    if status == "Paid":
        tx = db_manager.get_transaction_by_reference(reference)
        if tx:
            db_manager.mark_transaction_paid(tx["id"])
            db_manager.activate_subscription(tx["user_id"])

    return PlainTextResponse("OK", status_code=200)

# -------------------------------------------------
# Local Run
# -------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000)
