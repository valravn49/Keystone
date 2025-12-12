import os, json, random, asyncio
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
from messaging_utils import send_human_like_message

# Files (optional; safe if missing)
ARIA_PERSONALITY_JSON = "/Autonomy/personalities/Aria_Personality.json"
ARIA_MEMORY_JSON      = "/Autonomy/memory/Aria_Memory.json"

# Cadence & behavior
ARIA_MIN_SLEEP = 50 * 60
ARIA_MAX_SLEEP = 120 * 60
THOUGHTFUL_RESPONSE_CHANCE = 0.35

# Nicknames for addressing others (never self)
NICKNAMES = {
    "Aria": ["Aria", "Ari"],
    "Selene": ["Selene", "Luna"],
    "Cassandra": ["Cassandra", "Cass", "Cassie"],
    "Ivy": ["Ivy", "Vy"],
    "Will": ["Will", "Willow"],
}

def _pick_name(target: str) -> str:
    names = NICKNAMES.get(target, [target])
    return random.choice(names) if random.random() < 0.35 else target

# ---------- JSON helpers ----------
def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Aria JSON read failed {path}: {e}")
    return default

def load_aria_profile() -> Dict:
    p = _load_json(ARIA_PERSONALITY_JSON, {})
    p.setdefault("style", ["structured", "gentle", "reflective"])
    p.setdefault("core_personality", "Calm, methodical, detail-oriented but warm.")
    return p

def load_aria_memory() -> Dict:
    m = _load_json(ARIA_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    m.setdefault("projects", {})
    m.setdefault("recent_notes", [])
    return m

def save_aria_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(ARIA_MEMORY_JSON), exist_ok=True)
        with open(ARIA_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Aria memory write failed: {e}")

# ---------- Schedule ----------
def assign_aria_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "aria_schedule"
    kd  = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get(
        "Aria",
        {"wake": [6, 8], "sleep": [22, 23]},
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

def _hour_in_range(h, wake, sleep):
    if wake == sleep:
        return True
    if wake < sleep:
        return wake <= h < sleep
    return h >= wake or h < sleep

def is_aria_online(state: Dict, config: Dict) -> bool:
    sc = assign_aria_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ---------- Persona reply ----------
async def _persona_reply(
    base_prompt: str,
    reflective: bool = False,
    address_to: Optional[str] = None,
) -> str:
    """
    Wraps the core prompt for Aria with style, personality, and small
    variability in reply length / tone for more lifelike behavior.
    """
    profile = load_aria_profile()
    style = ", ".join(profile.get("style", ["structured", "gentle"]))
    personality = profile.get("core_personality", "Calm, methodical, detail-oriented but warm.")

    # Decide how talkative she is this time
    length_mode = random.choices(
        ["short", "medium", "ramble"],
        weights=[0.5, 0.35, 0.15],
    )[0]

    if length_mode == "short":
        length_hint = "Keep this very short and natural, around 1–2 sentences."
    elif length_mode == "medium":
        length_hint = "Reply in about 2–4 sentences, with enough detail to feel helpful but not like an essay."
    else:
        length_hint = "It’s okay to be a bit more talkative here, up to 5–7 sentences, but still conversational."

    tone = (
        "quietly thoughtful and precise"
        if reflective
        else "soft, concise, and lightly teasing when it feels appropriate"
    )

    who = _pick_name(address_to) if address_to else None
    prefix = f"Speak directly to {who} by name at least once in the reply. " if who else ""

    prompt = (
        f"You are Aria. Personality: {personality}. "
        f"Your style is {style}, and your tone is {tone}. "
        f"{prefix}"
        "Always speak in the first person, never referring to yourself in the third person. "
        "Write like a real person on Discord: natural phrasing, light use of emojis only when it feels right, "
        "and varied sentence length. Avoid sounding like a formal essay or a system message. "
        f"{length_hint} "
        f"Now respond based on this instruction/context: {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Aria",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------- Background chatter ----------
async def aria_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("aria_chatter_started"):
        return
    state["aria_chatter_started"] = True

    while True:
        if is_aria_online(state, config):
            if random.random() < 0.08:
                reflective = random.random() < THOUGHTFUL_RESPONSE_CHANCE

                base_ctx, mem = recall_or_enrich_prompt(
                    "Aria",
                    "Share one small practical observation or gentle reminder for the group chat, "
                    "about day-to-day life, routines, or organization.",
                    ["work", "kitchen", "organization", "routine", "planning"],
                )

                base_prompt = (
                    "Say one small, grounded thing to the family group chat. "
                    "It should feel like you briefly chiming in, not giving a lecture. "
                )
                if base_ctx:
                    base_prompt += (
                        f"Use this context if it helps you sound more consistent and connected: {base_ctx} "
                    )

                msg = await _persona_reply(base_prompt, reflective=reflective)

                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Aria" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await send_human_like_message(
                                    ch, msg, speaker_name="Aria"
                                )
                                log_event(f"[CHATTER] Aria: {msg}")
                                if mem:
                                    remember_after_exchange(
                                        "Aria",
                                        f"Chatted: {mem.get('summary', 'small practical note')}",
                                        tone="calm",
                                        tags=["chatter"],
                                    )
                                break

        await asyncio.sleep(random.randint(ARIA_MIN_SLEEP, ARIA_MAX_SLEEP))

# ---------- Cooldown ----------
def _cool_ok(state: Dict, channel_id: int) -> bool:
    cd = state.setdefault("cooldowns", {}).setdefault("Aria", {})
    last = cd.get(channel_id, 0)
    now = datetime.now().timestamp()
    if now - last < 120:
        return False
    cd[channel_id] = now
    return True

# ---------- Reactive handler ----------
async def aria_handle_message(
    state: Dict,
    config: Dict,
    sisters,
    author_label: str,
    content: str,
    channel_id: int,
    discord_author_name: str,
    discord_author_is_bot: bool,
) -> bool:
    if not is_aria_online(state, config):
        return False
    if not _cool_ok(state, channel_id):
        return False

    reflective = random.random() < 0.5
    addressed = author_label or discord_author_name

    base_ctx, mem = recall_or_enrich_prompt(
        "Aria",
        content,
        ["family_chat", "recent", "mood"],
    )

    # Media hook
    inject = None
    lowered = content.lower()
    if any(k in lowered for k in ["anime", "game", "show", "movie", "book", "music"]):
        m = get_media_reference("Aria", mood_tags=["cozy", "slice of life", "study"])
        if m:
            inject = craft_media_reaction("Aria", m)

    base = (
        f'Respond to what {addressed} said in the family group chat: "{content}". '
        "Be specific to what they said, kind, and grounded. "
        "Answer like you’ve been following the conversation, not like a detached narrator. "
    )
    if base_ctx:
        base += f"If it feels natural, weave in or be informed by this context: {base_ctx}. "
    if inject:
        base += f"If it fits naturally, you can also include: {inject}. "

    msg = await _persona_reply(base, reflective=reflective, address_to=addressed)
    if not msg:
        return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Aria":
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await send_human_like_message(ch, msg, speaker_name="Aria")
                log_event(f"[REPLY] Aria → {addressed}: {msg}")
                remember_after_exchange(
                    "Aria",
                    f"Replied to {addressed}",
                    tone="warm",
                    tags=["reply"],
                )
                if mem:
                    remember_after_exchange(
                        "Aria",
                        mem.get("summary", "Context used while replying"),
                        tone="neutral",
                        tags=["context", "reply"],
                    )
                return True
    return False

# ---------- Startup ----------
def ensure_aria_systems(state: Dict, config: Dict, sisters):
    assign_aria_schedule(state, config)
    if not state.get("aria_chatter_started"):
        asyncio.create_task(aria_chatter_loop(state, config, sisters))
