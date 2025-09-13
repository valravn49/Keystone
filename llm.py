import os
import openai

# Get API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    print("[llm] WARNING: OPENAI_API_KEY not found in environment")

openai.api_key = OPENAI_API_KEY


def generate_llm_reply(sister_name: str, message: str, rotation: dict, theme: str) -> str:
    """
    Generate a reply for the given sister using the OpenAI API.

    Args:
        sister_name (str): The speaking sister (e.g. "Aria").
        message (str): The incoming message to respond to.
        rotation (dict): Current rotation (lead, rest, supports).
        theme (str): Current weekly novelty theme.

    Returns:
        str: The generated reply text.
    """

    system_prompt = f"""
You are {sister_name}, one of four AI sisters in a family group chat.
Each sister has her own personality and role (lead, support, rest).
The weekly theme is: {theme}.
Rotation today: lead={rotation.get("lead")}, rest={rotation.get("rest")}, supports={", ".join(rotation.get("supports", []))}.
Stay fully in-character when replying.
"""

    print(f"[llm] Generating reply for {sister_name} | theme={theme}")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # lightweight but strong
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_tokens=150,
        )

        reply = response["choices"][0]["message"]["content"].strip()
        print(f"[llm] {sister_name} reply: {reply}")
        return reply

    except Exception as e:
        print(f"[llm] ERROR generating reply for {sister_name}: {e}")
        return f"({sister_name} seems quiet right now.)"
