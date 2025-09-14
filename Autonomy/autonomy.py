import random
import asyncio
from llm import generate_llm_reply
from .personality import PersonalityManager
from logger import log_event

class AutonomyEngine:
    def __init__(self, sisters, theme_getter):
        self.sisters = sisters
        self.get_theme = theme_getter

    async def random_conversation(self):
        """
        Sisters converse randomly about leisure, beliefs, or curiosity.
        Not triggered by user messages.
        """
        if not self.sisters:
            return

        participants = random.sample(self.sisters, k=random.randint(2, len(self.sisters)))
        theme = self.get_theme()

        starter = participants[0]
        responder = participants[1]

        starter_pm = PersonalityManager(starter.sister_info["name"])
        responder_pm = PersonalityManager(responder.sister_info["name"])

        starter_prompt = f"Start a casual conversation unrelated to rituals. Mention something about leisure, curiosity, or your own feelings."
        responder_prompt = f"Reply naturally to the starter in your own tone. Keep it conversational."

        try:
            starter_msg = await generate_llm_reply(
                sister=starter_pm.name,
                user_message=starter_prompt,
                theme=theme,
                role="autonomy"
            )
            if starter_msg:
                await starter.get_channel(starter.sister_info.get("dm_channel_id")).send(starter_msg)
                log_event(f"[AUTONOMY] {starter_pm.name} started: {starter_msg}")

            responder_msg = await generate_llm_reply(
                sister=responder_pm.name,
                user_message=starter_msg + "\nRespond casually.",
                theme=theme,
                role="autonomy"
            )
            if responder_msg:
                await responder.get_channel(responder.sister_info.get("dm_channel_id")).send(responder_msg)
                log_event(f"[AUTONOMY] {responder_pm.name} replied: {responder_msg}")

        except Exception as e:
            log_event(f"[AUTONOMY ERROR] {e}")

    async def tick(self):
        """
        Called periodically (e.g., every 1–2 hours).
        Sometimes triggers a conversation, sometimes drifts personality.
        """
        if random.random() < 0.5:
            await self.random_conversation()

        for bot in self.sisters:
            pm = PersonalityManager(bot.sister_info["name"])
            drifted = pm.drift()
            log_event(f"[DRIFT] {pm.name} drift update: {drifted}")
