from dotenv import load_dotenv
load_dotenv()

import os, time, hashlib, requests
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import db_manager

app = FastAPI()

PAYNOW_INIT_URL = "https://www.paynow.co.zw/interface/initiatetransaction"
PAYNOW_ID = os.getenv("PAYNOW_ID")
PAYNOW_KEY = os.getenv("PAYNOW_KEY")
BASE_URL = os.getenv("BASE_URL")
PAYMENT_AMOUNT = "2.00"

@app.on_event("startup")
def start():
    db_manager.init_db()

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
INTENTS = [
    "1️⃣ Sugar mummy",
    "2️⃣ Sugar daddy",
    "3️⃣ Benten",
    "4️⃣ Girlfriend",
    "5️⃣ Boyfriend",
    "6️⃣ 1 night stand",
    "7️⃣ Just vibes",
    "8️⃣ Friend"
]

AGE_RANGES = [
    "1️⃣ 18-25",
    "2️⃣ 26-30",
    "3️⃣ 31-35",
    "4️⃣ 36-40",
    "5️⃣ 41-50",
    "6️⃣ 50+"
]

INTENT_VALUE = {
    "1":"sugar mummy","2":"sugar daddy","3":"benten",
    "4":"girlfriend","5":"boyfriend","6":"1 night stand",
    "7":"just vibes","8":"friend"
}

AGE_VALUE = {
    "1":(18,25),"2":(26,30),"3":(31,35),
    "4":(36,40),"5":(41,50),"6":(50,99)
}

def infer_gender(intent):
    if intent in ["girlfriend","sugar mummy"]:
        return "female"
    if intent in ["boyfriend","benten","sugar daddy"]:
        return "male"
    return "any"

# -------------------------------------------------
# WEBHOOK
# -------------------------------------------------
@app.post("/webhook")
async def webhook(req: Request):
    data = await req.json()
    msg = data.get("message","")
    phone = data.get("phone","")

    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if msg.lower()=="exit":
        db_manager.set_state(uid,"WELCOME")
        return PlainTextResponse("Conversation ended. Type HELLO to restart.")

    if state=="WELCOME":
        db_manager.set_state(uid,"INTENT")
        return PlainTextResponse(
            "Welcome to Shelby Date Connections where you can find love easily.\n\n"
            "1️⃣ Fill in your details\n"
            "2️⃣ View 2 matches\n"
            "3️⃣ Pay $2 to unlock contacts\n"
            "4️⃣ Your privacy is our concern\n\n"
            "Type HELLO to start or EXIT to stop."
        )

    if state=="INTENT":
        if msg.lower()!="hello":
            return PlainTextResponse("Please type HELLO to continue.")
        db_manager.set_state(uid,"GET_INTENT")
        return PlainTextResponse("What are you looking for?\n"+"\n".join(INTENTS))

    if state=="GET_INTENT":
        intent = INTENT_VALUE.get(msg)
        if not intent:
            return PlainTextResponse("Please select a valid option.")
        db_manager.upsert_profile(uid,"intent",intent)
        db_manager.set_gender(uid,infer_gender(intent))
        db_manager.set_state(uid,"GET_AGE_RANGE")
        return PlainTextResponse("Preferred age range:\n"+"\n".join(AGE_RANGES))

    if state=="GET_AGE_RANGE":
        r = AGE_VALUE.get(msg)
        if not r:
            return PlainTextResponse("Choose a valid age range.")
        db_manager.upsert_profile(uid,"age_min",r[0])
        db_manager.upsert_profile(uid,"age_max",r[1])
        db_manager.set_state(uid,"GET_NAME")
        return PlainTextResponse("Your name:")

    if state=="GET_NAME":
        db_manager.upsert_profile(uid,"name",msg)
        db_manager.set_state(uid,"GET_AGE")
        return PlainTextResponse("Your age:")

    if state=="GET_AGE":
        if not msg.isdigit():
            return PlainTextResponse("Enter a valid age.")
        db_manager.upsert_profile(uid,"age",int(msg))
        db_manager.set_state(uid,"GET_LOCATION")
        return PlainTextResponse("Your location:")

    if state=="GET_LOCATION":
        db_manager.upsert_profile(uid,"location",msg)
        db_manager.set_state(uid,"GET_PHOTO")
        return PlainTextResponse("Send a photo (optional) or type SKIP")

    if state=="GET_PHOTO":
        if msg.lower()!="skip":
            db_manager.upsert_profile(uid,"photo_url",msg)
        db_manager.set_state(uid,"GET_PHONE")
        return PlainTextResponse("Your phone number:")

    if state=="GET_PHONE":
        db_manager.upsert_profile(uid,"contact_phone",msg)
        matches = db_manager.get_matches(uid)

        if not matches:
            return PlainTextResponse("No matches found yet. Please try again later.")

        preview = "🔥 Top Matches:\n\n"
        for m in matches:
            preview += f"{m['name']} ({m['age']}) - {m['location']} [{m['intent']}]\n"
            if m["photo_url"]:
                preview += f"{m['photo_url']}\n"

        db_manager.set_state(uid,"PAY")
        return PlainTextResponse(preview+"\n💳 Pay $2 to unlock contacts.")

    if state=="PAY":
        ref = f"PAY-{uid}-{int(time.time())}"
        hash_str = f"{PAYNOW_ID}{ref}{PAYMENT_AMOUNT}Unlock{BASE_URL}/paid{BASE_URL}/ipn{PAYNOW_KEY}"
        hash_val = hashlib.sha512(hash_str.encode()).hexdigest().upper()

        res = requests.post(PAYNOW_INIT_URL,data={
            "id":PAYNOW_ID,
            "reference":ref,
            "amount":PAYMENT_AMOUNT,
            "additionalinfo":"Unlock",
            "returnurl":f"{BASE_URL}/paid",
            "resulturl":f"{BASE_URL}/ipn",
            "status":"Message",
            "hash":hash_val
        })

        poll = res.text.split("pollurl=")[-1]
        db_manager.create_tx(uid,ref,poll)
        return PlainTextResponse(f"Pay here:\n{poll}")

    return PlainTextResponse("Thank you for using Shelby Date Connections.")
