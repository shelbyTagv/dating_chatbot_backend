from dotenv import load_dotenv
load_dotenv()

import os
import requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
import db_manager

app = FastAPI()

GREEN_API_URL = "https://api.greenapi.com"
ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN_INSTANCE = os.getenv("API_TOKEN_INSTANCE")
GREEN_API_AUTH_TOKEN = os.getenv("GREEN_API_AUTH_TOKEN")

@app.on_event("startup")
def startup():
    db_manager.init_db()

def send_whatsapp_message(phone: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    requests.post(url, json={"chatId": f"{phone}@c.us", "message": text}, timeout=15)

@app.get("/webhook")
async def verify_webhook(request: Request):
    return PlainTextResponse("OK")

@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and (not auth or auth.replace("Bearer ","") != GREEN_API_AUTH_TOKEN):
        raise HTTPException(status_code=401)

    payload = await request.json()
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status":"ignored"})

    sender = payload.get("senderData", {})
    message_data = payload.get("messageData", {})

    phone = sender.get("chatId","").split("@")[0]
    text = ""
    if "textMessageData" in message_data:
        text = message_data["textMessageData"].get("textMessage","").strip()
    elif "extendedTextMessageData" in message_data:
        text = message_data["extendedTextMessageData"].get("text","").strip()

    if not phone or not text:
        return JSONResponse({"status":"no-text"})

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status":"processed"})


# ------------------------------
# CHAT LOGIC
# ------------------------------
INTENT_MAP = {
    "1": "sugar mummy","2":"sugar daddy","3":"benten","4":"girlfriend",
    "5":"boyfriend","6":"1 night stand","7":"just vibes","8":"friend"
}
AGE_MAP = {"1":(18,25),"2":(26,30),"3":(31,35),"4":(36,40),"5":(41,50),"6":(50,99)}

def infer_gender(intent):
    if intent in ["girlfriend","sugar mummy"]: return "female"
    if intent in ["boyfriend","benten","sugar daddy"]: return "male"
    return "any"

def handle_message(phone, text):
    msg = text.strip()
    msg_l = msg.lower()

    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_new_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if msg_l=="exit":
        db_manager.set_state(uid,"NEW")
        return "❌ Conversation ended.\nType HELLO to start again."

    if state=="NEW":
        db_manager.set_state(uid,"GET_GENDER")
        return "Welcome! What is your gender? (MALE/FEMALE/OTHER)"

    if state=="GET_GENDER":
        if msg_l not in ["male","female","other"]: return "Please type MALE, FEMALE, or OTHER."
        db_manager.set_gender(uid,msg_l)
        db_manager.set_state(uid,"WELCOME")
        return "Thanks! Type HELLO to start."

    if state=="WELCOME":
        if msg_l!="hello": return "Type HELLO to continue."
        db_manager.set_state(uid,"GET_INTENT")
        return ("What are you looking for?\n1️⃣ Sugar mummy\n2️⃣ Sugar daddy\n3️⃣ Benten\n"
                "4️⃣ Girlfriend\n5️⃣ Boyfriend\n6️⃣ 1 night stand\n7️⃣ Just vibes\n8️⃣ Friend")

    if state=="GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent: return "Reply with a number (1–8)."
        db_manager.update_profile(uid,"intent",intent)
        db_manager.update_profile(uid,"preferred_gender",infer_gender(intent))
        db_manager.set_state(uid,"GET_AGE_RANGE")
        return "Preferred age range?\n1️⃣ 18-25\n2️⃣ 26-30\n3️⃣ 31-35\n4️⃣ 36-40\n5️⃣ 41-50\n6️⃣ 50+"

    if state=="GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r: return "Choose valid age range (1–6)."
        db_manager.update_profile(uid,"age_min",r[0])
        db_manager.update_profile(uid,"age_max",r[1])
        db_manager.set_state(uid,"GET_NAME")
        return "Your name?"

    if state=="GET_NAME":
        db_manager.update_profile(uid,"name",msg)
        db_manager.set_state(uid,"GET_AGE")
        return "Your age?"

    if state=="GET_AGE":
        if not msg.isdigit(): return "Enter a valid age."
        db_manager.update_profile(uid,"age",int(msg))
        db_manager.set_state(uid,"GET_LOCATION")
        return "Your location?"

    if state=="GET_LOCATION":
        db_manager.update_profile(uid,"location",msg)
        db_manager.set_state(uid,"GET_PHONE")
        return "Your phone number?"

    if state=="GET_PHONE":
        db_manager.update_profile(uid,"contact_phone",msg)
        # Fetch matches from existing DB
        matches = db_manager.get_matches(uid, limit=2)
        db_manager.set_state(uid,"PAY")

        if not matches:
            return "✅ Profile saved! No matches yet."

        preview = "🔥 Top Matches:\n\n"
        for m in matches:
            preview += f"{m['name']} ({m.get('age','?')}) – {m.get('location','Unknown')} [{m.get('intent','?')}]\n"
        preview += "\n💳 Pay $2 to unlock full contacts."
        if matches[0].get("more_available"):
            preview += "\n📌 More matches available!"
        return preview
