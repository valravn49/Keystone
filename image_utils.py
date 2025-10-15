"""
image_utils.py
----------------
Handles outfit and seasonal image generation for the sibling bots.
Uses OpenAI's DALL-E API if available; otherwise falls back to logging mode.
"""

import os
import random
import datetime
from logger import log_event

try:
    # ✅ Real image generation (requires OPENAI_API_KEY)
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def text2im(prompt: str, size: str = "1024x1024"):
        """Generate an image via OpenAI DALL-E 3."""
        try:
            image = client.images.generate(model="gpt-image-1", prompt=prompt, size=size)
            return image.data[0].url
        except Exception as e:
            log_event(f"[WARN] Image generation failed — falling back to log only: {e}")
            return None

except Exception as e:
    # ✅ Safe fallback if OpenAI not installed or key missing
    log_event(f"[INIT] OpenAI image client unavailable: {e}")

    def text2im(prompt: str, size: str = "1024x1024"):
        """Fallback: no real generation."""
        log_event(f"[FAKE IMAGE] Would have generated: {prompt}")
        return None


# ---------------------------------------------------------------------------
# Outfit generation logic
# ---------------------------------------------------------------------------

SEASONAL_THEMES = {
    12: "Christmas or festive cozy outfits with reds, greens, and soft layers",
    10: "Halloween or autumn styles — warm tones, cozy sweaters, maybe costumes",
    2: "Late-summer or back-to-school energy — lighter layers and soft colors",
    6: "Winter in Australia — coats, scarves, practical layers",
}

def _seasonal_prompt_addition():
    month = datetime.datetime.now().month
    return SEASONAL_THEMES.get(month, "Casual everyday seasonal style appropriate to the month")


def generate_outfit_prompt(name: str, personality: str, boldness: float = 0.5) -> str:
    """
    Builds a descriptive outfit prompt based on the sibling’s personality and current tone.
    """
    tone_descriptions = {
        "Aria": "soft structured fashion with calm academic tones",
        "Selene": "comfort-focused outfits with flowy fabrics and soft color palettes",
        "Cassandra": "disciplined, elegant minimalism — practical but polished",
        "Ivy": "bratty playful streetwear or cute chaos energy",
        "Will_masc": "casual nerdy fit — hoodies, jeans, sneakers",
        "Will_fem": "feminine androgynous outfits — skirts, light accessories, confidence under shyness",
    }

    base = tone_descriptions.get(name, "balanced casual outfit")
    season = _seasonal_prompt_addition()

    style = "bold expressive colors" if boldness > 0.7 else "subtle coordinated tones"
    return (
        f"{name}'s outfit today — {base}, {style}. "
        f"Set in a bright soft-light background, clean framing. "
        f"Include {season} influences."
    )


async def generate_and_post_daily_outfits(sisters, config, state):
    """
    Generates daily outfits for each sibling (and Will’s masc/fem variation).
    Each image is sent to Discord and logged.
    """

    try:
        for bot in sisters:
            sname = bot.sister_info["name"]

            # Boldness tweaks (influences color & style)
            boldness = random.uniform(0.3, 0.9)

            # Will has masc/fem split
            if sname == "Will":
                mode = "Will_fem" if random.random() > 0.7 else "Will_masc"
                prompt = generate_outfit_prompt(mode, "shy-nerdy but expressive", boldness)
            else:
                prompt = generate_outfit_prompt(sname, bot.sister_info.get("personality", ""), boldness)

            img_url = text2im(prompt)

            if img_url:
                try:
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(f"🧵 **{sname}’s outfit of the day**\n{img_url}")
                        log_event(f"[OUTFIT] {sname} outfit generated: {img_url}")
                except Exception as e:
                    log_event(f"[ERROR] Could not post outfit image for {sname}: {e}")
            else:
                log_event(f"[OUTFIT LOG] {sname}: {prompt}")

        state["last_outfit_update"] = datetime.datetime.now().isoformat()

    except Exception as e:
        log_event(f"[ERROR] Daily outfit generation failed: {e}")
