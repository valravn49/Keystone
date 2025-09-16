import random
import time
import re
import asyncio
from datetime import datetime

from llm import generate_llm_reply
from logger import log_event, append_conversation_log, append_ritual_log
from data_manager import parse_data_command, cross_file_summary

# Stub integrations
from bluetooth_integration import connect_device, disconnect_device, send_command, get_status
from media_processing import process_image, process_video, anonymize_image, generate_progress_contact_sheet

HISTORY_LIMIT = 6
COOLDOWN_SECONDS = 10
MESSAGE_LIMIT = 5
MESSAGE_WINDOW = 60

# Persona tone intros
PERSONA_TONES = {
    "Aria": {
        "intro_morning": "Good morning — be gentle with yourself today; remember your duties and care.",
        "intro_night": "Time to rest, sweet one. Reflect kindly on your progress.",
        "intro_end": "That’s enough time. You can stop now, love."
    },
    "Selene": {  # motherly
        "intro_morning": "Good morning, darling — take things slowly and be kind to your body today.",
        "intro_night": "Sleep well, my dear. I’ve been thinking of your care and comfort.",
        "intro_end": "Lovely — your time is up. Come relax and breathe."
    },
    "Cassandra": {
        "intro_morning": "Morning. Be prepared, stay disciplined, and do not slack.",
        "intro_night": "The day is done. Review your discipline and rest ready for tomorrow.",
        "intro_end": "Discipline complete. You may end the task — because I allow it."
    },
    "Ivy": {
        "intro_morning": "Wake up, sleepyhead~ Don’t dawdle or I’ll tease you all day.",
        "intro_night": "Bedtime already? Tuck in, cutie — naughty dreams await.",
        "intro_end": "Hehe~ done! Bet you squirmed — you can stop now 💕"
    }
}


# ---------------- Helpers ----------------
def add_to_history(state, channel_id, author, content):
    if channel_id not in state["history"]:
        state["history"][channel_id] = []
    state["history"][channel_id].append((author, content))
    if len(state["history"][channel_id]) > HISTORY_LIMIT:
        state["history"][channel_id] = state["history"][channel_id][-HISTORY_LIMIT:]


def get_today_rotation(state, config):
    idx = state["rotation_index"] % len(config["rotation"])
    lead = config["rotation"][idx]["name"]
    rest = config["rotation"][(idx + 1) % len(config["rotation"])]["name"]
    supports = [s["name"] for s in config["rotation"] if s["name"] not in [lead, rest]]
    return {"lead": lead, "rest": rest, "supports": supports}


def get_current_theme(state, config):
    today = datetime.now().date()
    if state.get("last_theme_update") is None or (today.weekday() == 0 and state.get("last_theme_update") != today):
        state["theme_index"] = (state.get("theme_index", 0) + 1) % len(config["themes"])
        state["last_theme_update"] = today
    return config["themes"][state.get("theme_index", 0)]


async def post_to_family(message: str, sender, sisters, config):
    for bot in sisters:
        if bot.is_ready():
            if not sender or bot.sister_info["name"] == sender:
                try:
                    channel = bot.get_channel(config["family_group_channel"])
                    if channel:
                        await channel.send(message)
                        log_event(f"{bot.sister_info['name']} posted: {message}")
                    else:
                        print(f"[ERROR] Channel {config['family_group_channel']} not found for {bot.sister_info['name']}")
                except Exception as e:
                    print(f"[ERROR] Failed to send with {bot.sister_info['name']}: {e}")
                break


# ---------------- Duration extraction ----------------
_DURATION_REGEX = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m)\b", re.I)

def _extract_duration_seconds(text: str):
    m = _DURATION_REGEX.search(text)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return val * 3600
    return val * 60

def _remove_duration_phrases(text: str):
    return _DURATION_REGEX.sub("", text).strip()


async def _schedule_spontaneous_end(state, sisters, config, sister_name, duration_seconds):
    """
    Persona-specific end notifications, mixing fixed persona line and LLM expansions.
    """
    async def _wait_and_notify():
        try:
            await asyncio.sleep(duration_seconds)
            persona = PERSONA_TONES.get(sister_name, {})
            intro = persona.get("intro_end", "Your task is complete. You may stop now.")

            if random.random() < 0.5:
                line = intro
            else:
                try:
                    expansion = await generate_llm_reply(
                        sister=sister_name,
                        user_message=f"{sister_name}: Expand this 1-line closing in your voice: \"{intro}\" Keep it 1 short sentence.",
                        theme=None,
                        role="lead",
                        history=[]
                    )
                    line = expansion if expansion else intro
                except Exception:
                    line = intro

            end_msg = f"{sister_name}: {line}"
            await post_to_family(end_msg, sender=sister_name, sisters=sisters, config=config)
            log_event(f"[TASK-END] {sister_name} notified task end (persona-mixed).")
        except asyncio.CancelledError:
            log_event(f"[TASK-END] Cancelled end notification for {sister_name}.")
        except Exception as e:
            log_event(f"[TASK-END] Error notifying end: {e}")

    t = asyncio.create_task(_wait_and_notify())
    key = f"{datetime.now().date().isoformat()}_{sister_name}"
    state.setdefault("spontaneous_end_tasks", {})[key] = t


# ---------------- Main handler ----------------
async def handle_sister_message(bot, message, state, config, sisters):
    if message.author == bot.user:
        return

    channel_id = message.channel.id
    content_lower = message.content.lower()
    now = datetime.now()

    if message.channel.id != config["family_group_channel"]:
        return
    if message.content.startswith("🌅") or message.content.startswith("🌙"):
        return

    # Cooldown
    last = state["last_reply_time"].get(channel_id)
    if last and (now - last).total_seconds() < COOLDOWN_SECONDS:
        return

    # Quota
    counts = state["message_counts"].setdefault(channel_id, [])
    now_ts = time.time()
    counts = [t for t in counts if now_ts - t <= MESSAGE_WINDOW]
    if len(counts) >= MESSAGE_LIMIT:
        state["message_counts"][channel_id] = counts
        return
    state["message_counts"][channel_id] = counts

    add_to_history(state, channel_id, str(message.author), message.content)
    history = state["history"].get(channel_id, [])

    rotation = get_today_rotation(state, config)

    # Determine addressed sister or default lead
    addressed_sister = None
    for s in config["rotation"]:
        if s["name"].lower() in content_lower:
            addressed_sister = s["name"]
            break
    if not addressed_sister:
        addressed_sister = rotation["lead"]

    # -------- Cross-file summary --------
    if any(k in content_lower for k in ["summary", "cross-file", "aggregate", "daily summary", "cross file"]):
        if bot.sister_info["name"] == addressed_sister:
            summary_text = cross_file_summary(str(message.author))
            intro = await generate_llm_reply(
                sister=addressed_sister,
                user_message=f"{message.author}: Requesting cross-file summary.\nProvide a brief intro then the summary.",
                theme=get_current_theme(state, config),
                role="lead" if addressed_sister == rotation["lead"] else "support",
                history=history
            )
            if intro:
                await message.channel.send(intro)
            await message.channel.send(summary_text)
            return

    # -------- Bluetooth & Media stubs --------
    if "bluetooth" in content_lower or "device" in content_lower:
        if bot.sister_info["name"] == addressed_sister:
            status = get_status("toy")
            await message.channel.send(
                f"{addressed_sister}: Pretend Bluetooth status → connected={status['connected']}, battery={status['battery']}"
            )
            return

    if any(k in content_lower for k in ["image", "photo", "picture", "video"]):
        if bot.sister_info["name"] == addressed_sister:
            await message.channel.send(
                f"{addressed_sister}: I can *pretend* to process media, but right now it’s just a placeholder."
            )
            return

    # -------- Natural-language logging --------
    handled, response, recall = parse_data_command(str(message.author), message.content)
    if handled and bot.sister_info["name"] == addressed_sister:
        await message.channel.send(response)

        style_hint = "Reply warmly in your own style after completing the request."
        if recall:
            style_hint += f" Mention that the last log entry was: {recall}"

        reply = await generate_llm_reply(
            sister=addressed_sister,
            user_message=f"{message.author}: {message.content}\n{style_hint}",
            theme=get_current_theme(state, config),
            role="lead" if addressed_sister == rotation["lead"] else "support",
            history=history
        )
        if reply:
            await message.channel.send(reply)

        # 1+1 rule
        if config.get("log_support_comments", True) and rotation["supports"]:
            chosen_support = random.choice(rotation["supports"])
            if chosen_support != addressed_sister:
                for bot_instance in sisters:
                    if bot_instance.sister_info["name"] == chosen_support:
                        support_reply = await generate_llm_reply(
                            sister=chosen_support,
                            user_message=f"{message.author}: {message.content}\nShort playful supportive comment.",
                            theme=get_current_theme(state, config),
                            role="support",
                            history=history
                        )
                        if support_reply:
                            await message.channel.send(support_reply)
                        break
        return

    # -------- Normal conversation --------
    name = bot.sister_info["name"]
    role = None
    should_reply = False
    if name == rotation["lead"]:
        role = "lead"; should_reply = True
    elif name in rotation["supports"]:
        role = "support"; should_reply = random.random() < 0.6
    elif name == rotation["rest"]:
        role = "rest"; should_reply = random.random() < 0.2

    if should_reply and role:
        if not history:
            return
        weights = list(range(len(history), 0, -1))
        author, content = random.choices(history, weights=weights, k=1)[0]

        style_hint = {
            "lead": "Reply in 2–4 sentences, guiding the conversation.",
            "support": "Reply in 1–2 sentences, playful or supportive.",
            "rest": "Reply briefly, 1 short remark."
        }[role]

        reply = await generate_llm_reply(
            sister=name,
            user_message=f"{author}: {content}\n{style_hint}",
            theme=get_current_theme(state, config),
            role=role,
            history=history
        )
        if reply:
            await message.channel.send(reply)
            log_event(f"[CHAT] {name} ({role}) → {author}: {reply}")
            append_conversation_log(
                sister=name,
                role=role,
                theme=get_current_theme(state, config),
                user_message=content,
                content=reply
            )
            state["last_reply_time"][channel_id] = now
            counts.append(now_ts)


# ---------------- Rituals ----------------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_morning")

    if intro:
        try:
            lead_msg = await generate_llm_reply(
                sister=lead,
                user_message=f"{lead}: Use this opening as your tone and expand into a 3-5 sentence morning message. \"{intro}\"",
                theme=theme,
                role="lead",
                history=[]
            )
            if not lead_msg:
                lead_msg = intro
        except Exception:
            lead_msg = intro
    else:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message="Good morning message: include theme, hygiene reminders, and discipline check. Write 3–5 sentences.",
            theme=theme,
            role="lead",
            history=[]
        )

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.7:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive morning comment, 1–2 sentences.",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.2:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Quiet short morning remark, 1 sentence.",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    state["rotation_index"] = state.get("rotation_index", 0) + 1
    log_event(f"[SCHEDULER] Morning message completed with {lead} as lead")


async def send_night_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    persona = PERSONA_TONES.get(lead, {})
    intro = persona.get("intro_night")

    if intro:
        try:
            lead_msg = await generate_llm_reply(
                sister=lead,
                user_message=f"{lead}: Use this opening as your tone and expand into a 3-5 sentence night message. \"{intro}\"",
                theme=theme,
                role="lead",
                history=[]
            )
            if not lead_msg:
                lead_msg = intro
        except Exception:
            lead_msg = intro
    else:
        lead_msg = await generate_llm_reply(
            sister=lead,
            user_message="Good night message: thank supporters, ask reflection, remind about outfits, and plug/service tasks. Write 3–5 sentences.",
            theme=theme,
            role="lead",
            history=[]
        )

    await post_to_family(lead_msg, sender=lead, sisters=sisters, config=config)
    append_ritual_log(lead, "lead", theme, lead_msg)

    for s in supports:
        if random.random() < 0.6:
            reply = await generate_llm_reply(
                sister=s,
                user_message="Short supportive night comment, 1–2 sentences.",
                theme=theme,
                role="support",
                history=[]
            )
            if reply:
                await post_to_family(reply, sender=s, sisters=sisters, config=config)
                append_ritual_log(s, "support", theme, reply)

    if random.random() < 0.15:
        rest_reply = await generate_llm_reply(
            sister=rest,
            user_message="Brief quiet night remark, 1 sentence.",
            theme=theme,
            role="rest",
            history=[]
        )
        if rest_reply:
            await post_to_family(rest_reply, sender=rest, sisters=sisters, config=config)
            append_ritual_log(rest, "rest", theme, rest_reply)

    log_event(f"[SCHEDULER] Night message completed with {lead} as lead")


# ---------------- Spontaneous tasks ----------------
async def send_spontaneous_task(state, config, sisters):
    if not config.get("spontaneous_chat", {}).get("enabled", False):
        return

    today = datetime.now().date()
    if state.get("last_task_date") == today:
        return

    if random.random() > config["spontaneous_chat"].get("reply_chance", 0.8):
        return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)

    if random.random() < config["spontaneous_chat"].get("starter_bias", 0.5):
        sister_name = rotation["lead"]
    else:
        sister_name = random.choice([s["name"] for s in config["rotation"]])

    task_prompt = (
        "Assign the user a spontaneous task in your own style. "
        "It can involve plug use, chastity checks, training, humiliation, service, "
        "Bluetooth toy/device checks, or asking for a media proof task (image/video). "
        "If you choose Bluetooth or media, phrase it naturally. "
        "You may decide on a duration (e.g. 2 hours) but DO NOT reveal the duration in the posted message. "
        "Keep it 1–3 sentences."
    )

    reply = await generate_llm_reply(
        sister=sister_name,
        user_message=task_prompt,
        theme=theme,
        role="lead",
        history=[]
    )

    if not reply:
        return

    duration_seconds = _extract_duration_seconds(reply)
    posted_reply = _remove_duration_phrases(reply) if duration_seconds else reply

    await post_to_family(posted_reply, sender=sister_name, sisters=sisters, config=config)
    log_event(f"[TASK] {sister_name} issued spontaneous task: {posted_reply}")

    parse_data_command(sister_name, "[SPONTANEOUS]
