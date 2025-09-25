import re
from io import BytesIO
import discord
from image_gen import text2im  # ✅ your existing image generator

# Trigger categories
TRIGGERS = {
    "outfit": ["outfit", "wearing", "clothes", "dress", "skirt", "jacket", "style", "look like"],
    "activity": ["doing", "exercise", "training", "reading", "gaming", "working", "writing"],
    "setting": ["room", "bedroom", "garden", "desk", "workspace", "kitchen", "scene"],
    "mood": ["vibe", "aesthetic", "feeling", "ambience", "energy"],
}

async def maybe_generate_image_request(sister: str, message: str, history=None):
    """
    Inspect the message for visual triggers. If matched, request image generation.
    Returns a (file, caption) tuple if successful, else None.
    """
    lower_msg = message.lower()
    matched_category = None

    # Check triggers
    for category, keywords in TRIGGERS.items():
        if any(kw in lower_msg for kw in keywords):
            matched_category = category
            break

    if not matched_category:
        return None

    # Prompt building
    context = " ".join(history[-3:]) if history else ""
    prompt = f"{sister}'s {matched_category}. {message}. Context: {context}"

    try:
        imgs = await text2im({
            "prompt": prompt,
            "size": "512x512",
            "n": 1
        })
        if imgs and "data" in imgs and len(imgs["data"]) > 0:
            # Convert to Discord File
            image_bytes = BytesIO(imgs["data"][0]["b64_json"].encode("utf-8"))
            file = discord.File(image_bytes, filename=f"{sister}_{matched_category}.png")
            caption = f"✨ {sister}'s {matched_category}"
            return file, caption
    except Exception as e:
        print(f"[ERROR] Image generation failed: {e}")

    return None
