import time
import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class TestCog(commands.Cog, name='TestCog'):
    """機器人診斷與測試指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==================== 指令 ====================

    @commands.command(name='ping')
    async def ping(self, ctx: commands.Context):
        """測試機器人是否在線，並回報延遲"""
        start = time.perf_counter()
        msg = await ctx.send("🏓 Pong!")
        end = time.perf_counter()

        roundtrip = round((end - start) * 1000)
        ws_latency = round(self.bot.latency * 1000)

        await msg.edit(
            content=(
                f"🏓 Pong!\n"
                f"📡 WebSocket 延遲 : `{ws_latency} ms`\n"
                f"↩️ 訊息來回延遲   : `{roundtrip} ms`"
            )
        )

    @commands.command(name='info')
    async def info(self, ctx: commands.Context):
        """顯示機器人基本資訊與目前狀態"""
        bot = self.bot
        guild_count = len(bot.guilds)
        cog_names = list(bot.cogs.keys())
        command_count = len(bot.commands)
        ws_latency = round(bot.latency * 1000)

        lines = [
            f"🤖 **{bot.user.name}** 狀態報告",
            f"",
            f"🆔 Bot ID       : `{bot.user.id}`",
            f"📡 WebSocket 延遲: `{ws_latency} ms`",
            f"🌐 所在伺服器   : `{guild_count}` 個",
            f"🧩 已載入 Cog   : `{len(cog_names)}` 個 → {', '.join(cog_names)}",
            f"⚙️ 指令總數     : `{command_count}` 個",
        ]
        await ctx.send('\n'.join(lines))


# ==================== 載入函數 ====================

async def setup(bot: commands.Bot):
    await bot.add_cog(TestCog(bot))
