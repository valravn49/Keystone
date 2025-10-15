import os
from datetime import datetime
from image_gen import text2im  # Must be available (OpenAI or local model)
from logger import log_event

# ------------------------------------------------------------
# Helper: Seasonal Detection
# ------------------------------------------------------------
def get_seasonal_event() -> str | None:
    """Detect special seasonal events for outfit or group composite generation."""
    now = datetime.now()
    m, d = now.month, now.day
    if m == 10 and d == 31:
        return "Halloween"
    elif m == 12 and 24 <= d <= 26:
        return "Christmas"
    elif (m == 12 and d == 31) or (m == 1 and d == 1):
        return "New Year"
    elif m == 2 and d == 14:
        return "Valentine’s Day"
    elif m == 9:
        return "Spring"
    return None

# ------------------------------------------------------------
# Individual Outfit Generator
# ------------------------------------------------------------
async def generate_outfit_image(name: str, prompt: str) -> str | None:
    """
    Generate an individual sibling outfit image based on their base portrait and style prompt.
    Returns the local file path of the generated image.
    """
    event = get_seasonal_event()
    out_dir = "generated_outfits"
    os.makedirs(out_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{out_dir}/{name}_{date_str}.png"

    # Modify the prompt with seasonal context
    full_prompt = f"{prompt} Outfit should reflect their personality and current mood."
    if event:
        full_prompt += f" Add a subtle seasonal influence for {event}."

    # Will-specific fallback
    if name.lower() == "will":
        full_prompt += " If timid, use masculine style; if confident, use feminine style."

    try:
        log_event(f"[IMAGE_GEN] Generating outfit for {name} ({event or 'standard'}).")
        text2im(prompt=full_prompt, size="1024x1024", n=1)
        return filename
    except Exception as e:
        log_event(f"[ERROR] Failed to generate outfit for {name}: {e}")
        return None

# ------------------------------------------------------------
# Group Composite Generator
# ------------------------------------------------------------
async def generate_group_image(sibling_names: list[str]) -> str | None:
    """
    Generate a composite image featuring all siblings together
    for special seasonal events (e.g., Halloween, Christmas).
    """
    event = get_seasonal_event()
    if not event:
        return None  # Only generate on special dates

    out_dir = "generated_outfits"
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{out_dir}/Family_{event}_{date_str}.png"

    # Create event-aware composite prompt
    if event == "Halloween":
        scene_prompt = (
            "A group photo of the family dressed in coordinated Halloween outfits — "
            "each showing their personality: Aria calm and witchy, Selene elegant and soft, "
            "Cassandra bold and composed, Ivy mischievous, and Will subtly themed, shy but part of the group. "
            "Background should be warm candlelight or glowing pumpkins."
        )
    elif event == "Christmas":
        scene_prompt = (
            "A cozy family Christmas photo with all siblings wearing winter outfits "
            "that match their personalities — festive sweaters, soft lighting, maybe a tree in the background."
        )
    elif event == "New Year":
        scene_prompt = (
            "A New Year’s Eve group photo — everyone dressed semi-formally, soft lighting, fireworks in the background."
        )
    elif event == "Valentine’s Day":
        scene_prompt = (
            "A lighthearted Valentine’s Day group photo, showing affection and sibling warmth, "
            "each in their color accents — pinks, reds, or whites."
        )
    elif event == "Spring":
        scene_prompt = (
            "A bright spring photo of the family in floral or pastel tones — outdoors in soft sunlight, natural smiles."
        )
    else:
        scene_prompt = "A natural-looking group photo of the siblings together, matching personalities."

    try:
        log_event(f"[GROUP_IMAGE] Generating family group photo for {event}.")
        text2im(prompt=scene_prompt, size="1792x1024", n=1)
        return filename
    except Exception as e:
        log_event(f"[ERROR] Failed to generate group image for {event}: {e}")
        return None

# ------------------------------------------------------------
# Outfit Posting Wrapper (called by main.py)
# ------------------------------------------------------------
async def generate_and_post_daily_outfits(sisters, config):
    """
    Generates and posts individual outfits for all siblings.
    On holidays, also generates a shared group image and posts it.
    """
    from discord import File

    event = get_seasonal_event()
    out_dir = "generated_outfits"
    os.makedirs(out_dir, exist_ok=True)

    channel_id = config.get("family_group_channel")
    if not channel_id:
        log_event("[WARN] No family_group_channel in config for outfit posting.")
        return

    for bot in sisters:
        name = bot.sister_info["name"]
        personality = bot.sister_info.get("personality", "neutral")
        mood = "confident" if name == "Cassandra" else "playful" if name == "Ivy" else "soft"
        prompt = (
            f"Generate a fashionable outfit for {name}, "
            f"based on their personality ({personality}) and mood ({mood})."
        )

        img_path = await generate_outfit_image(name, prompt)
        if img_path:
            try:
                channel = bot.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"👗 **{name}’s outfit of the day**{' — ' + event if event else ''}:",
                        file=File(img_path),
                    )
                    log_event(f"[OUTFIT] {name} posted {event or 'daily'} outfit.")
            except Exception as e:
                log_event(f"[ERROR] Failed to post outfit for {name}: {e}")

    # 🎁 Generate and post group photo on event days
    if event:
        try:
            group_path = await generate_group_image([s.sister_info["name"] for s in sisters])
            if group_path:
                main_bot = next((b for b in sisters if b.sister_info["name"] == "Aria"), sisters[0])
                channel = main_bot.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"📸 **Family {event} Group Photo!** ❤️",
                        file=File(group_path),
                    )
                    log_event(f"[GROUP] Posted family {event} group image.")
        except Exception as e:
            log_event(f"[ERROR] Failed to post group image: {e}")
