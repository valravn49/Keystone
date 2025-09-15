import os
import json
import random
import openai
import asyncio

openai.api_key = os.getenv("OPENAI_API_KEY")
MEMORY_DIR = "data/memory"

def load_personality(name: str):
    """Load full personality JSON for a sister."""
    path = os.path.join(MEMORY_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "core_personality": "Undefined.",
            "growth_path": {},
            "speech_examples": []
        }

def build_personality_summary(personality: dict) -> str:
    """Summarize traits and growth for prompt context."""
    core = personality.get("core_personality", "Undefined.")
    traits = personality.get("growth_path", {})
    if traits:
        sorted_traits = sorted(traits.items(), key=lambda x: -x[1])[:3]
        traits_summary = ", ".join([f"{t}={v:.2f}" for t, v in sorted_traits])
    else:
        traits_summary = "no traits"
    return f"{core} Key traits: {traits_summary}"

async def generate_llm_reply(sister, user_message, theme, role):
    personality = load_personality(sister)
    personality_summary = build_personality_summary(personality)

    # 30% chance: pick a pre-written speech example instead of LLM
    if personality.get("speech_examples") and random.random() < 0.3:
        example = random.choice(personality["speech_examples"])
        print(f"[LLM] {sister} used example: {example}")
        return example

    system_prompt = f"""
You are {sister}, part of a family group chat.
Personality: {personality_summary}
Current theme: {theme}
Role today: {role}

Guidelines:
- Lead: 2–4 guiding sentences
- Support: 1–2 playful/supportive sentences
- Rest: very short remark
- DM: intimate, natural
- Autonomous: casual chat about beliefs/leisure
- Stay consistent with personality traits and tone
- Do not prefix replies with your name
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
