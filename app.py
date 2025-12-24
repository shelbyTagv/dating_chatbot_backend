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
CHANNEL_LINK = "https://whatsapp.com/channel/0029VbC8NmJICVfoA76whO3I"
CHANNEL_ID = "120363385759714853@newsletter"

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

def send_channel_alert(name, age, location, intent, picture_url):
    """Sends a blurred preview alert to the WhatsApp Channel"""
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendFileByUrl/{API_TOKEN_INSTANCE}"
    
    # We use a placeholder 'blurred' image URL to tease users 
    # Or use the candidate's real picture_url if you want it visible
    image_to_send = picture_url if picture_url else "https://placehold.co/600x400?text=Photo+Hidden"

    caption = (
        f"🔔 *NEW CANDIDATE JOINED!* 🔔\n\n"
        f"👤 *Name:* {name}\n"
        f"🎂 *Age:* {age}\n"
        f"📍 *Location:* {location}\n"
        f"💖 *Looking for:* {intent}\n\n"
        f"👉 *Find them on the Bot here:* \nhttps://wa.me/{ID_INSTANCE.replace('waInstance', '')}"
    )

    payload = {
        "chatId": CHANNEL_ID,
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
    print(f"DEBUG DATA: {payload}")
    msg = text.strip() if text else ""
    msg_l = msg.lower()
    user = db_manager.get_user_by_phone(phone)
    if not user: user = db_manager.create_new_user(phone)
    uid = user["id"]

    # --- PROFILE COMMAND ---
    if msg_l == "profile":
        profile = db_manager.get_profile(uid)
        
        if not profile or not profile.get("name"):
            return "❌ Profile not found or incomplete. Type *HELLO* to start."

        caption = (f"👤 *YOUR PROFILE*\n"
                   f"━━━━━━━━━━━━━━━\n"
                   f"📝 *Name:* {profile['name']}\n"
                   f"🎂 *Age:* {profile['age']}\n"
                   f"📍 *Location:* {profile['location']}\n"
                   f"💖 *Looking for:* {profile.get('intent', 'N/A')}\n"
                   f"📞 *Contact:* {profile.get('contact_phone', 'N/A')}")

        if profile.get("picture"):
            # Sends the photo with the profile text as a caption
            send_whatsapp_image(phone, profile["picture"], caption)
            return "" # Return empty string because the image function handled the reply
        
        return caption



    db_manager.ensure_profile(uid)
    state = user.get("chat_state")
    if not state:
        state = "NEW"
        db_manager.set_state(uid, "NEW")


    if msg_l == "exit": db_manager.set_state(uid, "NEW"); return "❌ Ended. Type *HELLO* to start."

    if state == "NEW":
        # Check if the user is saying a valid greeting to start registration
        if msg_l in ["hello", "hi", "hey", "hie"]:
            db_manager.reset_profile(uid)
            db_manager.set_state(uid, "GET_GENDER")
            return ("👋 Welcome to Shelby Dating Connections!\n\n"
                    "Looking for Love, or just vibes: we got you covered. "
                    "Sending pictures is mandatory (you can skip by typing 'skip').\n\n"
                    "Please select your gender:\n• MALE\n• FEMALE")
        else:
            # If they are NEW and send something else, just prompt them to start
            return "👋 Welcome! Please type *HELLO* or *HI* to start finding matches."
    
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
                    "5️⃣ Boyfriend\n"
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
        return ("📍 *Where are you located?*\n\n"
                "Please enter your **City and Area**.\n"
                "Examples:\n"
                "• Harare, Budiriro\n"
                "• Bulawayo, Nkulumane\n"
                "• Mutare, Sakubva")
        
        
    if state == "GET_LOCATION":
        location_input = msg.strip().title()
        parts = location_input.replace(",", " ").split()
        
        if len(parts) < 2:
            return ("⚠️ *Please be more specific.*\n\n"
                    "We need your **City and Suburb** to find matches near you (e.g., Harare CBD or Harare Ruwa).")


        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHOTO")
        return "Almost done! Please send a clear photo of yourself."
    
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
                reply += "\nSelect Currency:\n1️⃣ USD ($2.00)\n2️⃣ ZiG (80 ZiG)"
                return reply
            else:
                # ADDED CHANNEL LINK HERE
                return ("⏳ Still looking for matches that fit your profile...\n\n"
                        f"📢 *Join our Channel* to see new people as they join:\n{CHANNEL_LINK}\n\n"
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
            # ADDED CHANNEL LINK HERE
            return ("✅ Profile saved! We couldn't find matches right now.\n\n"
                    f"🚀 *Don't wait!* Join our WhatsApp Channel for daily updates:\n{CHANNEL_LINK}\n\n"
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
        # ADDED CHANNEL LINK TO PAYMENT PROMPT
        return ("\n✨ *Unlock all details and contact numbers!*\n\n"
                "Select Currency to continue:\n"
                "1️⃣ USD ($2.00)\n"
                "2️⃣ ZiG (80 ZiG)\n\n"
                f"👉 *Follow our Channel for more:* {CHANNEL_LINK}")

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

@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and auth != f"Bearer {GREEN_API_AUTH_TOKEN}":
        raise HTTPException(status_code=401)

    payload = await request.json()
    
    # Debug: This will print the raw data to your terminal so you can see if the photo arrives
    print(f"RAW PAYLOAD: {payload}")

    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    phone = payload.get("senderData", {}).get("chatId", "").split("@")[0]
    msg_data = payload.get("messageData", {})
    
    # 1. Capture Text
    text = msg_data.get("textMessageData", {}).get("textMessage", "") or \
           msg_data.get("extendedTextMessageData", {}).get("text", "")

    # 2. Capture Photo (Green API often uses 'fileMessageData' for images)
    image_info = (
        msg_data.get("imageMessageData") or 
        msg_data.get("fileMessageData") or 
        msg_data.get("documentMessageData")
    )
    
    # If there is text OR an image, process it
    if text or image_info:
        reply = handle_message(phone, text, payload)
        if reply:
            send_whatsapp_message(phone, reply)

    return JSONResponse({"status": "processed"})
