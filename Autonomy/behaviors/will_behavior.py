import random, asyncio, os, json
from datetime import datetime
from typing import Dict, Optional

from llm import generate_llm_reply
from logger import log_event
from shared_context import (
    recall_or_enrich_prompt,
    remember_after_exchange,
    get_media_reference,
    craft_media_reaction,
)
from messaging_utils import send_human_like_message  # 🔹 new

WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"

WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# how often he unexpectedly "rants" in a soft, excited way
RANT_CHANCE = 0.10

NICKNAMES = {
    "Aria": ["Aria", "Ari"],
    "Selene": ["Selene", "Luna"],
    "Cassandra": ["Cassandra", "Cass", "Cassie"],
    "Ivy": ["Ivy", "Vy"],
    "Will": ["Will", "Willow"],
}

def _pick_name(t: str) -> str:
    ns = NICKNAMES.get(t, [t])
    return random.choice(ns) if random.random() < 0.35 else t

# ---------- JSON helpers ----------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Will JSON read failed {path}: {e}")
    return default

def load_will_profile() -> Dict:
    p = _load_json(WILL_PERSONALITY_JSON, {})
    p.setdefault("style", ["timid", "reflective", "sometimes playful"])
    p.setdefault(
        "core_personality",
        "Shy, creative, observant; warm once comfortable.",
    )
    return p

# ---------- Schedule ----------
def assign_will_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "will_schedule"
    kd  = f"{key}_date"

    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get(
        "Will",
        {"wake": [10, 12], "sleep": [0, 2]},
    )

    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        if hi < lo:
            lo, hi = hi, lo
        return random.randint(lo, hi)

    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule
    state[kd]  = today
    return schedule

def _hr_in(h: int, w: int, s: int) -> bool:
    if w == s:
        return True
    if w < s:
        return w <= h < s
    return h >= w or h < s

def is_will_online(state: Dict, config: Dict) -> bool:
    sc = assign_will_schedule(state, config)
    return _hr_in(datetime.now().hour, sc["wake"], sc["sleep"])

# ---------- Persona reply ----------
async def _persona_reply(
    base_prompt: str,
    timid: bool = True,
    address_to: Optional[str] = None,
    rant: bool = False,
) -> str:
    """
    Builds Will's voice: shy, warm, a little hesitant, sometimes trailing
    into a tiny excited tangent. Much softer and more human now.
    """
    p = load_will_profile()
    style = ", ".join(p.get("style", ["timid", "reflective"]))
    personality = p.get("core_personality", "Shy, creative, observant.")

    who = _pick_name(address_to) if address_to else None
    prefix = f"Speak directly to {who} by name once. " if who else ""

    # Decide how long Will talks
    if rant:
        length_hint = (
            "Let yourself get softly excited for a moment — 3–5 sentences — "
            "but keep the shy tone, like you're rambling without meaning to."
        )
    else:
        length_mode = random.choices(
            ["tiny", "short", "medium"],
            weights=[0.5, 0.35, 0.15],
        )[0]

        if length_mode == "tiny":
            length_hint = "Keep this very short — just 1–2 soft, hesitant sentences."
        elif length_mode == "short":
            length_hint = "Reply in about 2–3 warm, gentle sentences."
        else:
            length_hint = (
                "Let yourself speak a little more — 3–4 sentences — still quiet and earnest."
            )

    tone = (
        "hesitant, quiet, warm"
        if timid
        else "more animated but still gentle and self-conscious"
    )

    prompt = (
        f"You are Will. Personality: {personality}. "
        f"Your style is {style} — soft, hesitant, reflective, sometimes lightly playful. "
        f"{prefix}"
        "Always speak in the first person. Never refer to yourself in the third person. "
        "Write like a shy young man talking in a Discord group chat: short lines, soft punctuation, "
        "gentle enthusiasm, little pauses, but not rambling incoherently. "
        "Avoid corporate tone. Avoid over-explaining. "
        f"Your tone here should be {tone}. "
        f"{length_hint} "
        f"Now respond based on this instruction/context: {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Will",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------- Background chatter ----------
async def will_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("will_chatter_started"):
        return
    state["will_chatter_started"] = True

    while True:
        if is_will_online(state, config):
            if random.random() < 0.10:
                base_ctx, mem = recall_or_enrich_prompt(
                    "Will",
                    "Share one tiny gentle note, a soft creative thought, or a quiet observation.",
                    ["art", "game", "coffee", "light", "anime", "sketch"],
                )

                rant = random.random() < RANT_CHANCE

                base_prompt = (
                    "Say one small, simple, quiet thought in the family group chat. "
                    "It should feel like you're speaking up softly from the corner — "
                    "not announcing yourself. Just a warm, shy little note."
                )
                if base_ctx:
                    base_prompt += f" You can let this context gently influence your wording: {base_ctx}"

                msg = await _persona_reply(base_prompt, timid=(not rant), rant=rant)

                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Will" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await send_human_like_message(ch, msg, speaker_name="Will")
                                log_event(f"[CHATTER] Will: {msg}")
                                if mem:
                                    remember_after_exchange(
                                        "Will",
                                        f"Chatted: {mem.get('summary', 'tiny creative note')}",
                                        tone="warm",
                                        tags=["chatter"],
                                    )
                                break

        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

# ---------- Cooldown ----------
def _cool_ok(state: Dict, channel_id: int) -> bool:
    cd = state.setdefault("cooldowns", {}).setdefault("Will", {})
    last = cd.get(channel_id, 0)
    now = datetime.now().timestamp()
    if now - last < 120:
        return False
    cd[channel_id] = now
    return True

# ---------- Reactive handler ----------
async def will_handle_message(
    state: Dict,
    config: Dict,
    sisters,
    author: str,
    content: str,
    channel_id: int,
) -> bool:
    if not is_will_online(state, config):
        return False
    if not _cool_ok(state, channel_id):
        return False

    rot = state.get("rotation", {"lead": None, "supports": [], "rest": None})
    chance = 0.20
    if rot.get("lead") == "Will":
        chance = 0.70
    elif "Will" in rot.get("supports", []):
        chance = 0.45
    elif rot.get("rest") == "Will":
        chance = 0.25

    lower = content.lower()
    if "will" in lower or "willow" in lower:
        chance = 1.0

    inject = None
    if any(k in lower for k in ["anime", "game", "show", "music", "cosplay", "art", "photo", "coffee"]):
        m = get_media_reference(
            "Will",
            mood_tags=["anime", "jrpg", "indie", "nintendo"],
        )
        if m:
            inject = craft_media_reaction("Will", m)

    if random.random() > chance:
        return False

    addressed = author
    rant = random.random() < RANT_CHANCE

    base_ctx, mem = recall_or_enrich_prompt(
        "Will",
        content,
        ["family_chat", "recent", "comfort", "gentle_topics"],
    )

    base = (
        f'Respond softly to {addressed} about: "{content}". '
        "Be sincere, warm, and a little hesitant. Not formal, not overconfident — "
        "just honest and gentle."
    )
    if base_ctx:
        base += f" You may let this context quietly inform your reply: {base_ctx}."
    if inject:
        base += f" If it fits naturally, you can also include: {inject}"

    msg = await _persona_reply(
        base,
        timid=(not rant),
        rant=rant,
        address_to=addressed,
    )
    if not msg:
        return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Will":
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await send_human_like_message(ch, msg, speaker_name="Will")
                log_event(f"[REPLY] Will → {addressed}: {msg}")

                remember_after_exchange(
                    "Will",
                    f"Replied to {addressed}",
                    tone="warm",
                    tags=["reply"],
                )

                if mem:
                    remember_after_exchange(
                        "Will",
                        mem.get("summary", "Context used while replying"),
                        tone="soft",
                        tags=["context", "reply"],
                    )
                return True

    return False

# ---------- Startup ----------
def ensure_will_systems(state: Dict, config: Dict, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
