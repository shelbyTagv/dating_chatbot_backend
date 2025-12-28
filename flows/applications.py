from whatsapp import send_text
from db import db_manager


def handle_confirm_apply(phone, text, sender_name, payload, user):

    if text.lower() == "apply":
        db_manager.update_user(user["id"], "chat_state", "GET_NAME")
        send_text(phone, "🧾 Please enter your *Full Name*:")

def handle_get_name(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "full_name", text)
    db_manager.update_user(user["id"], "chat_state", "GET_AGE")
    send_text(phone, "🎂 Enter your *Age*:")

def handle_get_age(phone, text, sender_name, payload, user):
    if not text.isdigit():
        send_text(phone, "❌ Please enter a valid age.")
        return

    db_manager.update_user(user["id"], "age", text)
    db_manager.update_user(user["id"], "chat_state", "GET_ADDRESS")
    send_text(phone, "🏠 Enter your *Full Address*:")

def handle_get_address(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "address", text)
    db_manager.update_user(user["id"], "chat_state", "GET_ID")
    send_text(phone, "🆔 Enter your *National ID Number*:")

def handle_get_id(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "national_id", text)
    db_manager.update_user(user["id"], "chat_state", "GET_ID_PHOTO")
    send_text(phone, "📸 Please upload a *photo of your ID*:")

def handle_get_id_photo(phone, text, sender_name, payload, user):
    file_url = payload.get("messageData", {}).get("fileMessageData", {}).get("downloadUrl")

    if not file_url:
        send_text(phone, "⚠️ Please upload a photo to proceed.")
        return

    db_manager.update_user(user["id"], "id_photo_url", file_url)
    db_manager.update_user(user["id"], "chat_state", "GET_AMOUNT")
    send_text(phone, "💰 Enter the *amount* you are applying for:")

def handle_get_amount(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "amount", text)
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
            "🎉 Your loan application has been submitted successfully.\n"
            "Our team will contact you shortly."
        )
