import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

ID_INSTANCE = os.getenv("ID_INSTANCE")
API_TOKEN = os.getenv("API_TOKEN_INSTANCE")

BASE_URL = f"https://api.greenapi.com/waInstance{ID_INSTANCE}"
