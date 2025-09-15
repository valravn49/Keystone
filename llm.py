import os
import json
import openai
import asyncio
from datetime import datetime

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
            "essence": f"{name} has no defined personality.",
            "likes": [],
            "dislikes": [],
            "speech_examples": []
        }

def build_personality_summary(personality: dict):
    """Format essence, likes, dislikes, and examples into a summary."""
    essence = personality.get("essence", "")
    likes = ", ".join(personality.get("likes", [])[:3]) or "unspecified"
    dislikes = ", ".join(personality.get("dislikes", [])[:3]) or "unspecified"
    examples = "\n".join([f'- "{ex}"' for ex in personality.get("speech_examples", [])[:3]])
    return f"""
Essence: {essence}
Likes: {likes}
Dislikes: {dislikes}
Speech style examples:
{examples}
"""

async def generate_llm_reply(sister, user_message, theme, role, history=None):
    """
    Generate an in-character reply using OpenAI LLM.
    history: optional list of (speaker, message) tuples for context.
    """
    personality = load_personality(sister)
    personality_summary = build_personality_summary(personality)

    # Role-based style hints
    role_hints = {
        "lead": "2–4 sentences, guiding the conversation naturally.",
        "support": "1–2 sentences, playful or supportive if it fits.",
        "rest": "Very brief, one remark or reaction.",
        "dm": "Natural, intimate, conversational tone.",
        "autonomous": "Casual chat about your interests, beliefs, or daily life.",
    }
    style_hint = role_hints.get(role, "Stay in character.")

    # Build conversation context
    conversation_context = ""
    if history:
        formatted = [f"{speaker}: {msg}" for speaker, msg in history[-6:]]
        conversation_context = "\n".join(formatted)

    system_prompt = f"""
You are {sister}, part of a family group chat.
{personality_summary}

Current theme: {theme}
Role today: {role} → {style_hint}

Rules:
- Do NOT prefix replies with your own name.
- Do NOT default to generic encouragement unless it matches your personality.
- Use quirks, tone, and style from the examples.
- If responding autonomously, talk about your own interests or perspective.
"""

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Conversation so far:\n{conversation_context}\n\nUser said: {user_message}"}
                ],
                max_tokens=120,
                temperature=0.9,
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
