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

# Constants for Students
STUDENT_INTENTS = {
    "1": "friends",
    "2": "boyfriend",
    "3": "girlfriend",
    "4": "chills",
    "5": "just vibes"
}

ZIM_UNIVERSITIES = ["UZ", "HIT", "MSU", "NUST", "CUT", "LSU", "AU", "ZEGU", "CUZ", "GZU", "BUSE"]

def send_channel_alert(name, age, location, intent, picture_url):
    """Sends a blurred preview alert to the WhatsApp Channel"""
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendFileByUrl/{API_TOKEN_INSTANCE}"
    
    # We use a placeholder 'blurred' image URL to tease users 
    # Or use the candidate's real picture_url if you want it visible
    image_to_send = picture_url if picture_url else "https://www.classifieds.co.zw/storage/App/Models/Attachment/files/011/040/977/medium/o_1jcg88g5etuk4rd1n3m1eiv1g37.webp"

    caption = (
        f"🔔 *NEW CANDIDATE JOINED!* 🔔\n\n"
        f"👤 *Name:* {name}\n"
        f"🎂 *Age:* {age}\n"
        f"📍 *Location:* {location}\n"
        f"💖 *Looking for:* {intent}\n\n"
        f"👉 *Find them on the Bot here:* \nhttps://wa.me/{ID_INSTANCE.replace('waInstance', '')}"
    )

    payload = {
        "urlFile": image_to_send,
        "fileName": "preview.jpg",
        "caption": caption
    }

    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Channel Alert Error: {e}")
        
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
    
    send_whatsapp_message(phone, "✅ *Payment Successful!* Here are your matches:")

    for m in matches:
        caption = (f"👤 *Name:* {m['name']}\n"
                   f"🎂 *Age:* {m['age']}\n"
                   f"📍 *Location:* {m['location']}\n"
                   f"📞 *Contact:* {m['contact_phone']}")
        
        if m.get('picture'):
            send_whatsapp_image(phone, m['picture'], caption)
        else:
            send_whatsapp_message(phone, caption)
    
    db_manager.reset_user_payment(uid)
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
    pattern = r"^(077|078|071|073)\d{7}$"
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


def send_whatsapp_image(phone: str, image_path: str, caption: str):
    # Check if the path is a URL from Green API
    if image_path.startswith("http"):
        url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendFileByUrl/{API_TOKEN_INSTANCE}"
        payload = {
            "chatId": f"{phone}@c.us",
            "urlFile": image_path,
            "fileName": "profile_picture.jpg",
            "caption": caption
        }
    else:
        # Fallback for local files or fileIds
        url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendFileByUpload/{API_TOKEN_INSTANCE}"
        payload = {
            "chatId": f"{phone}@c.us",
            "fileId": image_path,
            "caption": caption
        }
    
    try:
        requests.post(url, json=payload, timeout=15)
    except Exception as e:
        print(f"Error sending image: {e}")

# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------

def handle_message(phone: str, text: str, payload: dict) -> str:
    msg = text.strip() if text else ""
    msg_l = msg.lower()
    
    # 1. User Initialization
    user = db_manager.get_user_by_phone(phone)
    if not user: 
        user = db_manager.create_new_user(phone)
    uid = user["id"]
    db_manager.ensure_profile(uid)
    
    # 2. Global Commands
    if msg_l == "exit": 
        db_manager.set_state(uid, "NEW")
        return "❌ Session ended. Type *HELLO* to start over."

    if msg_l == "profile":
        profile = db_manager.get_profile(uid)
        if not profile or not profile.get("name"):
            return "❌ Profile incomplete. Type *HELLO* to start."
        caption = (f"👤 *YOUR PROFILE*\n━━━━━━━━━━━━━━━\n"
                   f"📝 Name: {profile['name']}\n"
                   f"🎂 Age: {profile['age']}\n"
                   f"📍 Location/Uni: {profile.get('university') or profile.get('location')}\n"
                   f"💖 Looking for: {profile.get('intent')}")
        if profile.get("picture"):
            send_whatsapp_image(phone, profile["picture"], caption)
            return ""
        return caption

    state = user.get("chat_state", "NEW")

    # -------------------------------------------------
    # STARTING FLOW
    # -------------------------------------------------
    if state == "NEW":
        if msg_l in ["hello", "hi", "hey"]:
            db_manager.reset_profile(uid)
            db_manager.set_state(uid, "CHOOSE_USER_TYPE")
            return ("👋 Welcome to Shelby Dating!\n\n"
                    "Please select who you are:\n"
                    "1️⃣ University Student (Campus Dating)\n"
                    "2️⃣ Zimbabwean Citizen (General Dating)")
        return "👋 Type *HELLO* to start finding matches."

    if state == "CHOOSE_USER_TYPE":
        if msg == "1":
            db_manager.update_profile(uid, "user_type", "STUDENT")
            db_manager.set_state(uid, "GET_UNIVERSITY")
            return f"🎓 Which University are you at?\nValid: {', '.join(ZIM_UNIVERSITIES)}"
        elif msg == "2":
            db_manager.update_profile(uid, "user_type", "CITIZEN")
            db_manager.set_state(uid, "GET_GENDER")
            return "Please select your gender:\n• MALE\n• FEMALE"
        return "❗ Please choose 1 or 2."

    # -------------------------------------------------
    # 1. STUDENT FLOW
    # Flow: Uni -> Target Uni -> Intent -> Gender -> Name -> Photo -> Phone
    # -------------------------------------------------
    if state == "GET_UNIVERSITY":
        uni = msg.upper().strip()
        if uni not in ZIM_UNIVERSITIES:
            return f"❗ Use a valid abbreviation: {', '.join(ZIM_UNIVERSITIES[:5])}..."
        db_manager.update_profile(uid, "university", uni)
        db_manager.set_state(uid, "GET_TARGET_UNIVERSITY")
        return "🎯 Which University are you targeting for matches?"

    if state == "GET_TARGET_UNIVERSITY":
        target = msg.upper().strip()
        if target not in ZIM_UNIVERSITIES:
             return "❗ Enter a valid University abbreviation (e.g., UZ, HIT)."
        db_manager.update_profile(uid, "target_university", target)
        db_manager.set_state(uid, "GET_STUDENT_INTENT")
        return "💖 Your Intent:\n1️⃣ Friends\n2️⃣ Boyfriend\n3️⃣ Girlfriend\n4️⃣ Chills\n5️⃣ Just vibes"

    if state == "GET_STUDENT_INTENT":
        intent = STUDENT_INTENTS.get(msg)
        if not intent: return "❗ Choose 1-5."
        db_manager.update_profile(uid, "intent", intent)
        db_manager.set_state(uid, "GET_GENDER")
        return "Select your gender:\n• MALE\n• FEMALE"

    # -------------------------------------------------
    # 2. CITIZEN FLOW
    # Flow: Gender -> Intent -> Age Range -> Their Age -> Name -> Location -> Photo -> Phone
    # -------------------------------------------------
    if state == "GET_GENDER":
        if msg_l not in ["male", "female"]: return "❗ Type MALE or FEMALE."
        db_manager.update_profile(uid, "gender", msg_l)
        db_manager.update_profile(uid, "preferred_gender", "female" if msg_l == "male" else "male")
        
        # Branching Point
        if user.get("user_type") == "STUDENT":
            db_manager.set_state(uid, "GET_NAME")
            return "📝 Great! What is your name?"
        else:
            db_manager.set_state(uid, "GET_INTENT")
            options = ("1️⃣ Sugar mummy\n4️⃣ Girlfriend\n6️⃣ 1 night stand\n7️⃣ Just vibes\n8️⃣ Friend" if msg_l == "male" 
                       else "2️⃣ Sugar daddy\n3️⃣ Benten\n5️⃣ Boyfriend\n6️⃣ 1 night stand\n7️⃣ Just vibes\n8️⃣ Friend")
            return f"💖 What are you looking for?\n\n{options}"

    if state == "GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent: return "❗ Choose 1-8."
        db_manager.update_profile(uid, "intent", intent)
        db_manager.set_state(uid, "GET_AGE_RANGE")
        return "🎂 Preferred age range:\n1️⃣ 18–25\n2️⃣ 26–30\n3️⃣ 31–35\n4️⃣ 36–40\n5️⃣ 41–50\n6️⃣ 50+"

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r: return "❗ Choose 1–6."
        db_manager.update_profile(uid, "age_min", r[0])
        db_manager.update_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME") # Citizens now join Name flow
        return "📝 What is your name?"

    # -------------------------------------------------
    # SHARED FINAL STEPS (Differentiated inside)
    # -------------------------------------------------
    if state == "GET_NAME":
        if len(msg) < 3: return "❗ Name too short."
        db_manager.update_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        return "🎂 How old are you?"

    if state == "GET_AGE":
        if not msg.isdigit(): return "❗ Enter a number."
        age = int(msg)
        db_manager.update_profile(uid, "age", age)
        
        if user.get("user_type") == "STUDENT":
            # STUDENTS SKIP LOCATION -> GO TO PHOTO
            db_manager.set_state(uid, "GET_PHOTO")
            return "📸 Send a clear photo of yourself to continue."
        else:
            # CITIZENS GO TO LOCATION
            db_manager.set_state(uid, "GET_LOCATION")
            return "📍 Where are you located? (City and Suburb)"

    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHOTO")
        return "📸 Send a clear photo of yourself to continue."
    
    if state == "GET_PHOTO":
        if msg_l == "skip":
            db_manager.update_profile(uid, "picture", None)
            db_manager.set_state(uid, "GET_PHONE")
            return "⏩ Photo skipped. 📞 Now, enter the phone number where matches can contact you:"

        msg_data = payload.get("messageData", {})
        file_data = msg_data.get("fileMessageData", {})
        image_data = msg_data.get("imageMessageData", {})
        
        # 1. Try to get the ID or the URL (Green API sometimes sends one or the other)
        # Based on your logs, your instance is sending 'downloadUrl' inside 'fileMessageData'
        photo_link = (
            image_data.get("fileId") or 
            file_data.get("downloadUrl") or 
            image_data.get("downloadUrl")
        )

        if photo_link:
            db_manager.update_profile(uid, "picture", photo_link)
            db_manager.set_state(uid, "GET_PHONE")
            return "✅ Photo received! 📞 Finally, enter the phone number where matches can contact you (e.g., 0772111222):"
        
        # If we reach here, it means no link was found
        return "I saw your message, but I couldn't process the photo. Please try sending it again as a standard gallery image."
    

    # 1. UPDATED AWAITING_MATCHES STATE
    if state == "AWAITING_MATCHES":
        if msg_l == "status":
            matches = db_manager.get_matches(uid)
            if matches:
                db_manager.set_state(uid, "CHOOSE_CURRENCY")
                reply = "🔥 *Matches Found!* 🔥\n"
                for m in matches: 
                    reply += f"• {m['name']} — {m['location']}\n"
                reply += "\nSelect Currency:\n1️⃣ USD ($1.00)\n2️⃣ ZiG (40 ZiG)"
                return reply
            else:
                # ADDED CHANNEL LINK HERE
                return ("⏳ Still looking for matches that fit your profile...\n\n"
    
                        "Check back here later by typing *STATUS*.")

        if msg_l == "exit":
            db_manager.reset_profile(uid)
            db_manager.set_state(uid, "GET_GENDER")
            return "👋 Profile cleared. Let's start over!\n\nPlease select your gender:\n• MALE\n• FEMALE"

        return "🔍 You are currently waiting for matches. Type *STATUS* to check again or *EXIT* to redo your profile."

   # 2. UPDATED GET_PHONE STATE (The Preview Logic)
    if state == "GET_PHONE":
        clean_num = msg.strip().replace(" ", "").replace("+263", "0")
        if not is_valid_zim_phone(clean_num):
            return "❗ Invalid number. Please enter a Zimbabwean number (e.g., 0772123456)."

        db_manager.update_profile(uid, "contact_phone", msg)

        # --- NEW: ALERT THE CHANNEL ---
        # Fetch the newly completed profile info
        new_prof = db_manager.get_profile(uid)
        if new_prof:
            send_channel_alert(
                new_prof['name'], 
                new_prof['age'], 
                new_prof['location'], 
                new_prof['intent'], 
                new_prof['picture']
            )
        # ------------------------------


        matches = db_manager.get_matches(uid)

        if not matches: 
            db_manager.set_state(uid, "AWAITING_MATCHES") 
        
            return ("✅ Profile saved! We couldn't find matches right now.\n\n"
            
                    "Type *STATUS* here later to check again.")
        
        send_whatsapp_message(phone, "🔥 *Matches Found!* Here is a preview of people looking for you:")

        for m in matches[:3]:
            preview_caption = (f"👤 *Name:* {m['name']}\n"
                               f"🎂 *Age:* {m['age']}\n"
                               f"📍 *Location:* {m['location']}\n"
                               f"📞 *Contact:* [Locked 🔒 Pay to View]")
            
            if m.get('picture'):
                send_whatsapp_image(phone, m['picture'], preview_caption)
            else:
                send_whatsapp_message(phone, preview_caption)
    
        db_manager.set_state(uid, "CHOOSE_CURRENCY")
        
        return ("\n✨ *Unlock all details and contact numbers!*\n\n"
                "Select Currency to continue:\n"
                "1️⃣ USD ($1.00)\n"
                "2️⃣ ZiG (40 ZiG)\n\n"
                )

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
            success = create_pesepay_payment(uid, clean_num, "PZW211", "USD", 1.00)
            method_name = "EcoCash USD"
        elif state == "AWAITING_ECOCASH_ZIG":
            success = create_pesepay_payment(uid, clean_num, "PZW201", "ZWG", 40.00) # Updated to ZWG
            method_name = "EcoCash ZiG"
        else:
            success = create_pesepay_payment(uid, clean_num, "PZW212", "USD", 1.00)
            method_name = "InnBucks"

        if success:
            db_manager.set_state(uid, "PAYMENT_PENDING")
            
            # --- CUSTOM SUCCESS MESSAGE ---
            return (
                f"🚀 *Payment Initiated via {method_name}!*\n\n"
                f"📲 Please check the phone for **{clean_num}** right now. "
                "A prompt will appear asking for your **PIN**.\n\n"
                "⏳ *What to do next:*\n"
                "1. On the phone, Enter your PIN carefully.\n"
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

    # This is the final fallback for any unrecognized message or state
    db_manager.set_state(uid, "NEW")
    return "❗ Chat ended:Please type *HELLO* or *HI* to start finding matches."



# -------------------------------------------------
# WEBHOOK ENDPOINT
# -------------------------------------------------

import openai
from fastapi.responses import JSONResponse

# Add your OpenAI Key to your .env file
openai.api_key = os.getenv("OPENAI_API_KEY")

@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and auth != f"Bearer {GREEN_API_AUTH_TOKEN}":
        raise HTTPException(status_code=401)

    payload = await request.json()
    
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    # --- 1. ZIMBABWE VALIDATION GATEKEEPER ---
    phone = payload.get("senderData", {}).get("chatId", "").split("@")[0]
    if not phone.startswith("263"):
        # We silently ignore non-Zim numbers
        return JSONResponse({"status": "ignored", "reason": "non_zimbabwean"})

    msg_data = payload.get("messageData", {})
    text = msg_data.get("textMessageData", {}).get("textMessage", "") or \
           msg_data.get("extendedTextMessageData", {}).get("text", "")

    # Check for photo content
    image_info = (
        msg_data.get("imageMessageData") or 
        msg_data.get("fileMessageData") or 
        msg_data.get("documentMessageData")
    )
    
    if text or image_info:
        # Get the standard bot reply
        reply = handle_message(phone, text, payload)
        
        # --- 2. OPENAI INTERACTIVE FALLBACK ---
        # If the bot is about to send the "End of chat/Start over" message, 
        # we check if AI can give a better, more human response instead.
        if "type *HELLO*" in reply and text:
            reply = get_ai_response(text)
            
        if reply:
            send_whatsapp_message(phone, reply)

    return JSONResponse({"status": "processed"})

def get_ai_response(user_text):
    """Uses OpenAI to keep the bot interactive for off-script questions."""
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are Shelby, a helpful Zimbabwean dating assistant. If a user asks a question, answer concisely with local Zimbabwe slang (like 'shamwari', 'shaz'). If they seem lost, tell them to type HELLO to start the dating process."},
                {"role": "user", "content": user_text}
            ],
            max_tokens=150
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"AI Error: {e}")
        return "👋 I'm here to help! Type *HELLO* to start finding your match."