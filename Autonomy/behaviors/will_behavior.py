import os, json, random, asyncio
from datetime import datetime
from llm import generate_llm_reply
from logger import log_event

WILL_PERSONALITY_JSON = "/Autonomy/personalities/Will_Personality.json"
WILL_MEMORY_JSON      = "/Autonomy/memory/Will_Memory.json"

WILL_MIN_SLEEP = 40 * 60
WILL_MAX_SLEEP = 100 * 60

# Updated fallbacks (as requested): includes Nier: Automata, Zenless Zone Zero, Little Nightmares
WILL_FALLBACK_FAVORITES = [
    "The Legend of Zelda: Tears of the Kingdom",
    "Final Fantasy XIV",
    "Hades",
    "Stardew Valley",
    "Hollow Knight",
    "Elden Ring",
    "Nier: Automata",
    "Zenless Zone Zero",
    "Little Nightmares",
    "VR headsets",
    "retro game consoles",
    "PC building",
    "indie game dev videos",
    "tech teardown channels",
]

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Will JSON read failed: {e}")
    return default

def load_will_profile():
    # Will = shy/nerdy; on bold days leans femme. Keep tone gentle.
    return _load_json(WILL_PERSONALITY_JSON, {
        "interests": ["tech", "games", "anime", "music"],
        "style": ["casual", "timid", "sometimes playful"],
        "favorites": WILL_FALLBACK_FAVORITES
    })

def load_will_memory():
    mem = _load_json(WILL_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_will_memory(mem):
    try:
        os.makedirs(os.path.dirname(WILL_MEMORY_JSON), exist_ok=True)
        with open(WILL_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Will memory write failed: {e}")

# ------------------ SCHEDULE ------------------

def _pick_range(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_will_schedule(state, config):
    today = datetime.now().date()
    key, kd = "will_schedule", "will_schedule_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Will", {"wake": [10, 12], "sleep": [0, 2]})
    state[key] = {"wake": _pick_range(scfg["wake"]), "sleep": _pick_range(scfg["sleep"])}
    state[kd] = today
    return state[key]

def _hour_in_range(now, wake, sleep):
    return True if wake == sleep else (wake <= now < sleep if wake < sleep else now >= wake or now < sleep)

def is_will_online(state, config):
    sc = assign_will_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ------------------ CHATTY MODES ------------------

WILL_MODES = ["timid", "soft-playful", "brief-rant", "nostalgic"]

def _favorites_today(state):
    today = datetime.now().date()
    key, kd = "will_favs_today", "will_favs_date"
    if state.get(kd) == today and key in state:
        return state[key]
    favs = load_will_profile().get("favorites", WILL_FALLBACK_FAVORITES)
    picks = random.sample(favs, min(3, len(favs)))
    state[key], state[kd] = picks, today
    return picks

async def will_chatter_loop(state, config, sisters):
    if state.get("will_chatter_started"): return
    state["will_chatter_started"] = True
    while True:
        if is_will_online(state, config) and random.random() < 0.10:
            recent = [m for m in state.get("recent_messages", []) if m["author"] != "Will"][-4:]
            context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent]) or "Quiet room."
            mode = random.choices(WILL_MODES, weights=[50, 25, 15, 10], k=1)[0]
            progress = state.get("Will_project_progress", random.random())
            fav_hint = random.choice(_favorites_today(state))
            base = (
                f"Family context: {context}\nSpeak as Will in {mode} mode—shy by default, warm, concise. "
                f"2 short sentences. If natural, hint at {fav_hint} or your current project (~{int(progress*100)}%)."
            )
            try:
                msg = await generate_llm_reply("Will", base, theme=None, role="sister", history=[])
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Will" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[WILL CHATTER] {msg}")
                                state.setdefault("recent_messages", []).append({"author":"Will","content":msg})
                                state["recent_messages"] = state["recent_messages"][-25:]
            except Exception as e:
                log_event(f"[ERROR] Will chatter: {e}")
        await asyncio.sleep(random.randint(WILL_MIN_SLEEP, WILL_MAX_SLEEP))

async def will_handle_message(state, config, sisters, author, content, channel_id):
    if not is_will_online(state, config): return
    mentioned = "will" in content.lower()
    interests = load_will_profile().get("interests", [])
    p = 0.12 + 0.10 * sum(1 for kw in interests if kw.lower() in content.lower())
    if author == "Ivy": p += 0.25
    if mentioned: p = 1.0
    if random.random() >= min(0.95, p): return

    recent = [m for m in state.get("recent_messages", []) if m["author"] != "Will"][-3:]
    context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent])
    mode = random.choices(WILL_MODES, weights=[60, 20, 10, 10], k=1)[0]
    progress = state.get("Will_project_progress", random.random())
    fav_hint = random.choice(_favorites_today(state))
    prompt = (
        f"Family context: {context}\n{author} said: \"{content}\".\n"
        f"As Will in {mode} mode—short, shy, a touch playful. 1–2 sentences. "
        f"If it fits, nod to {fav_hint} or project (~{int(progress*100)}%)."
    )
    try:
        reply = await generate_llm_reply("Will", prompt, theme=None, role="sister", history=[])
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Will":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[WILL REPLY] → {author}: {reply}")
                        state.setdefault("recent_messages", []).append({"author":"Will","content":reply})
                        state["recent_messages"] = state["recent_messages"][-25:]
    except Exception as e:
        log_event(f"[ERROR] Will reactive: {e}")

def ensure_will_systems(state, config, sisters):
    assign_will_schedule(state, config)
    if not state.get("will_chatter_started"):
        asyncio.create_task(will_chatter_loop(state, config, sisters))
