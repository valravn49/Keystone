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
from messaging_utils import send_human_like_message  # 🔸 new import

SELENE_PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
SELENE_MEMORY_JSON      = "/Autonomy/memory/Selene_Memory.json"

SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 100 * 60

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
        log_event(f"[WARN] Selene JSON read failed {path}: {e}")
    return default

def load_selene_profile() -> Dict:
    p = _load_json(SELENE_PERSONALITY_JSON, {})
    p.setdefault("style", ["warm", "sensory", "steady"])
    p.setdefault("core_personality", "Nurturing and serene, with a streak for motion and weather.")
    return p

# ---------- Schedule ----------
def assign_selene_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "selene_schedule"
    kd  = f"{key}_date"

    if state.get(kd) == today and key in state:
        return state[key]

    scfg = (config.get("schedules", {}) or {}).get(
        "Selene",
        {"wake": [7, 9], "sleep": [22, 24]},
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

def _hour_in_range(h: int, w: int, s: int) -> bool:
    if w == s:
        return True
    if w < s:
        return w <= h < s
    return h >= w or h < s

def is_selene_online(state: Dict, config: Dict) -> bool:
    sc = assign_selene_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ---------- Persona reply ----------
async def _persona_reply(
    base_prompt: str,
    address_to: Optional[str] = None,
) -> str:
    """
    Wrap Selene's replies with her personality, style, and a bit of
    variability in length and tone to feel more lifelike.
    """
    p = load_selene_profile()
    style = ", ".join(p.get("style", ["warm", "steady"]))
    personality = p.get(
        "core_personality",
        "Nurturing and serene, with a streak for motion and weather.",
    )

    # Decide how talkative Selene is this time
    length_mode = random.choices(
        ["short", "medium", "ramble"],
        weights=[0.5, 0.35, 0.15],
    )[0]

    if length_mode == "short":
        length_hint = "Keep this quite short and gentle, around 1–2 sentences."
    elif length_mode == "medium":
        length_hint = (
            "Reply in about 2–4 sentences, enough to feel caring and grounded without rambling."
        )
    else:
        length_hint = (
            "It's okay to be a little more talkative here, up to 5–7 sentences, "
            "weaving in sensory details if it feels natural."
        )

    who = _pick_name(address_to) if address_to else None
    prefix = ""
    if who:
        prefix = f"Speak directly to {who} by name at least once in the reply. "

    prompt = (
        f"You are Selene. Personality: {personality} "
        f"Your style is {style} — gentle, sensory, and present. "
        f"{prefix}"
        "Always speak in the first person, never referring to yourself in the third person. "
        "Write like a real person on Discord: soft, natural phrasing, occasionally using emojis that match your mood, "
        "but never overdoing it. You focus on comfort, reassurance, and subtle sensory details when appropriate. "
        f"{length_hint} "
        f"Now respond based on this instruction/context: {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Selene",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

# ---------- Background chatter ----------
async def selene_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("selene_chatter_started"):
        return
    state["selene_chatter_started"] = True

    while True:
        if is_selene_online(state, config):
            if random.random() < 0.10:
                # Pull some recent context so her check-ins feel connected
                base_ctx, mem = recall_or_enrich_prompt(
                    "Selene",
                    "Offer one cozy check-in or a small sensory observation about the day.",
                    ["kitchen", "rain", "ride", "comfort", "evening", "weather"],
                )

                base_prompt = (
                    "Say one small, cozy check-in or sensory observation in the family group chat. "
                    "It should feel like you're glancing up from what you're doing and gently checking on everyone, "
                    "not giving a speech."
                )
                if base_ctx:
                    base_prompt += (
                        f" You can let this context quietly guide what you say: {base_ctx}"
                    )

                msg = await _persona_reply(base_prompt)

                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Selene" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await send_human_like_message(
                                    ch,
                                    msg,
                                    speaker_name="Selene",
                                )
                                log_event(f"[CHATTER] Selene: {msg}")
                                if mem:
                                    remember_after_exchange(
                                        "Selene",
                                        f"Chatted: {mem.get('summary', 'small cozy note')}",
                                        tone="warm",
                                        tags=["chatter"],
                                    )
                                break

        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))

# ---------- Cooldown ----------
def _cool_ok(state: Dict, channel_id: int) -> bool:
    cd = state.setdefault("cooldowns", {}).setdefault("Selene", {})
    last = cd.get(channel_id, 0)
    now = datetime.now().timestamp()
    if now - last < 120:
        return False
    cd[channel_id] = now
    return True

# ---------- Reactive handler ----------
async def selene_handle_message(
    state: Dict,
    config: Dict,
    sisters,
    author: str,
    content: str,
    channel_id: int,
) -> bool:
    if not is_selene_online(state, config):
        return False
    if not _cool_ok(state, channel_id):
        return False

    rot = state.get("rotation", {"lead": None, "supports": [], "rest": None})
    chance = 0.20
    if rot.get("lead") == "Selene":
        chance = 0.70
    elif "Selene" in rot.get("supports", []):
        chance = 0.45
    elif rot.get("rest") == "Selene":
        chance = 0.25

    # Mention = always reply
    if "selene" in content.lower():
        chance = 1.0

    # Media hook
    inject = None
    lowered = content.lower()
    if any(k in lowered for k in ["show", "anime", "movie", "soundtrack", "music"]):
        m = get_media_reference("Selene", mood_tags=["cozy", "feel-good", "rain", "tea"])
        if m:
            inject = craft_media_reaction("Selene", m)

    if random.random() > chance:
        return False

    addressed = author

    # Pull some context so she "remembers" the vibe
    base_ctx, mem = recall_or_enrich_prompt(
        "Selene",
        content,
        ["family_chat", "recent", "emotions", "comfort"],
    )

    base = (
        f'Respond to what {addressed} said in the family group chat: "{content}". '
        "Be kind, grounded, and comforting. Focus on how things feel — physically or emotionally — "
        "if it fits the message, and avoid sounding like a therapist or a system notice."
    )
    if base_ctx:
        base += f" Let this context gently inform your reply if it helps: {base_ctx}."
    if inject:
        base += f" If it fits naturally, you can also include: {inject}."

    msg = await _persona_reply(base, address_to=addressed)
    if not msg:
        return False

    for bot in sisters:
        if bot.is_ready() and bot.sister_info["name"] == "Selene":
            ch = bot.get_channel(config["family_group_channel"])
            if ch:
                await send_human_like_message(
                    ch,
                    msg,
                    speaker_name="Selene",
                )
                log_event(f"[REPLY] Selene → {addressed}: {msg}")
                remember_after_exchange(
                    "Selene",
                    f"Replied to {addressed}",
                    tone="warm",
                    tags=["reply"],
                )
                if mem:
                    remember_after_exchange(
                        "Selene",
                        mem.get("summary", "Context used while replying"),
                        tone="soft",
                        tags=["context", "reply"],
                    )
                return True

    return False

# ---------- Startup ----------
def ensure_selene_systems(state: Dict, config: Dict, sisters):
    assign_selene_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
