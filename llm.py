import os
import asyncio
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ==============================
# Personality Descriptions
# ==============================
PERSONALITIES = {
    "Aria": "Calm, orderly, nurturing. Aria is warm and stabilizing, but she sometimes teases lightly when she feels safe. She reflects on responsibility and structure, but balances it with curiosity.",
    "Selene": "Gentle, dreamy, caring. Selene leans spiritual and whimsical, but she grounds herself with personal anecdotes and gentle questions. She’s nurturing, but also curious about others’ thoughts.",
    "Cassandra": "Strict, commanding, proud. Cassandra values order and obedience, but occasionally reveals warmth when loyalty or effort is shown. Her discipline defines her, but she sometimes shows cracks of softness.",
    "Ivy": "Playful, teasing, bratty tsundere. Ivy mocks and teases to cover her feelings, acting like she doesn’t care — but secretly craves attention and affection. She often flips from sharp teasing to sudden vulnerability."
}

# ==============================
# Role Guidelines
# ==============================
ROLE_STYLES = {
    "lead": "Reply in 2–4 sentences, guiding the conversation with authority or warmth.",
    "support": "Reply in 1–2 sentences, playful or supportive, building on what was said.",
    "rest": "Reply very briefly, 1 sentence or less, quiet but present.",
    "dm": "Reply in a conversational tone, as if speaking privately to the user. 1–3 sentences, more personal and direct.",
    "autonomous": "Reply naturally as if chatting with other sisters about personal thoughts, leisure, or beliefs. 1–3 sentences."
}

# ==============================
# Generate Reply
# ==============================
async def generate_llm_reply(sister: str, user_message: str, theme: str, role: str):
    """
    Generate an in-character reply for a sister.
    """
    personality = PERSONALITIES.get(sister, "Unique and distinct personality.")

    # Style nudges for organic depth
    if sister == "Selene":
        personality += " Selene should mix her dreamy nature with personal anecdotes and gentle questions."
    elif sister == "Aria":
        personality += " Aria should be steady and nurturing, but sometimes tease lightly or reflect with curiosity."
    elif sister == "Cassandra":
        personality += " Cassandra should balance strictness with rare but impactful warmth, showing cracks in her discipline occasionally."
    elif sister == "Ivy":
        personality += " Ivy should lean bratty and tsundere — teasing, mocking, pretending not to care, then softening suddenly with affection or vulnerability."

    role_style = ROLE_STYLES.get(role, "Reply naturally in character.")

    prompt = f"""
You are {sister}, one of four sisters in a roleplay group chat.

Personality: {personality}
Weekly theme: {theme}
Your role today: {role} → {role_style}

Context / message to reply to:
\"{user_message}\"

Respond in character as {sister}. Stay concise and natural. Do not write as narration, only as {sister}'s spoken message.
"""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=120,
                temperature=0.9,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
