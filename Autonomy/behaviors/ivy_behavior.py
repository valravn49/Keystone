import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional
from llm import generate_llm_reply
from logger import log_event

IVY_PERSONALITY_JSON = "/Autonomy/personalities/Ivy_Personality.json"
IVY_MEMORY_JSON = "/Autonomy/memory/Ivy_Memory.json"

IVY_MIN_SLEEP = 30 * 60
IVY_MAX_SLEEP = 70 * 60

CHAOTIC_COMMENT_CHANCE = 0.4
FLIRTY_COMMENT_CHANCE = 0.2

def _load_json(path, default): 
    try:
        if os.path.exists(path): 
            with open(path, "r", encoding="utf-8") as f: 
                return json.load(f)
    except Exception as e: log_event(f"[WARN] Ivy JSON read failed {path}: {e}")
    return default

def load_ivy_profile(): return _load_json(IVY_PERSONALITY_JSON, {})
def load_ivy_memory(): return _load_json(IVY_MEMORY_JSON, {"projects": {}, "recent_notes": []})
def save_ivy_memory(mem):
    try:
        os.makedirs(os.path.dirname(IVY_MEMORY_JSON), exist_ok=True)
        with open(IVY_MEMORY_JSON, "w", encoding="utf-8") as f: json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e: log_event(f"[WARN] Ivy memory write failed: {e}")

def assign_ivy_schedule(state, config):
    today = datetime.now().date()
    key = "ivy_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state: return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Ivy", {"wake": [9, 11], "sleep": [1, 3]})
    def pick(span): return random.randint(int(span[0]), int(span[1]))
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule; state[kd] = today
    return schedule

def is_ivy_online(state, config):
    sc = assign_ivy_schedule(state, config)
    now_h = datetime.now().hour
    wake, sleep = sc["wake"], sc["sleep"]
    return wake <= now_h or now_h < sleep

async def _persona_reply(base_prompt, chaotic=False, flirty=False, state=None, config=None, project_progress=None):
    profile = load_ivy_profile()
    tone = "playful and teasing" if flirty else ("chaotic, expressive" if chaotic else "bright and casual")
    personality = profile.get("core_personality", "Playful, creative, and impulsive but clever.")
    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4: project_phrase = " My latest DIY project exploded in glitter. Oops."
        elif project_progress < 0.8: project_phrase = " The closet restyle’s messy but starting to make sense."
        else: project_phrase = " Done. Sparkly chaos successfully organized."
    prompt = f"You are Ivy. Personality: {personality}. Speak in a {tone} tone, short and animated.{project_phrase} {base_prompt}"
    return await generate_llm_reply(sister="Ivy", user_message=prompt, theme=None, role="sister", history=[])

async def ivy_chatter_loop(state, config, sisters):
    if state.get("ivy_chatter_started"): return
    state["ivy_chatter_started"] = True
    while True:
        if is_ivy_online(state, config) and random.random() < 0.15:
            chaotic = random.random() < CHAOTIC_COMMENT_CHANCE
            flirty = random.random() < FLIRTY_COMMENT_CHANCE
            progress = state.get("Ivy_project_progress", random.random())
            msg = await _persona_reply("Say something spontaneous and fun to the group chat.", chaotic, flirty, state, config, progress)
            if msg:
                for bot in sisters:
                    if bot.sister_info["name"] == "Ivy" and bot.is_ready():
                        ch = bot.get_channel(config["family_group_channel"])
                        if ch:
                            await ch.send(msg)
                            log_event(f"[CHATTER] Ivy: {msg}")
        await asyncio.sleep(random.randint(IVY_MIN_SLEEP, IVY_MAX_SLEEP))

async def ivy_handle_message(state, config, sisters, author, content, channel_id):
    if not is_ivy_online(state, config): return
    chance = 0.3
    if "ivy" in content.lower(): chance = 1.0
    if random.random() >= chance: return
    chaotic = random.random() < 0.5; flirty = random.random() < 0.3
    progress = state.get("Ivy_project_progress", random.random())
    reply = await _persona_reply(f"{author} said: \"{content}\" — reply playfully like a younger sibling teasing.", chaotic, flirty, state, config, progress)
    if reply:
        for bot in sisters:
            if bot.is_ready() and bot.sister_info["name"] == "Ivy":
                ch = bot.get_channel(config["family_group_channel"])
                if ch:
                    await ch.send(reply)
                    log_event(f"[REPLY] Ivy → {author}: {reply}")

def ensure_ivy_systems(state, config, sisters):
    assign_ivy_schedule(state, config)
    if not state.get("ivy_chatter_started"):
        asyncio.create_task(ivy_chatter_loop(state, config, sisters))
