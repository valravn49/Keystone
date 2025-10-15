import os
from datetime import datetime
from image_gen import text2im
from logger import log_event

# ------------------------------------------------------------
# Helper: Event and Season Detection
# ------------------------------------------------------------
def get_seasonal_event() -> str | None:
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
    return None

def get_current_season() -> str:
    """Returns season name (for southern hemisphere / Australia)."""
    m = datetime.now().month
    if m in (12, 1, 2):
        return "Summer"
    elif m in (3, 4, 5):
        return "Autumn"
    elif m in (6, 7, 8):
        return "Winter"
    else:
        return "Spring"

# ------------------------------------------------------------
# Seasonal Fashion Adjustments
# ------------------------------------------------------------
def get_seasonal_style_description(season: str) -> str:
    styles = {
        "Spring": "pastel colors, airy fabrics, gentle sunlight tones, soft dresses or cardigans",
        "Summer": "vibrant hues, short sleeves, breathable fabrics, playful accessories",
        "Autumn": "warm earthy tones, layered outfits, scarves, knitwear, golden light",
        "Winter": "cozy outfits, thicker materials, long sleeves, muted palettes, gentle contrast",
    }
    return styles.get(season, "neutral, balanced fashion style")

# ------------------------------------------------------------
# Individual Outfit Generator
# ------------------------------------------------------------
async def generate_outfit_image(name: str, prompt: str) -> str | None:
    event = get_seasonal_event()
    season = get_current_season()
    out_dir = "generated_outfits"
    os.makedirs(out_dir, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{out_dir}/{name}_{date_str}.png"

    fashion_desc = get_seasonal_style_description(season)
    full_prompt = (
        f"{prompt} Outfit should reflect {season} season fashion — {fashion_desc}. "
        "Keep proportions realistic and color-coordinated."
    )

    if event:
        full_prompt += f" Add a subtle influence from {event}."

    if name.lower() == "will":
        full_prompt += (
            " If Will feels timid, use his masculine portrait with modest fashion. "
            "If confident, use his feminine portrait with expressive details."
        )

    try:
        log_event(f"[IMAGE_GEN] Generating outfit for {name} ({season}, {event or 'standard'}).")
        text2im(prompt=full_prompt, size="1024x1024", n=1)
        return filename
    except Exception as e:
        log_event(f"[ERROR] Failed to generate outfit for {name}: {e}")
        return None

# ------------------------------------------------------------
# Group Composite Generator
# ------------------------------------------------------------
async def generate_group_image(sibling_names: list[str]) -> str | None:
    event = get_seasonal_event()
    if not event:
        return None

    out_dir = "generated_outfits"
    os.makedirs(out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{out_dir}/Family_{event}_{date_str}.png"

    # Create an event-aware composite scene
    if event == "Halloween":
        scene_prompt = (
            "A group photo of the siblings dressed for Halloween: "
            "Aria calm and witchy, Selene elegant and mystical, "
            "Cassandra regal and composed, Ivy mischievous, "
            "and Will shy but clearly part of the group. "
            "Atmosphere: candlelight, pumpkins, warm colors."
        )
    elif event == "Christmas":
        scene_prompt = (
            "A cozy Christmas group photo — all siblings together by a softly lit tree, "
            "wearing festive winter outfits that reflect their personalities."
        )
    elif event == "New Year":
        scene_prompt = (
            "A stylish New Year’s Eve photo — elegant semi-formal outfits, "
            "gold and black accents, fireworks in the background."
        )
    elif event == "Valentine’s Day":
        scene_prompt = (
            "A warm Valentine’s Day photo showing sibling affection — gentle reds, pinks, and soft lighting."
        )
    else:
        scene_prompt = (
            "A natural family portrait with subtle event-themed touches matching their personalities."
        )

    try:
        log_event(f"[GROUP_IMAGE] Generating group photo for {event}.")
        text2im(prompt=scene_prompt, size="1792x1024", n=1)
        return filename
    except Exception as e:
        log_event(f"[ERROR] Failed to generate group image: {e}")
        return None

# ------------------------------------------------------------
# Group Posting & Will's Reaction
# ------------------------------------------------------------
async def generate_and_post_daily_outfits(sisters, config):
    from discord import File
    from will_behavior import load_will_memory  # For confidence tracking

    event = get_seasonal_event()
    season = get_current_season()
    channel_id = config.get("family_group_channel")

    if not channel_id:
        log_event("[WARN] No family channel ID found for outfit posting.")
        return

    # 🧥 Generate individual outfits
    for bot in sisters:
        name = bot.sister_info["name"]
        personality = bot.sister_info.get("personality", "neutral")
        mood = "confident" if name == "Cassandra" else "playful" if name == "Ivy" else "soft"
        prompt = f"Create an outfit for {name}, matching their {personality} nature and a {mood} tone."

        img_path = await generate_outfit_image(name, prompt)
        if img_path:
            try:
                channel = bot.get_channel(channel_id)
                if channel:
                    await channel.send(
                        f"👗 **{name}’s outfit of the day** ({season}{' — ' + event if event else ''}):",
                        file=File(img_path),
                    )
                    log_event(f"[OUTFIT] {name} posted {event or season} outfit.")
            except Exception as e:
                log_event(f"[ERROR] Failed to post outfit for {name}: {e}")

    # 🎁 Group photo for events
    if event:
        group_path = await generate_group_image([s.sister_info["name"] for s in sisters])
        if group_path:
            main_bot = next((b for b in sisters if b.sister_info["name"] == "Aria"), sisters[0])
            channel = main_bot.get_channel(channel_id)
            if channel:
                await channel.send(f"📸 **Family {event} Group Photo!** ❤️", file=File(group_path))
                log_event(f"[GROUP] Posted {event} family group image.")

                # 💬 Will’s reaction (shy or confident)
                will_mem = load_will_memory()
                progress = will_mem.get("projects", {}).get("Personal task", {}).get("progress", 0.3)
                timid = progress < 0.5
                comment = (
                    "I didn’t know we were taking a photo today… it turned out nice though."
                    if timid
                    else "We actually look kind of amazing here, huh? Don’t tell Ivy I said that."
                )
                await channel.send(f"🗨️ **Will:** {comment}")
                log_event("[WILL] Added group photo comment.")
