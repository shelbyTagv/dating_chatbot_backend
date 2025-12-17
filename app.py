from dotenv import load_dotenv
load_dotenv()

import os
import time
import hashlib
import requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import db_manager

app = FastAPI()

# -------------------------------------------------
# ENV CONFIG
# -------------------------------------------------
GREEN_API_URL = os.getenv("GREEN_API_URL")  # e.g. https://api.green-api.com
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN")

PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")
PAYMENT_AMOUNT = "2.00"

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def start():
    db_manager.init_db()

# -------------------------------------------------
# WHATSAPP SENDERS
# -------------------------------------------------
def send_text(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN}"
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text
    }
    r = requests.post(url, json=payload, timeout=15)
    print("SEND_TEXT:", r.status_code, r.text)


def send_buttons(phone: str, text: str, buttons: list):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendButtons/{API_TOKEN}"
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text,
        "buttons": buttons
    }
    r = requests.post(url, json=payload, timeout=15)
    print("SEND_BUTTONS:", r.status_code, r.text)

# -------------------------------------------------
# CONSTANTS
# -------------------------------------------------
INTENTS = [
    ("1", "Sugar mummy"),
    ("2", "Sugar daddy"),
    ("3", "Benten"),
    ("4", "Girlfriend"),
    ("5", "Boyfriend"),
    ("6", "1 night stand"),
    ("7", "Just vibes"),
    ("8", "Friend"),
]

AGE_RANGES = [
    ("1", "18-25"),
    ("2", "26-30"),
    ("3", "31-35"),
    ("4", "36-40"),
    ("5", "41-50"),
    ("6", "50+"),
]

INTENT_VALUE = {
    "1": "sugar mummy",
    "2": "sugar daddy",
    "3": "benten",
    "4": "girlfriend",
    "5": "boyfriend",
    "6": "1 night stand",
    "7": "just vibes",
    "8": "friend",
}

AGE_VALUE = {
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
# WEBHOOK
# -------------------------------------------------
@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    print("WEBHOOK DATA:", data)

    # ---- SAFE MESSAGE EXTRACTION (GREEN API) ----
    msg = (
        data.get("messageData", {})
            .get("textMessageData", {})
            .get("textMessage", "")
    ).strip()

    phone = data.get("senderData", {}).get("sender", "")

    if not msg or not phone:
        return PlainTextResponse("OK")

    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    msg_lower = msg.lower()

    # -------------------------------------------------
    # EXIT
    # -------------------------------------------------
    if msg_lower == "exit":
        db_manager.set_state(uid, "WELCOME")
        send_text(phone, "Conversation ended. Type HELLO to restart.")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # WELCOME
    # -------------------------------------------------
    if state == "NEW" or state == "WELCOME":
        db_manager.set_state(uid, "INTENT")
        send_text(
            phone,
            "Welcome to Shelby Date Connections 💕\n\n"
            "• Fill in your details\n"
            "• View matches\n"
            "• Pay $2 to unlock contacts\n\n"
            "Type HELLO to begin."
        )
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # START
    # -------------------------------------------------
    if state == "INTENT":
        if msg_lower != "hello":
            send_text(phone, "Please type HELLO to continue.")
            return PlainTextResponse("OK")

        buttons = [{"id": k, "text": v} for k, v in INTENTS]
        db_manager.set_state(uid, "GET_INTENT")
        send_buttons(phone, "What are you looking for?", buttons)
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # GET INTENT
    # -------------------------------------------------
    if state == "GET_INTENT":
        intent = INTENT_VALUE.get(msg)
        if not intent:
            send_text(phone, "Please choose using the buttons.")
            return PlainTextResponse("OK")

        db_manager.upsert_profile(uid, "intent", intent)
        db_manager.set_gender(uid, infer_gender(intent))
        db_manager.set_state(uid, "GET_AGE_RANGE")

        buttons = [{"id": k, "text": v} for k, v in AGE_RANGES]
        send_buttons(phone, "Preferred age range:", buttons)
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # AGE RANGE
    # -------------------------------------------------
    if state == "GET_AGE_RANGE":
        r = AGE_VALUE.get(msg)
        if not r:
            send_text(phone, "Please select an age range using buttons.")
            return PlainTextResponse("OK")

        db_manager.upsert_profile(uid, "age_min", r[0])
        db_manager.upsert_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME")
        send_text(phone, "Your name:")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # NAME
    # -------------------------------------------------
    if state == "GET_NAME":
        db_manager.upsert_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        send_text(phone, "Your age:")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # AGE
    # -------------------------------------------------
    if state == "GET_AGE":
        if not msg.isdigit():
            send_text(phone, "Please enter a valid number.")
            return PlainTextResponse("OK")

        db_manager.upsert_profile(uid, "age", int(msg))
        db_manager.set_state(uid, "GET_LOCATION")
        send_text(phone, "Your location:")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # LOCATION
    # -------------------------------------------------
    if state == "GET_LOCATION":
        db_manager.upsert_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHOTO")
        send_text(phone, "Send a photo (or type SKIP):")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # PHOTO
    # -------------------------------------------------
    if state == "GET_PHOTO":
        if msg_lower != "skip":
            db_manager.upsert_profile(uid, "photo_url", msg)
        db_manager.set_state(uid, "GET_PHONE")
        send_text(phone, "Your contact phone number:")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # PHONE + MATCHES
    # -------------------------------------------------
    if state == "GET_PHONE":
        db_manager.upsert_profile(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)

        if not matches:
            send_text(phone, "No matches found yet. Try again later.")
            return PlainTextResponse("OK")

        text = "🔥 Top Matches:\n\n"
        for m in matches:
            text += f"{m['name']} ({m['age']}) – {m['location']} [{m['intent']}]\n"

        db_manager.set_state(uid, "PAY")
        send_text(phone, text + "\n💳 Pay $2 to unlock contacts.")
        return PlainTextResponse("OK")

    # -------------------------------------------------
    # PAY
    # -------------------------------------------------
    if state == "PAY":
        ref = f"PAY-{uid}-{int(time.time())}"
        hash_str = f"{PAYNOW_ID}{ref}{PAYMENT_AMOUNT}Unlock{BASE_URL}/paid{BASE_URL}/ipn{PAYNOW_KEY}"
        hash_val = hashlib.sha512(hash_str.encode()).hexdigest().upper()

        res = requests.post(PAYNOW_INIT_URL, data={
            "id": PAYNOW_ID,
            "reference": ref,
            "amount": PAYMENT_AMOUNT,
            "additionalinfo": "Unlock",
            "returnurl": f"{BASE_URL}/paid",
            "resulturl": f"{BASE_URL}/ipn",
            "status": "Message",
            "hash": hash_val
        })

        poll = res.text.split("pollurl=")[-1]
        db_manager.create_tx(uid, ref, poll)
        send_text(phone, f"Complete payment here:\n{poll}")
        return PlainTextResponse("OK")

    return PlainTextResponse("OK")
