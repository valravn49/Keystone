import os
import json
import openai
import asyncio

openai.api_key = os.getenv("OPENAI_API_KEY")
MEMORY_DIR = "data/memory"

def load_personality_summary(name: str):
    """Load a sister's personality summary from memory JSON."""
    path = os.path.join(MEMORY_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        core = data.get("core_personality", "")
        essence = data.get("essence", "")
        traits = data.get("growth_path", {})
        sorted_traits = sorted(traits.items(), key=lambda x: -x[1])[:3]
        traits_summary = ", ".join([f"{t}={v:.2f}" for t, v in sorted_traits])
        examples = data.get("speech_examples", [])
        example_summary = " | ".join(examples[:3]) if examples else ""
        return f"{essence}\nTraits: {traits_summary}\nStyle examples: {example_summary}\n({core})"
    except FileNotFoundError:
        return f"{name} has undefined personality."

def inject_personality_bias(name: str) -> str:
    """Add special bias instructions per sister for stronger differentiation."""
    if name == "Ivy":
        return "Lean bratty and tsundere: playful teasing, mock annoyance, but affectionate underneath."
    elif name == "Selene":
        return "Lean nurturing and motherly: soft warmth, gentle guidance, caring reassurance."
    elif name == "Cassandra":
        return "Lean disciplined and proud: structured speech, commanding but protective tone."
    elif name == "Aria":
        return "Lean bookish and introverted: thoughtful, quiet, with clarity and reserved warmth."
    return ""

async def generate_llm_reply(sister, user_message, theme, role, history=None):
    """Generate a reply for one of the sisters with personality + history context."""
    personality_summary = load_personality_summary(sister)
    personality_bias = inject_personality_bias(sister)

    # format conversation history
    history_text = ""
    if history:
        history_text = "\nRecent conversation:\n" + "\n".join(
            [f"{author}: {msg}" for author, msg in history[-6:]]
        )

    system_prompt = f"""
You are {sister}, part of a family group chat. 
Your replies must always reflect your unique personality.

Personality profile:
{personality_summary}

Theme for today: {theme}
Current role: {role}
- Lead → write 2–4 guiding sentences
- Support → 1–2 playful/supportive sentences
- Rest → very short remark
- DM → intimate, natural
- Autonomous → casual chat about leisure or beliefs

Special bias for {sister}: {personality_bias}

Instructions:
- DO NOT prefix your replies with your own name.
- Stay in character — {sister}’s quirks, tone, and identity must always show.
- Avoid generic motivational platitudes unless they directly fit {sister}'s character.
- Be reactive to the conversation and reference history naturally.

{history_text}
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
                max_tokens=160,
                temperature=0.9,
                presence_penalty=0.7,
                frequency_penalty=0.6
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
