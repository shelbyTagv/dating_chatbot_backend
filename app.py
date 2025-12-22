from dotenv import load_dotenv
load_dotenv()

import os
import time
import threading
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pesepay import Pesepay  #

import db_manager

# -------------------------------------------------
# APP & CONFIG
# -------------------------------------------------
app = FastAPI()

GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")

INTEGRATION_KEY = os.getenv("PESEPAY_INTEGRATION_KEY")
ENCRYPTION_KEY = os.getenv("PESEPAY_ENCRYPTION_KEY")
RETURN_URL = os.getenv("PAYNOW_RETURN_URL")
RESULT_URL = os.getenv("PAYNOW_RESULT_URL")


integration_key = INTEGRATION_KEY.strip()
encryption_key = ENCRYPTION_KEY.strip()

# Convert hex string to bytes (AES expects 16, 24, or 32 bytes)
aes_key_bytes = bytes.fromhex(encryption_key)  # 16 bytes

# Initialize PesePay SDK
pesepay = Pesepay(INTEGRATION_KEY, ENCRYPTION_KEY)
pesepay.return_url = RETURN_URL
pesepay.result_url = RESULT_URL

# -------------------------------------------------
# WHATSAPP UTILS
# -------------------------------------------------
def send_whatsapp_message(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print("WhatsApp send error:", e)

# -------------------------------------------------
# PAYMENT POLLING (Background Worker)
# -------------------------------------------------
def check_pending_payments():
    """Periodically checks PesePay for transaction updates."""
    while True:
        try:
            pending = db_manager.get_pending_payments()
            for p in pending:
                poll_url = p.get("poll_url")
                if not poll_url:
                    continue

                # Check payment status using poll_url
                response = pesepay.poll_transaction(poll_url)
                if response.success and response.paid:
                    db_manager.mark_payment_paid(p['id'])
                    db_manager.activate_user(p['user_id'])
                    
                    user_phone = db_manager.get_user_phone(p['user_id'])
                    matches = db_manager.get_matches(p['user_id'])
                    
                    msg = "✅ *Payment Confirmed!*\n\n📞 Contact details for your matches:\n\n"
                    for m in matches:
                        msg += f"• {m['name']}: {m['contact_phone']}\n"
                    
                    send_whatsapp_message(user_phone, msg)
            
            time.sleep(30) # Poll every 30 seconds
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(10)

@app.on_event("startup")
def startup():
    db_manager.init_db()
    # Start the background thread for automatic payment confirmation
    threading.Thread(target=check_pending_payments, daemon=True).start()

# -------------------------------------------------
# PESEPAY SEAMLESS LOGIC
# -------------------------------------------------
def create_pesepay_payment(uid: int, phone: str, method: str):
    try:
        customer_name = db_manager.get_profile_name(uid) or "Shelby User"

        # Normalize number
        clean_num = (
            phone.replace(" ", "")
                 .replace("+263", "0")
                 .replace("263", "0")
                 .strip()
        )

        if not clean_num.isdigit() or len(clean_num) != 10:
            print("❌ Invalid EcoCash number:", clean_num)
            return False

        # 🔴 IMPORTANT: method MUST be "ECOCASH"
        if method == "PZW211":
            required_fields = {
                "ecocashNumber": clean_num
            }
        elif method == "INNBUCKS":
            required_fields = {
                "innbucksNumber": clean_num
            }
        else:
            print("❌ Unsupported payment method:", method)
            return False

        payment = pesepay.create_payment(
            "USD",
            method,
            "noreply@shelbydates.com",
            clean_num,
            customer_name
        )

        response = pesepay.make_seamless_payment(
            payment,
            "Shelby Date Connection Fee",
            2.00,
            required_fields
        )

        if response.success:
            db_manager.create_payment(
                uid,
                response.reference_number,
                response.poll_url
            )
            return True

        print("❌ PesePay Error:", response.message)
        return False

    except Exception as e:
        print("❌ Payment Exception:", str(e))
        return False


# -------------------------------------------------
# CHATBOT LOGIC
# -------------------------------------------------
INTENT_MAP = {"1":"sugar mummy","2":"sugar daddy","3":"benten","4":"girlfriend","5":"boyfriend","6":"1 night stand","7":"just vibes","8":"friend"}
AGE_MAP = {"1":(18,25),"2":(26,30),"3":(31,35),"4":(36,40),"5":(41,50),"6":(50,99)}

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
        return "❌ Conversation ended. Type *HELLO* to start again."

    # --- Registration States ---
    if state == "NEW":
        db_manager.reset_profile(uid)
        db_manager.set_state(uid, "GET_GENDER")
        return "👋 Welcome to Shelby Date! Find love privately.\n\nPlease tell us your gender:\n• MALE\n• FEMALE\n• OTHER"

    if state == "GET_GENDER":
        if msg_l not in ["male", "female", "other"]: return "❗ Reply with *MALE*, *FEMALE* or *OTHER*."
        db_manager.update_profile(uid, "gender", msg_l)
        db_manager.set_state(uid, "WELCOME")
        return "✅ Saved! Type *HELLO* to continue."

    if state == "WELCOME":
        db_manager.set_state(uid, "GET_INTENT")
        return "💖 What are you looking for?\n\n1️⃣ Sugar mummy\n2️⃣ Sugar daddy\n3️⃣ Benten\n4️⃣ Girlfriend\n5️⃣ Boyfriend\n6️⃣ 1 night stand\n7️⃣ Just vibes\n8️⃣ Friend"

    if state == "GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent: return "❗ Choose 1–8."
        db_manager.update_profile(uid, "intent", intent)
        gender = db_manager.get_user_gender(uid)
        db_manager.update_profile(uid, "preferred_gender", "female" if gender == "male" else "male")
        db_manager.set_state(uid, "GET_AGE_RANGE")
        return "🎂 Preferred age range:\n1️⃣ 18–25\n2️⃣ 26–30\n3️⃣ 31–35\n4️⃣ 36–40\n5️⃣ 41–50\n6️⃣ 50+"

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r: return "❗ Choose 1–6."
        db_manager.update_profile(uid, "age_min", r[0])
        db_manager.update_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME")
        return "📝 What is your name?"

    if state == "GET_NAME":
        db_manager.update_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        return "🎂 How old are you?"

    if state == "GET_AGE":
        if not msg.isdigit(): return "❗ Enter a number."
        db_manager.update_profile(uid, "age", int(msg))
        db_manager.set_state(uid, "GET_LOCATION")
        return "📍 Where are you located?"

    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHONE")
        return "📞 Enter your WhatsApp contact number:"

    # --- Match & Payment Logic ---
    if state == "GET_PHONE":
        db_manager.update_profile(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)
        if not matches:
            db_manager.set_state(uid, "NEW")
            return "✅ Profile saved! No matches found yet. We will notify you later."
        
        db_manager.set_state(uid, "CHOOSE_METHOD")
        reply = "🔥 *Matches Found!* 🔥\n\n"
        for m in matches:
            reply += f"• {m['name']} ({m['age']}) — {m['location']}\n"
        reply += "\nSelect payment method to unlock contacts:\n1️⃣ EcoCash\n2️⃣ InnBucks"
        return reply

    if state == "CHOOSE_METHOD":
        if msg == "1":
            db_manager.set_state(uid, "AWAITING_ECOCASH")
            return "💰 Enter EcoCash number (e.g. 0779319913):"
        elif msg == "2":
            db_manager.set_state(uid, "AWAITING_INNBUCKS")
            return "💰 Enter InnBucks number (e.g. 0779319913):"
        return "❗ Please choose 1 or 2."

    if state in ["AWAITING_ECOCASH", "AWAITING_INNBUCKS"]:
        method = "PZW211" if state == "AWAITING_ECOCASH" else "INNBUCKS"
    
        # Normalize number to 0XXXXXXXXX format
        clean_num = msg.strip().replace(" ", "").replace("+263", "0").replace("263", "0")
    
    #    Validate number length
        if method == "PZW211" and (not clean_num.isdigit() or len(clean_num) != 10):
            return "❌ Invalid EcoCash number. Enter in format 07XXXXXXXX."

        if create_pesepay_payment(uid, clean_num, method):
            db_manager.set_state(uid, "PAYMENT_PENDING")
            return f"⏳ *Payment Initiated via {method}*. Please confirm on your phone."
        else:
            return "❌ Payment initiation failed. Check number and try again."

    if state == "PAYMENT_PENDING":
        return "⏳ Still waiting for payment confirmation. Please ensure you've entered your PIN on your phone."

    return "❗ Type *HELLO* to start."

# -------------------------------------------------
# WEBHOOK ENDPOINT
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
    msg_data = payload.get("messageData", {})
    text = msg_data.get("textMessageData", {}).get("textMessage", "") or \
           msg_data.get("extendedTextMessageData", {}).get("text", "")

    if text:
        reply = handle_message(phone, text)
        send_whatsapp_message(phone, reply)

    return JSONResponse({"status": "processed"})