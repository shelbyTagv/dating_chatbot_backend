from dotenv import load_dotenv
load_dotenv()

import os
import time
import threading
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pesepay import Pesepay

import db_manager

# -------------------------------------------------
# CONFIG
# -------------------------------------------------
app = FastAPI()

GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")

pesepay = Pesepay(os.getenv("PESEPAY_INTEGRATION_KEY").strip(), os.getenv("PESEPAY_ENCRYPTION_KEY").strip())
pesepay.return_url = os.getenv("PAYNOW_RETURN_URL")
pesepay.result_url = os.getenv("PAYNOW_RESULT_URL")

# -------------------------------------------------
# WHATSAPP & SUCCESS FLOW
# -------------------------------------------------
def send_whatsapp_message(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    try: requests.post(url, json=payload, timeout=10)
    except Exception as e: print("WA Error:", e)

def process_successful_payment(uid, reference):
    db_manager.mark_payment_paid(reference)
    db_manager.activate_user(uid)
    phone = db_manager.get_user_phone(uid)
    matches = db_manager.get_matches(uid)
    
    msg = "✅ *Payment Successful!*\n\n📞 Here are your matches:\n\n"
    for m in matches:
        msg += f"• {m['name']}: {m['contact_phone']}\n"
    
    send_whatsapp_message(phone, msg)
    db_manager.set_state(uid, "NEW")

# -------------------------------------------------
# BACKGROUND POLLING & TIMEOUT (60 Seconds)
# -------------------------------------------------
def check_pending_payments():
    while True:
        try:
            pending = db_manager.get_pending_payments()
            now = time.time()
            for p in pending:
                # 60 Second Timeout logic
                if (now - p['created_at'].timestamp()) > 60:
                    db_manager.set_state(p['user_id'], "NEW")
                    db_manager.mark_payment_paid(p['reference'])
                    send_whatsapp_message(db_manager.get_user_phone(p['user_id']), 
                                          "❌ *Payment Failed!* You took more than 1 minute to pay. Type *HELLO* to try again.")
                    continue

                if p.get("poll_url"):
                    res = pesepay.poll_transaction(p['poll_url'])
                    if res.success and res.paid:
                        process_successful_payment(p['user_id'], p['reference'])
            time.sleep(10)
        except Exception as e: print("Poll Error:", e); time.sleep(10)

@app.on_event("startup")
def startup():
    db_manager.init_db()
    threading.Thread(target=check_pending_payments, daemon=True).start()

# -------------------------------------------------
# PESEPAY SEAMLESS
# -------------------------------------------------
def create_pesepay_payment(uid, phone, method, currency, amount):
    try:
        clean_num = phone.replace("+263", "0").replace("263", "0").strip()
        # EcoCash uses customerPhoneNumber, InnBucks uses innbucksNumber
        fields = {"customerPhoneNumber": clean_num} if "PZW21" in method or "PZW20" in method else {"innbucksNumber": clean_num}
        
        payment = pesepay.create_payment(currency, method, "noreply@shelbydates.com", clean_num, db_manager.get_profile_name(uid))
        response = pesepay.make_seamless_payment(payment, "Shelby Fee", amount, fields)

        if response.success:
            ref = getattr(response, 'referenceNumber', getattr(response, 'reference_number', None))
            poll = getattr(response, 'pollUrl', getattr(response, 'poll_url', None))
            if ref and poll:
                db_manager.create_payment(uid, ref, poll)
                return True
        return False
    except Exception as e: print("Pay Error:", e); return False

# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------
INTENT_MAP = {"1":"sugar mummy","2":"sugar daddy","3":"benten","4":"girlfriend","5":"boyfriend","6":"1 night stand","7":"just vibes","8":"friend"}

def handle_message(phone: str, text: str) -> str:
    msg = text.strip(); msg_l = msg.lower()
    user = db_manager.get_user_by_phone(phone)
    if not user: user = db_manager.create_new_user(phone)
    uid, state = user["id"], user["chat_state"] or "NEW"

    if msg_l == "exit": db_manager.set_state(uid, "NEW"); return "❌ Ended. Type *HELLO* to start."

    if state == "NEW":
        db_manager.reset_profile(uid); db_manager.set_state(uid, "GET_GENDER")
        return "👋 Welcome to Shelby Date!\n\nPlease select your gender:\n• MALE\n• FEMALE"

    if state == "GET_GENDER":
        if msg_l not in ["male", "female"]: return "❗ Please type MALE or FEMALE."
        db_manager.update_profile(uid, "gender", msg_l); db_manager.set_state(uid, "GET_INTENT")
        return "💖 What are you looking for?\n\n1️⃣ Sugar mummy\n2️⃣ Sugar daddy\n3️⃣ Benten\n4️⃣ Girlfriend\n5️⃣ Boyfriend\n6️⃣ 1 night stand\n7️⃣ Just vibes\n8️⃣ Friend"

    if state == "GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent: return "❗ Choose 1-8."
        db_manager.update_profile(uid, "intent", intent); db_manager.set_state(uid, "GET_NAME")
        return "📝 What is your name?"

    if state == "GET_NAME":
        db_manager.update_profile(uid, "name", msg); db_manager.set_state(uid, "GET_PHONE")
        return "📞 Enter your WhatsApp number:"

    if state == "GET_PHONE":
        db_manager.update_profile(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)
        if not matches: db_manager.set_state(uid, "NEW"); return "✅ No matches found yet. Try again later."
        
        db_manager.set_state(uid, "CHOOSE_CURRENCY")
        reply = "🔥 *Matches Found!* 🔥\n"
        for m in matches: reply += f"• {m['name']} — {m['location']}\n"
        reply += "\nSelect Currency:\n1️⃣ USD ($2.00)\n2️⃣ ZiG (80 ZiG)"
        return reply

    if state == "CHOOSE_CURRENCY":
        if msg == "1": db_manager.set_state(uid, "CHOOSE_METHOD_USD"); return "USD Method:\n1️⃣ EcoCash\n2️⃣ InnBucks"
        if msg == "2": db_manager.set_state(uid, "AWAITING_ECOCASH_ZIG"); return "💰 Enter EcoCash ZiG number:"
        return "❗ Choose 1 or 2."

    if state == "CHOOSE_METHOD_USD":
        if msg == "1": db_manager.set_state(uid, "AWAITING_ECOCASH_USD"); return "💰 Enter EcoCash USD number:"
        if msg == "2": db_manager.set_state(uid, "AWAITING_INNBUCKS_USD"); return "💰 Enter InnBucks number:"
        return "❗ Choose 1 or 2."

    if state in ["AWAITING_ECOCASH_USD", "AWAITING_ECOCASH_ZIG", "AWAITING_INNBUCKS_USD"]:
        clean_num = msg.strip().replace("+263", "0").replace("263", "0")
        # ZiG rate is 40:1 ($2.00 = 80 ZiG)
        if state == "AWAITING_ECOCASH_USD": success = create_pesepay_payment(uid, clean_num, "PZW211", "USD", 2.00)
        elif state == "AWAITING_ECOCASH_ZIG": success = create_pesepay_payment(uid, clean_num, "PZW201", "ZIG", 80.00)
        else: success = create_pesepay_payment(uid, clean_num, "PZW212", "USD", 2.00)

        if success:
            db_manager.set_state(uid, "PAYMENT_PENDING")
            return "⏳ *Prompt Sent!* Enter your PIN. Expires in 1 min.\n\nType *STATUS* to check manually."
        return "❌ Error sending prompt. Try again."

    if state == "PAYMENT_PENDING":
        if msg_l == "status":
            pending = db_manager.get_pending_payments_for_user(uid)
            if not pending: return "❌ No active payment. Type *HELLO*."
            res = pesepay.poll_transaction(pending[0]['poll_url'])
            if res.success and res.paid:
                process_successful_payment(uid, pending[0]['reference'])
                return "✅ Verified! Sending matches..."
            return "⏳ Not paid yet. Enter PIN and type *STATUS* again."
        return "⏳ Waiting for PIN. Type *STATUS* to check."

    return "❗ Type *HELLO* to start."

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    if payload.get("typeWebhook") == "incomingMessageReceived":
        phone = payload["senderData"]["chatId"].split("@")[0]
        msg_data = payload.get("messageData", {})
        text = msg_data.get("textMessageData", {}).get("textMessage", "") or \
               msg_data.get("extendedTextMessageData", {}).get("text", "")
        if text: send_whatsapp_message(phone, handle_message(phone, text))
    return JSONResponse({"status": "ok"})