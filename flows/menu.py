from whatsapp import send_text
from utils.constants import STATE_MAIN_MENU, STATE_START
from db import db_manager


def handle_start(phone, text, sender_name, payload, user):
    db_manager.update_user(user["id"], "chat_state", STATE_MAIN_MENU)

    menu = (
        f"Welcome to *MICROHUB FINANCIAL SERVICES*, {sender_name}!\n\n"
        "1️⃣ Products & Services\n"
        "2️⃣ Contact Us\n"
        "3️⃣ FAQs(frequently Asked Questions)\n"
        "4️⃣ Talk to an Agent\n\n"
        "_Type EXIT to restart_"
    )
    send_text(phone, menu)

def handle_main_menu(phone, text, sender_name, payload, user):
    if text == "1":
        db_manager.update_user(user["id"], "chat_state", "CATALOGUE")
        send_text(phone, "📂 Products\n1️⃣ Loans\n2️⃣ Mukando\n3️⃣ Solar\n4️⃣ Funeral\n0️⃣ Back")

    elif text == "2":
        send_text(
            phone,
            "📍 *Microhub Branches*\n"
            "Harare: +263 777 123 456\n"
            "Bulawayo: +263 778 654 321\n\n"
            "Type 0 for menu"
        )

    elif text == "3":
        db_manager.update_user(user["id"], "chat_state", "FAQ_MENU")
        send_text(phone, "❓ FAQs\n1️⃣ Common Questions\n2️⃣ Ask AI\n0️⃣ Back")

    elif text == "4":
        db_manager.update_user(user["id"], "chat_state", "AGENT")
        send_text(phone, "👨‍💼 An agent will contact you shortly.")

    elif text == "0":
        handle_start(phone, text, sender_name, payload, user)

    send_text(phone, "❌ Invalid option. Please choose 1–4.")
