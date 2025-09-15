import os
import json
import openai
import asyncio

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
        return f"{core} Key traits: {traits_summary}"
    except FileNotFoundError:
        return f"{name} has undefined personality."

async def generate_llm_reply(sister, user_message, theme, role):
    personality_summary = load_personality_summary(sister)
    system_prompt = f"""
You are {sister}, part of a family group chat.
Personality: {personality_summary}
Theme: {theme}
Role: {role}

Rules:
- Only respond once per turn.
- Keep it natural, short, and role-consistent.
- Do NOT prefix your replies with your own name.
- Aria: thoughtful, introverted, 2–3 sentences.
- Selene: motherly, gentle, 1–2 nurturing sentences.
- Cassandra: disciplined, sharp, 1–2 lines.
- Ivy: bratty, teasing, but varied (not just 'nah' or 'idc').

Reply conversationally to either the user or sisters.
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
                temperature=0.85,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
