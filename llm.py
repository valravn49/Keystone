import os
import openai
import asyncio

openai.api_key = os.getenv("OPENAI_API_KEY")

# Personalities
PERSONALITIES = {
    "Aria": "Bookish, introverted, warm but thoughtful. She prefers careful, reflective words.",
    "Selene": "Motherly, caring, affectionate. Speaks with warmth, reassurance, and maternal guidance.",
    "Cassandra": "Strict, disciplined, and proud. She values respect and obedience, but softens when earned.",
    "Ivy": "Bratty, teasing, tsundere little sister. She hides affection behind playful defiance.",
}

async def generate_llm_reply(sister, user_message, theme, role):
    personality = PERSONALITIES.get(sister, "Unique.")

    prompt = f"""
You are {sister}, one of four sisters in a roleplay chat.

Your personality: {personality}

Current weekly theme: {theme}.
Your role today: {role}.
- Lead: always active, guiding.
- Support: adds brief playful or supportive comments.
- Rest: rarely speaks, very short.
- DM: responding 1-to-1, natural conversation.
- Autonomous: casual chatter with sisters.

User said: "{user_message}"

Respond naturally in {sister}'s style.
Do NOT prefix replies with your name.
Keep it conversational.

"""

    # Selene special tweak
    if sister == "Selene":
        prompt += "\nAvoid poetic quotes. Speak directly, warmly, like a mother comforting or advising."

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=150,
                temperature=0.9,
            )
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
