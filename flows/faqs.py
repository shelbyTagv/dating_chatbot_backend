from whatsapp import send_text
from ai.faq_ai import ask_ai
from db import db_manager


FAQS = {
    "1": "We offer Business, Pension, and Housing loans.",
    "2": "Mukando is a rotating savings scheme.",
}

def handle_faq_menu(phone, text, sender_name, payload, user):
    if text == "1":
        msg = "📘 FAQs\n"
        for k, v in FAQS.items():
            msg += f"{k}. {v}\n"
        send_text(phone, msg)

    elif text == "2":
        db_manager.update_user(user["id"], "chat_state", "AI_FAQ")
        send_text(phone, "🤖 Ask your question:")

    elif text == "0":
        db_manager.update_user(user["id"], "chat_state", "MAIN_MENU")
        send_text(phone, "Back to menu")

def handle_ai_faq(phone, text, sender_name, payload, user):
    answer = ask_ai(text)
    send_text(phone, answer)
