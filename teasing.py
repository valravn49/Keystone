import random
from llm import generate_llm_reply
from logger import log_event
from sisters_behavior import post_to_family, is_awake, get_today_rotation, get_current_theme

async def maybe_tease_will(state, config, sisters, author, message):
    """If Will posts about a favorite, sisters may tease him playfully."""
    if author != "Will":
        return

    favorites = state.get("will_favorites_today", [])
    if not favorites:
        return

    # Check if message mentions any favorite
    for fav in favorites:
        if fav.lower() in message.lower():
            rotation = get_today_rotation(state, config)
            theme = get_current_theme(state, config)

            teasers = []
            for bot in sisters:
                sname = bot.sister_info["name"]
                if sname == "Will":
                    continue
                if is_awake(bot.sister_info, rotation["lead"]) and random.random() < 0.5:
                    reply = await generate_llm_reply(
                        sister=sname,
                        user_message=f"Tease Will about his obsession with {fav}, keep it playful, short (1–2 sentences).",
                        theme=theme,
                        role="support",
                        history=[]
                    )
                    if reply:
                        teasers.append((sname, reply))

            # Send collected teasers
            for sname, reply in teasers:
                await post_to_family(reply, sender=sname, sisters=sisters, config=config)
                log_event(f"[TEASE] {sname} teased Will: {reply}")
            break
