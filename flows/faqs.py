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

    # First, check if user just entered FAQ menu
    if user["chat_state"] != "FAQ_MENU":
        # Update state to FAQ_MENU and show menu
        db_manager.update_user(user["id"], "chat_state", "FAQ_MENU")
        send_text(
            phone,
            "❓ *Microhub FAQs*\n\n"
            "1️⃣ What loans does Microhub offer?\n"
            "2️⃣ What are the loan requirements?\n"
            "3️⃣ How long does approval take?\n"
            "4️⃣ Do you offer SME loans?\n"
            "5️⃣ Can I apply via WhatsApp?\n"
            "6️⃣ Ask me any question\n\n"
            
        )
        return


    # AI FAQ
    if text == "6":
        db_manager.update_user(user["id"], "chat_state", "AI_FAQ")
        send_text(phone, "🤖 Ask me any question about Microhub services.")
        return

    # Show FAQ answer if valid choice
    if text in FAQS:
        send_text(phone, FAQS[text])
        return

    # If text is empty or invalid, show menu again
    send_text(
        phone,
        "❌ Invalid option. Please choose from the menu.\n\n"
        "❓ *Microhub FAQs*\n\n"
        "1️⃣ What loans does Microhub offer?\n"
        "2️⃣ What are the loan requirements?\n"
        "3️⃣ How long does approval take?\n"
        "4️⃣ Do you offer SME loans?\n"
        "5️⃣ Can I apply via WhatsApp?\n"
        "6️⃣ Ask me any question\n\n"
    )



# ---------------------------
# AI FAQ HANDLER
# ---------------------------

def handle_ai_faq(phone, text, sender_name, payload, user):

    answer = ask_microhub_ai(text)
    send_text(phone, answer)
