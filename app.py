import os, re, requests, db_manager
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

def send_text(phone, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    res = requests.post(url, json=payload)
    print(f"SENT: {res.status_code}")
    return res

def handle_message(phone, msg, sender_name):
    user = db_manager.get_user(phone)
    if not user: user = db_manager.create_user(phone)
    uid, state = user['id'], user['chat_state']

    # --- 1. WELCOME ---
    if state == "START" or msg.lower() in ["hi", "hello", "menu"]:
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        menu = (f"Welcome to *MicroHub*, {sender_name}!\n\n"
                "How can we help you today? Reply with a number:\n"
                "1️⃣ Product Catalogue\n"
                "2️⃣ Contact Us\n"
                "3️⃣ FAQs\n"
                "4️⃣ Chat with Agent")
        send_text(phone, menu)

    # --- 2. MAIN MENU LOGIC ---
    elif state == "MAIN_MENU":
        if msg == "1":
            db_manager.update_user(uid, "chat_state", "CATALOGUE")
            send_text(phone, "📂 *Product Catalogue*\nChoose a category:\n1️⃣ Loans\n2️⃣ Mukando\n3️⃣ Solar Systems\n4️⃣ Funeral Plan\n\n0️⃣ Back to Main Menu")
        elif msg == "2":
            send_text(phone, "📍 *Contact Us*\nVisit our Harare Branch at 123 Samora Machel.\nCall: +263 777 123 456\n\nType *Menu* to return.")
        else:
            send_text(phone, "Please reply with 1, 2, or 3.")

    # --- 3. CATALOGUE LOGIC ---
    elif state == "CATALOGUE":
        if msg == "1":
            db_manager.update_user(uid, "chat_state", "LOANS")
            send_text(phone, "💰 *Available Loans*\n1️⃣ Business Loan\n2️⃣ Pension Loan\n3️⃣ Housing Loan\n\n0️⃣ Back")
        elif msg == "0":
            db_manager.update_user(uid, "chat_state", "START")
            handle_message(phone, "hi", sender_name)

    # --- 4. LOAN APPLICATION START ---
    elif state == "LOANS":
        loan_types = {"1": "Business Loan", "2": "Pension Loan", "3": "Housing Loan"}
        if msg in loan_types:
            db_manager.update_user(uid, "selected_product", loan_types[msg])
            db_manager.update_user(uid, "chat_state", "GET_ID")
            send_text(phone, f"You selected *{loan_types[msg]}*.\n\nPlease enter your National ID (e.g., 632156742S22):")
        elif msg == "0":
            db_manager.update_user(uid, "chat_state", "MAIN_MENU")
            handle_message(phone, "1", sender_name)

    # --- 5. DATA COLLECTION ---
    elif state == "GET_ID":
        # ID Validation
        if not re.match(r"^\d{9}[A-Z]\d{2}$", msg.upper()):
            return send_text(phone, "❌ Invalid format. Please enter ID like 632156742S22")
        
        db_manager.update_user(uid, "name", msg.upper())
        db_manager.update_user(uid, "chat_state", "CONFIRM")
        send_text(phone, f"Confirm ID: {msg.upper()}?\nReply 'YES' to submit or 'NO' to restart.")

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if data.get("typeWebhook") == "incomingMessageReceived":
        msg_data = data.get("messageData", {})
        # Extracts text from standard or extended messages
        text = msg_data.get("textMessageData", {}).get("textMessage") or \
               msg_data.get("extendedTextMessageData", {}).get("text", "")
        
        phone = data["senderData"]["chatId"].split("@")[0]
        sender = data["senderData"]["senderName"]
        
        if text:
            handle_message(phone, text, sender)
    return {"status": "ok"}