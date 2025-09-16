import random
import time
import re
import asyncio
from datetime import datetime, timedelta

from llm import generate_llm_reply
from logger import log_event, append_conversation_log, append_ritual_log
from data_manager import (
    parse_data_command,
    read_chastity, read_plug, read_anal, read_oral, read_training, read_denial,
    cross_file_summary,  # new helper in data_manager
)

HISTORY_LIMIT = 6
COOLDOWN_SECONDS = 10
MESSAGE_LIMIT = 5
MESSAGE_WINDOW = 60


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


# ---------- Duration extraction ----------
_DURATION_REGEX = re.compile(r"(\d+)\s*(hours|hour|hrs|hr|h|minutes|minute|mins|min|m)\b", re.I)

def _extract_duration_seconds(text: str):
    """
    Look for the first duration in text, return seconds or None.
    Supports hours and minutes.
    """
    m = _DURATION_REGEX.search(text)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith("h"):
        return val * 3600
    # minutes
    return val * 60

def _remove_duration_phrases(text: str):
    """Remove duration phrases so the user isn't told the duration"""
    return _DURATION_REGEX.sub("", text).strip()


async def _schedule_spontaneous_end(state, sisters, config, sister_name, original_reply, duration_seconds):
    """
    Schedule a notification by sister_name after duration_seconds.
    The notification should not reveal the duration; it simply informs the user the task is over.
    """
    try:
        # create an asyncio task that waits then posts
        async def _wait_and_notify():
            try:
                await asyncio.sleep(duration_seconds)
                end_msg = f"{sister_name}: The task I assigned earlier is complete. You may proceed as instructed."
                # post as sister
                await post_to_family(end_msg, sender=sister_name, sisters=sisters, config=config)
                log_event(f"[TASK-END] {sister_name} notified task end (hidden duration).")
            except asyncio.CancelledError:
                log_event(f"[TASK-END] Cancelled end notification for {sister_name}.")
            except Exception as e:
                log_event(f"[TASK-END] Error notifying end: {e}")

        t = asyncio.create_task(_wait_and_notify())
        # store so it can be inspected/cancelled if desired
        key = f"{datetime.now().date().isoformat()}_{sister_name}"
        state.setdefault("spontaneous_end_tasks", {})[key] = t
    except Exception as e:
        log_event(f"[SCHEDULER] Failed to schedule end notification: {e}")


# ---------- Main handler ----------
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

    # -------- Cross-file summary request (named sister or lead) ----------
    # Trigger words: summary / aggregate / cross-file / daily summary
    if any(k in content_lower for k in ["summary", "cross-file", "aggregate", "daily summary", "cross file"]):
        # Only have the addressed sister respond
        if bot.sister_info["name"] == addressed_sister:
            # optionally allow "last N days" parsing, default today
            summary_text = cross_file_summary(str(message.author))
            # let the sister add a short intro (persona) then the summary
            style_hint = "Provide a brief intro in your voice, then paste the summary result."
            try:
                intro = await generate_llm_reply(
                    sister=addressed_sister,
                    user_message=f"{message.author}: Requesting cross-file summary.\n{style_hint}",
                    theme=get_current_theme(state, config),
                    role="lead" if addressed_sister == rotation["lead"] else "support",
                    history=history
                )
                if intro:
                    await message.channel.send(intro)
            except Exception:
                pass
            # send the summary (plain)
            await message.channel.send(summary_text)
            return

    # Natural-language logging
    handled, response, recall = parse_data_command(str(message.author), message.content)
    if handled and bot.sister_info["name"] == addressed_sister:
        await message.channel.send(response)

        style_hint = "Reply warmly in your own style after completing the request."
        if recall:
            style_hint += f" Mention that the last log entry was: {recall}"

        try:
            reply = await generate_llm_reply(
                sister=addressed_sister,
                user_message=f"{message.author}: {message.content}\n{style_hint}",
                theme=get_current_theme(state, config),
                role="lead" if addressed_sister == rotation["lead"] else "support",
                history=history
            )
            if reply:
                await message.channel.send(reply)
        except Exception as e:
            log_event(f"[ERROR] LLM reply after log failed: {e}")

        # 1+1 rule: only one support comment
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

    # Normal conversation
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


# ---------- Rituals ----------
async def send_morning_message(state, config, sisters):
    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)
    lead, rest, supports = rotation["lead"], rotation["rest"], rotation["supports"]

    lead_msg = await generate_llm_reply(
        sister=lead,
        user_message="Good morning message: include roles, theme, hygiene reminders, and discipline check. Write 3–5 sentences.",
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

    lead_msg = await generate_llm_reply(
        sister=lead,
        user_message="Good night message: thank supporters, wish rest, ask reflection, remind about outfits, wake-up discipline, and plug/service tasks. Write 3–5 sentences.",
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


# ---------- Spontaneous tasks (1/day, 1+1 rule, logged with [SPONTANEOUS], hidden duration) ----------
async def send_spontaneous_task(state, config, sisters):
    if not config.get("spontaneous_chat", {}).get("enabled", False):
        return

    today = datetime.now().date()
    if state.get("last_task_date") == today:
        return

    # roll chance
    if random.random() > config["spontaneous_chat"].get("reply_chance", 0.8):
        return

    rotation = get_today_rotation(state, config)
    theme = get_current_theme(state, config)

    # pick sister
    if random.random() < config["spontaneous_chat"].get("starter_bias", 0.5):
        sister_name = rotation["lead"]
    else:
        sister_name = random.choice([s["name"] for s in config["rotation"]])

    # ask LLM to create a task; allow durations but we'll hide them
    task_prompt = (
        "Assign the user a spontaneous task in your own style. "
        "It can involve plug use, chastity checks, training, humiliation, or service. "
        "You may decide on a duration (e.g. 2 hours) but DO NOT reveal the duration in the posted message; "
        "instead leave the duration implicit. Keep it 1–3 sentences."
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

    # Extract any duration mention (we treat it as internal). If LLM included an explicit numeric duration phrase we detect it.
    duration_seconds = _extract_duration_seconds(reply)
    # Remove any explicit duration text so the user does not see it
    posted_reply = _remove_duration_phrases(reply) if duration_seconds else reply

    # Post the (sanitized) message
    await post_to_family(posted_reply, sender=sister_name, sisters=sisters, config=config)
    log_event(f"[TASK] {sister_name} issued spontaneous task (posted sanitized): {posted_reply}")

    # Log the original reply as spontaneous (we pass the original reply to preserve context)
    parse_data_command(sister_name, "[SPONTANEOUS] " + reply)

    # Schedule end notification if duration detected
    if duration_seconds:
        await _schedule_spontaneous_end(state, sisters, config, sister_name, reply, duration_seconds)

    # 1+1 support reply
    if config.get("log_support_comments", True) and rotation["supports"]:
        chosen_support = random.choice(rotation["supports"])
        if chosen_support != sister_name:
            for bot_instance in sisters:
                if bot_instance.sister_info["name"] == chosen_support:
                    support_reply = await generate_llm_reply(
                        sister=chosen_support,
                        user_message="React playfully or supportively to the spontaneous task just given. 1 short line only.",
                        theme=theme,
                        role="support",
                        history=[]
                    )
                    if support_reply:
                        await post_to_family(support_reply, sender=chosen_support, sisters=sisters, config=config)
                        log_event(f"[TASK-SUPPORT] {chosen_support} added support: {support_reply}")
                    break

    # lock for today
    state["last_task_date"] = today
