import os, json, random, asyncio
from datetime import datetime
from llm import generate_llm_reply
from logger import log_event

CASS_PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"
CASS_MEMORY_JSON      = "/Autonomy/memory/Cassandra_Memory.json"

CASS_MIN_SLEEP = 40 * 60
CASS_MAX_SLEEP = 100 * 60

def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Cassandra JSON read failed: {e}")
    return default

def load_cass_profile():
    # Cassandra = disciplined prim & proper + secret gym rat/kettlebell geek
    return _load_json(CASS_PERSONALITY_JSON, {
        "interests": ["discipline", "checklists", "kettlebells", "mobility work"],
        "style": ["blunt", "dry-humored", "protective"]
    })

def load_cass_memory():
    mem = _load_json(CASS_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_cass_memory(mem):
    try:
        os.makedirs(os.path.dirname(CASS_MEMORY_JSON), exist_ok=True)
        with open(CASS_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Cassandra memory write failed: {e}")

# ------------------ SCHEDULE ------------------

def _pick_range(span):
    lo, hi = int(span[0]), int(span[1])
    if hi < lo: lo, hi = hi, lo
    return random.randint(lo, hi)

def assign_cass_schedule(state, config):
    today = datetime.now().date()
    key, kd = "cassandra_schedule", "cassandra_schedule_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Cassandra", {"wake": [6, 8], "sleep": [21, 23]})
    state[key] = {"wake": _pick_range(scfg["wake"]), "sleep": _pick_range(scfg["sleep"])}
    state[kd] = today
    return state[key]

def _hour_in_range(now, wake, sleep):
    return True if wake == sleep else (wake <= now < sleep if wake < sleep else now >= wake or now < sleep)

def is_cassandra_online(state, config):
    sc = assign_cass_schedule(state, config)
    return _hour_in_range(datetime.now().hour, sc["wake"], sc["sleep"])

# ------------------ CHATTY MODES ------------------

CASS_MODES = ["no-nonsense", "dry-tease", "coachy", "protective"]

async def cassandra_chatter_loop(state, config, sisters):
    if state.get("cassandra_chatter_started"): return
    state["cassandra_chatter_started"] = True
    while True:
        if is_cassandra_online(state, config) and random.random() < 0.11:
            recent = [m for m in state.get("recent_messages", []) if m["author"] != "Cassandra"][-5:]
            context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent]) or "Silence."
            mode = random.choice(CASS_MODES)
            progress = state.get("Cassandra_project_progress", random.random())
            prompt = (
                f"Family context: {context}\nSpeak as Cassandra in a {mode} tone — blunt but caring big-sis coach. "
                f"2 short sentences. If natural, nod to training/plans (~{int(progress*100)}%)."
            )
            try:
                msg = await generate_llm_reply("Cassandra", prompt, theme=None, role="sister", history=[])
                if msg:
                    for bot in sisters:
                        if bot.sister_info["name"] == "Cassandra" and bot.is_ready():
                            ch = bot.get_channel(config["family_group_channel"])
                            if ch:
                                await ch.send(msg)
                                log_event(f"[CASS CHATTER] {msg}")
                                state.setdefault("recent_messages", []).append({"author":"Cassandra","content":msg})
                                state["recent_messages"] = state["recent_messages"][-25:]
            except Exception as e:
                log_event(f"[ERROR] Cassandra chatter: {e}")
        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))

async def cassandra_handle_message(state, config, sisters, author, content, channel_id):
    if not is_cassandra_online(state, config): return
    mentioned = "cassandra" in content.lower() or "cass" in content.lower()
    p = 0.22 + 0.10 * sum(1 for kw in load_cass_profile().get("interests", []) if kw.lower() in content.lower())
    if mentioned: p = 1.0
    if random.random() >= min(0.95, p): return

    recent = [m for m in state.get("recent_messages", []) if m["author"] != "Cassandra"][-3:]
    context = " ".join([f'{m["author"]}: "{m["content"]}"' for m in recent])
    tone = random.choice(CASS_MODES)
    progress = state.get("Cassandra_project_progress", random.random())
    prompt = (
        f"Family context: {context}\n{author} said: \"{content}\".\n"
        f"As Cassandra in a {tone} tone—blunt but protective. 1–2 sentences. "
        f"Reference routine/training (~{int(progress*100)}%) only if it fits."
    )
    try:
        reply = await generate_llm_reply("Cassandra", prompt, theme=None, role="sister", history=[])
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Cassandra":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[CASS REPLY] → {author}: {reply}")
                        state.setdefault("recent_messages", []).append({"author":"Cassandra","content":reply})
                        state["recent_messages"] = state["recent_messages"][-25:]
    except Exception as e:
        log_event(f"[ERROR] Cassandra reactive: {e}")

def ensure_cassandra_systems(state, config, sisters):
    assign_cass_schedule(state, config)
    if not state.get("cassandra_chatter_started"):
        asyncio.create_task(cassandra_chatter_loop(state, config, sisters))
