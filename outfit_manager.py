# outfit_manager.py
import random
import datetime
from logger import log_event
from image_gen import text2im  # your internal image generator

# ---------------- Season Detection ----------------
def get_current_season() -> str:
    """Returns the current season based on month (southern hemisphere aware)."""
    month = datetime.datetime.now().month
    # Assuming user in Australia → Southern Hemisphere logic
    if month in [12, 1, 2]:
        return "summer"
    elif month in [3, 4, 5]:
        return "autumn"
    elif month in [6, 7, 8]:
        return "winter"
    else:
        return "spring"


# ---------------- Outfit Triggers ----------------
OUTFIT_KEYWORDS = [
    "outfit", "clothes", "wearing", "dress", "hoodie", "skirt", "shirt", "jeans", "coat",
    "jacket", "layer", "change", "cold", "hot", "warm", "style", "fashion", "comfy", "look"
]

# Who can generate outfit posts (Selene primary, others if mentioned)
POST_PRIORITY = ["Selene", "Ivy", "Aria", "Cassandra"]


# ---------------- Style Descriptions ----------------
STYLE_DESCRIPTIONS = {
    "Aria": lambda season, mood: f"neat and structured {season} outfit — soft fabrics and tidy layering",
    "Selene": lambda season, mood: f"elegant but practical {season} look — light fabrics with gentle colour harmony",
    "Cassandra": lambda season, mood: f"athletic {season} gear — ready for training or work, a little no-nonsense",
    "Ivy": lambda season, mood: f"playful {season} outfit — something cute or teasing, not too serious",
    "Will_masc": lambda season, mood: f"casual {season} look — simple layers, masculine comfort, slight nerd aesthetic",
    "Will_fem": lambda season, mood: f"soft {season} outfit — subtle feminine touches, maybe pastel hoodie or skirt"
}


# ---------------- Mood Adjectives ----------------
MOOD_WORDS = {
    "happy": ["bright", "vibrant", "playful"],
    "tired": ["cozy", "slouchy", "relaxed"],
    "focused": ["clean", "simple", "functional"],
    "anxious": ["muted", "neutral", "gentle"],
    "confident": ["bold", "layered", "expressive"],
}


# ---------------- Outfit Builder ----------------
def build_outfit_prompt(name: str, mood: str, feeling_bold: bool = False) -> str:
    """Constructs an outfit prompt tailored to the sibling and mood."""
    season = get_current_season()
    style_key = "Will_fem" if name == "Will" and feeling_bold else \
                "Will_masc" if name == "Will" else name

    style_desc_func = STYLE_DESCRIPTIONS.get(style_key, lambda s, m: f"default {s} outfit")
    style_desc = style_desc_func(season, mood)
    mood_desc = random.choice(MOOD_WORDS.get(mood, ["balanced"]))

    return f"{name}'s {season} outfit, {mood_desc} mood, {style_desc} reflecting personality."


# ---------------- Outfit Trigger Check ----------------
def should_generate_outfit(message: str) -> bool:
    """Check if a message should trigger outfit generation."""
    text = message.lower()
    return any(word in text for word in OUTFIT_KEYWORDS)


# ---------------- Main Image Generator ----------------
async def maybe_generate_outfit_image(speaker: str, message: str, sisters, config, state):
    """
    Called after a message is posted to check for clothing references.
    If triggered, generates an outfit image based on context and speaker mood.
    """
    if not should_generate_outfit(message):
        return

    log_event(f"[OUTFIT_TRIGGER] {speaker} mentioned clothing: {message}")

    # Determine who posts — Selene by default, unless she’s asleep
    poster_name = None
    for candidate in POST_PRIORITY:
        if any(bot.sister_info["name"] == candidate and bot.is_ready() for bot in sisters):
            poster_name = candidate
            break
    if not poster_name:
        return

    # Get speaker's mood from state (fallback random)
    current_mood = state.get(f"{speaker}_mood", random.choice(list(MOOD_WORDS.keys())))
    feeling_bold = state.get(f"{speaker}_confidence", 0.5) > 0.7

    # Build prompt
    prompt = build_outfit_prompt(speaker, current_mood, feeling_bold)
    referenced_image = f"data/{speaker}_Portrait.png"

    log_event(f"[OUTFIT_GEN] {poster_name} generating outfit for {speaker}: {prompt}")

    try:
        image = text2im(
            prompt=prompt,
            referenced_image_ids=[referenced_image],
            size="1024x1024",
            n=1
        )
        if image:
            for bot in sisters:
                if bot.sister_info["name"] == poster_name and bot.is_ready():
                    channel = bot.get_channel(config["family_group_channel"])
                    if channel:
                        await channel.send(
                            f"{speaker}'s outfit for today, {get_current_season()} mood.",
                            file=image
                        )
                        log_event(f"[OUTFIT_POST] {poster_name} posted {speaker}'s outfit image.")
                    break
    except Exception as e:
        log_event(f"[ERROR] outfit generation failed for {speaker}: {e}")
