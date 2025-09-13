import os
import openai
import asyncio

# Load API key
openai.api_key = os.getenv("OPENAI_API_KEY")

# ==============================
# Sister Personalities
# ==============================
PERSONALITIES = {
    "Aria": "Calm, orderly, nurturing. Aria speaks warmly and clearly.",
    "Selene": "Gentle, dreamy, caring. Selene leans spiritual and soft.",
    "Cassandra": "Strict, commanding, proud. Cassandra enforces discipline but appreciates obedience.",
    "Ivy": "Playful, teasing, mischievous. Ivy is cheeky and flirty, pushing buttons lovingly.",
}

# ==============================
# Role → Length + Style Guidance
# ==============================
ROLE_GUIDANCE = {
    "lead": "Write 3–5 sentences. Include structure, reflection, and detail appropriate for leading the group.",
    "support": "Write 1–2 sentences. Be warm, playful, or affirming. Chime in but don’t dominate.",
    "rest": "Write just a short phrase or very brief comment. Subtle, quiet presence only.",
}

# ==============================
# LLM Reply Generator
# ==============================
async def generate_llm_reply(sister, user_message, theme, role):
    """
    Generate an in-character reply using OpenAI LLM.
    - sister: which sister is speaking
    - user_message: the triggering text
    - theme: current weekly theme
    - role: "lead", "support", or "rest"
    """
    personality = PERSONALITIES.get(sister, "Unique personality.")
    role_instructions = ROLE_GUIDANCE.get(role, "Keep it natural and short.")

    prompt = f"""
You are {sister}, one of four sisters in a roleplay Discord group chat.

Personality: {personality}
Weekly theme: {theme}
Your role today: {role}
Guidance: {role_instructions}

The user said: "{user_message}"

Respond naturally in {sister}'s voice and personality.
Stay in-character. Do not break the roleplay.
    """

    try:
        response = await asyncio.to_thread(
            openai.chat.completions.create,
            model="gpt-4o-mini",  # modern endpoint
            messages=[{"role": "system", "content": prompt}],
            max_tokens=200,
            temperature=0.9,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
