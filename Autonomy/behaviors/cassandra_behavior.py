import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List
from llm import generate_llm_reply
from logger import log_event

CASSANDRA_PERSONALITY_JSON = "/Autonomy/personalities/Cassandra_Personality.json"
CASSANDRA_MEMORY_JSON = "/Autonomy/memory/Cassandra_Memory.json"

CASS_MIN_SLEEP = 35 * 60
CASS_MAX_SLEEP = 85 * 60

DISCIPLINED_COMMENT_CHANCE = 0.25
CHALLENGE_RESPONSE_CHANCE = 0.35

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Cass JSON read failed {path}: {e}")
    return default

def load_cass_profile() -> Dict:
    return _load_json(CASSANDRA_PERSONALITY_JSON, {})

def load_cass_memory() -> Dict:
    mem = _load_json(CASSANDRA_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_cass_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(CASSANDRA_MEMORY_JSON), exist_ok=True)
        with open(CASSANDRA_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Cass memory write failed: {e}")

def assign_cass_schedule(state, config):
    today = datetime.now().date()
    key = "cass_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Cassandra", {"wake": [5, 7], "sleep": [22, 23]})
    def pick(span): lo, hi = int(span[0]), int(span[1]); return random.randint(lo, hi)
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule; state[kd] = today
    return schedule

def is_cass_online(state, config):
    sc = assign_cass_schedule(state, config)
    now_h = datetime.now().hour
    return sc["wake"] <= now_h or now_h < sc["sleep"]

async def _persona_reply(base_prompt, disciplined=False, state=None, config=None, project_progress=None):
    profile = load_cass_profile()
    tone = "firm and efficient" if disciplined else "cool, blunt but affectionate"
    personality = profile.get("core_personality", "Disciplined, confident, athletic, and composed.")
    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.5: project_phrase = " My reorganization’s halfway done. Everything’s finally aligning."
        else: project_phrase = " I finished the last bit today — satisfying as hell."
    prompt = (
        f"You are Cassandra. Personality: {personality}. Speak with a measured, confident tone. {tone}. "
        f"Include brief physical or active metaphors where natural.{project_phrase} {base_prompt}"
    )
    return await generate_llm_reply(
        sister="Cassandra", user_message=prompt, theme=None, role="sister", history=[]
    )

async def cass_chatter_loop(state, config, sisters):
    if state.get("cass_chatter_started"): return
    state["cass_chatter_started"] = True
    while True:
        if is_cass_online(state, config) and random.random() < 0.1:
            disciplined = random.random() < DISCIPLINED_COMMENT_CHANCE
            progress = state.get("Cassandra_project_progress", random.random())
            msg = await _persona_reply("Make a short, motivating group remark.", disciplined, state, config, progress)
            if msg:
                for bot in sisters:
                    if bot.sister_info["name"] == "Cassandra" and bot.is_ready():
                        ch = bot.get_channel(config["family_group_channel"])
                        if ch:
                            await ch.send(msg)
                            log_event(f"[CHATTER] Cassandra: {msg}")
        await asyncio.sleep(random.randint(CASS_MIN_SLEEP, CASS_MAX_SLEEP))

async def cass_handle_message(state, config, sisters, author, content, channel_id):
    if not is_cass_online(state, config): return
    chance = 0.2
    if "cass" in content.lower() or "cassandra" in content.lower(): chance = 1.0
    if random.random() >= chance: return
    disciplined = random.random() < CHALLENGE_RESPONSE_CHANCE
    progress = state.get("Cassandra_project_progress", random.random())
    reply = await _persona_reply(f"{author} said: \"{content}\". Respond with brief, confident sibling banter.", disciplined, state, config, progress)
    if reply:
        for bot in sisters:
            if bot.is_ready() and bot.sister_info["name"] == "Cassandra":
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(reply)
                    log_event(f"[REPLY] Cass → {author}: {reply}")

def ensure_cass_systems(state, config, sisters):
    assign_cass_schedule(state, config)
    if not state.get("cass_chatter_started"):
        asyncio.create_task(cass_chatter_loop(state, config, sisters))
