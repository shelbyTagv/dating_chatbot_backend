from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ask_microhub_ai(question):

    system_prompt = (
        "You are a Microhub Financial Services assistant. "
        "You may ONLY answer questions related to Microhub loans, "
        "financial products, branches, or application processes. "
        "If a question is unrelated, politely say you can only help "
        "with Microhub services."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content

    except Exception:
        return "⚠️ Our AI service is currently unavailable. Please try again later."
