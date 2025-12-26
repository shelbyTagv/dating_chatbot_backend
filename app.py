import os, re, requests, db_manager
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"
BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

# --- Green API Helpers ---

def send_text(phone, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    response = requests.post(url, json=payload)
    print(f"DEBUG: Outgoing Text Status: {response.status_code}, Response: {response.text}")
    return response

def send_list(phone, title, text, button_text, rows):
    url = f"{BASE_URL}/sendListMessage/{API_TOKEN}"
    payload = {
        "chatId": f"{phone}@c.us",
        "message": text,
        "title": title,
        "buttonText": button_text,
        "sections": [{"title": "Select an Option", "rows": rows}]
    }
    response = requests.post(url, json=payload)
    print(f"DEBUG: Outgoing List Status: {response.status_code}, Response: {response.text}")
    return response

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

    # Logic for Welcome Message
    if state == "START" or msg.lower() in ["hi", "hello", "hey"]:
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        send_list(phone, "MicroHub Virtual Assistant", 
                  f"Good afternoon {sender_name}, how can we help you today?", 
                  "View Menu", 
                  [
                      {"title": "Product Catalogue", "description": "View our loans"},
                      {"title": "Contact Us", "description": "Our branches"},
                      {"title": "FAQs", "description": "Questions"},
                      {"title": "Let's Chat", "description": "Talk to us"}
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
        data = await request.json()
        print(f"DEBUG: Full Payload Received: {data}")

        if data.get("typeWebhook") == "incomingMessageReceived":
            msg_data = data.get("messageData", {})
            sender_data = data.get("senderData", {})
            
            phone = sender_data.get("chatId", "").split("@")[0]
            sender_name = sender_data.get("senderName", "Customer")
            
            # Logic to extract text from ANY message type (Standard, Extended, or List)
            text = ""
            if "textMessageData" in msg_data:
                text = msg_data["textMessageData"].get("textMessage", "")
            elif "extendedTextMessageData" in msg_data:
                text = msg_data["extendedTextMessageData"].get("text", "")
            elif "listResultMessageData" in msg_data:
                text = msg_data["listResultMessageData"].get("title", "")
            elif "buttonsResultMessageData" in msg_data:
                text = msg_data["buttonsResultMessageData"].get("buttonText", "")

            print(f"DEBUG: Extracted Text: '{text}' from Phone: {phone}")

            if text or "fileMessageData" in msg_data:
                # This calls your logic and internal send functions
                handle_message(phone, text, sender_name, data)
                
        return {"status": "ok"}
    except Exception as e:
        print(f"CRITICAL WEBHOOK ERROR: {e}")
        return {"status": "error"}

@app.on_event("startup")
def startup():
    db_manager.init_db()