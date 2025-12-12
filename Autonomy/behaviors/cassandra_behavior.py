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

CASS_PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"

CASS_MIN_SLEEP = 40 * 60
CASS_MAX_SLEEP = 90 * 60

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
        log_event(f"[WARN] Cass JSON read failed {path}: {e}")
    return default

def load_cass_profile() -> Dict:
    p = _load_json(CASS_PERSONALITY_JSON, {})
    p.setdefault("style", ["disciplined", "confident", "concise"])
    p.setdefault(
        "core_personality",
        "Disciplined and composed; blunt but fair; action first."
    )
    return p

# ---------- Schedule ----------
def assign_cass_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "cass_schedule"
    kd  = f"{key}_date"

    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get(
        "Cassandra",
        {"wake": [5, 7], "sleep": [21, 23]},
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

def is_cass_online(state: Dict, config: Dict) -> bool:
    sc = assign_cass_schedule(state, config)
    return _hr_in(datetime.now().hour, sc["wake"], sc["sleep"])

# ---------- Persona reply ----------
async def _persona_reply(
    base_prompt: str,
    address_to: Optional[str] = None,
) -> str:
    """
    Wraps Cassandra's replies with her personality, style, and a bit of
    variability in length while staying crisp and actionable.
    """
    p = load_cass_profile()
    style = ", ".join(p.get("style", ["disciplined", "concise"]))
    personality = p.get(
        "core_personality",
        "Disciplined and composed; blunt but fair."
    )

    length_mode = random.choices(
        ["short", "medium", "ramble"],
        weights=[0.55, 0.35, 0.10],  # she favors short
    )[0]

    if length_mode == "short":
        length_hint = "Keep this very short and sharp, ideally 1–2 sentences."
    elif length_mode == "medium":
        length_hint = (
            "Reply in about 2–4 sentences, with a clear point and maybe one extra clarifying detail."
        )
    else:
        length_hint = (
            "You can be a little more expansive here, up to 5–6 sentences, "
            "but still focused, structured, and free of fluff."
        )

    who = _pick_name(address_to) if address_to else None
    prefix = f"Speak directly to {who} by name at least once. " if who else ""

    prompt = (
        f"You are Cassandra. Personality: {personality} "
        f"Your style is {style} — assertive, clean, no fluff, but not cruel. "
        f"{prefix}"
        "Always speak in the first person, never referring to yourself in the third person. "
        "Write like a real person on Discord: direct, confident phrasing, not a corporate email. "
        "You give clear nudges, set boundaries, and push for action, but you still care about the person you're talking to. "
        f"{length_hint} "
        f"Now respond based on this instruction/context: {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Cassandra",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------- Background chatter ----------
async def cass_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("cass_chatter_started"):
        return
    state["cass_chatter_started"] = True

    while True:
        if is_cass_online(state, config):
            if random.random() < 0.12:
                base_ctx, mem = recall_or_enrich_prompt(
                    "Cassandra",
                    "Offer a brisk check-in or a quick nudge to keep momentum.",
                    ["workout", "order", "plan", "routine", "progress"],
                )

                base_prompt = (
                    "Say one brief, focused check-in or nudge in the family group chat. "
                    "It should feel like you're keeping everyone on track, not barking orders."
                )
                if base_ctx:
                    base_prompt += (
                        f" You can let this context guide what you pick as the focus: {base_ctx}"
                    )

                msg = await _persona_reply(base_prompt)

                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Cassandra" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await send_human_like_message(
                                    ch,
                                    msg,
                                    speaker_name="Cassandra",
                                )
                                log_event(f"[CHATTER] Cassandra: {msg}")
                                if mem:
                                    remember_after_exchange(
                                        "Cassandra",
                                        f"Chatted: {mem.get('summary', 'quick momentum nudge')}",
                                        tone="firm",
                                        tags=["chatter"],
                                    )
                                break

        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))

# ---------- Cooldown ----------
def _cool_ok(state: Dict, channel_id: int) -> bool:
    cd = state.setdefault("cooldowns", {}).setdefault("Cassandra", {})
    last = cd.get(channel_id, 0)
    now = datetime.now().timestamp()
    if now - last < 120:
        return False
    cd[channel_id] = now
    return True

# ---------- Reactive handler ----------
async def cass_handle_message(
    state: Dict,
    config: Dict,
    sisters,
    author_label: str,
    content: str,
    channel_id: int,
    discord_author_name: str,
    discord_author_is_bot: bool,
) -> bool:
    if not is_cass_online(state, config):
        return False
    if not _cool_ok(state, channel_id):
        return False

    addressed = author_label or discord_author_name

    base_ctx, mem = recall_or_enrich_prompt(
        "Cassandra",
        content,
        ["family_chat", "plans", "habits", "progress"],
    )

    inject = None
    lower = content.lower()
    if any(k in lower for k in ["doc", "plan", "show", "film", "music", "anime", "gym", "lift", "workout"]):
        m = get_media_reference(
            "Cassandra",
            mood_tags=["discipline", "strategy", "documentary", "drama"],
        )
        if m:
            inject = craft_media_reaction("Cassandra", m)

    base = (
        f'Respond to what {addressed} said in the family group chat: "{content}". '
        "Give one clear point or next step. Be crisp, constructive, and honest, "
        "but do not be cruel or mocking."
    )
    if base_ctx:
        base += f" If it helps, let this context inform your reply: {base_ctx}."
    if inject:
        base += f" If it fits naturally with what they said, you can also include: {inject}."

    msg = await _persona_reply(base, address_to=addressed)
    if not msg:
        return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Cassandra":
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await send_human_like_message(
                    ch,
                    msg,
                    speaker_name="Cassandra",
                )
                log_event(f"[REPLY] Cassandra → {addressed}: {msg}")
                remember_after_exchange(
                    "Cassandra",
                    f"Replied to {addressed}",
                    tone="firm",
                    tags=["reply"],
                )
                if mem:
                    remember_after_exchange(
                        "Cassandra",
                        mem.get("summary", "Context used while replying"),
                        tone="neutral",
                        tags=["context", "reply"],
                    )
                return True

    return False

# ---------- Startup ----------
def ensure_cass_systems(state: Dict, config: Dict, sisters):
    assign_cass_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(cass_chatter_loop(state, config, sisters))
