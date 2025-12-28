from whatsapp import send_text

def handle_agent(phone, text, sender_name, payload, user):
    send_text(
        phone,
        "👨‍💼 Thank you. An agent has been notified and will reach out shortly."
    )
