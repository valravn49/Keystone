import os
import io
import random
import base64
from datetime import datetime
from openai import OpenAI
import pytz

import discord
from logger import log_event

# -------------------------------------------------------------------
# OpenAI Client
# -------------------------------------------------------------------
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# AEDT timezone
AEDT = pytz.timezone("Australia/Sydney")

# -------------------------------------------------------------------
# Base portrait paths (update if your structure changes)
# -------------------------------------------------------------------
BASE_PORTRAITS = {
    "Aria": "/Autonomy/assets/portraits/aria_base.png",
    "Selene": "/Autonomy/assets/portraits/selene_base.png",
    "Cassandra": "/Autonomy/assets/portraits/cass_base.png",
    "Ivy": "/Autonomy/assets/portraits/ivy_base.png",
    "Will_masc": "/Autonomy/assets/portraits/will_masc.png",
    "Will_fem": "/Autonomy/assets/portraits/will_fem.png",
}

# -------------------------------------------------------------------
# Outfit style presets
# -------------------------------------------------------------------
STYLE_PRESETS = {
    "Aria": [
        "structured casual with soft neutrals and tidy layers",
        "academic autumn look — cardigan, skirt, and tidy notes nearby",
        "soft minimalist outfit with a neat ponytail",
    ],
    "Selene": [
        "cozy sweater and flowing skirt, warm earthy tones",
        "homely aesthetic with an apron and mug of tea",
        "soft nightwear and candlelight mood",
    ],
    "Cassandra": [
        "sharp blazer and athletic wear mix, confident stance",
        "gym outfit, calm but disciplined energy",
        "tailored clothing, hair pinned neatly",
    ],
    "Ivy": [
        "playful streetwear with layered accessories",
        "casual pastel outfit with rebellious flair",
        "punk-meets-cute with mismatched textures",
    ],
    "Will_masc": [
        "relaxed hoodie and jeans, shy but composed",
        "minimalist techwear, hands in pockets",
        "quiet urban casual, looking thoughtful",
    ],
    "Will_fem": [
        "feminine tech-core outfit — cropped jacket, soft makeup",
        "cozy pastel look with headset and light eyeliner",
        "androgynous streetwear with delicate accessories",
    ],
}

# -------------------------------------------------------------------
# Seasonal & Event Modifiers
# -------------------------------------------------------------------
SEASONAL_MODS = {
    1: "light summer wear, airy colors, sunlight tone",
    2: "late summer transitioning to autumn hues",
    3: "cozy fall layers, earthy palette",
    4: "festive winter holiday theme — subtle decorations",
    5: "spring renewal look with soft greens and whites",
    6: "warm early winter tones, scarf or jacket",
    7: "sunny summer casual vibe",
    8: "breezy late summer tones",
    9: "autumnal balance — cardigan or layered outfit",
    10: "Halloween aesthetic — themed accessory or hint of costume",
    11: "late spring mix of comfort and warmth",
    12: "Christmas theme — subtle reds, greens, and cozy decor",
}

# -------------------------------------------------------------------
# Outfit generation
# -------------------------------------------------------------------
async def generate_and_post_outfits(sisters, config):
    """Generate and post each sibling's outfit image for the day."""
    now = datetime.now(AEDT)
    month = now.month
    today_str = now.strftime("%Y-%m-%d")

    for bot in sisters:
        sname = bot.sister_info["name"]
        if not bot.is_ready():
            continue

        # Determine base portrait and style
        if sname == "Will":
            # Choose masc or fem depending on Will's mood probability
            will_mode = random.choice(["masc", "fem"]) if random.random() > 0.7 else "masc"
            base_image_path = BASE_PORTRAITS.get(f"Will_{will_mode}")
            style_choice = random.choice(STYLE_PRESETS.get(f"Will_{will_mode}", []))
        else:
            base_image_path = BASE_PORTRAITS.get(sname)
            style_choice = random.choice(STYLE_PRESETS.get(sname, []))

        seasonal_modifier = SEASONAL_MODS.get(month, "")
        event_text = ""
        if month == 10:
            event_text = "with a Halloween-inspired accessory or tone"
        elif month == 12:
            event_text = "with subtle Christmas or festive styling"

        # Compose image generation prompt
        outfit_prompt = (
            f"{sname} wearing {style_choice}, {seasonal_modifier}, {event_text}. "
            f"Keep the face and art style consistent with their portrait. "
            f"Lighting should match a realistic indoor environment. "
            f"Maintain aesthetic continuity — same person, same mood, but daily outfit variation."
        )

        try:
            with open(base_image_path, "rb") as f:
                base_bytes = f.read()

            response = client.images.generate(
                model="gpt-image-3",
                prompt=outfit_prompt,
                image=base_bytes,
                size="1024x1024",
            )

            # Decode the generated image
            image_base64 = response.data[0].b64_json
            image_bytes = base64.b64decode(image_base64)

            file_name = f"{sname}_{today_str}.png"
            file_path = f"/Autonomy/daily_outfits/{file_name}"

            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(image_bytes)

            # Post to Discord
            channel = bot.get_channel(config["family_group_channel"])
            if channel:
                file = discord.File(file_path, filename=file_name)
                await channel.send(
                    f"👗 **{sname}’s outfit for {today_str}:**", file=file
                )
                log_event(f"[OUTFIT] {sname} outfit generated and posted.")

        except Exception as e:
            log_event(f"[ERROR] Outfit generation failed for {sname}: {e}")
