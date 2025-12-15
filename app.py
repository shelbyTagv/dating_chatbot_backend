from dotenv import load_dotenv
load_dotenv()

import os
from flask import Flask, request, jsonify
import db_manager
import requests
import hashlib
import time

load_dotenv()
app = Flask(__name__)

PAYNOW_URL = "https://www.paynow.co.zw/interface/initiatetransaction"

@app.route("/whatsapp/webhook", methods=["POST"])
def whatsapp_webhook():
    payload = request.json
    phone = payload["from"]
    text = payload["text"].strip()
    reply = handle_message(phone, text)
    return jsonify({"reply": reply})

def handle_message(phone, text):
    user = db_manager.get_or_create_user(phone)
    uid = user["id"]
    state = user["chat_state"]

    if state == "START":
        db_manager.update_chat_state(uid, "GET_NAME")
        return "Welcome ❤️ What is your name?"

    if state == "GET_NAME":
        db_manager.update_profile_field(uid, "name", text)
        db_manager.update_chat_state(uid, "GET_AGE")
        return "How old are you?"

    if state == "GET_AGE":
        if not text.isdigit():
            return "Please enter a valid age."
        db_manager.update_profile_field(uid, "age", int(text))
        db_manager.update_chat_state(uid, "GET_GENDER")
        return "Gender? (Male/Female/Other)"

    if state == "GET_GENDER":
        db_manager.update_profile_field(uid, "gender", text.capitalize())
        db_manager.update_chat_state(uid, "GET_LOCATION")
        return "Which city are you in?"

    if state == "GET_LOCATION":
        db_manager.update_profile_field(uid, "location", text)
        db_manager.update_chat_state(uid, "GET_MOTIVE")
        return "What are you looking for? (Soulmate / Casual / Sugar)"

    if state == "GET_MOTIVE":
        db_manager.update_profile_field(uid, "motive", text)
        db_manager.update_chat_state(uid, "AWAITING_PAYMENT")
        return initiate_payment(uid)

    if state == "AWAITING_PAYMENT":
        return "Please complete your Ecocash payment to continue."

    if state == "ACTIVE_SEARCH":
        match = db_manager.find_match(uid, user.get("motive"))
        if match:
            return f"🔥 Match Found!\nName: {match['name']}\nAge: {match['age']}\nLocation: {match['location']}"
        return "No matches yet. Please check again later."

    return "Something went wrong. Please restart."

# ---------- PAYNOW ----------

def initiate_payment(user_id):
    ref = f"SUB-{user_id}-{int(time.time())}"
    amount = "5.00"
    auth_string = os.getenv("PAYNOW_ID") + ref + amount + os.getenv("PAYNOW_KEY")
    hash_val = hashlib.sha512(auth_string.encode()).hexdigest()

    payload = {
        "id": os.getenv("PAYNOW_ID"),
        "reference": ref,
        "amount": amount,
        "status": "Message",
        "hash": hash_val
    }

    r = requests.post(PAYNOW_URL, data=payload)
    poll_url = r.text.split("pollurl=")[-1]

    db_manager.create_transaction(user_id, ref, poll_url, amount)
    return "💰 Payment initiated. Please confirm on Ecocash."


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
