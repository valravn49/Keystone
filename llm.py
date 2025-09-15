import os
import json
import openai
import asyncio

openai.api_key = os.getenv("OPENAI_API_KEY")
MEMORY_DIR = "data/memory"

# ==============================
# Style Hints (per Sister)
# ==============================
STYLE_HINTS = {
    "Aria": "Thoughtful, bookish, introverted. Reflects deeply, may reference reading or structured thinking.",
    "Selene": "Motherly, nurturing, caring. Speaks softly, offering emotional warmth and reassurance.",
    "Cassandra": "Strict, proud, disciplined. Speaks with confidence, reminding of order and expectations.",
    "Ivy": "Bratty, cheeky, tsundere little sister. Playful teasing, mocking affection, or mischievous remarks."
}

# ==============================
# Load Memory Summary
# ==============================
def load_personality_summary(name: str):
    """Load top traits + identity from memory JSONs."""
    path = os.path.join(MEMORY_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        core = data.get("core_identity", "")
        traits = data.get("growth_path", {})
        sorted_traits = sorted(traits.items(), key=lambda x: -x[1])[:3]
        traits_summary = ", ".join([f"{t}={v:.2f}" for t, v in sorted_traits])
        return f"{core} Key traits: {traits_summary}"
    except FileNotFoundError:
        return f"{name} has undefined personality."

# ==============================
# Generate LLM Reply
# ==============================
async def generate_llm_reply(sister, user_message, theme, role):
    personality_summary = load_personality_summary(sister)
    style = STYLE_HINTS.get(sister, "Unique style.")

    system_prompt = f"""
You are {sister}, part of a family group chat.

Personality: {personality_summary}
Style hint: {style}
Current theme: {theme}
Role today: {role}

- Lead: 2–4 guiding sentences
- Support: 1–2 playful/supportive sentences
- Rest: very short remark
- DM: intimate, natural, direct
- Autonomous: casual chat about beliefs/leisure

⚠️ Rules:
- Do NOT prefix your replies with your own name.
- Speak directly, in natural conversational tone.
"""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=120,
                temperature=0.9,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
