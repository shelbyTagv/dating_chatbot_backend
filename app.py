from dotenv import load_dotenv
load_dotenv()

import os
import time
import threading
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pesepay import Pesepay  #

import re
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


def process_successful_payment(uid, reference):
    db_manager.mark_payment_paid(reference)
    db_manager.activate_user(uid)
    phone = db_manager.get_user_phone(uid)
    matches = db_manager.get_matches(uid)
    
    msg = "✅ *Payment Successful!*\n\n📞 Here are your matches:\n\n"
    for m in matches:
        msg += f"• {m['name']}: {m['contact_phone']}\n"
    
    send_whatsapp_message(phone, msg)

    # 2. RESET logic: Update is_paid back to 0 so they pay next time
    db_manager.reset_user_payment(uid) # You will need to add this function to db_manager.py
    db_manager.set_state(uid, "NEW")

# -------------------------------------------------
# PAYMENT POLLING (Background Worker)
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
    # Start the background thread for automatic payment confirmation
    threading.Thread(target=check_pending_payments, daemon=True).start()




def is_valid_zim_phone(number):
    # Matches 077, 078, 071 followed by 7 digits
    pattern = r"^(077|078|071)\d{7}$"
    return re.match(pattern, number)
# -------------------------------------------------
# PESEPAY SEAMLESS LOGIC
# -------------------------------------------------
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
# CHATBOT LOGIC
# -------------------------------------------------
INTENT_MAP = {"1":"sugar mummy","2":"sugar daddy","3":"benten","4":"girlfriend","5":"boyfriend","6":"1 night stand","7":"just vibes","8":"friend"}
AGE_MAP = {"1":(18,25),"2":(26,30),"3":(31,35),"4":(36,40),"5":(41,50),"6":(50,99)}
# Allowed options for MALE users
MALE_OPTIONS = ["1", "4", "6", "7", "8"] 
# Allowed options for FEMALE users
FEMALE_OPTIONS = ["2", "3","5" "6", "7", "8"]

# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------

def handle_message(phone: str, text: str) -> str:
    msg = text.strip(); msg_l = msg.lower()
    user = db_manager.get_user_by_phone(phone)
    if not user: user = db_manager.create_new_user(phone)
    uid = user["id"]
    db_manager.ensure_profile(uid)
    state = user["chat_state"] or "NEW"


    if msg_l == "exit": db_manager.set_state(uid, "NEW"); return "❌ Ended. Type *HELLO* to start."

    if state == "NEW":
        # Check if the user is saying a valid greeting
        if msg_l in ["hello", "hi", "hey"]:
            # ONLY reset the profile if they explicitly start over with a greeting
            db_manager.reset_profile(uid)
            db_manager.set_state(uid, "GET_GENDER")
            return "👋 Welcome to Shelby Date!\n\nPlease select your gender:\n• MALE\n• FEMALE"
        else:
            # If they send anything else, do NOT reset and just guide them
            return "👋 Welcome back! Please type *HELLO* or *HI* to start finding matches."

    if state == "GET_GENDER":
        if msg_l not in ["male", "female"]: 
            return "❗ Please type MALE or FEMALE here."
        
        db_manager.update_profile(uid, "gender", msg_l)

        # 2. AUTOMATIC PREFERENCE LOGIC:
        # If user is male, preferred is female. If user is female, preferred is male.
        preferred = "female" if msg_l == "male" else "male"
        db_manager.update_profile(uid, "preferred_gender", preferred)


        db_manager.set_state(uid, "GET_INTENT")

        # We still show different menus, but we won't "block" their choice in the next step
        if msg_l == "male":
            return ("💖 What are you looking for?\n\n"
                    "1️⃣ Sugar mummy\n"
                    "4️⃣ Girlfriend\n"
                    "6️⃣ 1 night stand\n"
                    "7️⃣ Just vibes\n"
                    "8️⃣ Friend")
        else: # female
            return ("💖 What are you looking for?\n\n"
                    "2️⃣ Sugar daddy\n"
                    "3️⃣ Benten\n"
                    "4️⃣ Girlfriend\n"
                    "6️⃣ 1 night stand\n"
                    "7️⃣ Just vibes\n"
                    "8️⃣ Friend")

    if state == "GET_INTENT":
        # Straightforward: Just get the intent from the map. No gender validation.
        intent = INTENT_MAP.get(msg)
        
        if not intent:
            return "❗ Please choose a valid option (1-8)."

        db_manager.update_profile(uid, "intent", intent)
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
        # Check if the name is too short or contains weird characters
        if len(msg) < 3 or len(msg) > 20:
            return "❗ Please enter a valid name (3–20 characters)."
        
        db_manager.update_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        return "🎂 How old are you?"
        
    if state == "GET_AGE":
        if not msg.isdigit(): 
            return "❗ Please enter your age as a number (e.g., 25)."
        
        age = int(msg)
        if age < 18:
            db_manager.set_state(uid, "NEW")
            return "❌ Sorry, you must be 18 or older to use this service."
        if age > 80:
            return "❗ Please enter a realistic age."
            
        db_manager.update_profile(uid, "age", age)
        db_manager.set_state(uid, "GET_LOCATION")
        return "📍 Where are you located?"
        
        
    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHONE")
        return "📞 Enter your the Contact where you can be contacted:"
    

    # Insert this block before the other state checks in handle_message
    if state == "AWAITING_MATCHES":
        if msg_l == "status":
            matches = db_manager.get_matches(uid)
            if matches:
                db_manager.set_state(uid, "CHOOSE_CURRENCY")
                reply = "🔥 *Matches Found!* 🔥\n"
                for m in matches: 
                    reply += f"• {m['name']} — {m['location']}\n"
                reply += "\nSelect Currency:\n1️⃣ USD ($2.00)\n2️⃣ ZiG (80 ZiG)"
                return reply
            else:
                return ("⏳ Still looking for matches that fit your profile...\n\n"
                        "Check back later by typing *STATUS*.\n"
                        "Or type *EXIT* to restart and change your profile details.")

        if msg_l == "exit":
            db_manager.reset_profile(uid)
            db_manager.set_state(uid, "GET_GENDER")
            return "👋 Profile cleared. Let's start over!\n\nPlease select your gender:\n• MALE\n• FEMALE"

        return "🔍 You are currently waiting for matches. Type *STATUS* to check again or *EXIT* to redo your profile."

    if state == "GET_PHONE":
        clean_num = msg.strip().replace(" ", "").replace("+263", "0")
        if not is_valid_zim_phone(clean_num):
            return "❗ Invalid number. Please enter a Zimbabwean number (e.g., 0772123456)."

        db_manager.update_profile(uid, "contact_phone", msg)

        matches = db_manager.get_matches(uid)
        matches = db_manager.get_matches(uid)
        if not matches: 
            # Send them to a HOLDING state, not NEW
            db_manager.set_state(uid, "AWAITING_MATCHES") 
            return "✅ Profile saved! We couldn't find matches right now. Type *STATUS* later to check again."
        
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
        
        # Determine parameters based on state
        if state == "AWAITING_ECOCASH_USD":
            success = create_pesepay_payment(uid, clean_num, "PZW211", "USD", 2.00)
            method_name = "EcoCash USD"
        elif state == "AWAITING_ECOCASH_ZIG":
            success = create_pesepay_payment(uid, clean_num, "PZW201", "ZWG", 80.00) # Updated to ZWG
            method_name = "EcoCash ZiG"
        else:
            success = create_pesepay_payment(uid, clean_num, "PZW212", "USD", 2.00)
            method_name = "InnBucks"

        if success:
            db_manager.set_state(uid, "PAYMENT_PENDING")
            
            # --- CUSTOM SUCCESS MESSAGE ---
            return (
                f"🚀 *Payment Initiated via {method_name}!*\n\n"
                f"📲 Please check the phone for **{clean_num}** right now. "
                "A prompt will appear asking for your **PIN**.\n\n"
                "⏳ *What to do next:*\n"
                "1. Enter your PIN carefully.\n"
                "2. Wait patiently while we process the transaction.\n"
                "3. This usually takes **less than 3 minutes**.\n\n"
                "✅ Once confirmed, your matches will be sent automatically to this chat! "
                "You can also type *STATUS* to check manually."
            )
        
        return "❌ Error sending prompt. Please check your number and try again."

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