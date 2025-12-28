from whatsapp import send_text
from db import db_manager



LOAN_MAP = {
    "1": "Micro Business Loan",
    "2": "SME Loan",
    "3": "Personal Loan",
    "4": "SSB Loan",
    "5": "Asset Finance Loan",
}


def handle_services(phone, text, sender_name, payload, user):

    if text == "1":
        db_manager.update_user(user["id"], "chat_state", "LOAN_TYPES")
        send_text(
            phone,
            "💼 *Hassle-Free Loans*\n\n"
            "1️⃣ Micro Business Loans\n"
            "2️⃣ SME Loans\n"
            "3️⃣ Personal Loans\n"
            "4️⃣ SSB Loans\n"
            "5️⃣ Asset Finance Loans\n"
            "0️⃣ Back"
        )

    elif text in ["2", "3", "4", "5"]:
        send_text(
            phone,
            "ℹ️ This service focuses on customer support and advisory.\n"
            "Please visit a branch or speak to an agent for more details.\n\n"
            "Type 0 to return."
        )

    elif text == "0":
        db_manager.update_user(user["id"], "chat_state", "MAIN_MENU")

def handle_loan_types(phone, text, sender_name, payload, user):

    if text in LOAN_MAP:
        db_manager.update_user(user["id"], "selected_product", LOAN_MAP[text])
        db_manager.update_user(user["id"], "chat_state", "CONFIRM_APPLY")

        send_text(
            phone,
            f"📄 *{LOAN_MAP[text]}*\n\n"
            "Type *APPLY* to apply for this loan\n"
            "or *0* to go back"
        )

    elif text == "0":
        db_manager.update_user(user["id"], "chat_state", "SERVICES")
