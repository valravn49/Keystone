import os
import random
from logger import log_event

# Optional import: only if your system already uses OpenAI or other image generation backends.
try:
    from image_gen import text2im
except ImportError:
    text2im = None

# ---------------------------------------------------------------------
# Outfit generation control
# ---------------------------------------------------------------------

def _portrait_path(name: str) -> str:
    """Return each sibling's portrait path."""
    portraits = {
        "Aria": "/Autonomy/portraits/Aria_Portrait.png",
        "Selene": "/Autonomy/portraits/Selene_Portrait.png",
        "Cassandra": "/Autonomy/portraits/Cassandra_Portrait.png",
        "Ivy": "/Autonomy/portraits/Ivy_Portrait.png",
        "Will_masc": "/Autonomy/portraits/Will_Portrait_Masc.png",
        "Will_fem": "/Autonomy/portraits/Will_Portrait_Fem.png",
    }
    return portraits.get(name)

def _get_seasonal_descriptor() -> str:
    """Return short outfit bias depending on month (AEDT)."""
    import datetime, pytz
    now = datetime.datetime.now(pytz.timezone("Australia/Sydney"))
    m = now.month
    if m in (12, 1, 2):
        return "summer, light fabrics, bright colors"
    elif m in (3, 4, 5):
        return "autumn, cozy but breathable layers"
    elif m in (6, 7, 8):
        return "winter, warm layers, coats, boots"
    else:
        return "spring, soft tones, airy clothing"

def _outfit_prompt(name: str, season: str) -> str:
    """Generate outfit description prompt fitting personality."""
    style_prompts = {
        "Aria": f"Aria in {season} — neat, minimalist academic look, structured blouse or sweater, subtle tones.",
        "Selene": f"Selene in {season} — cozy maternal look, soft cardigan, pastel skirt or loungewear.",
        "Cassandra": f"Cassandra in {season} — disciplined and sharp look, business-casual, boots or jacket.",
        "Ivy": f"Ivy in {season} — playful look, layered streetwear or cute outfit, maybe mismatched accessories.",
        "Will_masc": f"Will in {season} — shy, casual masculine outfit; hoodie or graphic tee, sneakers, relaxed jeans.",
        "Will_fem": f"Will in {season} — timid but expressive feminine outfit; skirt, soft sweater, light accessories.",
    }
    return style_prompts.get(name, f"Generic outfit for {name} in {season}.")

async def generate_daily_outfit_images(state, sisters):
    """Generate one outfit image per sibling (once per day)."""
    if text2im is None:
        log_event("[WARN] image_gen backend not available — skipping outfit generation.")
        return

    from datetime import datetime
    today = datetime.now().date()
    if state.get("outfit_date") == today:
        log_event("[INFO] Outfits already generated today.")
        return

    state["outfit_date"] = today
    season = _get_seasonal_descriptor()

    for bot in sisters:
        name = bot.sister_info["name"]
        base_img = _portrait_path(name)

        # Will special case: use masc or fem depending on state
        if name == "Will":
            will_mode = random.choices(["masc", "fem"], weights=[0.7, 0.3])[0]
            base_img = _portrait_path(f"Will_{will_mode}")
            name = f"Will_{will_mode}"

        prompt = _outfit_prompt(name, season)
        try:
            log_event(f"[IMAGE] Generating outfit for {name}: {prompt}")
            result = await text2im(
                prompt=prompt,
                referenced_image_ids=[base_img] if base_img else [],
                size="1024x1024",
            )
            log_event(f"[IMAGE] Outfit generated for {name}")
        except Exception as e:
            log_event(f"[ERROR] Outfit generation failed for {name}: {e}")

    log_event("[SYSTEM] Daily outfit generation complete.")
