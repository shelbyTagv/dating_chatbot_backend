from openai import OpenAI
from config import OPENAI_API_KEY

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = (
    "You are the Microhub Finance Assistant. "
    "Answer ONLY about Loans, Mukando, Solar Systems, and Funeral Plans. "
    "If unrelated, politely decline."
)

def ask_ai(question: str) -> str:
    try:
        res = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}
            ]
        )
        return res.choices[0].message.content
    except Exception as e:
        print(f"OpenAI error: {e}")
        return "AI is currently unavailable. Please try again later."
