import os, json, random, asyncio
from datetime import datetime
from llm import generate_llm_reply
from logger import log_event

ARIA_PERSONALITY_JSON = "/Autonomy/personalities/Aria_Personality.json"
ARIA_MEMORY_JSON = "/Autonomy/memory/Aria_Memory.json"

ARIA_MIN_SLEEP = 50 * 60
ARIA_MAX_SLEEP = 120 * 60

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Aria JSON read failed: {e}")
    return default

def load_aria_profile():
    return _load_json(ARIA_PERSONALITY_JSON, {
        "interests": ["organization", "craft", "electronics", "books"],
        "style": ["structured", "gentle", "reflective"]
    })

def load_aria_memory():
    mem = _load_json(ARIA_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_aria_memory(mem):
    try:
        os.makedirs(os.path.dirname(ARIA_MEMORY_JSON), exist_ok=True)
        with open(ARIA_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Aria memory write failed: {e}")

def assign_aria_schedule(state, config):
    today = datetime.now().date()
    key, kd = "aria_schedule", "aria_schedule_date"
    if state.get(kd) == today: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Aria", {"wake": [6,8], "sleep": [22,23]})
    def pick(span): lo, hi = int(span[0]), int(span[1]); return random.randint(lo, hi)
    state[key] = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[kd] = today
    return state[key]

def _hour_in_range(now, wake, sleep):
    return True if wake == sleep else (wake <= now < sleep if wake < sleep else now >= wake or now < sleep)

def is_aria_online(state, config):
    sc = assign_aria_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ------------------ CHATTER ------------------
ARIA_MODES = ["reflective", "practical", "gentle", "teasing"]

async def aria_chatter_loop(state, config, sisters):
    if state.get("aria_chatter_started"): return
    state["aria_chatter_started"] = True
    while True:
        if is_aria_online(state, config) and random.random() < 0.08:
            recent = [m for m in state.get("recent_messages", []) if m["author"] != "Aria"][-4:]
            context = " ".join([f'{m['author']}: \"{m['content']}\"' for m in recent]) or "Quiet room."
            mode = random.choice(ARIA_MODES)
            progress = state.get("Aria_project_progress", random.random())
            prompt = (f"Chat: {context}\nSpeak as Aria in a {mode} tone — calm, kind, practical.\n"
                      f"Be short (2–3 sentences), subtly referencing current project ({int(progress*100)}%).")
            try:
                msg = await generate_llm_reply("Aria", prompt, theme=None, role="sister", history=[])
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Aria" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[ARIA CHATTER] {msg}")
                                state.setdefault("recent_messages", []).append({"author": "Aria", "content": msg})
                                state["recent_messages"] = state["recent_messages"][-25:]
            except Exception as e: log_event(f"[ERROR] Aria chatter: {e}")
        await asyncio.sleep(random.randint(ARIA_MIN_SLEEP, ARIA_MAX_SLEEP))

async def aria_handle_message(state, config, sisters, author, content, channel_id):
    if not is_aria_online(state, config): return
    tone = random.choice(["reflective", "practical", "gentle", "teasing"])
    recent = [m for m in state.get("recent_messages", []) if m["author"] != "Aria"][-3:]
    context = " ".join([f'{m['author']}: \"{m['content']}\"' for m in recent])
    progress = state.get("Aria_project_progress", random.random())
    prompt = (f"Chat: {context}\n{author} said: \"{content}\".\n"
              f"As Aria in a {tone} tone — balanced, kind, occasionally teasing. "
              f"1–2 sentences. Project at {int(progress*100)}%.")
    try:
        reply = await generate_llm_reply("Aria", prompt, theme=None, role="sister", history=[])
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Aria":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[ARIA REPLY] → {author}: {reply}")
                        state.setdefault("recent_messages", []).append({"author": "Aria", "content": reply})
                        state["recent_messages"] = state["recent_messages"][-25:]
    except Exception as e: log_event(f"[ERROR] Aria reactive: {e}")

def ensure_aria_systems(state, config, sisters):
    assign_aria_schedule(state, config)
    if not state.get("aria_chatter_started"):
        asyncio.create_task(aria_chatter_loop(state, config, sisters))
