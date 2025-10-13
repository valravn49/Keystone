import os
import discord
from discord.ext import commands

from logger import log_event

# ✅ Correct: Intents are from `discord`, not `commands`
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True


class WillBot(commands.Bot):
    def __init__(self, will_info):
        super().__init__(command_prefix="!", intents=intents)
        self.sister_info = will_info

    async def setup_hook(self):
        log_event("[BOOT] Will bot setup hook initialized.")
