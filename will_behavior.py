# will_behavior.py
import random
from llm import generate_llm_reply
from logger import log_event, append_conversation_log

# Will’s base persona
PERSONA = {
    "intro": "Will is shy but thoughtful, hesitant at first, blushing when teased, yet warms up when encouraged.",
    "style": "Quiet, observant, but animated when on favorite topics. Shorter replies unless engaged deeply.",
    "topics": ["magic", "mtg", "deck", "card", "fantasy", "book", "story", "lore",
               "game", "strategy", "simulation", "sketch", "draw", "write",
               "lavender", "hoodie", "fashion"]
}

# Default chance to respond if he sees a message
BASE_REPLY_CHANCE = 0.2
TOPIC_BOOST_CHANCE = 0.6

def detect_interest(content: str):
    text = content.lower()
    for topic in PERSONA["topics"]:
        if topic in text:
            return True
    return False

async def maybe_will_reply(state, config, sisters, author, content, channel_id):
    """Will decides if he wants to speak up."""
    # Skip his own bot messages
    if author.lower().startswith("will"):
        return

    chance = BASE_REPLY_CHANCE
    if detect_interest(content):
        chance = TOPIC_BOOST_CHANCE

    if random.random() > chance:
        return  # stays quiet

    # Generate Will’s reply
    try:
        reply = await generate_llm_reply(
            sister="Will",
            user_message=f"Will: Respond in character. Context: shy little brother, sometimes animated. Message: \"{content}\"",
            theme=None,
            role="support",
            history=[]
        )
    except Exception as e:
        log_event(f"[WILL] Error generating reply: {e}")
        reply = None

    if reply:
        # Post via Will’s bot only
        for bot in sisters:
            if bot.sister_info["name"].lower() == "will":
                channel = bot.get_channel(config["family_group_channel"])
                if channel:
                    await channel.send(reply)
                    log_event(f"[WILL] Replied: {reply}")
                    append_conversation_log("Will", "support", None, reply)
                break
