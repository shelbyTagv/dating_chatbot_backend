import os, re, requests, db_manager
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

# --- Green API Helpers ---

def send_text(phone, text):
    requests.post(f"{URL}/sendMessage/{API_TOKEN}", json={"chatId": f"{phone}@c.us", "message": text})

def send_list(phone, title, text, button_text, rows):
    """Sends a WhatsApp Modal/List"""
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text,
        "title": title,
        "buttonText": button_text,
        "sections": [{"title": "Select an Option", "rows": rows}]
    }
    requests.post(f"{URL}/sendListMessage/{API_TOKEN}", json=payload)

def send_buttons(phone, text, buttons):
    """Sends simple interaction buttons"""
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text,
        "buttons": buttons
    }
    requests.post(f"{URL}/sendButtons/{API_TOKEN}", json=payload)

# --- Logic ---

def handle_message(phone, msg, sender_name, payload):
    user = db_manager.get_user(phone)
    if not user: user = db_manager.create_user(phone)
    uid = user['id']
    state = user['chat_state']

    # 1. Main Welcome
    if state == "START":
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        send_list(phone, "MicroHub Virtual Assistant", 
                  f"Good afternoon {sender_name}, how can we help you today?", 
                  "View Menu", 
                  [
                      {"title": "Product Catalogue", "description": "View our loans and plans"},
                      {"title": "Contact Us", "description": "Branch locations"},
                      {"title": "FAQs", "description": "Common questions"},
                      {"title": "Let's Chat", "description": "Talk to an agent"}
                  ])
        return

    # 2. Main Menu Selection
    if msg == "Product Catalogue":
        db_manager.update_user(uid, "chat_state", "CATALOGUE_SELECT")
        send_list(phone, "Products", "View our products", "Browse", [
            {"title": "Loans"}, {"title": "Mukando"}, {"title": "Solar Systems"}, {"title": "Funeral Plan"}
        ])
        return

    # 3. Loan Type Selection
    if msg == "Loans" and state == "CATALOGUE_SELECT":
        db_manager.update_user(uid, "chat_state", "LOAN_DETAIL")
        send_list(phone, "Loan Types", "We offer specialized loans for your needs", "View Loans", [
            {"title": "Business Loan"}, {"title": "Pension Loan"}, {"title": "Housing Loan"}
        ])
        return

    # 4. Product Explanation
    if msg == "Business Loan" and state == "LOAN_DETAIL":
        db_manager.update_user(uid, "selected_product", "Business Loan")
        db_manager.update_user(uid, "chat_state", "PRE_APPLY")
        text = ("📈 *Business Loans*\nDesigned for SMEs and traders. Get up to $5000 with flexible terms.\n\n"
                "To apply, click the button below.")
        send_buttons(phone, text, [{"buttonId": "apply", "buttonText": {"displayText": "Apply"}}])
        return

    # 5. Branch Selection
    if msg.lower() == "apply":
        db_manager.update_user(uid, "chat_state", "GET_BRANCH")
        send_list(phone, "Select Branch", "Choose the nearest branch", "Branches", [
            {"title": "Harare CBD"}, {"title": "Bulawayo"}, {"title": "Mutare"}
        ])
        return

    # 6. Data Collection Flow
    if state == "GET_BRANCH":
        db_manager.update_user(uid, "selected_branch", msg)
        db_manager.update_user(uid, "chat_state", "GET_ID")
        send_text(phone, "Please enter your National ID number (e.g., 632156742S22):")
        return

    if state == "GET_ID":
        if not re.match(r"^\d{9}[A-Z]\d{2}$", msg.upper().replace("-","")):
            return send_text(phone, "Invalid format. Please use 632156742S22.")
        db_manager.update_user(uid, "name", msg.upper()) # Using name field temporarily to store ID
        db_manager.update_user(uid, "chat_state", "GET_PHOTO")
        send_text(phone, "Please upload a clear Selfie (Photo):")
        return

    if state == "GET_PHOTO":
        file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")
        if not file_url: return send_text(phone, "Please upload a photo to continue.")
        # Store photo URL in a temporary way or db_manager
        db_manager.update_user(uid, "chat_state", "GET_AMOUNT")
        send_text(phone, "How much do you want to borrow?")
        return

    if state == "GET_AMOUNT":
        db_manager.update_user(uid, "chat_state", "CONFIRM")
        send_buttons(phone, f"Confirm Application for {user['selected_product']}?", [
            {"buttonId": "confirm", "buttonText": {"displayText": "Confirm"}},
            {"buttonId": "cancel", "buttonText": {"displayText": "Cancel"}}
        ])
        return

    if msg.lower() == "cancel":
        db_manager.update_user(uid, "chat_state", "START")
        handle_message(phone, "hi", sender_name, payload) # Restart
        return

@app.post("/webhook")
async def webhook(request: Request):
    try:
        payload = await request.json()
        
        # Log the payload so you can see it in Railway logs
        print(f"Incoming Webhook: {payload}")

        if payload.get("typeWebhook") == "incomingMessageReceived":
            sender_data = payload.get("senderData", {})
            msg_data = payload.get("messageData", {})
            
            # 1. Extract the Phone Number and Sender Name
            chat_id = sender_data.get("chatId", "")
            phone = chat_id.split("@")[0]
            sender_name = sender_data.get("senderName", "Customer")

            # 2. Extract Text from ALL possible WhatsApp message types
            text = ""
            
            # Standard Text Message
            if "textMessageData" in msg_data:
                text = msg_data["textMessageData"].get("textMessage", "")
            
            # List/Modal Selection (The "Browse" menu)
            elif "listResultMessageData" in msg_data:
                text = msg_data["listResultMessageData"].get("title", "")
            
            # Button Click (The "Apply" or "Confirm" buttons)
            elif "buttonsResultMessageData" in msg_data:
                # Green API sometimes puts it in 'buttonId' or 'buttonText'
                text = msg_data["buttonsResultMessageData"].get("buttonText", "")
            
            # Extended Text (Links/Captions)
            elif "extendedTextMessageData" in msg_data:
                text = msg_data["extendedTextMessageData"].get("text", "")

            # 3. Process the logic and get the reply string
            if text or "fileMessageData" in msg_data:
                # We pass the payload to handle_message so it can process images/files
                reply = handle_message(phone, text, sender_name, payload)
                
                # 4. CRITICAL: Actually send the reply back to WhatsApp
                # Note: If handle_message uses send_list or send_buttons internally, 
                # it might return None. If it returns a string, we send it as text.
                if reply and isinstance(reply, str):
                    send_text(phone, reply)
            
        return {"status": "success"}

    except Exception as e:
        print(f"Webhook Error: {e}")
        return {"status": "error", "message": str(e)}

@app.on_event("startup")
def startup():
    db_manager.init_db()