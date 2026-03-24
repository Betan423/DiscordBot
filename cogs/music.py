import asyncio
import json
import logging
import os
import random
import re
import subprocess
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import discord
import yt_dlp as youtube_dl
from discord.ext import commands

logger = logging.getLogger(__name__)

# ==================== 路徑設定 ====================

BASE_DIR = Path(__file__).parent.parent
DOWNLOAD_PATH = BASE_DIR / "downloads"
DOWNLOAD_PATH.mkdir(exist_ok=True)
PROGRESS_FILE = BASE_DIR / "random_progress.json"

# ==================== FFmpeg 路徑 ====================

FFMPEG_PATH = BASE_DIR / "ffmpeg.exe"
FFPROBE_PATH = BASE_DIR / "ffprobe.exe"

if not FFMPEG_PATH.exists():
    FFMPEG_PATH = BASE_DIR / "ffmpeg"
    FFPROBE_PATH = BASE_DIR / "ffprobe"

if not FFMPEG_PATH.exists():
    logger.warning(f"FFmpeg 不存在於 {FFMPEG_PATH}，將使用系統 PATH 中的 ffmpeg")
    FFMPEG_PATH = "ffmpeg"
    FFPROBE_PATH = "ffprobe"
else:
    logger.info(f"使用本地 FFmpeg: {FFMPEG_PATH}")
    FFMPEG_PATH = str(FFMPEG_PATH)
    FFPROBE_PATH = str(FFPROBE_PATH)

# ==================== 常數 ====================

ALLOWED_CHANNEL_ID = 1464851408552722574
ANNOUNCEMENT_CHANNEL_ID = 1251174751225905326
LOCAL_SOUND_PATH = BASE_DIR / "gogo.ogg"
AUDIO_EXTENSIONS = ('.mp3', '.webm', '.m4a', '.wav', '.mp4', '.ogg')

ENABLE_VOLUME_NORMALIZATION = True
TARGET_VOLUME = 0.7

# ==================== yt-dlp 設定 ====================

YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'outtmpl': str(DOWNLOAD_PATH / '%(title)s.%(ext)s'),
    'restrictfilenames': False,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extractor_args': {
        'youtube': {
            'player_client': ['android', 'ios'],
        }
    }
}

FFMPEG_OPTIONS = {
    'executable': FFMPEG_PATH,
    'options': '-vn -af "loudnorm=I=-16:TP=-1.5:LRA=11"'
}

# loudnorm 說明：
# I=-16  : 目標整合響度 (LUFS)，-16 是廣播標準
# TP=-1.5: 真實峰值限制 (dBTP)
# LRA=11 : 響度範圍目標

ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)


# ==================== 進度管理（模組層級，供 bot.py 匯入） ====================

def save_random_progress(random_state: dict) -> None:
    """保存隨機播放進度至 JSON"""
    try:
        progress_data = {}
        for guild_id, state in random_state.items():
            if state['active']:
                progress_data[str(guild_id)] = {
                    'folder': str(state['folder']),
                    'remaining': [str(f) for f in state['remaining']],
                    'last_updated': datetime.now().isoformat()
                }
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存 {len(progress_data)} 個伺服器的進度")
    except Exception as e:
        logger.error(f"保存進度失敗: {e}")


def load_random_progress() -> dict:
    """從 JSON 讀取隨機播放進度"""
    try:
        if not PROGRESS_FILE.exists():
            logger.info("進度文件不存在，使用空白進度")
            return {}
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            progress_data = json.load(f)
        loaded_state = {}
        for guild_id_str, data in progress_data.items():
            guild_id = int(guild_id_str)
            folder_path = Path(data['folder'])
            if not folder_path.exists():
                logger.warning(f"資料夾不存在，跳過: {folder_path}")
                continue
            remaining_files = [
                Path(fp) for fp in data['remaining'] if Path(fp).exists()
            ]
            if remaining_files:
                loaded_state[guild_id] = {
                    'active': False,
                    'folder': folder_path,
                    'remaining': remaining_files,
                    'last_updated': data.get('last_updated', '')
                }
        logger.info(f"已讀取 {len(loaded_state)} 個伺服器的進度")
        return loaded_state
    except Exception as e:
        logger.error(f"讀取進度失敗: {e}")
        return {}


def clear_random_progress(guild_id: int = None) -> None:
    """清除進度（可指定伺服器，或傳入 None 清除全部）"""
    try:
        if guild_id is None:
            if PROGRESS_FILE.exists():
                PROGRESS_FILE.unlink()
            logger.info("已清除所有進度")
        else:
            if PROGRESS_FILE.exists():
                with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                if str(guild_id) in progress_data:
                    del progress_data[str(guild_id)]
                    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
                        json.dump(progress_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"已清除伺服器 {guild_id} 的進度")
    except Exception as e:
        logger.error(f"清除進度失敗: {e}")


# ==================== 輔助函數 ====================

def get_video_id(url: str) -> Optional[str]:
    """從 URL 提取 YouTube 影片 ID"""
    patterns = [
        r'(?:v=|/)([0-9A-Za-z_-]{11}).*',
        r'(?:embed/)([0-9A-Za-z_-]{11})',
        r'(?:watch\?v=)([0-9A-Za-z_-]{11})'
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def get_bilibili_id(url: str) -> Optional[str]:
    """從 URL 提取 Bilibili BV/AV 號"""
    for pattern in [r'(?:BV)([0-9A-Za-z]{10})', r'(?:av|AV)(\d+)']:
        if re.search(pattern, url):
            full = re.search(r'(BV[0-9A-Za-z]{10}|[aA][vV]\d+)', url)
            return full.group(1) if full else None
    return None


def find_existing_file(video_id: str) -> Optional[Path]:
    """在 downloads 資料夾查找已快取的檔案"""
    if not video_id:
        return None
    for file in DOWNLOAD_PATH.iterdir():
        if video_id in file.name and file.suffix in AUDIO_EXTENSIONS:
            return file
    return None


def get_audio_duration(file_path: str) -> int:
    """取得音訊長度（秒）"""
    try:
        result = subprocess.run(
            [FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=5
        )
        return int(float(result.stdout.strip()))
    except Exception as e:
        logger.warning(f"無法獲取音頻長度: {e}")
        return 0


def format_time(seconds: int) -> str:
    """將秒數格式化為 MM:SS"""
    return f"{seconds // 60}:{str(seconds % 60).zfill(2)}"


def create_progress_bar(current: int, total: int, length: int = 20) -> str:
    """建立文字進度條"""
    if total <= 0:
        return "-" * length
    pos = min(int((current / total) * length), length - 1)
    return "-" * pos + "🔘" + "-" * (length - pos - 1)


def shuffle_smartly(songs: List[Path]) -> List[Path]:
    """智能洗牌：盡量避免前綴相似的歌曲連續播放"""
    if len(songs) <= 2:
        random.shuffle(songs)
        return songs
    shuffled = songs.copy()
    random.shuffle(shuffled)
    for _ in range(50):
        needs_adjustment = False
        for i in range(len(shuffled) - 1):
            a, b = shuffled[i].stem.lower(), shuffled[i + 1].stem.lower()
            if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:
                needs_adjustment = True
                if i + 2 < len(shuffled):
                    shuffled[i + 1], shuffled[i + 2] = shuffled[i + 2], shuffled[i + 1]
        if not needs_adjustment:
            break
    return shuffled


# ==================== YTDLSource ====================

class YTDLSource(discord.PCMVolumeTransformer):
    """音訊來源：包裝 FFmpegPCMAudio 並附加元資料"""

    def __init__(self, source, *, data, volume=None, file_path=None):
        if volume is None:
            volume = TARGET_VOLUME if ENABLE_VOLUME_NORMALIZATION else 0.5
        super().__init__(source, volume)
        self.start_time = time.time()
        self.data = data
        self.title = data.get('title', 'Unknown')
        self.file_path = file_path

    @classmethod
    async def from_url(cls, url: str, *, loop=None):
        """從 URL 下載並建立音訊來源"""
        loop = loop or asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=True)
            )
            if 'entries' in data:
                data = data['entries'][0]
            file_path = ytdl.prepare_filename(data)
            return cls(
                discord.FFmpegPCMAudio(file_path, **FFMPEG_OPTIONS),
                data=data, file_path=file_path
            )
        except Exception as e:
            logger.error(f"從 URL 載入失敗: {e}")
            raise

    @classmethod
    async def from_file(cls, file_path: str, *, loop=None):
        """從本地檔案建立音訊來源"""
        try:
            return cls(
                discord.FFmpegPCMAudio(str(file_path), **FFMPEG_OPTIONS),
                data={'title': Path(file_path).name},
                file_path=str(file_path)
            )
        except Exception as e:
            logger.error(f"從文件載入失敗: {e}")
            raise


# ==================== MusicCog ====================

class MusicCog(commands.Cog, name='MusicCog'):
    """音樂播放功能 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.song_queue: deque = deque()
        # random_state 結構: {guild_id: {'active': bool, 'folder': Path, 'remaining': list}}
        self.random_state: dict = {}

    # ==================== 內部輔助方法 ====================

    async def _play_local_sound(self, voice_client: discord.VoiceClient) -> None:
        """播放進場音效，等待播放完成後才返回"""
        if not LOCAL_SOUND_PATH.exists():
            logger.warning(f"音效文件不存在: {LOCAL_SOUND_PATH}")
            return
        try:
            audio_source = discord.FFmpegPCMAudio(str(LOCAL_SOUND_PATH))
            voice_client.play(audio_source)
            while voice_client.is_playing():
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"播放本地音效失敗: {e}")

    async def _play_next(self, ctx: commands.Context) -> None:
        """播放下一首（先從 song_queue，再從隨機列表）"""
        guild_id = ctx.guild.id

        if not ctx.voice_client:
            logger.warning("play_next: Voice client 不存在")
            return
        if not ctx.voice_client.is_connected():
            logger.warning("play_next: Voice client 未連接")
            return
        if ctx.voice_client.is_playing():
            logger.warning("play_next: 已經在播放中，忽略")
            return

        if self.song_queue:
            player = self.song_queue.popleft()
            player.start_time = time.time()

            def after_song(error):
                if error:
                    logger.error(f'播放錯誤: {error}')
                asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop)

            try:
                ctx.voice_client.play(player, after=after_song)
                await ctx.send(f"正在播放: {player.title}")
                logger.info(f"播放佇列歌曲: {player.title}")
            except Exception as e:
                logger.error(f"播放失敗: {e}")
                await ctx.send(f"❌ 播放失敗: {e}")
            return

        if guild_id in self.random_state and self.random_state[guild_id]['active']:
            await self._continue_random_play(ctx)
        else:
            await ctx.send("播放列表已經結束！")

    async def _download_song(self, url: str) -> Optional[str]:
        """非同步下載歌曲，返回本地檔案路徑"""
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: ytdl.extract_info(url, download=True)
            )
            if 'entries' in data:
                data = data['entries'][0]
            return ytdl.prepare_filename(data)
        except Exception as e:
            logger.error(f"下載失敗: {e}")
            return None

    async def _check_voice_channel_empty(self, ctx: commands.Context) -> bool:
        """若語音頻道只剩機器人則自動離開，回傳 True"""
        for vc in self.bot.voice_clients:
            if len(vc.channel.members) == 1:
                await vc.disconnect()
                await ctx.send("众人将与一人离别,唯其人将觐见奇迹，此乃命运使然")
                return True
        return False

    async def _continue_random_play(self, ctx: commands.Context) -> None:
        """從隨機播放列表選下一首並播放"""
        guild_id = ctx.guild.id
        logger.info(f"continue_random_play 被調用，guild_id={guild_id}")

        if guild_id not in self.random_state or not self.random_state[guild_id]['active']:
            logger.warning(f"隨機播放未啟用或狀態不存在，guild_id={guild_id}")
            return

        state = self.random_state[guild_id]
        voice_client = ctx.voice_client

        if not voice_client:
            logger.warning("Voice client 不存在")
            return
        if not voice_client.is_connected():
            logger.error("Voice client 未連接到語音頻道")
            self.random_state[guild_id]['active'] = False
            await ctx.send("❌ 語音連接已斷開，隨機播放已停止")
            return
        if voice_client.is_playing():
            logger.warning("已經在播放中，忽略此次調用")
            return
        if await self._check_voice_channel_empty(ctx):
            self.random_state[guild_id]['active'] = False
            logger.info("頻道已空，停止播放")
            return

        # 若列表已空，重新洗牌
        if not state['remaining']:
            logger.info("歌曲播放完畢，重新洗牌")
            all_songs = [
                f for f in state['folder'].iterdir()
                if f.suffix.lower() in AUDIO_EXTENSIONS
            ]
            if not all_songs:
                await ctx.send("資料夾中沒有歌曲了！")
                self.random_state[guild_id]['active'] = False
                return
            state['remaining'] = shuffle_smartly(all_songs)
            await ctx.send("🔄 播放列表已重新洗牌！")

        selected_song = state['remaining'].pop(0)
        logger.info(f"選擇歌曲: {selected_song.name}")

        if not selected_song.exists():
            logger.warning(f"文件不存在，跳過: {selected_song.name}")
            await ctx.send(f"⚠️ 文件不存在，跳過: {selected_song.name}")
            await self._continue_random_play(ctx)
            return

        try:
            player = await YTDLSource.from_file(selected_song, loop=self.bot.loop)
            player.start_time = time.time()

            def after_play(error):
                if error:
                    logger.error(f"播放錯誤: {error}")
                asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop)

            if voice_client.is_playing():
                logger.info("停止當前播放")
                voice_client.stop()
                await asyncio.sleep(1)

            if not voice_client.is_connected():
                logger.error("播放前發現未連接")
                self.random_state[guild_id]['active'] = False
                return

            voice_client.play(player, after=after_play)
            logger.info(f"開始播放: {player.title}")
            save_random_progress(self.random_state)

            await ctx.send(
                f"🎲 隨機播放: {player.title}\n"
                f"📝 剩餘 {len(state['remaining'])} 首歌曲"
            )
        except Exception as e:
            logger.error(f"播放失敗: {e}")
            await ctx.send("播放失敗，跳過此歌曲")
            await self._continue_random_play(ctx)

    async def _handle_youtube_link(self, message: discord.Message, url: str) -> None:
        """處理頻道中貼上的 YouTube 連結"""
        guild_id = message.guild.id

        if not message.guild.voice_client:
            if not message.author.voice:
                await message.channel.send("你必須先加入一個語音頻道！")
                return
            voice_client = await message.author.voice.channel.connect()
            await self._play_local_sound(voice_client)

        async with message.channel.typing():
            await message.channel.send(f"🎵 正在處理: `{url}`")

            video_id = get_video_id(url)
            existing_file = find_existing_file(video_id) if video_id else None

            if existing_file:
                file_path = existing_file
                await message.channel.send(f"🗂️ 使用快取檔案: `{existing_file.name}`")
            else:
                file_path = await self._download_song(url)
                if not file_path:
                    await message.channel.send("❌ 下載失敗，請稍後再試。")
                    return
                await message.channel.send("✅ 下載完成！")

            try:
                player = await YTDLSource.from_file(file_path, loop=self.bot.loop)
                self.song_queue.append(player)
                is_random_active = guild_id in self.random_state and self.random_state[guild_id]['active']

                if is_random_active:
                    await message.channel.send(
                        f"🎵 已新增至插播列表: `{player.title}`\n"
                        f"💡 播完後將繼續隨機播放"
                    )
                else:
                    await message.channel.send(f"已新增至播放列表: `{player.title}`")

                if not message.guild.voice_client.is_playing():
                    ctx = await self.bot.get_context(message)
                    await self._play_next(ctx)
                elif is_random_active:
                    await message.channel.send(
                        f"📍 插播順序: 還有 {len(self.song_queue)} 首歌曲在您前面"
                    )
            except Exception as e:
                logger.error(f"創建播放器失敗: {e}")
                await message.channel.send("❌ 無法播放此文件。")

    async def _handle_bilibili_link(self, message: discord.Message, url: str) -> None:
        """處理頻道中貼上的 Bilibili 連結"""
        guild_id = message.guild.id

        if not message.guild.voice_client:
            if not message.author.voice:
                await message.channel.send("你必須先加入一個語音頻道！")
                return
            voice_client = await message.author.voice.channel.connect()
            await self._play_local_sound(voice_client)

        async with message.channel.typing():
            await message.channel.send(f"📺 正在處理 Bilibili: `{url}`")

            bili_id = get_bilibili_id(url)
            existing_file = find_existing_file(bili_id) if bili_id else None

            if existing_file:
                file_path = existing_file
                await message.channel.send(f"🗂️ 使用快取檔案: `{existing_file.name}`")
            else:
                bili_opts = YTDL_OPTIONS.copy()
                bili_opts['extractor_args'] = {}
                bili_opts['http_headers'] = {
                    'Referer': 'https://www.bilibili.com',
                    'User-Agent': (
                        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                        'Chrome/120.0.0.0 Safari/537.36'
                    ),
                }
                bili_ytdl = youtube_dl.YoutubeDL(bili_opts)
                loop = asyncio.get_event_loop()
                try:
                    data = await loop.run_in_executor(
                        None, lambda: bili_ytdl.extract_info(url, download=True)
                    )
                    if 'entries' in data:
                        data = data['entries'][0]
                    file_path = bili_ytdl.prepare_filename(data)
                except Exception as e:
                    logger.error(f"Bilibili 下載失敗: {e}")
                    await message.channel.send(
                        f"❌ Bilibili 下載失敗: {e}\n"
                        "💡 提示：部分影片需要登入帳號，請確認 yt-dlp 已更新至最新版本。"
                    )
                    return

                if not file_path:
                    await message.channel.send("❌ 下載失敗，請稍後再試。")
                    return
                await message.channel.send("✅ Bilibili 音訊下載完成！")

            try:
                player = await YTDLSource.from_file(file_path, loop=self.bot.loop)
                self.song_queue.append(player)
                is_random_active = guild_id in self.random_state and self.random_state[guild_id]['active']

                if is_random_active:
                    await message.channel.send(
                        f"📺 已新增 Bilibili 至插播列表: `{player.title}`\n"
                        f"💡 播完後將繼續隨機播放"
                    )
                else:
                    await message.channel.send(f"📺 已新增至播放列表: `{player.title}`")

                if not message.guild.voice_client.is_playing():
                    ctx = await self.bot.get_context(message)
                    await self._play_next(ctx)
                elif is_random_active:
                    await message.channel.send(
                        f"📍 插播順序: 還有 {len(self.song_queue)} 首歌曲在您前面"
                    )
            except Exception as e:
                logger.error(f"創建 Bilibili 播放器失敗: {e}")
                await message.channel.send("❌ 無法播放此 Bilibili 音訊。")

    # ==================== 事件監聽 ====================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """監聽訊息：處理連結自動播放與無前綴指令"""
        if message.author == self.bot.user:
            return

        # 特殊頻道自動回應
        if (message.channel.id == ANNOUNCEMENT_CHANNEL_ID and
                message.content == '出發！前進！'):
            await message.channel.send("操你媽學三小")
            return

        # YouTube / Bilibili 連結自動偵測（限指定頻道）
        if message.channel.id == ALLOWED_CHANNEL_ID:
            yt_match = re.search(
                r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w-]+)',
                message.content
            )
            if yt_match:
                await self._handle_youtube_link(message, yt_match.group(0))
                return

            bili_match = re.search(
                r'(https?://(?:www\.)?(?:bilibili\.com/video/|b23\.tv/)[\w/?=&%-]+)',
                message.content
            )
            if bili_match:
                await self._handle_bilibili_link(message, bili_match.group(0))
                return

        # 無前綴短指令（所有頻道可用）
        content = message.content.strip()

        simple_commands = {
            's': self._cmd_skip,
            'q': self._cmd_queue,
            'l': self._cmd_leave,
            'np': self._cmd_nowplaying,
            'ds': self._cmd_delete_song,
            'unrandom': self._cmd_unrandom,
            'ur': self._cmd_unrandom,
            'urd': self._cmd_unrandom,
            'status': self._cmd_status,
            'reshuffle': self._cmd_reshuffle,
            'clear': self._cmd_clear,
            'progress': self._cmd_progress,
            'reset_progress': self._cmd_reset_progress,
        }

        if content in simple_commands:
            ctx = await self.bot.get_context(message)
            await simple_commands[content](ctx)
            return

        random_match = re.fullmatch(r'^random(?:\s+(.*))?$', content)
        if random_match:
            ctx = await self.bot.get_context(message)
            folder = random_match.group(1)
            await self._cmd_random(ctx, folder.strip() if folder else '')
            return

        volume_match = re.fullmatch(r'^(?:volume|vol)(?:\s+(\d+))?$', content, re.IGNORECASE)
        if volume_match:
            ctx = await self.bot.get_context(message)
            vol_str = volume_match.group(1)
            await self._cmd_volume(ctx, int(vol_str) if vol_str else None)
            return

        await self.bot.process_commands(message)

    # ==================== 指令（以 & 前綴呼叫） ====================

    @commands.command(name='s')
    async def skip(self, ctx: commands.Context):
        """跳過當前歌曲"""
        await self._cmd_skip(ctx)

    @commands.command(name='q')
    async def queue(self, ctx: commands.Context):
        """顯示播放列表"""
        await self._cmd_queue(ctx)

    @commands.command(name='l')
    async def leave(self, ctx: commands.Context):
        """離開語音頻道"""
        await self._cmd_leave(ctx)

    @commands.command(name='np')
    async def nowplaying(self, ctx: commands.Context):
        """顯示當前播放歌曲"""
        await self._cmd_nowplaying(ctx)

    @commands.command(name='ds')
    async def delete_song(self, ctx: commands.Context):
        """刪除並跳過當前歌曲"""
        await self._cmd_delete_song(ctx)

    @commands.command(name='random')
    async def random_song(self, ctx: commands.Context, folder: str = ''):
        """啟動隨機播放"""
        await self._cmd_random(ctx, folder)

    @commands.command(name='unrandom')
    async def unrandom(self, ctx: commands.Context):
        """停止隨機播放（保存進度）"""
        await self._cmd_unrandom(ctx)

    @commands.command(name='status')
    async def status(self, ctx: commands.Context):
        """顯示機器人目前狀態"""
        await self._cmd_status(ctx)

    @commands.command(name='reshuffle')
    async def reshuffle(self, ctx: commands.Context):
        """重新洗牌隨機列表"""
        await self._cmd_reshuffle(ctx)

    @commands.command(name='clear')
    async def clear_queue(self, ctx: commands.Context):
        """清空插播列表"""
        await self._cmd_clear(ctx)

    @commands.command(name='progress')
    async def show_progress(self, ctx: commands.Context):
        """顯示隨機播放進度"""
        await self._cmd_progress(ctx)

    @commands.command(name='reset_progress')
    async def reset_progress(self, ctx: commands.Context):
        """清除隨機播放進度"""
        await self._cmd_reset_progress(ctx)

    @commands.command(name='volume')
    async def volume(self, ctx: commands.Context, vol: int = None):
        """設定音量 (0-1000)"""
        await self._cmd_volume(ctx, vol)

    @commands.command(name='vol')
    async def vol(self, ctx: commands.Context, v: int = None):
        """音量簡短指令"""
        await self._cmd_volume(ctx, v)

    # ==================== 指令實作（_cmd_ 開頭，供指令與 on_message 共用） ====================

    async def _cmd_skip(self, ctx: commands.Context):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ 已跳過當前歌曲！")
        else:
            await ctx.send("❌ 目前沒有歌曲正在播放！")
            guild_id = ctx.guild.id
            if guild_id in self.random_state and self.random_state[guild_id]['active']:
                if ctx.voice_client and not ctx.voice_client.is_playing():
                    await ctx.send("🔄 正在重新啟動隨機播放...")
                    await self._continue_random_play(ctx)

    async def _cmd_queue(self, ctx: commands.Context):
        if not self.song_queue:
            await ctx.send("播放列表目前是空的。")
            return
        song_list = '\n'.join(
            f"{i + 1}. {song.title}" for i, song in enumerate(self.song_queue)
        )
        await ctx.send(f"當前播放列表:\n{song_list}")

    async def _cmd_leave(self, ctx: commands.Context):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("再見！")
        else:
            await ctx.send("機器人不在任何語音頻道中！")

    async def _cmd_nowplaying(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            await ctx.send("❌ 目前沒有正在播放的歌曲！")
            return
        source = vc.source
        elapsed = int(time.time() - getattr(source, 'start_time', time.time()))
        total_duration = get_audio_duration(source.file_path) if getattr(source, 'file_path', None) else 0
        guild_id = ctx.guild.id
        is_random = guild_id in self.random_state and self.random_state[guild_id]['active']
        mode_text = "🎲 隨機模式" if is_random else "📝 列表模式"
        if total_duration > 0:
            bar = create_progress_bar(elapsed, total_duration)
            await ctx.send(
                f"🎶 正在播放: **{source.title}**\n"
                f"`{format_time(elapsed)} {bar} {format_time(total_duration)}`\n"
                f"{mode_text}"
            )
        else:
            await ctx.send(
                f"🎶 正在播放: **{source.title}**（無法取得歌曲長度）\n"
                f"{mode_text}"
            )

    async def _cmd_delete_song(self, ctx: commands.Context):
        vc = ctx.voice_client
        guild_id = ctx.guild.id
        if not vc or not vc.is_playing():
            await ctx.send("❌ 目前沒有正在播放的歌曲！")
            return
        current = vc.source
        if not isinstance(current, YTDLSource):
            await ctx.send("⚠️ 目前播放的不是可刪除的來源。")
            return
        file_path = current.file_path
        title = current.title
        is_random_active = guild_id in self.random_state and self.random_state[guild_id]['active']
        if is_random_active:
            state = self.random_state[guild_id]
            file_path_obj = Path(file_path)
            if file_path_obj in state['remaining']:
                state['remaining'].remove(file_path_obj)
                logger.info(f"已從隨機播放列表中移除: {file_path_obj.name}")
        vc.stop()
        await ctx.send(f"⏭️ 正在跳過並刪除: {title}")
        await asyncio.sleep(1.5)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                await ctx.send(f"🗑️ 已刪除歌曲: {title}")
                logger.info(f"已刪除文件: {file_path}")
        except Exception as e:
            logger.error(f"刪除文件失敗: {e}")
            await ctx.send(f"⚠️ 無法刪除檔案: {e}")

    async def _cmd_random(self, ctx: commands.Context, folder: str = ''):
        guild_id = ctx.guild.id
        target_folder = Path(folder) if folder else DOWNLOAD_PATH
        if not target_folder.exists():
            await ctx.send(f"❌ 資料夾不存在：{target_folder}")
            return
        all_songs = [
            f for f in target_folder.iterdir()
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]
        if not all_songs:
            await ctx.send(f"❌ {target_folder} 中沒有可以播放的音樂檔案！")
            return
        if not ctx.voice_client:
            if not ctx.author.voice:
                await ctx.send("你必須先加入一個語音頻道！")
                return
            voice_client = await ctx.author.voice.channel.connect()
            await self._play_local_sound(voice_client)
        has_saved = (
            guild_id in self.random_state and
            self.random_state[guild_id]['folder'] == target_folder and
            len(self.random_state[guild_id]['remaining']) > 0
        )
        if has_saved:
            self.random_state[guild_id]['active'] = True
            remaining_count = len(self.random_state[guild_id]['remaining'])
            await ctx.send(
                f"🔄 繼續上次的隨機播放！\n"
                f"📁 資料夾: {target_folder.name}\n"
                f"🎵 剩餘 {remaining_count} 首歌曲\n"
                f"💡 提示: 使用 `random new` 或 `reshuffle` 重新開始"
            )
        else:
            self.random_state[guild_id] = {
                'active': True,
                'folder': target_folder,
                'remaining': shuffle_smartly(all_songs)
            }
            await ctx.send(
                f"🎲 已啟動智能隨機播放！\n"
                f"📁 資料夾: {target_folder.name}\n"
                f"🎵 共 {len(all_songs)} 首歌曲\n"
                f"💡 提示: 可以隨時貼上連結插播，播完後會繼續隨機播放"
            )
        if not self.song_queue:
            await self._continue_random_play(ctx)

    async def _cmd_unrandom(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        if guild_id in self.random_state:
            self.random_state[guild_id]['active'] = False
            save_random_progress(self.random_state)
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        await ctx.send("🛑 已停止隨機播放模式（進度已保存）")

    async def _cmd_status(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        vc = ctx.voice_client
        if not vc:
            await ctx.send("❌ 機器人不在語音頻道中")
            return
        lines = [
            "🎵 **機器人狀態**", "",
            f"📍 頻道: {vc.channel.name}",
            f"👥 成員數: {len(vc.channel.members)}",
        ]
        if vc.is_playing():
            lines.append(f"▶️ 正在播放: {vc.source.title}")
        else:
            lines.append("⏸️ 目前暫停")
        if guild_id in self.random_state and self.random_state[guild_id]['active']:
            state = self.random_state[guild_id]
            lines += ["", "🎲 **隨機播放模式**",
                      f"📁 資料夾: {state['folder'].name}",
                      f"🎵 剩餘歌曲: {len(state['remaining'])}"]
        if self.song_queue:
            lines += ["", f"📝 **插播列表**: {len(self.song_queue)} 首"]
        await ctx.send('\n'.join(lines))

    async def _cmd_reshuffle(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        if guild_id not in self.random_state or not self.random_state[guild_id]['active']:
            await ctx.send("❌ 目前不在隨機播放模式")
            return
        state = self.random_state[guild_id]
        all_songs = [
            f for f in state['folder'].iterdir()
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]
        if not all_songs:
            await ctx.send("❌ 資料夾中沒有歌曲")
            return
        state['remaining'] = shuffle_smartly(all_songs)
        save_random_progress(self.random_state)
        await ctx.send(f"🔄 已重新洗牌！共 {len(all_songs)} 首歌曲")

    async def _cmd_clear(self, ctx: commands.Context):
        if not self.song_queue:
            await ctx.send("插播列表已經是空的")
            return
        cleared = len(self.song_queue)
        self.song_queue.clear()
        await ctx.send(f"🗑️ 已清空 {cleared} 首插播歌曲")

    async def _cmd_progress(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        if guild_id not in self.random_state:
            await ctx.send("❌ 沒有隨機播放進度")
            return
        state = self.random_state[guild_id]
        all_songs = [
            f for f in state['folder'].iterdir()
            if f.suffix.lower() in AUDIO_EXTENSIONS
        ]
        total = len(all_songs)
        remaining = len(state['remaining'])
        played = total - remaining
        pct = int((played / total) * 100) if total > 0 else 0
        status_emoji = "▶️" if state['active'] else "⏸️"
        await ctx.send(
            f"📊 **隨機播放進度**\n\n"
            f"{status_emoji} 狀態: {'播放中' if state['active'] else '已暫停'}\n"
            f"📁 資料夾: {state['folder'].name}\n"
            f"🎵 總歌曲: {total} 首\n"
            f"✅ 已播放: {played} 首\n"
            f"📝 剩餘: {remaining} 首\n"
            f"📈 進度: {pct}%\n"
            f"{'─' * 20}\n"
            f"{'█' * (pct // 5)}{'░' * (20 - pct // 5)}"
        )

    async def _cmd_reset_progress(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        if guild_id not in self.random_state:
            await ctx.send("❌ 沒有需要清除的進度")
            return
        del self.random_state[guild_id]
        clear_random_progress(guild_id)
        await ctx.send("🗑️ 已清除隨機播放進度\n💡 使用 `random` 開始新的隨機播放")

    async def _cmd_volume(self, ctx: commands.Context, volume: int = None):
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            await ctx.send("❌ 目前沒有正在播放的歌曲！")
            return
        if volume is None:
            current_volume = int(vc.source.volume * 100)
            norm_status = "啟用" if ENABLE_VOLUME_NORMALIZATION else "停用"
            boost_warn = " 🔥 擴音模式中！" if current_volume > 100 else ""
            await ctx.send(
                f"🔊 當前音量: {current_volume}%{boost_warn}\n"
                f"📊 音量標準化: {norm_status}\n"
                f"💡 使用 `volume [0-1000]` 調整音量（超過100%為擴音模式，可能失真）"
            )
            return
        volume = max(0, min(10000, volume))
        if isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = volume / 100.0
            if volume > 200:
                await ctx.send(f"🔥 音量已設為 {volume}%（極度擴音，注意失真！）")
            elif volume > 100:
                await ctx.send(f"📢 音量已設為 {volume}%（擴音模式）")
            else:
                await ctx.send(f"🔊 音量已設為 {volume}%")
        else:
            await ctx.send("⚠️ 當前音源不支援音量調整")
