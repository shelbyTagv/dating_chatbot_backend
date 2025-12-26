import os, re, requests, db_manager
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

# --- UPDATED HELPERS ---

def send_text(phone, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    res = requests.post(url, json=payload)
    print(f"OUTGOING TEXT [{res.status_code}]: {res.text}")
    return res

def send_list(phone, title, text, button_text, rows):
    """This creates the POP-UP MODAL you want"""
    url = f"{BASE_URL}/sendListMessage/{API_TOKEN}"
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text,
        "title": title,
        "buttonText": button_text,
        "sections": [{"title": "Select an Option", "rows": rows}]
    }
    res = requests.post(url, json=payload)
    print(f"OUTGOING LIST [{res.status_code}]: {res.text}")
    
    # If the List Modal fails (403), send as text so user isn't stuck
    if res.status_code != 200:
        fallback = f"*{title}*\n{text}\n\nType your choice:\n" + "\n".join([f"• {r['title']}" for r in rows])
        send_text(phone, fallback)
    return res

# --- LOGIC WITH THE 'VIEW MENU' BUTTON ---

def handle_message(phone, msg, sender_name, payload):
    user = db_manager.get_user(phone)
    if not user: user = db_manager.create_user(phone)
    uid, state = user['id'], user['chat_state']

    print(f"DEBUG: Processing State {state} for msg '{msg}'")

    # STEP 1: Welcome & 'View Menu' Button
    if state == "START" or msg.lower() in ["hi", "hello", "reset"]:
        db_manager.update_user(uid, "chat_state", "AWAITING_MENU")
        
        # We try to send a button. If your instance is 'Developer', this might fail 403.
        url = f"{BASE_URL}/sendButtons/{API_TOKEN}"
        btn_payload = {
            "chatId": f"{phone}@c.us",
            "message": f"Welcome to Microhub, {sender_name}! How can we help you today?",
            "buttons": [{"buttonId": "1", "buttonText": {"displayText": "View Menu"}}]
        }
        res = requests.post(url, json=btn_payload)
        
        # If buttons are forbidden (403), fallback to text instruction
        if res.status_code != 200:
            send_text(phone, f"Welcome to Microhub, {sender_name}! Type *MENU* to see our services.")
        return

    # STEP 2: Handle 'View Menu' or 'Menu' text to show MODAL
    if state == "AWAITING_MENU" and (msg.lower() == "view menu" or msg.lower() == "menu"):
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        send_list(phone, "Microhub Services", "Please select a service from the list below:", "Browse", [
            {"title": "Product Catalogue", "description": "Loans, Solar, and more"},
            {"title": "Contact Us", "description": "Find our branches"},
            {"title": "FAQs", "description": "Get quick answers"}
        ])
        return

    # STEP 3: Handle Catalogue Selection
    if state == "MAIN_MENU" and "Catalogue" in msg:
        db_manager.update_user(uid, "chat_state", "CATALOGUE")
        send_list(phone, "Catalogue", "View our products", "Explore", [
            {"title": "Loans"}, {"title": "Solar Systems"}, {"title": "Funeral Plan"}
        ])
        return

# --- WEBHOOK REMAINS THE SAME ---
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    print(f"INCOMING: {data}")
    if data.get("typeWebhook") == "incomingMessageReceived":
        msg_data = data.get("messageData", {})
        sender_data = data.get("senderData", {})
        phone = sender_data.get("chatId", "").split("@")[0]
        name = sender_data.get("senderName", "Customer")
        
        # Extract text from standard, extended, list, or buttons
        text = ""
        if "textMessageData" in msg_data:
            text = msg_data["textMessageData"].get("textMessage", "")
        elif "extendedTextMessageData" in msg_data:
            text = msg_data["extendedTextMessageData"].get("text", "")
        elif "listResultMessageData" in msg_data:
            text = msg_data["listResultMessageData"].get("title", "")
        elif "buttonsResultMessageData" in msg_data:
            text = msg_data["buttonsResultMessageData"].get("buttonText", "")

        if text:
            handle_message(phone, text, name, data)
    return {"status": "ok"}