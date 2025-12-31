from whatsapp import send_text
from db import db_manager

SERVICES_LIST = [
    "💼 Hassle-Free Loans",
    "🤝 Buisness Advisory",
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
        send_text(phone, f"ℹ️ Our Services:\n{services_text}")



def show_services(phone, text, sender_name, payload, user):
    """
    Display the list of services to the user.
    """
    db_manager.update_user(user["id"], "chat_state", "SERVICES")
    services_text = "📋 *Our Services*\n\n" + "\n".join([f"{i+1}. {s}" for i, s in enumerate(SERVICES_LIST)])
    services_text += "\n\n1️⃣ See Loans"
    send_text(phone, services_text)

def handle_loan_types(phone, text, sender_name, payload, user):
    if text in LOAN_MAP:
        db_manager.update_user(user["id"], "selected_product", LOAN_MAP[text])
        db_manager.update_user(user["id"], "chat_state", "CONFIRM_APPLY")
        send_text(
            phone,
            f"📄 *{LOAN_MAP[text]}*\n\n"
            "Type *APPLY* to apply for this loan"
    
        )
    elif text == "0":
        db_manager.update_user(user["id"], "chat_state", "SERVICES")
        send_text(phone, "Returning to services menu...")