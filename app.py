import os, re, requests, db_manager
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# --- GLOBALS ---
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

# --- WHATSAPP HELPERS ---

def send_text(phone, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    res = requests.post(url, json=payload)
    print(f"OUTGOING TEXT [{res.status_code}]: {res.text}")
    return res

def send_list(phone, title, text, button_text, rows):
    # This uses the 'sendInteractiveButtons' method which is more stable
    url = f"{BASE_URL}/sendInteractiveButtons/{API_TOKEN}"
    
    # We turn your rows into 'reply' buttons
    # Note: WhatsApp official limit is 3 buttons. For 4+ options, we use text.
    buttons = []
    for i, row in enumerate(rows[:3]): # Takes first 3 options as buttons
        buttons.append({
            "type": "reply",
            "buttonId": f"id_{i}",
            "buttonText": row['title']
        })

    payload = {
        "chatId": f"{phone}@c.us",
        "header": title,
        "body": text,
        "footer": "MicroHub Assistant",
        "buttons": buttons
    }
    
    res = requests.post(url, json=payload)
    print(f"OUTGOING BUTTONS [{res.status_code}]: {res.text}")
    return res

# --- CHATBOT LOGIC ---

def handle_message(phone, msg, sender_name, payload):
    user = db_manager.get_user(phone)
    if not user: user = db_manager.create_user(phone)
    uid, state = user['id'], user['chat_state']

    # START: Send the 'View Menu' button
    if state == "START" or msg.lower() in ["hi", "hello"]:
        db_manager.update_user(uid, "chat_state", "AWAITING_MENU_CLICK")
        
        # This sends one single button that says 'View Menu'
        url = f"{BASE_URL}/sendInteractiveButtons/{API_TOKEN}"
        payload = {
            "chatId": f"{phone}@c.us",
            "body": f"Welcome to Microhub, {sender_name}! How can we help you today?",
            "buttons": [{"type": "reply", "buttonId": "main_menu", "buttonText": "View Menu"}]
        }
        requests.post(url, json=payload)

    # When they click 'View Menu', pop up the product list
    elif state == "AWAITING_MENU_CLICK" and "View Menu" in msg:
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        send_list(phone, "Our Services", "Choose an option below:", "Select", [
            {"title": "Product Catalogue"},
            {"title": "Contact Us"},
            {"title": "FAQs"}
        ])

    elif state == "MAIN_MENU":
        if "Catalogue" in msg:
            db_manager.update_user(uid, "chat_state", "CATALOGUE")
            send_list(phone, "Products", "Our offerings:", "Browse", [
                {"title": "Loans"}, {"title": "Solar Systems"}, {"title": "Funeral Plan"}
            ])
        elif "Contact" in msg:
            send_text(phone, "📍 *Our Branches:*\n1. Harare: 123 Samora Machel\n2. Bulawayo: 45 Main St\n\nCall us: +263...")

    elif state == "CATALOGUE":
        if "Loans" in msg:
            db_manager.update_user(uid, "chat_state", "LOAN_TYPES")
            send_list(phone, "Loans", "Choose a loan:", "Types", [
                {"title": "Business Loan"}, {"title": "Pension Loan"}
            ])

    elif state == "LOAN_TYPES":
        db_manager.update_user(uid, "selected_product", msg)
        db_manager.update_user(uid, "chat_state", "GET_ID")
        send_text(phone, f"You selected *{msg}*.\n\nPlease enter your National ID (e.g. 632156742S22):")

    elif state == "GET_ID":
        # ID Validation
        clean_id = msg.upper().replace(" ", "").replace("-", "")
        if not re.match(r"^\d{9}[A-Z]\d{2}$", clean_id):
            return send_text(phone, "❌ Invalid ID. Please use format: 632156742S22")
        
        db_manager.update_user(uid, "name", clean_id) # Using 'name' column for ID
        db_manager.update_user(uid, "chat_state", "CONFIRM_FINAL")
        send_text(phone, "✅ Details captured. Type 'CONFIRM' to submit your application.")

# --- WEBHOOK ENDPOINT ---

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print(f"INCOMING: {data}")

    if data.get("typeWebhook") == "incomingMessageReceived":
        msg_data = data.get("messageData", {})
        sender_data = data.get("senderData", {})
        phone = sender_data.get("chatId", "").split("@")[0]
        name = sender_data.get("senderName", "Client")

        # Extraction logic for all types
        text = ""
        if "textMessageData" in msg_data:
            text = msg_data["textMessageData"].get("textMessage", "")
        elif "extendedTextMessageData" in msg_data:
            text = msg_data["extendedTextMessageData"].get("text", "")
        elif "listResultMessageData" in msg_data:
            text = msg_data["listResultMessageData"].get("title", "")

        if text:
            handle_message(phone, text, name, data)

    return {"status": "ok"}

@app.on_event("startup")
def startup():
    db_manager.init_db()