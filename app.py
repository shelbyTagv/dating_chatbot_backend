import os, re, requests, db_manager, openai
from fastapi import FastAPI, Request
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()
openai.api_key = os.getenv("OPENAI_API_KEY")

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"

def send_text(phone, text):
    url = f"{BASE_URL}/sendMessage/{API_TOKEN}"
    payload = {"chatId": f"{phone}@c.us", "message": text}
    res = requests.post(url, json=payload)
    print(f"SENT: {res.status_code}")
    return res

def get_ai_response(user_query):
    """Handles Microhub context-aware FAQs using OpenAI"""
    system_prompt = (
        "You are the Microhub Finance AI Assistant. Only answer questions related to "
        "Microhub's financial products: Pension Loans, Business Loans, Solar Systems, "
        "Mukando, and Funeral Plans. If a question is outside this context, politely "
        "inform the user you can only help with Microhub Finance inquiries."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ]
        )
        return response.choices[0].message.content
    except:
        return "I'm having trouble connecting to my brain. Please try again later or type '4' for an agent."

def handle_message(phone, msg, sender_name, payload):
    user = db_manager.get_user(phone)
    if not user: user = db_manager.create_user(phone)
    uid, state = user['id'], user['chat_state']

    # --- MAIN BRANCHES ---
    if state == "START" or msg.lower() in ["hi", "hello", "menu"]:
        db_manager.update_user(uid, "chat_state", "MAIN_MENU")
        return send_text(phone, f"Welcome to *MicroHub*, {sender_name}!\n\n1️⃣ Product Catalogue\n2️⃣ Contact Us\n3️⃣ AI FAQs\n4️⃣ Direct Agent")

    elif state == "MAIN_MENU":
        if msg == "1":
            db_manager.update_user(uid, "chat_state", "CATALOGUE")
            return send_text(phone, "📂 *Catalogue*\n1️⃣ Loans\n2️⃣ Mukando\n3️⃣ Solar Systems\n4️⃣ Funeral Plan\n0️⃣ Back")
        elif msg == "2":
            return send_text(phone, "📍 Harare: 123 Samora Machel\n📍 Bulawayo: 45 Main St\n\nType 'Menu' to go back.")
        elif msg == "3":
            db_manager.update_user(uid, "chat_state", "AI_FAQ")
            return send_text(phone, "🤖 *Microhub AI FAQ*\nAsk me anything about our loans or products:")
        elif msg == "4":
            return send_text(phone, "👨‍💼 Redirecting to an agent... Please wait.")

    # --- AI FAQ HANDLER ---
    elif state == "AI_FAQ":
        if msg.lower() == "exit":
            db_manager.update_user(uid, "chat_state", "START")
            return handle_message(phone, "hi", sender_name, payload)
        answer = get_ai_response(msg)
        return send_text(phone, f"{answer}\n\n_(Type 'Exit' to stop asking questions)_")

    # --- CATALOGUE BRANCHING ---
    elif state == "CATALOGUE":
        if msg == "1":
            db_manager.update_user(uid, "chat_state", "LOAN_SUB")
            return send_text(phone, "💰 *Loans*\n1️⃣ Business Loan\n2️⃣ Pension Loan\n3️⃣ Housing\n0️⃣ Back")
        elif msg == "2":
            db_manager.update_user(uid, "chat_state", "MUKANDO")
            return send_text(phone, "🤝 *Mukando Types*\n1️⃣ Personal Mukando\n2️⃣ Group Mukando\n0️⃣ Back")
        # Add Solar and Funeral branches similarly...

    # --- LOAN APPLICATION FLOW (The 'Absolute Logic') ---
    elif state == "LOAN_SUB":
        loan_name = "Business Loan" if msg == "1" else "Pension Loan"
        db_manager.update_user(uid, "selected_product", loan_name)
        db_manager.update_user(uid, "chat_state", "CONFIRM_INTENT")
        return send_text(phone, f"You selected *{loan_name}*.\n\nType 'APPLY' to start your application or 'BACK' to change.")

    elif state == "CONFIRM_INTENT":
        if msg.lower() == "apply":
            db_manager.update_user(uid, "chat_state", "GET_ID")
            return send_text(phone, "Please enter your National ID (Format: 632156742S22):")

    elif state == "GET_ID":
        if not re.match(r"^\d{9}[A-Z]\d{2}$", msg.upper()):
            return send_text(phone, "❌ Invalid format. Try again (e.g., 632156742S22):")
        db_manager.update_user(uid, "name", msg.upper()) # Save ID in name field temporarily
        db_manager.update_user(uid, "chat_state", "GET_PHOTO")
        return send_text(phone, "📸 Please upload a Selfie (Photo):")

    elif state == "GET_PHOTO":
        file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")
        if not file_url: return send_text(phone, "⚠️ Please send a photo to continue.")
        # Store file_url in DB (assuming you added a column 'selfie_url')
        db_manager.update_user(uid, "chat_state", "GET_AMT")
        return send_text(phone, "💵 Amount required (e.g., $500):")

    elif state == "GET_AMT":
        db_manager.update_user(uid, "chat_state", "GET_DESC")
        return send_text(phone, "📝 Provide a short description of your business:")

    elif state == "GET_DESC":
        db_manager.update_user(uid, "chat_state", "FINAL_CONFIRM")
        # Logic to fetch all collected data for summary
        summary = (f"📑 *Review Details:*\nID: {user['name']}\nProduct: {user['selected_product']}\n"
                   f"Amount: {user['amount']}\nDesc: {msg}\n\nReply 'CONFIRM' to submit or 'CANCEL' to restart.")
        return send_text(phone, summary)

    elif state == "FINAL_CONFIRM":
        if msg.lower() == "confirm":
            db_manager.update_user(uid, "chat_state", "START")
            return send_text(phone, "✅ Application Submitted! Our team will contact you shortly.")
        elif msg.lower() == "cancel":
            db_manager.update_user(uid, "chat_state", "START")
            return handle_message(phone, "hi", sender_name, payload)

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