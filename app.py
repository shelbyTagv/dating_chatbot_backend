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
# BUTTON DEFINITIONS
# -------------------------------------------------
INTENT_BUTTONS = [
    {"id": "intent_sugar_mummy", "text": "Sugar mummy"},
    {"id": "intent_sugar_daddy", "text": "Sugar daddy"},
    {"id": "intent_benten", "text": "Benten"},
]

INTENT_BUTTONS_2 = [
    {"id": "intent_girlfriend", "text": "Girlfriend"},
    {"id": "intent_boyfriend", "text": "Boyfriend"},
    {"id": "intent_1night", "text": "1 night stand"},
]

INTENT_BUTTONS_3 = [
    {"id": "intent_vibes", "text": "Just vibes"},
    {"id": "intent_friend", "text": "Friend"},
]

AGE_RANGE_BUTTONS = [
    {"id": "age_18_25", "text": "18–25"},
    {"id": "age_26_30", "text": "26–30"},
    {"id": "age_31_35", "text": "31–35"},
]

AGE_RANGE_BUTTONS_2 = [
    {"id": "age_36_40", "text": "36–40"},
    {"id": "age_41_50", "text": "41–50"},
    {"id": "age_50_plus", "text": "50+"},
]

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()

# -------------------------------------------------
# WHATSAPP SENDERS
# -------------------------------------------------
def send_text(chat_id: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    requests.post(url, json={"chatId": f"{chat_id}@c.us", "message": text})

def send_buttons(chat_id: str, text: str, buttons: list):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendButtons/{API_TOKEN_INSTANCE}"
    payload = {
        "chatId": f"{chat_id}@c.us",
        "message": text,
        "buttons": buttons
    }
    requests.post(url, json=payload)

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

    sender = payload.get("senderData", {})
    message = payload.get("messageData", {})
    phone = sender.get("chatId", "").split("@")[0]

    text = ""
    button_id = None
    media = None

    if "textMessageData" in message:
        text = message["textMessageData"].get("textMessage", "").strip()

    elif "buttonsResponseMessageData" in message:
        button_id = message["buttonsResponseMessageData"].get("buttonId")

    elif "imageMessageData" in message:
        media = message["imageMessageData"].get("downloadUrl")

    reply = handle_message(phone, text, button_id, media)
    if reply:
        send_text(phone, reply)

    return JSONResponse({"status": "ok"})

# -------------------------------------------------
# GENDER INFERENCE
# -------------------------------------------------
def infer_gender(intent: str):
    female = ["sugar mummy", "girlfriend"]
    male = ["sugar daddy", "benten", "boyfriend"]

    if intent in female:
        return "Female"
    if intent in male:
        return "Male"
    return "Any"

# -------------------------------------------------
# CHAT LOGIC
# -------------------------------------------------
def handle_message(phone, text, button_id=None, media=None):
    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if text.lower() == "exit":
        db_manager.reset_user(uid)
        return "Conversation ended. Type HELLO to start again."

    # RANDOM MESSAGE → WELCOME
    if state == "NEW":
        db_manager.update_chat_state(uid, "AWAITING_HELLO")
        return (
            "Welcome to Shelby Date Connections where you can find love easily.\n\n"
            "1️⃣ Fill in your details & preferences\n"
            "2️⃣ View 2 matches\n"
            "3️⃣ Pay $2 to unlock contacts\n"
            "4️⃣ Your privacy is our concern\n\n"
            "Type HELLO to start or EXIT anytime."
        )

    if state == "AWAITING_HELLO":
        if text.lower() != "hello":
            return "Please type HELLO to continue or EXIT to cancel."
        db_manager.update_chat_state(uid, "GET_INTENT")
        send_buttons(phone, "What are you looking for?", INTENT_BUTTONS)
        send_buttons(phone, "Choose one:", INTENT_BUTTONS_2)
        send_buttons(phone, "More options:", INTENT_BUTTONS_3)
        return None

    if state == "GET_INTENT" and button_id:
        intent_map = {
            "intent_sugar_mummy": "sugar mummy",
            "intent_sugar_daddy": "sugar daddy",
            "intent_benten": "benten",
            "intent_girlfriend": "girlfriend",
            "intent_boyfriend": "boyfriend",
            "intent_1night": "1 night stand",
            "intent_vibes": "just vibes",
            "intent_friend": "friend",
        }

        intent = intent_map.get(button_id)
        db_manager.update_profile_field(uid, "relationship_type", intent)
        db_manager.update_profile_field(uid, "gender", infer_gender(intent))
        db_manager.update_chat_state(uid, "GET_AGE_RANGE")

        send_buttons(phone, "Preferred age range:", AGE_RANGE_BUTTONS)
        send_buttons(phone, "Select:", AGE_RANGE_BUTTONS_2)
        return None

    if state == "GET_AGE_RANGE" and button_id:
        age_map = {
            "age_18_25": (18, 25),
            "age_26_30": (26, 30),
            "age_31_35": (31, 35),
            "age_36_40": (36, 40),
            "age_41_50": (41, 50),
            "age_50_plus": (50, 70),
        }

        a = age_map.get(button_id)
        db_manager.update_profile_field(uid, "age_min", a[0])
        db_manager.update_profile_field(uid, "age_max", a[1])
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
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Where are you located?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_PHOTO")
        return "Send a photo (optional) or type SKIP."

    if state == "GET_PHOTO":
        if media:
            db_manager.update_profile_field(uid, "photo_url", media)
        db_manager.update_chat_state(uid, "GET_PHONE")
        return "Enter your phone number."

    if state == "GET_PHONE":
        db_manager.update_profile_field(uid, "contact_phone", text)
        db_manager.update_chat_state(uid, "PREVIEW_MATCHES")
        return preview_matches(uid)

    if state == "AWAITING_PAYMENT":
        return "Please complete payment to unlock contacts."

    return None

# -------------------------------------------------
# MATCH PREVIEW
# -------------------------------------------------
def preview_matches(uid):
    matches = db_manager.ai_match_preview(uid)[:2]
    if not matches:
        return "No matches yet. Try again later."

    msg = "🔥 Top Matches:\n\n"
    for m in matches:
        msg += f"{m['name']} ({m['age']}) – {m['location']}\nPreference: {m['relationship_type']}\n\n"

    db_manager.update_chat_state(uid, "AWAITING_PAYMENT")
    msg += initiate_payment(uid)
    return msg

# -------------------------------------------------
# PAYMENT
# -------------------------------------------------
def initiate_payment(uid):
    ref = f"PAY-{uid}-{int(time.time())}"
    raw = f"{PAYNOW_ID}{ref}{PAYMENT_AMOUNT}Unlock{BASE_URL}/paid{BASE_URL}/paynow/ipn{PAYNOW_KEY}"
    hash_val = hashlib.sha512(raw.encode()).hexdigest().upper()

    payload = {
        "id": PAYNOW_ID,
        "reference": ref,
        "amount": PAYMENT_AMOUNT,
        "additionalinfo": "Unlock Matches",
        "returnurl": f"{BASE_URL}/paid",
        "resulturl": f"{BASE_URL}/paynow/ipn",
        "status": "Message",
        "hash": hash_val
    }

    r = requests.post(PAYNOW_INIT_URL, data=payload)
    if "pollurl=" not in r.text.lower():
        return "\nPayment failed. Type HELLO to restart."

    poll = r.text.split("pollurl=")[-1].strip()
    db_manager.create_transaction(uid, ref, poll, PAYMENT_AMOUNT)
    return f"\nPay $2 here:\n{poll}"

# -------------------------------------------------
# PAYNOW IPN
# -------------------------------------------------
@app.post("/paynow/ipn")
async def ipn(request: Request):
    data = await request.form()
    ref = data.get("reference")
    status = data.get("status")

    if status and status.lower() == "paid":
        tx = db_manager.get_transaction_by_reference(ref)
        if tx:
            db_manager.mark_transaction_paid(tx["id"])
            db_manager.unlock_full_profiles(tx["user_id"])

    return PlainTextResponse("OK")
