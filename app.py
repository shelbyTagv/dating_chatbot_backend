from dotenv import load_dotenv
load_dotenv()

import os
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import db_manager

import uuid
import threading
import hashlib
import time

app = FastAPI()

GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")

PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
PAYNOW_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
RETURN_URL = os.getenv("PAYNOW_RETURN_URL")
RESULT_URL = os.getenv("PAYNOW_RESULT_URL")

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()
    start_payment_polling()

VALID_PREFIXES = ["071","072","073","074","075","076","077","078","079"]

def validate_ecocash_number(number: str) -> bool:
    number = number.strip()
    if not number.isdigit() or len(number) != 10 or number[:3] not in VALID_PREFIXES:
        return False
    return True

def generate_paynow_hash(values: dict) -> str:
    s = "".join(str(values[k]) for k in sorted(values.keys()))
    s += PAYNOW_KEY
    return hashlib.sha512(s.encode()).hexdigest().upper()

def create_paynow_payment(uid, ecocash_phone):
    ref = f"ORDER-{uuid.uuid4().hex[:10]}"
    payload = {
        "id": PAYNOW_ID,
        "reference": ref,
        "amount": "2.00",
        "additionalinfo": "Dating Match Unlock",
        "returnurl": RETURN_URL,
        "resulturl": RESULT_URL,
        "authemail": "payments@example.com",
        "phone": ecocash_phone,
        "method": "ecocash"
    }
    payload["hash"] = generate_paynow_hash(payload)

    try:
        r = requests.post(PAYNOW_URL, data=payload, timeout=20)
    except Exception as e:
        print("Paynow request failed:", e)
        return None

    poll_url = None
    pay_url = None
    for line in r.text.splitlines():
        if line.lower().startswith("pollurl="):
            poll_url = line.split("=", 1)[1]
        if line.lower().startswith("browserurl="):
            pay_url = line.split("=", 1)[1]

    if not poll_url or not pay_url:
        print("Invalid Paynow response:", r.text)
        return None

    db_manager.create_payment(uid, ref, poll_url)
    return pay_url

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
                            msg += f"{m['name']} — {m['contact_phone']}\n"
                        send_whatsapp_message(phone, msg)
                except Exception as e_inner:
                    print(f"Error polling payment {p['id']}: {e_inner}")
        except Exception as e_outer:
            print("Payment polling error:", e_outer)
        time.sleep(20)

def start_payment_polling():
    threading.Thread(target=poll_payments, daemon=True).start()


# -------------------------------------------------
# WHATSAPP SEND
# -------------------------------------------------
def send_whatsapp_message(phone, text):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    requests.post(
        url,
        json={"chatId": f"{phone}@c.us", "message": text},
        timeout=15
    )

# -------------------------------------------------
# WEBHOOK
# -------------------------------------------------
@app.get("/webhook")
async def verify():
    return PlainTextResponse("OK")

@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and auth != f"Bearer {GREEN_API_AUTH_TOKEN}":
        raise HTTPException(status_code=401)

    payload = await request.json()
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    sender = payload.get("senderData", {})
    phone = sender.get("chatId", "").split("@")[0]

    msg = payload.get("messageData", {})
    text = (
        msg.get("textMessageData", {}).get("textMessage")
        or msg.get("extendedTextMessageData", {}).get("text")
        or ""
    ).strip()

    if not phone or not text:
        return JSONResponse({"status": "empty"})

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status": "processed"})

# -------------------------------------------------
# CHAT CONSTANTS (UX PRESERVED)
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

# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------
def handle_message(phone, text):

    
    msg = text.strip()
    msg_l = msg.lower()

    # ------------------------------
    # USER / PROFILE (ONE ONLY)
    # ------------------------------
    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_new_user(phone)
    elif not user["chat_state"]:
        db_manager.set_state(user["id"], "NEW")
        user["chat_state"] = "NEW"

    uid = user["id"]
    state = user["chat_state"]

    print(f"PHONE: {phone}, STATE: {state}, MSG: {msg}")

    # ensure exactly ONE profile exists
    db_manager.ensure_profile(uid)

    # ------------------------------
    # EXIT
    # ------------------------------
    if msg_l == "exit":
        db_manager.set_state(uid, "NEW")
        return "❌ Conversation ended.\n\nType *HELLO* to start again."

    # ------------------------------
    # FLOW
    # ------------------------------
    if state == "":
        db_manager.reset_profile(uid)  # reset profile on new flow
        db_manager.set_state(uid, "GET_GENDER")
        return (
            "👋 Welcome!\n\n"
            "Please tell us your gender:\n"
            "• MALE\n"
            "• FEMALE\n"
            "• OTHER"
        )

    if state == "GET_GENDER":
        msg_l = msg.lower().strip()
        if msg_l not in ["male", "female", "other"]:
            return "❗ Please reply with *MALE*, *FEMALE*, or *OTHER*."
        db_manager.set_gender(uid, msg_l)
        db_manager.set_state(uid, "WELCOME")
        return "✅ Saved!\n\nType *HELLO* to continue."

    if state == "WELCOME":
        if msg_l != "hello":
            return "👉 Please type *HELLO* to proceed."
        db_manager.set_state(uid, "GET_INTENT")
        return (
            "💖 What are you looking for?\n\n"
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
            return "❗ Please choose a number between *1 – 8*."
        db_manager.update_profile(uid, "intent", intent)
        db_manager.update_profile(uid, "preferred_gender", infer_gender(intent))
        db_manager.set_state(uid, "GET_AGE_RANGE")
        return (
            "🎂 Preferred age range:\n\n"
            "1️⃣ 18–25\n"
            "2️⃣ 26–30\n"
            "3️⃣ 31–35\n"
            "4️⃣ 36–40\n"
            "5️⃣ 41–50\n"
            "6️⃣ 50+"
        )

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r:
            return "❗ Please select a valid option *(1 – 6)*."
        db_manager.update_profile(uid, "age_min", r[0])
        db_manager.update_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME")
        return "📝 What is your *name*?"

    if state == "GET_NAME":
        db_manager.update_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        return "🎂 How old are you?"

    if state == "GET_AGE":
        if not msg.isdigit():
            return "❗ Please enter a valid age."
        db_manager.update_profile(uid, "age", int(msg))
        db_manager.set_state(uid, "GET_LOCATION")
        return "📍 Where are you located?"

    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHONE")
        return "📞 Enter your contact number:"

    if state == "GET_PHONE":
        db_manager.update_profile(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)
        db_manager.set_state(uid, "PAY")

        if not matches:
            return (
                "✅ Profile saved successfully!\n\n"
                "🚫 No matches found yet.\n"
                "We will notify you when new matches appear."
            )

        reply = "🔥 *Top Matches for You* 🔥\n\n"
        for m in matches:
            reply += f"• {m['name']} ({m['age']}) — {m['location']}\n"
        reply += "\n💰 Pay *$2* to unlock contact details."
        return reply

    # ------------------------------
    # PAYMENT LOGIC
    # ------------------------------
    if state == "PAY":
        db_manager.set_state(uid, "AWAITING_ECOCASH")
        return "💰 Please enter your EcoCash number (e.g., 0779319913) to pay $2."

    if state == "AWAITING_ECOCASH":
        # Normalize number
        if msg.startswith("+263"):
            msg = "0" + msg[4:]
        elif msg.startswith("263"):
            msg = "0" + msg[3:]

        if not validate_ecocash_number(msg):
            return "❌ Invalid EcoCash number. Enter like 0779319913."

        db_manager.update_profile(uid, "contact_phone", msg)

        link = create_paynow_payment(uid, msg)
        if not link:
            return "❌ Payment initiation failed. Try again later."

        db_manager.set_state(uid, "PAYMENT_PENDING")
        return (
            "💳 EcoCash payment initiated.\n\n"
            "📲 Check your phone and enter your EcoCash PIN.\n\n"
            f"{link}\n\n"
            "⏳ Waiting for confirmation..."
        )

    if state == "PAYMENT_PENDING":
        return "⏳ Waiting for EcoCash payment confirmation..."

    # ------------------------------
    # FALLBACK
    # ------------------------------
    return "❗ Sorry, I didn't understand that. Please follow the instructions above."


    
    
