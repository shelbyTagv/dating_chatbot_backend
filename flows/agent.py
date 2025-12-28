from db import db_manager
from whatsapp import send_text
import threading
import time

# ----------------------------------
# Step 1: User requests an agent
# ----------------------------------

def handle_agent(phone, text, sender_name, payload, user):
    """
    First handler when user chooses Talk to Agent
    """
    db_manager.update_user(user["id"], "chat_state", "AGENT_WAIT")
    
    # Send initial connecting message with "dots"
    send_text(phone, "👨‍💼 Connecting you to an agent. Please wait...")
    
    # Start a background thread to simulate agent joining
    threading.Thread(target=_simulate_agent_join, args=(phone, user["id"])).start()


# ----------------------------------
# Step 2: Background thread simulates agent
# ----------------------------------

def _simulate_agent_join(phone, user_id):
    """
    Waits ~2 minutes then sends agent joined message
    """
    # Simulate typing dots
    dots = ["Connecting.", "Connecting..", "Connecting..."]
    for i in range(3):  # Repeat 3 times (~9 seconds total)
        send_text(phone, dots[i % len(dots)])
        time.sleep(3)

    # Wait the remainder to reach ~2 minutes
    time.sleep(105)  # 105 seconds → total ~2 min with previous dots

    # Agent joined
    send_text(phone, "✅ You are now connected to a Microhub agent. Please type your message.")

    # Update user state to AGENT to allow normal conversation with agent
    db_manager.update_user(user_id, "chat_state", "AGENT")
