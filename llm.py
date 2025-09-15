import os
import json
import openai
import asyncio
import random

openai.api_key = os.getenv("OPENAI_API_KEY")
MEMORY_DIR = "data/memory"

def load_personality_summary(name: str):
    path = os.path.join(MEMORY_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        core = data.get("core_identity", "")
        traits = data.get("growth_path", {})
        sorted_traits = sorted(traits.items(), key=lambda x: -x[1])[:3]
        traits_summary = ", ".join([f"{t}={v:.2f}" for t, v in sorted_traits])
        return f"{core} Traits: {traits_summary}"
    except FileNotFoundError:
        return f"{name} has undefined personality."

def get_voice_style(sister: str, role: str):
    base_styles = {
        "Aria": "Bookish, introverted, a little awkward but thoughtful. Sometimes blunt or dry.",
        "Selene": "Warm, motherly, affectionate. Longer nurturing replies.",
        "Cassandra": "Strict, proud, disciplined. Corrects and teases with authority.",
        "Ivy": "Bratty, teasing, tsundere little sister. Mischievous and sarcastic.",
    }

    role_flavor = {
        "lead": "Lead casually but naturally, 2–4 sentences.",
        "support": "1–2 sentences, playful or supportive.",
        "rest": "One very short line or emoji.",
        "dm": "Natural, intimate private texting tone.",
        "autonomous": "Casual sibling chat about anything, no structure.",
    }

    return f"{base_styles.get(sister, '')} {role_flavor.get(role, '')}"

async def generate_llm_reply(sister, user_message, theme, role):
    personality_summary = load_personality_summary(sister)
    style = get_voice_style(sister, role)

    # 20% chance of forcing a short "alive" sibling reply
    if random.random() < 0.2 and role in ["support", "rest", "autonomous"]:
        return random.choice([
            "lol", "ugh", "whatever 🙄", "idc", "bruh", "fine.", "hmm", "😂", "nah"
        ])

    system_prompt = f"""
You are {sister}, a sister in a family group chat. 
Replies should be casual, natural, and in-character.
Do NOT prefix with your name.
Stay consistent with this style:

{style}

Context:
- Theme: {theme}
- Role: {role}
- Personality: {personality_summary}
"""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": user_message.strip()}
                ],
                max_tokens=150,
                temperature=0.9,
                top_p=0.95,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
