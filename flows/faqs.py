from db import db_manager
from whatsapp import send_text
from ai import ask_microhub_ai
from db import db_manager

# ---------------------------
# HARD-CODED FAQ CONTENT
# ---------------------------

FAQS = {
    "1": (
        "💼 *Loans Offered*\n\n"
        "• Micro Business Loans\n"
        "• SME Loans\n"
        "• Personal Salary-Based Loans\n"
        "• SSB Loans\n"
        "• Asset Finance Loans"
    ),
    "2": (
        "📄 *Loan Requirements*\n\n"
        "• Valid National ID\n"
        "• Proof of income or business\n"
        "• Recent bank statements\n"
        "• Completed application form"
    ),
    "3": (
        "⏱ *Approval Time*\n\n"
        "Loan approval typically takes 24–72 hours "
        "after all required documents are submitted."
    ),
    "4": (
        "🏢 *SME Loans*\n\n"
        "Yes. We offer flexible financing solutions "
        "for Small and Medium Enterprises."
    ),
    "5": (
        "📲 *WhatsApp Applications*\n\n"
        "Yes. You can apply for a loan directly through this WhatsApp chatbot."
    )
}

# ---------------------------
# FAQ MENU HANDLER
# ---------------------------

def handle_faq_menu(phone, text, sender_name, payload, user):
    text = text.strip()  # normalize input

    # Back to main menu
    if text == "0":
        db_manager.update_user(user["id"], "chat_state", "MAIN_MENU")
        return

    # AI FAQ
    if text == "6":
        db_manager.update_user(user["id"], "chat_state", "AI_FAQ")
        send_text(phone, "🤖 Ask me any question about Microhub services.\n\nType '0' to go back.")
        return

    # Show FAQ answer if valid choice
    if text in FAQS:
        send_text(phone, FAQS[text])
        return

    # If text is empty or invalid, show menu
    send_text(
        phone,
        "❓ *Microhub FAQs*\n\n"
        "1️⃣ What loans does Microhub offer?\n"
        "2️⃣ What are the loan requirements?\n"
        "3️⃣ How long does approval take?\n"
        "4️⃣ Do you offer SME loans?\n"
        "5️⃣ Can I apply via WhatsApp?\n"
        "6️⃣ Ask AI a question\n\n"
        "0️⃣ Back to Main Menu"
    )


# ---------------------------
# AI FAQ HANDLER
# ---------------------------

def handle_ai_faq(phone, text, sender_name, payload, user):

    if text == "0":
        db_manager.update_user(user["id"], "chat_state", "FAQ_MENU")
        return

    answer = ask_microhub_ai(text)
    send_text(phone, answer)
