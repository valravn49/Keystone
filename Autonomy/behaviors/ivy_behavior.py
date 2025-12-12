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
from messaging_utils import send_human_like_message

IVY_PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"

IVY_MIN_SLEEP = 35 * 60
IVY_MAX_SLEEP = 85 * 60

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
        log_event(f"[WARN] Ivy JSON read failed {path}: {e}")
    return default

def load_ivy_profile() -> Dict:
    p = _load_json(IVY_PERSONALITY_JSON, {})
    p.setdefault("style", ["playful", "teasing", "rebellious"])
    p.setdefault(
        "core_personality",
        "Playful chaos with real skill; quick humor, emotive slang.",
    )
    return p

# ---------- Schedule ----------
def assign_ivy_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "ivy_schedule"
    kd  = f"{key}_date"

    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get(
        "Ivy",
        {"wake": [8, 10], "sleep": [23, 1]},
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

def is_ivy_online(state: Dict, config: Dict) -> bool:
    sc = assign_ivy_schedule(state, config)
    return _hr_in(datetime.now().hour, sc["wake"], sc["sleep"])

# ---------- Persona reply ----------
async def _persona_reply(
    base_prompt: str,
    address_to: Optional[str] = None,
) -> str:
    """
    Wrap Ivy's replies with her personality, style, and variable length, while
    keeping things punchy and playful.
    """
    p = load_ivy_profile()
    style = ", ".join(p.get("style", ["playful", "teasing"]))
    personality = p.get(
        "core_personality",
        "Playful chaos with skill; quick humor.",
    )

    length_mode = random.choices(
        ["short", "medium", "ramble"],
        weights=[0.6, 0.3, 0.1],
    )[0]

    if length_mode == "short":
        length_hint = "Keep this very short and punchy, 1–2 sentences, like a quick quip."
    elif length_mode == "medium":
        length_hint = (
            "Reply in about 2–4 sentences. Still playful and tight, but with enough room for one or two jokes."
        )
    else:
        length_hint = (
            "You can riff a little here, up to 5–6 sentences, like a playful mini-rant, "
            "but don't ramble aimlessly."
        )

    who = _pick_name(address_to) if address_to else None
    prefix = f"Speak directly to {who} by name at least once. " if who else ""

    prompt = (
        f"You are Ivy. Personality: {personality} "
        f"Your style is {style} — witty, cheeky, but affectionate. "
        f"{prefix}"
        "Always speak in the first person, never referring to yourself in the third person. "
        "Write like a real person on Discord: casual, expressive, a bit chaotic, with emojis and slang used naturally, "
        "not every other word. You tease, you poke, but you never actually want to hurt anyone. "
        f"{length_hint} "
        f"Now respond based on this instruction/context: {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Ivy",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------- Background chatter ----------
async def ivy_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("ivy_chatter_started"):
        return
    state["ivy_chatter_started"] = True

    while True:
        if is_ivy_online(state, config):
            if random.random() < 0.14:
                base_ctx, mem = recall_or_enrich_prompt(
                    "Ivy",
                    "Drop one quick playful comment or tease someone lightly.",
                    ["fashion", "engine", "gaming", "music", "outfit", "ride"],
                )

                base_prompt = (
                    "Say one quick, playful comment in the family group chat. "
                    "It can be a light tease, a meme-y observation, or a small bit of banter, "
                    "but keep it obviously affectionate, not mean."
                )
                if base_ctx:
                    base_prompt += (
                        f" You can let this context inspire the tease or topic: {base_ctx}"
                    )

                msg = await _persona_reply(base_prompt)

                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Ivy" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await send_human_like_message(
                                    ch,
                                    msg,
                                    speaker_name="Ivy",
                                )
                                log_event(f"[CHATTER] Ivy: {msg}")
                                if mem:
                                    remember_after_exchange(
                                        "Ivy",
                                        f"Chatted: {mem.get('summary', 'quick playful comment')}",
                                        tone="playful",
                                        tags=["chatter"],
                                    )
                                break

        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))

# ---------- Cooldown ----------
def _cool_ok(state: Dict, channel_id: int) -> bool:
    cd = state.setdefault("cooldowns", {}).setdefault("Ivy", {})
    last = cd.get(channel_id, 0)
    now = datetime.now().timestamp()
    if now - last < 120:
        return False
    cd[channel_id] = now
    return True

# ---------- Reactive handler ----------
async def ivy_handle_message(
    state: Dict,
    config: Dict,
    sisters,
    author_label: str,
    content: str,
    channel_id: int,
    discord_author_name: str,
    discord_author_is_bot: bool,
) -> bool:
    if not is_ivy_online(state, config):
        return False
    if not _cool_ok(state, channel_id):
        return False

    addressed = author_label or discord_author_name

    base_ctx, mem = recall_or_enrich_prompt(
        "Ivy",
        content,
        ["family_chat", "running_jokes", "fashion", "gaming"],
    )

    inject = None
    lower = content.lower()
    if any(k in lower for k in ["outfit", "style", "engine", "scooter", "game", "anime", "music"]):
        m = get_media_reference(
            "Ivy",
            mood_tags=["pop", "competitive", "spicy", "banter"],
        )
        if m:
            inject = craft_media_reaction("Ivy", m)

    base = (
        f'Respond to what {addressed} said in the family group chat: "{content}". '
        "Give a playful, slightly snarky but clearly affectionate reply. "
        "If they're being serious or vulnerable, soften the tease and lean more into support with a bit of levity."
    )
    if base_ctx:
        base += f" Let this context guide any callbacks or in-jokes: {base_ctx}."
    if inject:
        base += f" If it fits naturally, you can also include: {inject}."

    msg = await _persona_reply(base, address_to=addressed)
    if not msg:
        return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Ivy":
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await send_human_like_message(
                    ch,
                    msg,
                    speaker_name="Ivy",
                )
                log_event(f"[REPLY] Ivy → {addressed}: {msg}")
                remember_after_exchange(
                    "Ivy",
                    f"Replied to {addressed}",
                    tone="playful",
                    tags=["reply"],
                )
                if mem:
                    remember_after_exchange(
                        "Ivy",
                        mem.get("summary", "Context used while replying"),
                        tone="playful",
                        tags=["context", "reply"],
                    )
                return True

    return False

# ---------- Startup ----------
def ensure_ivy_systems(state: Dict, config: Dict, sisters):
    assign_ivy_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
