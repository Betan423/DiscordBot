import sys  # 1. 新增引入 sys 模組來讀取命令列參數
import asyncio
import logging
import socket
from pathlib import Path

import discord
from discord.ext import commands

from cogs.music import MusicCog
from cogs.music import load_random_progress
from cogs.test import TestCog
from cogs.fun import FunCog
from cogs.achievements import AchievementCog

# ==================== 日誌設置 ====================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== 路徑設定 ====================

BASE_DIR = Path(__file__).parent

# ==================== 常數 ====================

ALLOWED_CHANNEL_ID = 1464851408552722574
ANNOUNCEMENT_CHANNEL_ID = 1251174751225905326


# ==================== Bot 類別 ====================

class MusicBot(commands.Bot):
    """音樂機器人主類別"""

    # 2. 讓 Bot 初始化時可以接收 is_test_mode 參數
    def __init__(self, is_test_mode=False):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(command_prefix='&', intents=intents)
        self.is_test_mode = is_test_mode  # 將測試模式狀態存起來

    async def setup_hook(self):
        """Bot 啟動時載入所有 Cog"""
        await self.add_cog(MusicCog(self))
        logger.info("已載入 MusicCog")
        await self.add_cog(TestCog(self))
        logger.info("已載入 TestCog")
        await self.add_cog(FunCog(self))
        logger.info("已載入 FunCog")
        await self.add_cog(AchievementCog(self))
        logger.info("已載入 AchievementCog")

    async def on_ready(self):
        """Bot 就緒事件"""
        await self.wait_until_ready()
        logger.info(f'機器人已登入為 {self.user}')

        # 取得目前 IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            current_ip = s.getsockname()[0]
            s.close()
        except Exception:
            current_ip = "無法偵測 IP"

        print(f'機器人已登入：{self.user}')
        print(f'目前 IP 位址：{current_ip}')

        # 通知上線頻道 (管理員/開發者專用頻道，這個通常保留作為除錯用)
        channel = self.get_channel(ALLOWED_CHANNEL_ID)
        if channel:
            await channel.send(f"✅ **已上線！**\n📡 目前樹莓派 IP: `{current_ip}`")

        # 載入隨機播放進度到 MusicCog
        music_cog: MusicCog = self.cogs.get('MusicCog')
        if music_cog:
            loaded = load_random_progress()
            if loaded:
                music_cog.random_state.update(loaded)
                logger.info(f"已載入 {len(loaded)} 個伺服器的播放進度")

        # 公告頻道上線訊息
        ann_channel = self.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if ann_channel:
            # 3. 判斷如果不是測試模式，才發送公告
            if not self.is_test_mode:
                await ann_channel.send("出發！前進！")
            else:
                logger.info("🔧 測試模式啟動：略過發送『出發！前進！』公告")
        else:
            logger.warning("找不到公告頻道")

    async def on_member_remove(self, member: discord.Member):
        """成員離開伺服器事件"""
        channel = self.get_channel(ANNOUNCEMENT_CHANNEL_ID)
        if channel:
            await channel.send(f'@everyone {member.name} 已退出伺服器。')


# ==================== 主程式 ====================

def main():
    # 4. 檢查終端機指令中是否有包含 "test" 參數
    is_test = "test" in sys.argv

    token_file = BASE_DIR / "token.txt"
    try:
        if not token_file.exists():
            raise FileNotFoundError("找不到 token.txt 文件")
        token = token_file.read_text().strip()
        if not token:
            raise ValueError("token.txt 文件是空的")
            
        logger.info("正在啟動機器人...")
        # 將判斷結果傳入 Bot
        bot = MusicBot(is_test_mode=is_test)
        bot.run(token)
    except Exception as e:
        logger.error(f"啟動失敗: {e}")
        exit(1)


if __name__ == "__main__":
    main()