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

def show_services(phone, user):
    """
    Display the list of services to the user.
    """
    db_manager.update_user(user["id"], "chat_state", "SERVICES")
    services_text = "📋 *Our Services*\n\n" + "\n".join([f"{i+1}. {s}" for i, s in enumerate(SERVICES_LIST)])
    services_text += "\n\n1️⃣ See Loans\n0️⃣ Back to Main Menu"
    send_text(phone, services_text)

def handle_service_selection(phone, text, user):
    """
    Handles user's selection in the services menu.
    """
    if text == "1":  # Show loans
        db_manager.update_user(user["id"], "chat_state", "LOAN_TYPES")
        loans_text = "\n".join([f"{i}️⃣ {loan}" for i, loan in LOAN_MAP.items()])
        send_text(phone, f"💼 *Hassle-Free Loans*\n\n{loans_text}\n0️⃣ Back")
    elif text == "0":  # Back to main menu
        db_manager.update_user(user["id"], "chat_state", "MAIN_MENU")
        from flows.menu import handle_main_menu  # Avoid circular import
        handle_main_menu(phone, "0", user.get("name", ""), None, user)
    else:
        send_text(phone, "❌ Invalid option. Please choose 1 for Loans or 0 to go back.")

def handle_loan_types(phone, text, user):
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
        show_services(phone, user)
    else:
        send_text(phone, "❌ Invalid selection. Choose a loan number or 0 to go back.")
