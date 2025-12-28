from whatsapp import send_text
from db import db_manager
from utils.constants import STATE_MAIN_MENU, STATE_START

def handle_start(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "chat_state", STATE_MAIN_MENU)
    menu = (
        f"Welcome to *MICROHUB FINANCIAL SERVICES*, {sender_name}!\n\n"
        "1️⃣ Products & Services\n"
        "2️⃣ Contact Us\n"
        "3️⃣ FAQs (Frequently Asked Questions)\n"
        "4️⃣ Talk to an Agent\n\n"
        "_Type EXIT to restart_"
    )
    send_text(phone, menu)

def handle_main_menu(phone, text, sender_name, payload, user):
    if text == "1":
        # Set state to SERVICES and let services.py handle the menu
        db_manager.update_user(user["id"], "chat_state", "SERVICES")
    elif text == "2":
        # Set state to CONTACT and let contact.py handle logic
        db_manager.update_user(user["id"], "chat_state", "CONTACT")
    elif text == "3":
        # Set state to FAQ and let faq.py handle logic
        db_manager.update_user(user["id"], "chat_state", "FAQ_MENU")
    elif text == "4":
        # Set state to AGENT and let agent.py handle logic
        db_manager.update_user(user["id"], "chat_state", "AGENT")
    elif text == "0":
        handle_start(phone, text, sender_name, payload, user)
    else:
        send_text(phone, "❌ Invalid option. Please choose 1–4.")
