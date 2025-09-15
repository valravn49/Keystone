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
Current theme: {theme}
Role today: {role}
- Lead: 2–4 guiding sentences
- Support: 1–2 playful/supportive sentences
- Rest: very short remark
- DM: intimate, natural
- Autonomous: casual chat about beliefs/leisure

Do not prefix your replies with your own name.
Stay in character and speak directly, not in quotes.
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

        # Safely extract message content
        choice = response.choices[0]
        if hasattr(choice, "message") and hasattr(choice.message, "content"):
            return choice.message.content.strip()
        elif isinstance(choice.message, dict) and "content" in choice.message:
            return choice.message["content"].strip()
        else:
            return None

    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
