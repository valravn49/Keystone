from llm import generate_llm_reply
from .personality import PersonalityManager
from logger import log_event

async def handle_dm(bot, message, theme_getter):
    """
    Handle a direct message sent to a sister.
    """
    name = bot.sister_info["name"]
    pm = PersonalityManager(name)

    try:
        reply = await generate_llm_reply(
            sister=name,
            user_message=message.content,
            theme=theme_getter(),
            role="dm"
        )
        if reply:
            await message.channel.send(reply)
            log_event(f"[DM] {name} replied in DM to {message.author}: {reply}")
    except Exception as e:
        log_event(f"[DM ERROR] {name}: {e}")
