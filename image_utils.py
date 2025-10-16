# … (imports and earlier sections unchanged)
import json
import random
import datetime
import pytz
import base64
import discord
from openai import OpenAI
from logger import log_event

client = OpenAI()
AEDT = pytz.timezone("Australia/Sydney")

# -------------------------------------------------------------------
# 🧍‍♀️ Outfit cross-awareness memory
# -------------------------------------------------------------------
def log_outfit(name: str, description: str, event: str):
    """Store outfit info for the sibling."""
    memory = load_memory(name)
    entry = {
        "date": str(datetime.datetime.now(AEDT).date()),
        "event": event,
        "description": description,
    }
    memory.setdefault("outfit_log", []).append(entry)
    memory["outfit_log"] = memory["outfit_log"][-30:]
    save_memory(name, memory)

def get_recent_outfit_reference(name: str) -> str | None:
    """Recall past outfit from the same sibling."""
    memory = load_memory(name)
    if not memory.get("outfit_log"):
        return None
    past = random.choice(memory["outfit_log"])
    date = past["date"]
    event = past.get("event", "Normal")
    desc = past.get("description", "")
    if event in ["Christmas", "Halloween", "Valentine's Day"]:
        return f"You wore something similar back around {event.lower()} last time."
    return f"I think you wore that same {desc.split()[0]} a while ago."

def get_cross_reference(name: str, others: list[str]) -> str | None:
    """
    Create a playful or affectionate reference about another sibling's outfit.
    """
    if not others:
        return None
    target = random.choice(others)
    target_mem = load_memory(target)
    if not target_mem.get("outfit_log"):
        return None
    ref = target_mem["outfit_log"][-1]  # yesterday or today’s look
    desc = ref.get("description", "")
    tone = random.choice([
        f"{target}'s look today actually kinda suits them.",
        f"Not gonna lie, {target}'s outfit looked comfy — jealous.",
        f"I saw what {target} wore today… bold choice!",
        f"{target} keeps outdoing us lately with those outfits.",
        f"{target}’s outfit reminds me of one they wore ages ago.",
    ])
    if desc:
        tone += f" ({desc})"
    return tone

# -------------------------------------------------------------------
# 🧵 Outfit generation and posting (expanded)
# -------------------------------------------------------------------
async def generate_and_post_daily_outfits(config: dict, sisters: list):
    event = detect_special_event()
    season = _get_season()

    all_outfits = {}

    # STEP 1: generate and store all images + metadata
    for bot in sisters:
        name = bot.sister_info["name"]
        mood = random.choice(["relaxed", "focused", "playful", "gentle"])
        boldness = random.uniform(0.3, 0.9)
        prompt, base = generate_outfit_prompt(name, mood=mood, boldness=boldness)
        img_data = await generate_image(prompt, base_image_path=base)
        if not img_data:
            continue

        path = _save_temp_image(img_data, name)
        description = f"{mood} mood, {season} season, {event} look"
        log_outfit(name, description, event)
        all_outfits[name] = {"path": path, "description": description}

    # STEP 2: post all outfits, then trigger cross-comments
    for bot in sisters:
        name = bot.sister_info["name"]
        if name not in all_outfits:
            continue

        try:
            channel = bot.get_channel(config["family_group_channel"])
            if not channel:
                continue

            recall = get_recent_outfit_reference(name)
            caption = f"📸 **{name}’s outfit of the day** — {event} ({season.title()})"
            if recall:
                caption += f"\n_{recall}_"

            await channel.send(
                caption,
                file=discord.File(all_outfits[name]["path"], filename=f"{name}_outfit.png")
            )
            log_event(f"[POST] {name} outfit posted.")

        except Exception as e:
            log_event(f"[ERROR] Failed posting outfit for {name}: {e}")

    # STEP 3: have random siblings react to each other
    await asyncio.sleep(random.randint(5, 15))  # short pause so posts appear before chatter
    await trigger_cross_outfit_comments(sisters, config)
    log_event("[POST] Outfit cross-reactions triggered.")

# -------------------------------------------------------------------
# 💬 Outfit reaction chatter
# -------------------------------------------------------------------
async def trigger_cross_outfit_comments(sisters: list, config: dict):
    """
    After outfits are posted, generate 1–3 quick sibling comments referencing each other’s looks.
    """
    speaker_pool = random.sample([s.sister_info["name"] for s in sisters], k=random.randint(1, 3))

    for speaker in speaker_pool:
        others = [n.sister_info["name"] for n in sisters if n.sister_info["name"] != speaker]
        line = get_cross_reference(speaker, others)
        if not line:
            continue

        try:
            for bot in sisters:
                if bot.sister_info["name"] == speaker:
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(f"💬 {line}")
                        log_event(f"[CHAT] {speaker} cross-comment: {line}")
                    break
        except Exception as e:
            log_event(f"[ERROR] Cross outfit comment failed: {e}")
