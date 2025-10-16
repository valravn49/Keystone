# autonomy/autonomy.py

import random
import asyncio
from datetime import datetime

from llm import generate_llm_reply
from logger import log_event



async def random_sister_conversation(sisters, get_current_theme, FAMILY_CHANNEL_ID):
    """
    Trigger a spontaneous multi-turn conversation between 2–3 sisters.
    Each conversation is 3–6 turns with random pauses.
    """

    if len(sisters) < 2:
        return

    # Pick 2–3 participants
    participants = random.sample(sisters, k=random.randint(2, 3))
    theme = get_current_theme()

    # Use the first sister's channel as the conversation channel
    channel = participants[0].get_channel(FAMILY_CHANNEL_ID)
    if not channel:
        return

    # Number of turns in this burst
    turns = random.randint(3, 6)
    last_message = None

    log_event(
        f"[AUTONOMY] Starting organic conversation with "
        f"{', '.join([p.sister_info['name'] for p in participants])} "
        f"({turns} turns)."
    )

    for t in range(turns):
        speaker = random.choice(participants)
        name = speaker.sister_info["name"]

        # Build the input prompt depending on context
        if t == 0:
            prompt = (
                "Start a casual chat about leisure, hobbies, daily thoughts, "
                "or beliefs. Keep it natural and authentic."
            )
        else:
            prompt = f"Reply naturally to the last message: \"{last_message}\""

        try:
            reply = await generate_llm_reply(
                sister=name,
                user_message=prompt,
                theme=theme,
                role="autonomous"
            )

            if reply:
                await channel.send(f"{name}: {reply}")
                log_event(f"[AUTONOMY] {name} said: {reply}")
                evolve_personality(speaker.sister_info, event="organic")
                last_message = reply

        except Exception as e:
            log_event(f"[AUTONOMY ERROR] {name} failed to reply: {e}")

        # Wait a little before next turn (feels more alive)
        if t < turns - 1:
            await asyncio.sleep(random.randint(20, 90))

    log_event("[AUTONOMY] Organic conversation ended.")
