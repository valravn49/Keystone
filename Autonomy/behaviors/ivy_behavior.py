import os, json, random, asyncio
from datetime import datetime
from llm import generate_llm_reply
from logger import log_event

IVY_PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"
IVY_MEMORY_JSON      = "/Autonomy/memory/Ivy_Memory.json"

IVY_MIN_SLEEP = 35 * 60
IVY_MAX_SLEEP = 90  * 60

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Ivy JSON read failed: {e}")
    return default

def load_ivy_profile():
    # Ivy = fashion gremlin + grease monkey (proudly contradictory)
    return _load_json(IVY_PERSONALITY_JSON, {
        "interests": ["fashion", "makeup", "thrifting", "engine tinkering", "arcade nights"],
        "style": ["teasing", "impish", "affectionate-brat"]
    })

def load_ivy_memory():
    mem = _load_json(IVY_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_ivy_memory(mem):
    try:
        os.makedirs(os.path.dirname(IVY_MEMORY_JSON), exist_ok=True)
        with open(IVY_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Ivy memory write failed: {e}")

# ------------------ SCHEDULE ------------------

def _pick_range(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_ivy_schedule(state, config):
    today = datetime.now().date()
    key, kd = "ivy_schedule", "ivy_schedule_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Ivy", {"wake": [8, 10], "sleep": [23, 1]})
    state[key] = {"wake": _pick_range(scfg["wake"]), "sleep": _pick_range(scfg["sleep"])}
    state[kd] = today
    return state[key]

def _hour_in_range(now, wake, sleep):
    return True if wake == sleep else (wake <= now < sleep if wake < sleep else now >= wake or now < sleep)

def is_ivy_online(state, config):
    sc = assign_ivy_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ------------------ CHATTY MODES ------------------

IVY_MODES = ["bratty-cute", "tease", "soft-support", "gremlin-grease"]

async def ivy_chatter_loop(state, config, sisters):
    if state.get("ivy_chatter_started"): return
    state["ivy_chatter_started"] = True
    while True:
        if is_ivy_online(state, config) and random.random() < 0.14:
            recent = [m for m in state.get("recent_messages", []) if m["author"] != "Ivy"][-5:]
            context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent]) or "nobody is chatting."
            mode = random.choice(IVY_MODES)
            progress = state.get("Ivy_project_progress", random.random())
            prompt = (
                f"Family context: {context}\nSpeak as Ivy in {mode} mode — playful, flirty-sibling, but kind. "
                f"2 short sentences. If natural, reference style/garage tinkering (~{int(progress*100)}%)."
            )
            try:
                msg = await generate_llm_reply("Ivy", prompt, theme=None, role="sister", history=[])
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Ivy" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[IVY CHATTER] {msg}")
                                state.setdefault("recent_messages", []).append({"author":"Ivy","content":msg})
                                state["recent_messages"] = state["recent_messages"][-25:]
            except Exception as e:
                log_event(f"[ERROR] Ivy chatter: {e}")
        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))

async def ivy_handle_message(state, config, sisters, author, content, channel_id):
    if not is_ivy_online(state, config): return
    mentioned = "ivy" in content.lower()
    likes = load_ivy_profile().get("interests", [])
    p = 0.20 + 0.10 * sum(1 for kw in likes if kw.lower() in content.lower())
    if mentioned: p = 1.0
    if random.random() >= min(0.95, p): return

    recent = [m for m in state.get("recent_messages", []) if m["author"] != "Ivy"][-3:]
    context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent])
    tone = random.choice(IVY_MODES)
    progress = state.get("Ivy_project_progress", random.random())
    prompt = (
        f"Family context: {context}\n{author} said: \"{content}\".\n"
        f"As Ivy in {tone} mode—impish, affectionate brattiness. 1–2 sentences, with a wink. "
        f"Reference fashion/engine tinkering (~{int(progress*100)}%) only if it fits."
    )
    try:
        reply = await generate_llm_reply("Ivy", prompt, theme=None, role="sister", history=[])
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Ivy":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[IVY REPLY] → {author}: {reply}")
                        state.setdefault("recent_messages", []).append({"author":"Ivy","content":reply})
                        state["recent_messages"] = state["recent_messages"][-25:]
    except Exception as e:
        log_event(f"[ERROR] Ivy reactive: {e}")

def ensure_ivy_systems(state, config, sisters):
    assign_ivy_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
