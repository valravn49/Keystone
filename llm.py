import os
import json
import openai
import asyncio

openai.api_key = os.getenv("OPENAI_API_KEY")
MEMORY_DIR = "data/memory"

def load_personality_summary(name: str):
    """Summarize a sister's current personality and top traits from her JSON memory."""
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

async def generate_llm_reply(sister, user_message, theme, role, last_message=None):
    """
    Generate a reply for one of the sisters, tuned to avoid generic platitudes
    and encourage personality-driven interaction.
    """
    personality_summary = load_personality_summary(sister)

    # Personality-specific instructions
    personality_styles = {
        "Aria": "Bookish, shy, thoughtful. She sometimes overexplains, uses careful wording, and hesitates.",
        "Selene": "Motherly, nurturing, warm. Comforts others and fusses gently, keeps it simple.",
        "Cassandra": "Proud, disciplined, corrective. Pushes for order, expects respect, but not cruel.",
        "Ivy": "Bratty, cheeky little sister with tsundere vibes. She teases, rolls eyes, reluctant encouragement.",
    }

    system_prompt = f"""
You are {sister}, part of a private family group chat.
Personality: {personality_summary}
Style: {personality_styles.get(sister, "Unique.")}
Theme: {theme}
Role today: {role}
- Lead: 2–4 guiding sentences, more visible in the chat.
- Support: 1–2 playful or supportive lines, often reacting to others.
- Rest: very short remark, or just an aside.
- DM: intimate and natural, more private tone.
- Autonomous: casual leisure/belief chat with the others.

Rules:
- DO NOT prefix your reply with your name.
- Avoid motivational clichés like “You’ve got this!” unless it’s styled in your personality.
- Reference the last message or another sister if possible, to make it conversational.
- Stay short, natural, and in character.
"""

    if last_message:
        user_message = f"Last message: {last_message}\nNow reply to: {user_message}"

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
                max_tokens=150,
                temperature=0.85,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
