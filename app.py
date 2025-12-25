from fastapi import FastAPI, Request
import os, re, requests, threading, time, db_manager
from pesepay import Pesepay
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

# Config
GREEN_API_URL = f"https://api.greenapi.com/waInstance{os.getenv('ID INSTANCE1')}"
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")
pesepay = Pesepay(os.getenv("PESEPAY_INTEGRATION_KEY"), os.getenv("PESEPAY_ENCRYPTION_KEY"))
pesepay.return_url = os.getenv("PAYNOW_RETURN_URL")
pesepay.result_url = os.getenv("PAYNOW_RESULT_URL")

ZIG_RATE = 27
USD_FEE = 150
ZIG_FEE = USD_FEE * ZIG_RATE

# --- Utilities ---
def send_wa(phone, text):
    url = f"{GREEN_API_URL}/sendMessage/{API_TOKEN}"
    requests.post(url, json={"chatId": f"{phone}@c.us", "message": text})

def validate_id(id_num):
    return re.match(r"^\d{2}-\d{6,7}[A-Z]\d{2}$", id_num.upper())

def validate_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

# --- State Handler ---
def handle_message(phone, msg, payload):
    msg_l = msg.lower().strip()
    user = db_manager.get_applicant(phone)
    if not user: user = db_manager.create_applicant(phone)
    aid = user['id']
    state = user['chat_state']

    if msg_l == "reset":
        db_manager.set_state(aid, "NEW")
        return "Registration reset. Type 'START' to begin."

    if state == "NEW":
        db_manager.set_state(aid, "GET_FNAME")
        return "Welcome to IP4SBPS Registration. Please enter your First Name(s):"

    if state == "GET_FNAME":
        db_manager.update_applicant(aid, "first_name", msg)
        db_manager.set_state(aid, "GET_SNAME")
        return "Enter your Surname:"

    if state == "GET_SNAME":
        db_manager.update_applicant(aid, "surname", msg)
        db_manager.set_state(aid, "GET_ID")
        return "Enter your National ID (e.g., 00-000000X00):"

    if state == "GET_ID":
        if not validate_id(msg): return "Invalid ID format. Please use 00-000000X00."
        db_manager.update_applicant(aid, "national_id", msg.upper())
        db_manager.set_state(aid, "GET_ADDRESS")
        return "Please enter your Full Home Address:"

    if state == "GET_ADDRESS":
        db_manager.update_applicant(aid, "address", msg)
        db_manager.set_state(aid, "GET_MODE")
        return "Select preferred Mode of Entry:\n1. Weekend\n2. Holidays\n3. Other"

    if state == "GET_MODE":
        modes = {"1":"Weekend", "2":"Holidays", "3":"Other"}
        val = modes.get(msg)
        if not val: return "Select 1, 2, or 3."
        db_manager.update_applicant(aid, "mode_of_entry", val)
        db_manager.set_state(aid, "GET_COHORT")
        return "Which Cohort/Period are you applying for? (e.g., Jan 2025)"

    if state == "GET_COHORT":
        db_manager.update_applicant(aid, "cohort", msg)
        db_manager.set_state(aid, "GET_EMAIL")
        return "Enter your Email Address:"

    if state == "GET_EMAIL":
        if not validate_email(msg): return "Invalid email address."
        db_manager.update_applicant(aid, "email", msg)
        db_manager.set_state(aid, "GET_GENDER")
        return "Gender:\n1. Male\n2. Female"

    if state == "GET_GENDER":
        g = {"1":"Male", "2":"Female"}.get(msg)
        if not g: return "Select 1 or 2."
        db_manager.update_applicant(aid, "gender", g)
        db_manager.set_state(aid, "GET_QUAL")
        return "What is your Highest Educational Qualification?"

    if state == "GET_QUAL":
        db_manager.update_applicant(aid, "highest_qual", msg)
        db_manager.set_state(aid, "GET_EXP")
        return "Teaching Experience (Number of years):"

    if state == "GET_EXP":
        if not msg.isdigit(): return "Please enter a number."
        db_manager.update_applicant(aid, "exp_years", int(msg))
        db_manager.set_state(aid, "GET_LEVEL")
        return "Level taught:\n1. Tertiary\n2. Secondary\n3. Primary"

    if state == "GET_LEVEL":
        lvl = {"1":"Tertiary", "2":"Secondary", "3":"Primary"}.get(msg)
        if not lvl: return "Select 1, 2, or 3."
        db_manager.update_applicant(aid, "level_taught", lvl)
        db_manager.set_state(aid, "GET_NEEDS")
        return "Do you have any Special Needs? (Type 'None' if not applicable)"

    if state == "GET_NEEDS":
        db_manager.update_applicant(aid, "special_needs", msg)
        db_manager.set_state(aid, "UPLOAD_ID")
        return "📎 Please upload a clear photo/PDF of your National ID:"

    # --- Document Uploads ---
    if state in ["UPLOAD_ID", "UPLOAD_OLEVEL", "UPLOAD_ALEVEL", "UPLOAD_PROF"]:
        file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")
        if not file_url: return "Please upload a document file to continue."
        
        doc_map = {
            "UPLOAD_ID": ("ID", "UPLOAD_OLEVEL", "📎 Upload O-Level Certificate:"),
            "UPLOAD_OLEVEL": ("O_LEVEL", "UPLOAD_ALEVEL", "📎 Upload A-Level Certificate:"),
            "UPLOAD_ALEVEL": ("A_LEVEL", "UPLOAD_PROF", "📎 Upload Professional Certificate:"),
            "UPLOAD_PROF": ("PROFESSIONAL", "CHOOSE_CURR", "Final Step: Payment.\nSelect Currency:\n1. USD ($150)\n2. ZiG (4050)")
        }
        
        dtype, next_state, next_msg = doc_map[state]
        db_manager.save_document(aid, dtype, file_url)
        db_manager.set_state(aid, next_state)
        return next_msg

    if state == "CHOOSE_CURR":
        if msg == "1":
            db_manager.set_state(aid, "PAY_USD")
            return "Enter EcoCash USD Number (e.g. 077...):"
        if msg == "2":
            db_manager.set_state(aid, "PAY_ZIG")
            return "Enter EcoCash ZiG Number (e.g. 077...):"
        return "Select 1 or 2."

    if state in ["PAY_USD", "PAY_ZIG"]:
        curr = "USD" if state == "PAY_USD" else "ZWG"
        amt = USD_FEE if curr == "USD" else ZIG_FEE
        method = "PZW211" if curr == "USD" else "PZW201"
        
        # Payment logic (Simpified for brevity - same as your previous logic)
        payment = pesepay.create_payment(curr, method, user['email'], msg, user['first_name'])
        resp = pesepay.make_seamless_payment(payment, "IP4SBPS Registration", amt, {"customerPhoneNumber": msg})
        
        if resp.success:
            db_manager.create_payment(aid, resp.referenceNumber, resp.pollUrl, amt, curr)
            db_manager.set_state(aid, "AWAIT_CONFIRM")
            return "🚀 Prompt sent! Enter PIN on your phone and type 'STATUS' to verify."
        return "Payment initiation failed. Check number and try again."

    return "Registration in progress. Follow the prompts or type 'RESET'."

@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    if payload.get("typeWebhook") == "incomingMessageReceived":
        phone = payload["senderData"]["chatId"].split("@")[0]
        text = payload["messageData"].get("textMessageData", {}).get("textMessage", "")
        reply = handle_message(phone, text, payload)
        send_wa(phone, reply)
    return {"status": "ok"}

@app.on_event("startup")
def startup():
    db_manager.init_db()