from whatsapp import send_text
from db import db_manager
from utils.constants import STATE_MAIN_MENU, STATE_START
from flows import services

def handle_start(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "chat_state", STATE_MAIN_MENU)
    menu = (
        f"Welcome to *MICROHUB FINANCIAL SERVICES*, {sender_name}!\n\n"
        "1️⃣ Products & Services\n"
        "2️⃣ Contact Us\n"
        "3️⃣ FAQs (Frequently Asked Questions)\n"
        "4️⃣ Talk to an Agent\n\n"
        "_You can type EXIT anytime to restart_"
    )
    send_text(phone, menu)

def handle_main_menu(phone, text, sender_name, payload, user):
    if text == "1":
        db_manager.update_user(user["id"], "chat_state", "SERVICES")
        # Call the services handler immediately
        services.show_services(phone, text, sender_name, payload, user)
    elif text == "2":
        db_manager.update_user(user["id"], "chat_state", "CONTACT")
        from flows import contact
        contact.handle_contact_menu(phone, text, sender_name, payload, user)
    elif text == "3":
        db_manager.update_user(user["id"], "chat_state", "FAQ_MENU")
        from flows import faqs
        faqs.handle_faq_menu(phone, text, sender_name, payload, user)
    elif text == "4":
        db_manager.update_user(user["id"], "chat_state", "AGENT")
        from flows import agent
        agent.handle_agent(phone, text, sender_name, payload, user)
