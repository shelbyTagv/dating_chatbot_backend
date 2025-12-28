from fastapi import FastAPI, Request
from db import db_manager
from flows import menu, services, faqs, agent, applications, contact

app = FastAPI()

STATE_HANDLERS = {
    "START": menu.handle_start,
    "MAIN_MENU": menu.handle_main_menu,
    "SERVICES": services.handle_services,
    "LOAN_TYPES": services.handle_loan_types,
    "FAQ_MENU": faqs.handle_faq_menu,
    "AI_FAQ": faqs.handle_ai_faq,
    "AGENT": agent.handle_agent,
    "CONFIRM_APPLY": applications.handle_confirm_apply,
    "GET_NAME": applications.handle_get_name,
    "GET_AGE": applications.handle_get_age,
    "GET_ADDRESS": applications.handle_get_address,
    "GET_ID": applications.handle_get_id,
    "GET_ID_PHOTO": applications.handle_get_id_photo,
    "GET_AMOUNT": applications.handle_get_amount,
    "FINAL_CONFIRM": applications.handle_final_confirm,
}



@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if data.get("typeWebhook") != "incomingMessageReceived":
        return {"status": "ignored"}

    sender = data.get("senderData", {})
    msg_data = data.get("messageData", {})

    phone = sender.get("chatId", "").split("@")[0]
    sender_name = sender.get("senderName", "Customer")

    text = ""
    if "textMessageData" in msg_data:
        text = msg_data["textMessageData"].get("textMessage", "")
    elif "extendedTextMessageData" in msg_data:
        text = msg_data["extendedTextMessageData"].get("text", "")

    user = db_manager.get_user(phone)
    if not user:
        user = db_manager.create_user(phone)

    if text.lower() in ["exit", "reset", "restart"]:
        db_manager.update_user(user["id"], "chat_state", "START")

    state = user["chat_state"]
    handler = STATE_HANDLERS.get(state, menu.handle_start)

    handler(phone, text, sender_name, data, user)

    return {"status": "ok"}

@app.on_event("startup")
def startup():
    print("Server ready")
