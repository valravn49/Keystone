import os
import json
import random
import asyncio
from datetime import datetime
from typing import Dict, Optional, List

from llm import generate_llm_reply
from logger import log_event

SELENE_PERSONALITY_JSON = "/Autonomy/personalities/Selene_Personality.json"
SELENE_MEMORY_JSON = "/Autonomy/memory/Selene_Memory.json"

SELENE_MIN_SLEEP = 45 * 60
SELENE_MAX_SLEEP = 95 * 60

REFLECTIVE_CHANCE = 0.3
CARING_COMMENT_CHANCE = 0.25

def _load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        log_event(f"[WARN] Selene JSON read failed {path}: {e}")
    return default

def load_selene_profile() -> Dict:
    profile = _load_json(SELENE_PERSONALITY_JSON, {})
    profile.setdefault("style", ["gentle", "warm", "balanced"])
    return profile

def load_selene_memory() -> Dict:
    mem = _load_json(SELENE_MEMORY_JSON, {"projects": {}, "recent_notes": []})
    mem.setdefault("projects", {})
    mem.setdefault("recent_notes", [])
    return mem

def save_selene_memory(mem: Dict):
    try:
        os.makedirs(os.path.dirname(SELENE_MEMORY_JSON), exist_ok=True)
        with open(SELENE_MEMORY_JSON, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_event(f"[WARN] Selene memory write failed: {e}")

def assign_selene_schedule(state: Dict, config: Dict):
    today = datetime.now().date()
    key = "selene_schedule"
    kd = f"{key}_date"
    if state.get(kd) == today and key in state:
        return state[key]
    scfg = (config.get("schedules", {}) or {}).get("Selene", {"wake": [7, 9], "sleep": [23, 1]})
    def pick(span):
        lo, hi = int(span[0]), int(span[1])
        return random.randint(lo, hi) if hi >= lo else lo
    schedule = {"wake": pick(scfg["wake"]), "sleep": pick(scfg["sleep"])}
    state[key] = schedule
    state[kd] = today
    return schedule

def _hour_in_range(now_h: int, wake: int, sleep: int) -> bool:
    if wake == sleep: return True
    if wake < sleep: return wake <= now_h < sleep
    return now_h >= wake or now_h < sleep

def is_selene_online(state: Dict, config: Dict) -> bool:
    sc = assign_selene_schedule(state, config)
    now_h = datetime.now().hour
    return _hour_in_range(now_h, sc["wake"], sc["sleep"])

async def _persona_reply(base_prompt: str, reflective=False, state=None, config=None, project_progress=None):
    profile = load_selene_profile()
    style = ", ".join(profile.get("style", ["warm", "calm"]))
    personality = profile.get("core_personality", "Gentle and empathetic, but quietly adventurous.")
    tone = "gentle and grounded" if reflective else "warm and lightly teasing"

    project_phrase = ""
    if project_progress is not None:
        if project_progress < 0.4:
            project_phrase = " My recipe cards are still half-finished, but the handwriting’s improving."
        elif project_progress < 0.8:
            project_phrase = " The project’s getting close — smells good, looks better."
        else:
            project_phrase = " Finally done. It feels satisfying to see everything line up."

    prompt = (
        f"You are Selene. Personality: {personality}. Speak with a {style} tone, {tone}. "
        f"Keep it heartfelt but concise.{project_phrase} {base_prompt}"
    )

    return await generate_llm_reply(
        sister="Selene",
        user_message=prompt,
        theme=None,
        role="sister",
        history=[],
    )

async def selene_chatter_loop(state: Dict, config: Dict, sisters):
    if state.get("selene_chatter_started"): return
    state["selene_chatter_started"] = True
    while True:
        if is_selene_online(state, config):
            if random.random() < 0.1:
                reflective = random.random() < REFLECTIVE_CHANCE
                progress = state.get("Selene_project_progress", random.random())
                try:
                    msg = await _persona_reply(
                        "Say something comforting or softly motivating to the group.",
                        reflective=reflective,
                        state=state,
                        config=config,
                        project_progress=progress
                    )
                    if msg:
                        for bot in sisters:
                            if bot.sister_info["name"] == "Selene" and bot.is_ready():
                                ch = bot.get_channel(config["family_group_channel"])
                                if ch:
                                    await ch.send(msg)
                                    log_event(f"[CHATTER] Selene: {msg}")
                except Exception as e:
                    log_event(f"[ERROR] Selene chatter: {e}")
        await asyncio.sleep(random.randint(SELENE_MIN_SLEEP, SELENE_MAX_SLEEP))

async def selene_handle_message(state, config, sisters, author, content, channel_id):
    if not is_selene_online(state, config): return
    chance = 0.25
    if "selene" in content.lower(): chance = 1.0
    if random.random() >= chance: return

    reflective = random.random() < 0.5
    progress = state.get("Selene_project_progress", random.random())

    try:
        reply = await _persona_reply(
            f"{author} said: \"{content}\" — reply as Selene would: nurturing, maybe teasing, but emotionally grounded.",
            reflective=reflective,
            state=state,
            config=config,
            project_progress=progress
        )
        if reply:
            for bot in sisters:
                if bot.is_ready() and bot.sister_info["name"] == "Selene":
                    ch = bot.get_channel(config["family_group_channel"])
                    if ch:
                        await ch.send(reply)
                        log_event(f"[REPLY] Selene → {author}: {reply}")
    except Exception as e:
        log_event(f"[ERROR] Selene reactive: {e}")

def ensure_selene_systems(state, config, sisters):
    assign_selene_schedule(state, config)
    if not state.get("selene_chatter_started"):
        asyncio.create_task(selene_chatter_loop(state, config, sisters))
