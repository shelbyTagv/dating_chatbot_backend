
from whatsapp import send_text
from db import db_manager

SERVICES_LIST = [
    "💼 Hassle-Free Loans",
    "🤝 Customer Centric Staff",
    "📈 Regular updates on status of Loans",
    "🖥 Technologically driven products",
    "🎓 Training and Advisory"
]

LOAN_MAP = {
    "1": "Micro Business Loan",
    "2": "SME Loan",
    "3": "Personal Loan",
    "4": "SSB Loan",
    "5": "Asset Finance Loan"
}

def handle_services(phone, text, sender_name, payload, user):
    if text == "1":
        db_manager.update_user(user["id"], "chat_state", "LOAN_TYPES")
        loans_text = "\n".join([f"{i}️⃣ {loan}" for i, loan in LOAN_MAP.items()])
        send_text(phone, f"💼 *Hassle-Free Loans*\n\n{loans_text}\n0️⃣ Back")

    elif text in ["2", "3", "4", "5"]:
        services_text = "\n".join(SERVICES_LIST)
        send_text(phone, f"ℹ️ Our Services:\n{services_text}\n\nType 0 to return.")

    elif text == "0":
        db_manager.update_user(user["id"], "chat_state", "MAIN_MENU")

def handle_loan_types(phone, text, sender_name, payload, user):
    """
    Handles loan selection from the user.
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
        send_text(phone, "Returning to services menu...")
