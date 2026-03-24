import asyncio
import json
import logging
import random
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

# ==================== 積分資料路徑 ====================

BASE_DIR = Path(__file__).parent.parent
SCORE_FILE = BASE_DIR / "scores.json"

# ==================== 關鍵字觸發清單 ====================

# 會被回嗆的關鍵字（訊息中含有即觸發）
SNARK_TRIGGERS = ['幹', '靠', '爛', '廢', '白痴', '機掰', '他媽', '他妈']
yelloC = ['黃C', '黃c','呂某']
# 隨機回嗆語句
SNARK_RESPONSES = [
    "你說誰呢？😤",
    "自己說自己嗎？",
    "冷靜一下好嗎 🧘",
    "嘴巴乾淨一點🙂",
    "是在跟誰嗆啊",
    "幹嘛這麼激動",
    "你今天心情不好喔",
    "說這種話，你媽知道嗎？",
    "沒事沒事，呼吸一下",
]
C_RESPONSES = [ '罵太兇了吧']
# 語錄庫（可自行擴充）
QUOTES = [
    "人生就是一場旅程，重要的不是目的地，而是沿途的風景。",
    "打王者輸了不要怪隊友，先想想自己。",
    "睡覺是最便宜的旅行。",
    "今天的努力，是為了明天可以繼續擺爛。",
    "世界上最遠的距離，是我在打 code 你叫我吃飯。",
    "有些人失去了才知道珍貴，比如我的頭髮。",
    "不要問我在幹嘛，我也不知道。",
    "成功的路上並不擁擠，因為大部分人都在睡覺。",
    "少說廢話多喝水，早點睡覺少掉髮。",
    "快樂很簡單，你想太多了。",
]

# 抽籤結果
FORTUNE_RESULTS = [
    ("大吉", "✨ 今日諸事皆宜，財運、感情雙豐收！"),
    ("中吉", "🌟 運勢不錯，小心謹慎更上層樓。"),
    ("小吉", "🍀 平穩中帶點小好運，把握機會。"),
    ("末吉", "🌱 運勢平平，穩住就是勝利。"),
    ("凶",   "⚠️ 今日諸事不宜，少出門為妙。"),
    ("大凶", "💀 今天最好躺平別動，動了更慘。"),
    ("水痘", "🦠 今天可能會長水痘，注意Ikea鯊魚！"),
    ("鐵鎚", "🔨 今天可能會被鐵鎚砸到，注意安全！"),
    ("黃C" , "😭 你這輩子有了")

]

# 觸發積分的行為
SCORE_TRIGGERS = {
    '打call': 5,
    '讚': 3,
    '神': 10,
    '強': 3,
}


# ==================== 積分管理 ====================

def load_scores() -> dict:
    """從 JSON 讀取積分"""
    try:
        if not SCORE_FILE.exists():
            return {}
        with open(SCORE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"讀取積分失敗: {e}")
        return {}


def save_scores(scores: dict) -> None:
    """將積分寫入 JSON"""
    try:
        with open(SCORE_FILE, 'w', encoding='utf-8') as f:
            json.dump(scores, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存積分失敗: {e}")


def add_score(scores: dict, guild_id: int, user_id: int,
              username: str, amount: int) -> int:
    """給指定使用者加分，回傳新積分"""
    gid = str(guild_id)
    uid = str(user_id)
    if gid not in scores:
        scores[gid] = {}
    if uid not in scores[gid]:
        scores[gid][uid] = {'name': username, 'score': 0}
    scores[gid][uid]['name'] = username   # 保持名稱最新
    scores[gid][uid]['score'] += amount
    return scores[gid][uid]['score']


# ==================== FunCog ====================

class FunCog(commands.Cog, name='FunCog'):
    """互動娛樂功能 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scores: dict = load_scores()
        # 記錄進行中的猜數字遊戲 {channel_id: {'answer': int, 'host': str}}
        self.guess_games: dict = {}

    # ==================== 關鍵字監聽 ====================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.content.startswith(self.bot.command_prefix):
            return

        content = message.content.strip()
        guild_id = message.guild.id if message.guild else None
        channel = message.channel

        # ── 搞笑：髒話回嗆 ──
        if any(kw in content for kw in SNARK_TRIGGERS):
            result = random.randint(1, 10)
            if result == 1:
                await channel.send(random.choice(SNARK_RESPONSES))

        # ── 搞笑：黃C ──
        if any(kw in content for kw in yelloC):
            await channel.send(random.choice(C_RESPONSES))

        # ── 搞笑：語錄 ──
        if '語錄' in content:
            await channel.send(f'📖 **語錄**\n{random.choice(QUOTES)}')

        # ── 文字遊戲：骰子 ──
        if '骰子' in content:
            result = random.randint(1, 6)
            faces = ['⚀', '⚁', '⚂', '⚃', '⚄', '⚅']
            await channel.send(
                f'🎲 {message.author.display_name} 擲出了 **{result}** 點！ {faces[result - 1]}'
            )

        # ── 文字遊戲：抽籤 ──
        if '抽籤' in content:
            name, desc = random.choice(FORTUNE_RESULTS)
            await channel.send(
                f'🎋 **{message.author.display_name}** 抽到了 —— **{name}**\n{desc}'
            )

        # ── 文字遊戲：猜數字開始 ──
        # 格式：猜數字 或 猜數字 50（指定上限）
        if content.startswith('猜數字'):
            parts = content.split()
            try:
                limit = int(parts[1]) if len(parts) > 1 else 100
                limit = max(10, min(limit, 10000))
            except ValueError:
                limit = 100
            answer = random.randint(1, limit)
            self.guess_games[channel.id] = {
                'answer': answer,
                'host': message.author.display_name,
                'limit': limit,
                'attempts': 0,
            }
            await channel.send(
                f'🔢 **猜數字遊戲開始！**\n'
                f'我心裡有一個 1 ～ {limit} 的數字，請輸入你的猜測！\n'
                f'（輸入 `取消猜數字` 結束遊戲）'
            )
            return

        # ── 文字遊戲：取消猜數字 ──
        if content == '取消猜數字':
            if channel.id in self.guess_games:
                answer = self.guess_games.pop(channel.id)['answer']
                await channel.send(f'遊戲已取消，答案是 **{answer}**。')
            return

        # ── 文字遊戲：猜數字作答 ──
        if channel.id in self.guess_games:
            game = self.guess_games[channel.id]
            try:
                guess = int(content)
            except ValueError:
                pass
            else:
                game['attempts'] += 1
                answer = game['answer']
                if guess < answer:
                    await channel.send(f'📉 太小了！再猜猜看（第 {game["attempts"]} 次）')
                elif guess > answer:
                    await channel.send(f'📈 太大了！再猜猜看（第 {game["attempts"]} 次）')
                else:
                    del self.guess_games[channel.id]
                    attempts = game['attempts']
                    await channel.send(
                        f'🎉 **答對了！** 答案就是 **{answer}**！\n'
                        f'{message.author.display_name} 用了 {attempts} 次猜中！'
                    )
                    # 猜中得分，次數越少分越高
                    if guild_id:
                        bonus = max(1, 20 - attempts)
                        new_score = add_score(
                            self.scores, guild_id,
                            message.author.id,
                            message.author.display_name, bonus
                        )
                        save_scores(self.scores)
                        await channel.send(
                            f'🏅 +{bonus} 積分（共 {new_score} 分）'
                        )
                return

        # ── 群組：隨機（格式：隨機 內容）──
        if content.startswith('隨機'):
            # 取得 '隨機' 後面的字串
            # .split() 會自動把多個連續空白（包含半形與全形空白）切分成列表
            raw_items = content[2:].strip()
            items = raw_items.split()

            if not items:
                # 狀況一：沒有輸入任何選項（只打了「隨機」），擲骰子 1~6
                result = random.randint(1, 6)
                await channel.send(
                    f'{message.author.mention}\n'
                    f'隨機 [ 1~6 ]\n'
                    f'→ **{result}**'
                )
            else:
                # 狀況二：有輸入多個選項，從中隨機挑選一個
                result = random.choice(items)
                items_str = " ".join(items)  # 將選項組合起來顯示在括號內
                await channel.send(
                    f'{message.author.mention}\n'
                    f'隨機 [ {items_str} ]\n'
                    f'→ **{result}**'
                )

        # ── 群組：投票（格式：投票 你的題目）──
        if content.startswith('投票 ') or content.startswith('投票　'):
            topic = content[3:].strip()
            if topic:
                msg = await channel.send(
                    f'📊 **投票時間！**\n\n**{topic}**\n\n'
                    f'✅ 贊成　　❌ 反對　　🤷 不表態'
                )
                for emoji in ['✅', '❌', '🤷']:
                    await msg.add_reaction(emoji)

        # ── 個人化：積分觸發關鍵字 ──
        if guild_id:
            for kw, pts in SCORE_TRIGGERS.items():
                if kw in content:
                    # 若有 @ 提及，給被提及的人加分
                    if message.mentions:
                        for target in message.mentions:
                            if target == self.bot.user:
                                continue
                            new_score = add_score(
                                self.scores, guild_id,
                                target.id, target.display_name, pts
                            )
                            save_scores(self.scores)
                            await channel.send(
                                f'🌟 {target.display_name} 獲得 +{pts} 積分！（共 {new_score} 分）'
                            )
                    break

        # ── 指令路由（無前綴版） ──
        if content == '排行':
            ctx = await self.bot.get_context(message)
            await self._cmd_leaderboard(ctx)
        elif content == '我的積分':
            ctx = await self.bot.get_context(message)
            await self._cmd_my_score(ctx)
        elif content.startswith('點名'):
            ctx = await self.bot.get_context(message)
            await self._cmd_pick(ctx)
        elif content.startswith('抽獎'):
            parts = content.split()
            seconds = 30
            try:
                seconds = int(parts[1])
            except (IndexError, ValueError):
                pass
            ctx = await self.bot.get_context(message)
            await self._cmd_lottery(ctx, seconds)

    # ==================== 指令（& 前綴版） ====================

    @commands.command(name='排行')
    async def leaderboard(self, ctx: commands.Context):
        """顯示伺服器積分排行榜"""
        await self._cmd_leaderboard(ctx)

    @commands.command(name='我的積分')
    async def my_score(self, ctx: commands.Context):
        """查詢自己的積分"""
        await self._cmd_my_score(ctx)

    @commands.command(name='點名')
    async def pick(self, ctx: commands.Context):
        """從語音頻道隨機點一個人"""
        await self._cmd_pick(ctx)

    @commands.command(name='抽獎')
    async def lottery(self, ctx: commands.Context, seconds: int = 30):
        """發起抽獎，倒數後從加入反應的人中抽一位"""
        await self._cmd_lottery(ctx, seconds)

    @commands.command(name='+1')
    async def plus_one(self, ctx: commands.Context, member: discord.Member = None):
        """給某人 +1 積分"""
        if not member:
            await ctx.send('請指定要 +1 的對象，例如：`&+1 @某人`')
            return
        if member == ctx.author:
            await ctx.send('不能給自己加分喔 😏')
            return
        new_score = add_score(
            self.scores, ctx.guild.id,
            member.id, member.display_name, 1
        )
        save_scores(self.scores)
        await ctx.send(f'👍 {member.display_name} +1 積分！（共 {new_score} 分）')

    # ==================== 指令實作 ====================

    async def _cmd_leaderboard(self, ctx: commands.Context):
        gid = str(ctx.guild.id)
        guild_scores = self.scores.get(gid, {})
        if not guild_scores:
            await ctx.send('目前還沒有任何積分紀錄！')
            return
        sorted_scores = sorted(
            guild_scores.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        medals = ['🥇', '🥈', '🥉']
        lines = ['🏆 **積分排行榜**\n']
        for i, (uid, data) in enumerate(sorted_scores[:10]):
            prefix = medals[i] if i < 3 else f'`{i + 1}.`'
            lines.append(f'{prefix} **{data["name"]}** — {data["score"]} 分')
        await ctx.send('\n'.join(lines))

    async def _cmd_my_score(self, ctx: commands.Context):
        gid = str(ctx.guild.id)
        uid = str(ctx.author.id)
        guild_scores = self.scores.get(gid, {})
        score = guild_scores.get(uid, {}).get('score', 0)
        # 計算排名
        sorted_scores = sorted(
            guild_scores.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        rank = next(
            (i + 1 for i, (u, _) in enumerate(sorted_scores) if u == uid),
            None
        )
        rank_text = f'第 {rank} 名' if rank else '尚無排名'
        await ctx.send(
            f'📊 **{ctx.author.display_name}** 的積分\n'
            f'💰 積分：{score} 分\n'
            f'🏅 排名：{rank_text}'
        )

    async def _cmd_pick(self, ctx: commands.Context):
        vc = ctx.voice_client
        if not vc:
            # 若 bot 不在語音頻道，找發話者所在的頻道
            if ctx.author.voice:
                members = [
                    m for m in ctx.author.voice.channel.members
                    if not m.bot
                ]
            else:
                await ctx.send('你或機器人必須在語音頻道中才能點名！')
                return
        else:
            members = [m for m in vc.channel.members if not m.bot]

        if not members:
            await ctx.send('頻道裡沒有其他人可以點名！')
            return

        chosen = random.choice(members)
        await ctx.send(
            f'🎯 點名結果：**{chosen.display_name}** 你被點到了！'
        )
        # 被點名 +2 積分
        new_score = add_score(
            self.scores, ctx.guild.id,
            chosen.id, chosen.display_name, 2
        )
        save_scores(self.scores)
        await ctx.send(f'🌟 {chosen.display_name} 因被點名獲得 +2 積分！（共 {new_score} 分）')

    async def _cmd_lottery(self, ctx: commands.Context, seconds: int = 30):
        seconds = max(5, min(seconds, 300))
        msg = await ctx.send(
            f'🎰 **抽獎開始！**\n'
            f'請在 {seconds} 秒內點擊下方 🎟️ 參加！\n'
            f'時間到後自動抽出得獎者！'
        )
        await msg.add_reaction('🎟️')
        await ctx.send(f'⏳ 倒數 {seconds} 秒...')
        await asyncio.sleep(seconds)

        # 重新抓取訊息以獲取最新反應
        try:
            msg = await ctx.channel.fetch_message(msg.id)
        except discord.NotFound:
            await ctx.send('抽獎訊息不見了！')
            return

        participants = []
        for reaction in msg.reactions:
            if str(reaction.emoji) == '🎟️':
                async for user in reaction.users():
                    if not user.bot:
                        participants.append(user)
                break

        if not participants:
            await ctx.send('😢 沒有人參加抽獎...')
            return

        winner = random.choice(participants)
        await ctx.send(
            f'🎉 **抽獎結果出爐！**\n'
            f'共 {len(participants)} 人參加\n'
            f'得獎者是 ➡️ **{winner.mention}** 🎊'
        )
        # 得獎者 +15 積分
        new_score = add_score(
            self.scores, ctx.guild.id,
            winner.id, winner.display_name, 15
        )
        save_scores(self.scores)
        await ctx.send(f'🌟 {winner.display_name} 因中獎獲得 +15 積分！（共 {new_score} 分）')