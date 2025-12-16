from dotenv import load_dotenv
load_dotenv()

import os
import time
import hashlib
import requests

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse

# Assuming db_manager.py is in the same directory and uses lazy loading
import db_manager

# -------------------------------------------------
# App Initialization & Config
# -------------------------------------------------
app = FastAPI()

PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")

# Define the verification token here, read from environment variables
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

#Remove comment later 
# -------------------------------------------------
# WhatsApp Webhook - VERIFICATION (The FIX)
# -------------------------------------------------
@app.get("/webhook")
async def verify_webhook(request: Request):
    """Handles the Meta GET request for webhook verification."""
    
    # 1. Get the parameters Meta sent in the request URL
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    # 2. Check if the mode is 'subscribe' and the token matches your secret
    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        # Success: Return the challenge string back to Meta
        return PlainTextResponse(challenge, status_code=200)
    else:
        # Failure: Mismatch, token is wrong, or mode is wrong
        raise HTTPException(status_code=403, detail="Verification failed: Token mismatch or wrong mode.")


# -------------------------------------------------
# WhatsApp Webhook - INCOMING MESSAGES (POST)
# -------------------------------------------------
@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Handles incoming WhatsApp messages."""
    try:
        # Note: The request from Meta is complex, we need to extract the message text/phone
        # This example assumes your message parsing logic is handled by a different tool
        # that feeds a simplified payload to this endpoint, but we should use the raw Meta payload here.
        
        # --- Simplified Payload Handling (as used in your original post) ---
        payload = await request.json()
        phone = payload["from"]
        text = payload["text"].strip()
        
    except Exception:
        # If the incoming request is not in the format expected by the bot, ignore it
        return JSONResponse(content={"status": "Payload processed but ignored"}), 200

    # Ensure phone number is in a format your DB can read (e.g., stripping the "+")
    if phone.startswith("+"):
        phone = phone[1:] 

    reply = handle_message(phone, text)
    # The return here only confirms to Meta you received the message;
    # you still need to send the reply back using the WhatsApp API token.
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
        # Simple validation for the sake of progression
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
        # Simple validation for the sake of progression
        if text.capitalize() not in ["Soulmate", "Casual", "Sugar"]:
            return "Please enter Soulmate, Casual, or Sugar."
            
        db_manager.update_profile_field(uid, "motive", text.capitalize())
        db_manager.update_chat_state(uid, "AWAITING_PAYMENT")
        return initiate_payment(uid)

    if state == "AWAITING_PAYMENT":
        return "💰 Please complete your EcoCash payment to continue."

    if state == "ACTIVE_SEARCH":
        # 1. Get user profile details to pass to the matching query
        profile = db_manager.get_user_profile(uid)
        
        if not profile:
             return "Your profile is incomplete. Cannot search for a match."
             
        # 2. Use the ADVANCED matching query (from the refactored db_manager.py)
        # Note: We are using location, but the find_potential_matches query is complex
        match = db_manager.find_potential_matches(uid, profile["location"]) 
        
        if match:
            # Note: This reply only shows the match data, you still need to send it via WhatsApp API
            return (
                "🔥 Match Found!\n"
                f"Name: {match['match_name']}\n"
                f"Age: {match['match_age']}\n"
                f"Motive: {match['match_motive']}\n"
                f"Contact: +{match['match_phone']}" # Give the user the phone number to contact
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

    # Hashing logic for Paynow
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

    return f"💰 Payment initiated. Please confirm on EcoCash. Pay here: {poll_url}"

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

    # Note: A full implementation should verify the Paynow hash here for security.

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
    # Make sure to run with reload and use the correct app:app format for uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)