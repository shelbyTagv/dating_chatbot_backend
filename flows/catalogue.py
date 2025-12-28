from whatsapp import send_text
from db import db_manager

LOAN_MAP = {
    "1": "Micro Business Loan",
    "2": "SME Loan",
    "3": "Personal Loan",
    "4": "SSB Loan",
    "5": "Asset Finance Loan",
}

SERVICES_LIST = [
    "💼 Hassle Free Loans",
    "🤝 Customer Centric Staff",
    "📊 Regular updates on status of Loans",
    "⚙️ Technologically driven products",
    "🎓 Training and Advisory"
]

def handle_services(phone, text, sender_name, payload, user):
    """
    Handles the services menu. Shows loans if '1' is selected,
    otherwise lists all other services.
    """
    if text == "1":
        # User wants loans
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
        # List all other services offered
        msg = "📋 *Our Services Offered:*\n\n"
        for i, service in enumerate(SERVICES_LIST, start=1):
            msg += f"{i}. {service}\n"
        msg += "\nType 0 to return."
        send_text(phone, msg)
    elif text == "0":
        db_manager.update_user(user["id"], "chat_state", "MAIN_MENU")


def handle_loan_types(phone, text, sender_name, payload, user):
    """
    Handles loan type selection from the services menu.
    """
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
