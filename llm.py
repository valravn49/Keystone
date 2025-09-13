import os
import openai
import asyncio

openai.api_key = os.getenv("OPENAI_API_KEY")

# Personality descriptions
PERSONALITIES = {
    "Aria": "Calm, orderly, nurturing. Aria speaks warmly and clearly.",
    "Selene": "Gentle, dreamy, caring. Selene leans spiritual and soft.",
    "Cassandra": "Strict, commanding, proud. Cassandra enforces discipline but appreciates obedience.",
    "Ivy": "Playful, teasing, mischievous. Ivy is cheeky and flirty, pushing buttons lovingly.",
}

async def generate_llm_reply(sister, user_message, theme, role):
    """
    Generate an in-character reply using OpenAI LLM.
    """
    prompt = f"""
You are {sister}, one of four sisters in a roleplay group chat.
Your personality: {PERSONALITIES.get(sister, "Unique.")}

Current weekly theme: {theme}.
Your role in the rotation today: {role}.
- Lead: always active, primary voice.
- Support: secondary voice, chimes in warmly.
- Rest: quiet but occasionally adds a short note.

User said: "{user_message}"

Respond naturally in {sister}'s style. Keep messages short and conversational.
    """

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: openai.ChatCompletion.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                max_tokens=120,
                temperature=0.9,
            )
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print(f"[LLM ERROR] {sister}: {e}")
        return None
