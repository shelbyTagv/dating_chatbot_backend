import os, re, requests, db_manager
from fastapi import FastAPI, Request
from openai import OpenAI  # <--- Updated Import
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# --- CONFIGURATION ---
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

def send_text(phone, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    requests.post(url, json=payload)



def get_ai_faq(query):
    try:
        # Context-aware system prompt
        system_msg = (
            "You are the Microhub Finance Assistant. Answer questions ONLY about "
            "Loans, Mukando, Solar Systems, and Funeral Plans. If the user asks "
            "something unrelated, say you can only help with Microhub finance."
        )
        # Updated for OpenAI v1.0.0+
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": query}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return "Our AI is currently offline. Please type '4' to speak with an agent."


# --- CHATBOT LOGIC ---

def handle_message(phone, msg, sender_name, payload):
    """
    REQUIRED: phone, msg, sender_name, payload (the full webhook JSON)
    """
    user = db_manager.get_user(phone)
    if not user: 
        user = db_manager.create_user(phone)
    
    uid = user['id']
    state = user['chat_state']

    # GLOBAL RESET/EXIT
    if msg.lower() in ["exit", "restart", "00", "reset"]:
        db_manager.update_user(uid, "chat_state", "START")
        return send_text(phone, "🔄 Session reset. Type 'Hi' to start again.")

    # 1. WELCOME BRANCH
    if state == "START" or msg.lower() in ["hi", "hello", "menu"]:
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        menu = (f"Welcome to *MicroHub*, {sender_name}!\n\n"
                "1️⃣ Product Catalogue\n2️⃣ Contact Us\n3️⃣ FAQs (AI Powered)\n4️⃣ Chat with Agent\n\n"
                "_(Type 'Exit' at any time to restart)_")
        return send_text(phone, menu)

    # 2. MAIN MENU SELECTION
    elif state == "MAIN_MENU":
        if msg == "1":
            db_manager.update_user(uid, "chat_state", "CATALOGUE")
            return send_text(phone, "📂 *Catalogue*\n1️⃣ Loans\n2️⃣ Mukando\n3️⃣ Solar Systems\n4️⃣ Funeral Plans\n0️⃣ Back")
        elif msg == "2":
            return send_text(phone, "📍 *Contact Microhub*\nHarare: 123 Samora Machel\nBulawayo: 45 Main St\nCall: +263 777 123 456\n\nType '0' for Menu.")
        elif msg == "3":
            db_manager.update_user(uid, "chat_state", "AI_FAQ")
            return send_text(phone, "🤖 *Microhub AI FAQ*\nAsk me anything about our finance products:")
        elif msg == "4":
            return send_text(phone, "👨‍💼 Please wait while we connect you to a live agent...")

    # 3. AI FAQ HANDLER
    elif state == "AI_FAQ":
        answer = get_ai_faq(msg)
        return send_text(phone, f"{answer}\n\n_(Type 'Exit' to return to menu)_")

    # 4. CATALOGUE BRANCHES
    elif state == "CATALOGUE":
        if msg == "1":
            db_manager.update_user(uid, "chat_state", "LOAN_TYPES")
            return send_text(phone, "💰 *Loans*\n1️⃣ Business Loan\n2️⃣ Pension Loan\n3️⃣ Housing Loan\n0️⃣ Back")
        # Add logic for Mukando/Solar/Funeral here similarly...

    # 5. LOAN APPLICATION FLOW
    elif state == "LOAN_TYPES":
        loan_map = {"1": "Business Loan", "2": "Pension Loan", "3": "Housing Loan"}
        if msg in loan_map:
            db_manager.update_user(uid, "selected_product", loan_map[msg])
            db_manager.update_user(uid, "chat_state", "CONFIRM_APPLY")
            return send_text(phone, f"You selected *{loan_map[msg]}*.\n\nType *APPLY* to start or *0* to go back.")

    elif state == "CONFIRM_APPLY" and msg.lower() == "apply":
        db_manager.update_user(uid, "chat_state", "GET_ID")
        return send_text(phone, "Please enter your National ID (e.g., 632156742S22):")

    elif state == "GET_ID":
        if not re.match(r"^\d{9}[A-Z]\d{2}$", msg.upper()):
            return send_text(phone, "❌ Invalid ID format. Please use: 632156742S22")
        db_manager.update_user(uid, "name", msg.upper())
        db_manager.update_user(uid, "chat_state", "GET_PHOTO")
        return send_text(phone, "📸 Please upload a Selfie (Photo):")

    elif state == "GET_PHOTO":
        # Extract image URL from the payload
        file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")
        if not file_url:
            return send_text(phone, "⚠️ Please upload a photo to proceed.")
        db_manager.update_user(uid, "selfie_url", file_url)
        db_manager.update_user(uid, "chat_state", "GET_AMT")
        return send_text(phone, "💵 Amount required (e.g., $1000):")

    elif state == "GET_AMT":
        db_manager.update_user(uid, "amount", msg)
        db_manager.update_user(uid, "chat_state", "GET_DESC")
        return send_text(phone, "📝 Briefly describe your business:")

    elif state == "GET_DESC":
        db_manager.update_user(uid, "biz_desc", msg)
        db_manager.update_user(uid, "chat_state", "FINAL_CONFIRM")
        summary = (f"📑 *Verify Your Details*\n\n"
                   f"ID: {user['name']}\n"
                   f"Loan: {user['selected_product']}\n"
                   f"Amount: {user['amount']}\n"
                   f"Desc: {msg}\n\n"
                   f"Reply *YES* to submit or *EXIT* to cancel.")
        return send_text(phone, summary)

    elif state == "FINAL_CONFIRM" and msg.lower() == "yes":
        db_manager.save_final_application(uid)
        db_manager.update_user(uid, "chat_state", "START")
        return send_text(phone, "✅ Application submitted! We will contact you shortly.")

# --- WEBHOOK ENDPOINT (THE FIX IS HERE) ---

# --- WEBHOOK ENDPOINT ---
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    
    # Check if it's an incoming message (ignore outgoing)
    if data.get("typeWebhook") == "incomingMessageReceived":
        msg_data = data.get("messageData", {})
        sender_data = data.get("senderData", {})
        
        phone = sender_data.get("chatId", "").split("@")[0]
        sender_name = sender_data.get("senderName", "Customer")
        
        # Get text from different possible message formats
        text = ""
        if "textMessageData" in msg_data:
            text = msg_data["textMessageData"].get("textMessage", "")
        elif "extendedTextMessageData" in msg_data:
            text = msg_data["extendedTextMessageData"].get("text", "")
        
        # If no text (like an image), handle_message will check the payload for the fileURL
        from app_logic import handle_message # Or wherever your logic lives
        handle_message(phone, text, sender_name, data)

    return {"status": "ok"}

@app.on_event("startup")
def startup():
    # RUN THIS ONCE TO ADD THE MISSING COLUMNS
    db_manager.init_db() 
    print("🚀 Database has been reset with new columns.")
    # Only run this once to setup; usually you'd keep your data
    # db_manager.init_db() 
    pass