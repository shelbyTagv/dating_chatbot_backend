from dotenv import load_dotenv
load_dotenv()

import os
import uuid
import time
import threading
import hashlib
import requests

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

import db_manager

# -------------------------------------------------
# APP
# -------------------------------------------------
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

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()
    threading.Thread(target=poll_payments, daemon=True).start()

# -------------------------------------------------
# WHATSAPP (GREEN API)
# -------------------------------------------------
def send_whatsapp_message(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("WhatsApp send error:", e)

# -------------------------------------------------
# PAYNOW UTILS
# -------------------------------------------------
VALID_PREFIXES = ["071","072","073","074","075","076","077","078","079"]

def validate_ecocash_number(num: str) -> bool:
    return num.isdigit() and len(num) == 10 and num[:3] in VALID_PREFIXES

def generate_paynow_hash(values: dict) -> str:
    s = "".join(str(values[k]) for k in sorted(values.keys()))
    s += PAYNOW_KEY
    return hashlib.sha512(s.encode()).hexdigest().upper()

def create_paynow_payment(uid: int, phone: str):
    ref = f"ORDER-{uuid.uuid4().hex[:10]}"
    payload = {
        "id": PAYNOW_ID,
        "reference": ref,
        "amount": "2.00",
        "additionalinfo": "Dating Match Unlock",
        "returnurl": "https://example.com/return",
        "resulturl": "https://example.com/result",
        "authemail": "payments@example.com",
        "phone": phone,
        "method": "ecocash"
    }
    payload["hash"] = generate_paynow_hash(payload)

    try:
        r = requests.post(PAYNOW_URL, data=payload, timeout=20)
        poll_url = None
        for line in r.text.splitlines():
            if line.lower().startswith("pollurl="):
                poll_url = line.split("=", 1)[1]

        if not poll_url:
            print("Invalid Paynow response:", r.text)
            return None

        db_manager.create_payment(uid, ref, poll_url)
        return "📲 Check your phone and approve the EcoCash payment."
    except Exception as e:
        print("Paynow error:", e)
        return None

# -------------------------------------------------
# PAYMENT POLLING
# -------------------------------------------------
def poll_payments():
    while True:
        try:
            pending = db_manager.get_pending_payments()
            for p in pending:
                try:
                    r = requests.get(p["poll_url"], timeout=15)
                    if "paid" in r.text.lower():
                        db_manager.mark_payment_paid(p["id"])
                        db_manager.activate_user(p["user_id"])

                        phone = db_manager.get_user_phone(p["user_id"])
                        matches = db_manager.get_matches(p["user_id"])

                        msg = "✅ *Payment Confirmed!*\n\n📞 Contact details:\n\n"
                        for m in matches:
                            msg += f"{m['name']} — {m['phone']}\n"

                        send_whatsapp_message(phone, msg)
                except Exception as e:
                    print("Polling error:", e)
        except Exception as outer:
            print("Polling loop error:", outer)

        time.sleep(20)

# -------------------------------------------------
# WEBHOOK (GREEN API)
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

    # Safely extract text message
    text = ""
    msg_data = payload.get("messageData", {})

    if "textMessageData" in msg_data:
        text = msg_data["textMessageData"].get("textMessage", "")

    elif "extendedTextMessageData" in msg_data:
        text = msg_data["extendedTextMessageData"].get("text", "")
    text = text.strip()

    if not text:
        return JSONResponse({"status": "ignored"})

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)

    return JSONResponse({"status": "processed"})


# -------------------------------------------------
# CHAT CONSTANTS
# -------------------------------------------------
INTENT_MAP = {
    "1": "sugar mummy",
    "2": "sugar daddy",
    "3": "benten",
    "4": "girlfriend",
    "5": "boyfriend",
    "6": "1 night stand",
    "7": "just vibes",
    "8": "friend"
}

AGE_MAP = {
    "1": (18, 25),
    "2": (26, 30),
    "3": (31, 35),
    "4": (36, 40),
    "5": (41, 50),
    "6": (50, 99)
}

def infer_gender(intent):
    if intent in ["girlfriend", "sugar mummy"]:
        return "female"
    if intent in ["boyfriend", "benten", "sugar daddy"]:
        return "male"
    return "any"
def auto_preferred_gender(user_gender: str) -> str:
    return "female" if user_gender == "male" else "male"


# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------
def handle_message(phone: str, text: str) -> str:
    msg = text.strip()
    msg_l = msg.lower()

    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_new_user(phone)

    uid = user["id"]
    state = user["chat_state"] or "NEW"

    db_manager.ensure_profile(uid)

    if msg_l == "exit":
        db_manager.set_state(uid, "NEW")
        return "❌ Conversation ended.\n\nType *HELLO* to start again."

    if state == "NEW":
        db_manager.ensure_profile(uid)
        db_manager.reset_profile(uid)
        db_manager.set_state(uid, "GET_GENDER")
        return (
            "👋 Welcome to Shelby Date connections! Where you can find love in the comfort of your home: Your Privacy is our concern\n\n"
            "Please tell us your gender:\n"
            "• MALE\n• FEMALE\n• OTHER"
        )

    if state == "GET_GENDER":
        if msg_l not in ["male", "female", "other"]:
            return "❗ Reply with *MALE*, *FEMALE* or *OTHER*."
        db_manager.update_profile(uid, "gender", msg_l)
        db_manager.set_state(uid, "WELCOME")
        return "✅ Saved!\n\nType *HELLO* to continue."

    if state == "WELCOME":
        if msg_l != "hello":
            return "👉 Type *HELLO* to proceed."
        db_manager.set_state(uid, "GET_INTENT")
        return (
            "💖 What are you looking for?\n\n"
            "1️⃣ Sugar mummy\n2️⃣ Sugar daddy\n3️⃣ Benten\n"
            "4️⃣ Girlfriend\n5️⃣ Boyfriend\n6️⃣ 1 night stand\n"
            "7️⃣ Just vibes\n8️⃣ Friend"
        )
    
    if state == "GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent:
            return "❗ Choose a number (1–8)."

        # save intent
        db_manager.update_profile(uid, "intent", intent)

        # fetch gender from DB
        gender = db_manager.get_user_gender(uid)
        if not gender:
            return "❌ Gender not set. Please restart by typing EXIT."

    # auto-derive preferred gender (strict opposite)
        preferred_gender = "female" if gender == "male" else "male"
        db_manager.update_profile(uid, "preferred_gender", preferred_gender)

        db_manager.set_state(uid, "GET_AGE_RANGE")
        return (
            "🎂 Preferred age range:\n\n"
            "1️⃣ 18–25\n2️⃣ 26–30\n3️⃣ 31–35\n"
            "4️⃣ 36–40\n5️⃣ 41–50\n6️⃣ 50+"
        )
    

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r:
            return "❗ Choose a valid option."
        db_manager.update_profile(uid, "age_min", r[0])
        db_manager.update_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME")
        return "📝 What is your name?"

    if state == "GET_NAME":
        db_manager.update_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        return "🎂 How old are you?"

    if state == "GET_AGE":
        if not msg.isdigit():
            return "❗ Enter a valid age."
        db_manager.update_profile(uid, "age", int(msg))
        db_manager.set_state(uid, "GET_LOCATION")
        return "📍 Where are you located?"

    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHONE")
        return "📞 Enter your contact number:"

    if state == "GET_PHONE":
        db_manager.update_profile(uid, "temp_contact_phone", msg)
        db_manager.update_profile(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)
        db_manager.set_state(uid, "AWAITING_ECOCASH")

        if not matches:
            db_manager.set_state(uid, "NEW")
            return (
                "✅ Profile saved!\n\n"
                "🚫 No matches found yet. Please check again Later\n\n"
                "🔄 Conversation ended.\n"
                "Type *HELLO* anytime to start again."
            )


        reply = "🔥 *Top Matches for You* 🔥\n\n"
        for m in matches:
            reply += f"• {m['name']} ({m['age']}) — {m['location']}\n"
        reply += "\n💰 Pay *$2* to unlock contact details, 💰 Enter your EcoCash number (e.g. 0779319913):"
        return reply


    if state == "AWAITING_ECOCASH":
        num = msg.replace("+263", "0").replace("263", "0")
        if not validate_ecocash_number(num):
            return "❌ Invalid EcoCash number."
        db_manager.update_profile(uid, "temp_contact_phone", num)
        res = create_paynow_payment(uid, num)
        if not res:
            return "❌ Payment initiation failed."
        db_manager.set_state(uid, "PAYMENT_PENDING")
        return res + "\n\n⏳ Waiting for confirmation..."

    if state == "PAYMENT_PENDING":
        return "⏳ Waiting for EcoCash payment confirmation..."

    return "❗ Please follow the instructions above."
