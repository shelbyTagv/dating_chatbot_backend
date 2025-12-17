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

def send_whatsapp_message(phone, text):
    url = f"{GREEN_API_URL}/waInstance{ID_INSTANCE}/sendMessage/{API_TOKEN_INSTANCE}"
    requests.post(
        url,
        json={"chatId": f"{phone}@c.us", "message": text},
        timeout=15
    )

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

# ------------------------------
# CHAT LOGIC
# ------------------------------
INTENT_MAP = {
    "1": "sugar mummy", "2": "sugar daddy", "3": "benten",
    "4": "girlfriend", "5": "boyfriend",
    "6": "1 night stand", "7": "just vibes", "8": "friend"
}

AGE_MAP = {
    "1": (18, 25), "2": (26, 30), "3": (31, 35),
    "4": (36, 40), "5": (41, 50), "6": (50, 99)
}

def infer_gender(intent):
    if intent in ["girlfriend", "sugar mummy"]:
        return "female"
    if intent in ["boyfriend", "benten", "sugar daddy"]:
        return "male"
    return "any"

def handle_message(phone, text):
    msg = text.strip().lower()

    user = db_manager.get_user_by_phone(phone)
    if not user:
        user = db_manager.create_new_user(phone)
        db_manager.create_profile(user["id"])

    uid = user["id"]
    state = user["chat_state"]

    if msg == "exit":
        db_manager.set_state(uid, "NEW")
        return "Conversation ended. Type HELLO to restart."

    if state == "NEW":
        db_manager.set_state(uid, "GET_GENDER")
        return "Welcome! What is your gender? (MALE/FEMALE/OTHER)"

    if state == "GET_GENDER":
        if msg not in ["male", "female", "other"]:
            return "Please reply MALE, FEMALE, or OTHER."
        db_manager.set_gender(uid, msg)
        db_manager.set_state(uid, "WELCOME")
        return "Thanks! Type HELLO to continue."

    if state == "WELCOME":
        if msg != "hello":
            return "Type HELLO to proceed."
        db_manager.set_state(uid, "GET_INTENT")
        return (
            "What are you looking for?\n"
            "1 Sugar mummy\n2 Sugar daddy\n3 Benten\n4 Girlfriend\n"
            "5 Boyfriend\n6 1 night stand\n7 Just vibes\n8 Friend"
        )

    if state == "GET_INTENT":
        intent = INTENT_MAP.get(text)
        if not intent:
            return "Choose 1–8."
        db_manager.update_profile(uid, "intent", intent)
        db_manager.update_profile(uid, "preferred_gender", infer_gender(intent))
        db_manager.set_state(uid, "GET_AGE_RANGE")
        return "Preferred age range? (1–6)"

    if state == "GET_AGE_RANGE":
        r = AGE_MAP.get(text)
        if not r:
            return "Choose a valid range (1–6)."
        db_manager.update_profile(uid, "age_min", r[0])
        db_manager.update_profile(uid, "age_max", r[1])
        db_manager.set_state(uid, "GET_NAME")
        return "Your name?"

    if state == "GET_NAME":
        db_manager.update_profile(uid, "name", text)
        db_manager.set_state(uid, "GET_AGE")
        return "Your age?"

    if state == "GET_AGE":
        if not text.isdigit():
            return "Enter a valid age."
        db_manager.update_profile(uid, "age", int(text))
        db_manager.set_state(uid, "GET_LOCATION")
        return "Your location?"

    if state == "GET_LOCATION":
        db_manager.update_profile(uid, "location", text)
        db_manager.set_state(uid, "GET_PHONE")
        return "Your contact phone?"

    if state == "GET_PHONE":
        db_manager.update_profile(uid, "contact_phone", text)
        matches = db_manager.get_matches(uid)
        db_manager.set_state(uid, "PAY")

        if not matches:
            return "Profile saved. No matches yet."

        reply = "Top Matches:\n\n"
        for m in matches:
            reply += f"{m['name']} ({m['age']}) - {m['location']}\n"
        reply += "\nPay $2 to unlock contacts."
        return reply
