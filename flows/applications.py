import re
from whatsapp import send_text
from db import db_manager


ID_REGEX = re.compile(r"^\d{2}-\d{7}[A-Za-z]\d{2}$")


def handle_confirm_apply(phone, text, sender_name, payload, user):
    if text.lower() == "apply":
        db_manager.update_user(user["id"], "chat_state", "GET_NAME")
        send_text(phone, "🧾 Please enter your *Full Name* (e.g. John Doe):")

def handle_get_name(phone, text, sender_name, payload, user):
    if len(text.split()) < 2 or not all(part.isalpha() for part in text.replace(" ", "")):
        send_text(phone, "❌ Please enter a valid *full name* (first and last name).")
        return

    db_manager.update_user(user["id"], "full_name", text.strip())
    db_manager.update_user(user["id"], "chat_state", "GET_AGE")
    send_text(phone, "🎂 Enter your *Age* (18+):")

def handle_get_age(phone, text, sender_name, payload, user):
    if not text.isdigit() or int(text) < 18:
        send_text(phone, "❌ Age must be a number and *18 or above*.")
        return

    db_manager.update_user(user["id"], "age", int(text))
    db_manager.update_user(user["id"], "chat_state", "GET_ADDRESS")
    send_text(phone, "🏠 Enter your *Full Residential Address*:")

def handle_get_address(phone, text, sender_name, payload, user):
    if len(text.strip()) < 10:
        send_text(phone, "❌ Address is too short. Please enter full details.")
        return

    db_manager.update_user(user["id"], "address", text.strip())
    db_manager.update_user(user["id"], "chat_state", "GET_ID")
    send_text(phone, "🆔 Enter your *National ID Number* (e.g. 63-2156742S22):")

def handle_get_id(phone, text, sender_name, payload, user):
    text = text.replace(" ", "")

    if not ID_REGEX.match(text):
        send_text(
            phone,
            "❌ Invalid ID format.\n"
            "Correct format example:\n"
            "*63-2156742S22*"
        )
        return

    db_manager.update_user(user["id"], "national_id", text.upper())
    db_manager.update_user(user["id"], "chat_state", "GET_ID_PHOTO")
    send_text(phone, "📸 Upload a *clear photo of your National ID*:")

def handle_get_id_photo(phone, text, sender_name, payload, user):
    file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")

    if not file_url:
        send_text(phone, "⚠️ Please upload an image of your ID to proceed.")
        return

    db_manager.update_user(user["id"], "id_photo_url", file_url)
    db_manager.update_user(user["id"], "chat_state", "GET_PROOF_OF_WORK")
    send_text(
        phone,
        "🏢 Upload *Proof of Work*\n"
        "(Payslip, Employment Letter, or Business License):"
    )

def handle_get_proof_of_work(phone, text, sender_name, payload, user):
    file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")

    if not file_url:
        send_text(
            phone,
            "⚠️ Please upload a document or image as *Proof of Work*."
        )
        return

    db_manager.update_user(user["id"], "proof_of_work_url", file_url)
    db_manager.update_user(user["id"], "chat_state", "GET_AMOUNT")
    send_text(phone, "💰 Enter the *Loan Amount* you are applying for:")

def handle_get_amount(phone, text, sender_name, payload, user):
    if not text.isdigit() or int(text) <= 0:
        send_text(phone, "❌ Please enter a valid numeric amount.")
        return

    db_manager.update_user(user["id"], "amount", int(text))
    db_manager.update_user(user["id"], "chat_state", "FINAL_CONFIRM")

    send_text(
        phone,
        "✅ *Confirm Submission*\n\n"
        "Reply *YES* to submit your application\n"
        "or *EXIT* to cancel"
    )

def handle_final_confirm(phone, text, sender_name, payload, user):
    if text.lower() == "yes":
        db_manager.save_final_application(user["id"])
        db_manager.update_user(user["id"], "chat_state", "START")

        send_text(
            phone,
            "🎉 *Application Submitted Successfully!*\n\n"
            "Our team will contact you shortly."
        )
