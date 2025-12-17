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

# -------------------------------------------------
# STARTUP
# -------------------------------------------------
@app.on_event("startup")
def startup():
    db_manager.init_db()

# -------------------------------------------------
# WHATSAPP SEND
# -------------------------------------------------
def send_whatsapp_message(phone, text):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    requests.post(
        url,
        json={"chatId": f"{phone}@c.us", "message": text},
        timeout=15
    )

# -------------------------------------------------
# WEBHOOK
# -------------------------------------------------
@app.get("/webhook")
async def verify():
    return PlainTextResponse("OK")

@app.post("/webhook")
async def webhook(request: Request):
    auth = request.headers.get("Authorization")
    if GREEN_API_AUTH_TOKEN and auth != f"Bearer {GREEN_API_AUTH_TOKEN}":
        raise HTTPException(status_code=401)

    payload = await request.json()
    if payload.get("typeWebhook") != "incomingMessageReceived":
        return JSONResponse({"status": "ignored"})

    sender = payload.get("senderData", {})
    phone = sender.get("chatId", "").split("@")[0]

    msg = payload.get("messageData", {})
    text = (
        msg.get("textMessageData", {}).get("textMessage")
        or msg.get("extendedTextMessageData", {}).get("text")
        or ""
    ).strip()

    if not phone or not text:
        return JSONResponse({"status": "empty"})

    reply = handle_message(phone, text)
    send_whatsapp_message(phone, reply)
    return JSONResponse({"status": "processed"})

# -------------------------------------------------
# CHAT CONSTANTS (UX PRESERVED)
# -------------------------------------------------
INTENT_MAP = {
    "1": "sugar mummy",
    "2": "sugar daddy",
    "3": "benten",
    "4": "girlfriend",
    "5": "boyfriend",
    "6": "1 night stand",
    "7": "just vibes",
    "8": "friend"
}

AGE_MAP = {
    "1": (18, 25),
    "2": (26, 30),
    "3": (31, 35),
    "4": (36, 40),
    "5": (41, 50),
    "6": (50, 99)
}

def infer_gender(intent):
    if intent in ["girlfriend", "sugar mummy"]:
        return "female"
    if intent in ["boyfriend", "benten", "sugar daddy"]:
        return "male"
    return "any"

# -------------------------------------------------
# CHAT HANDLER
# -------------------------------------------------
def handle_message(phone, text):
    msg = text.strip()
    msg_l = msg.lower()

    # ------------------------------
    # USER / PROFILE (ONE ONLY)
    # ------------------------------
    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_user(phone)

    uid = user["id"]

    # ensure exactly ONE profile exists
    db_manager.ensure_profile(uid)

    state = user["chat_state"]

    # ------------------------------
    # EXIT
    # ------------------------------
    if msg_l == "exit":
        db_manager.set_state(uid, "NEW")
        return "❌ Conversation ended.\n\nType *HELLO* to start again."

    # ------------------------------
    # FLOW
    # ------------------------------
    if state == "NEW":
        db_manager.set_state(uid, "GET_GENDER")
        return (
            "👋 Welcome!\n\n"
            "Please tell us your gender:\n"
            "• MALE\n"
            "• FEMALE\n"
            "• OTHER"
        )

    if state == "GET_GENDER":
        if msg_l not in ["male", "female", "other"]:
            return "❗ Please reply with *MALE*, *FEMALE*, or *OTHER*."
        db_manager.set_gender(uid, msg_l)
        db_manager.set_state(uid, "WELCOME")
        return "✅ Saved!\n\nType *HELLO* to continue."

    if state == "WELCOME":
        if msg_l != "hello":
            return "👉 Please type *HELLO* to proceed."
        db_manager.set_state(uid, "GET_INTENT")
        return (
            "💖 What are you looking for?\n\n"
            "1️⃣ Sugar mummy\n"
            "2️⃣ Sugar daddy\n"
            "3️⃣ Benten\n"
            "4️⃣ Girlfriend\n"
            "5️⃣ Boyfriend\n"
            "6️⃣ 1 night stand\n"
            "7️⃣ Just vibes\n"
            "8️⃣ Friend"
        )

    if state == "GET_INTENT":
        intent = INTENT_MAP.get(msg)
        if not intent:
            return "❗ Please choose a number between *1 – 8*."
        db_manager.update_profile(uid, "intent", intent)
        db_manager.update_profile(uid, "preferred_gender", infer_gender(intent))
        db_manager.set_state(uid, "GET_AGE_RANGE")
        return (
            "🎂 Preferred age range:\n\n"
            "1️⃣ 18–25\n"
            "2️⃣ 26–30\n"
            "3️⃣ 31–35\n"
            "4️⃣ 36–40\n"
            "5️⃣ 41–50\n"
            "6️⃣ 50+"
        )

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(msg)
        if not r:
            return "❗ Please select a valid option *(1 – 6)*."
        db_manager.update_profile(uid, "age_min", r[0])
        db_manager.update_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME")
        return "📝 What is your *name*?"

    if state == "GET_NAME":
        db_manager.update_profile(uid, "name", msg)
        db_manager.set_state(uid, "GET_AGE")
        return "🎂 How old are you?"

    if state == "GET_AGE":
        if not msg.isdigit():
            return "❗ Please enter a valid age."
        db_manager.update_profile(uid, "age", int(msg))
        db_manager.set_state(uid, "GET_LOCATION")
        return "📍 Where are you located?"

    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", msg)
        db_manager.set_state(uid, "GET_PHONE")
        return "📞 Enter your contact number:"

    if state == "GET_PHONE":
        db_manager.update_profile(uid, "contact_phone", msg)
        matches = db_manager.get_matches(uid)
        db_manager.set_state(uid, "PAY")

        if not matches:
            return (
                "✅ Profile saved successfully!\n\n"
                "🚫 No matches found yet.\n"
                "We will notify you when new matches appear."
            )

        reply = "🔥 *Top Matches for You* 🔥\n\n"
        for m in matches:
            reply += f"• {m['name']} ({m['age']}) — {m['location']}\n"
        reply += "\n💰 Pay *$2* to unlock contact details."
        return reply
