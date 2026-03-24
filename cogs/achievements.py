"""
cogs/achievements.py — 成就系統

觸發方式：
  查詢  → 發送「成就」或「我的成就」或 &成就
  管理  → &給予成就 @某人 成就ID  （需管理員權限）
  重置  → &重置成就 @某人          （需管理員權限）

翻頁方式：
  Bot 送出圖片後自動加上 ⬅️ ➡️ 反應，點擊即翻頁。
  60 秒無操作自動關閉（移除反應監聽）。

成就解鎖（自動）：
  本 Cog 透過 on_message 監聽訊息數量、特定行為，
  並提供 check_and_unlock() 供其他 Cog 呼叫。
"""
from pilmoji import Pilmoji
import asyncio
import io
import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ==================== 路徑 ====================

BASE_DIR   = Path(__file__).parent.parent
ACH_FILE   = BASE_DIR / "achievements.json"   # 使用者解鎖紀錄
SCORE_FILE = BASE_DIR / "scores.json"          # 與 fun.py 共用

# ==================== 字型 ====================

FONT_BOLD   = str(BASE_DIR / "fonts" / "NotoSansCJK-Bold.ttc")
FONT_NORMAL = str(BASE_DIR / "fonts" / "NotoSansCJK-Regular.ttc")

# ==================== 調色盤 ====================

BG_DARK      = ( 22,  28,  48)
BG_CARD      = ( 30,  38,  65)
BG_PANEL     = ( 38,  48,  82)
BG_HEADER    = ( 20,  26,  55)
CYAN         = ( 80, 220, 220)
GOLD         = (255, 210,  60)
PURPLE_LIGHT = (180, 140, 255)
GREEN_BRIGHT = ( 80, 230, 140)
LOCKED_BG    = ( 26,  30,  50)
LOCKED_FG    = ( 70,  78, 110)
LOCKED_BORD  = ( 55,  62,  95)

RARITY_COLOR = {
    "普通": (140, 160, 200),
    "稀有": ( 60, 180, 255),
    "史詩": (200,  90, 255),
    "傳說": (255, 200,  40),
    "隱藏": (255, 110, 170),
}
RARITY_GLOW = {
    "普通": ( 30,  50,  80),
    "稀有": ( 10,  40,  90),
    "史詩": ( 50,  20,  80),
    "傳說": ( 80,  55,   0),
    "隱藏": ( 70,  20,  50),
}

# ==================== 版面常數 ====================

COLS     = 4
ROWS     = 2
PER_PAGE = COLS * ROWS   # 8
CARD_W   = 210
CARD_H   = 128
GAP      = 12
MARGIN   = 24
HEADER_H = 100
FOOTER_H = 48

# ==================== 成就定義（32 個）====================
# 每筆欄位：
#   id        : 唯一識別字串
#   name      : 顯示名稱
#   desc      : 描述（14字以內顯示最佳，超過自動截斷）
#   emoji     : 圖示
#   rarity    : 普通 / 稀有 / 史詩 / 傳說 / 隱藏
#   category  : 社交 / 音樂 / 遊戲 / 積分 / 特殊
#   condition : 自動解鎖條件說明（供程式判斷用的 key）
#   threshold : 數值條件門檻（None 表示特殊邏輯）

ALL_ACHIEVEMENTS = [

    # ── 社交類（8個）──
    {
        "id": "first_message",
        "name": "破冰者",
        "desc": "第一次在伺服器發言",
        "emoji": "💬",
        "rarity": "普通",
        "category": "社交",
        "condition": "message_count",
        "threshold": 1,
    },
    {
        "id": "chatterbox",
        "name": "話嘮",
        "desc": "累積發言500次",
        "emoji": "💭",
        "rarity": "普通",
        "category": "社交",
        "condition": "message_count",
        "threshold": 500,
    },
    {
        "id": "veteran_talker",
        "name": "資深話嘮",
        "desc": "累積發言2000次",
        "emoji": "🗣️",
        "rarity": "稀有",
        "category": "社交",
        "condition": "message_count",
        "threshold": 2000,
    },
    {
        "id": "night_owl",
        "name": "夜貓子",
        "desc": "深夜12點後發言50次",
        "emoji": "🦉",
        "rarity": "稀有",
        "category": "社交",
        "condition": "night_message_count",
        "threshold": 50,
    },
    {
        "id": "generous",
        "name": "熱心腸",
        "desc": "給他人+1超過20次",
        "emoji": "🤝",
        "rarity": "普通",
        "category": "社交",
        "condition": "give_score_count",
        "threshold": 20,
    },
    {
        "id": "super_generous",
        "name": "散財童子",
        "desc": "給他人+1超過100次",
        "emoji": "💸",
        "rarity": "稀有",
        "category": "社交",
        "condition": "give_score_count",
        "threshold": 100,
    },
    {
        "id": "voted",
        "name": "民主鬥士",
        "desc": "參與投票超過10次",
        "emoji": "📊",
        "rarity": "普通",
        "category": "社交",
        "condition": "vote_count",
        "threshold": 10,
    },
    {
        "id": "shadow",
        "name": "潛行者",
        "desc": "加入後30天首次發言",
        "emoji": "👤",
        "rarity": "史詩",
        "category": "社交",
        "condition": "late_first_message",
        "threshold": None,
    },

    # ── 音樂類（8個）──
    {
        "id": "first_song",
        "name": "初次聆聽",
        "desc": "第一次使用音樂功能",
        "emoji": "🎶",
        "rarity": "普通",
        "category": "音樂",
        "condition": "song_played",
        "threshold": 1,
    },
    {
        "id": "music_fan",
        "name": "音樂狂熱",
        "desc": "累積播放100首歌曲",
        "emoji": "🎵",
        "rarity": "稀有",
        "category": "音樂",
        "condition": "song_played",
        "threshold": 100,
    },
    {
        "id": "music_addict",
        "name": "音樂成癮",
        "desc": "累積播放500首歌曲",
        "emoji": "🎸",
        "rarity": "史詩",
        "category": "音樂",
        "condition": "song_played",
        "threshold": 500,
    },
    {
        "id": "dj",
        "name": "傳說DJ",
        "desc": "累積播放1000首歌曲",
        "emoji": "🎧",
        "rarity": "傳說",
        "category": "音樂",
        "condition": "song_played",
        "threshold": 1000,
    },
    {
        "id": "bilibili_user",
        "name": "二次元居民",
        "desc": "播放10首Bilibili音樂",
        "emoji": "📺",
        "rarity": "普通",
        "category": "音樂",
        "condition": "bilibili_played",
        "threshold": 10,
    },
    {
        "id": "skipper",
        "name": "跳針剋星",
        "desc": "使用跳過指令50次",
        "emoji": "⏭️",
        "rarity": "普通",
        "category": "音樂",
        "condition": "skip_count",
        "threshold": 50,
    },
    {
        "id": "random_lover",
        "name": "隨機愛好者",
        "desc": "使用隨機播放100次",
        "emoji": "🎲",
        "rarity": "稀有",
        "category": "音樂",
        "condition": "random_play_count",
        "threshold": 100,
    },
    {
        "id": "bass_booster",
        "name": "震耳欲聾",
        "desc": "音量調超過500%一次",
        "emoji": "📢",
        "rarity": "史詩",
        "category": "音樂",
        "condition": "max_volume",
        "threshold": 500,
    },

    # ── 遊戲類（8個）──
    {
        "id": "first_guess",
        "name": "初學者",
        "desc": "第一次猜數字猜中",
        "emoji": "🔢",
        "rarity": "普通",
        "category": "遊戲",
        "condition": "guess_win",
        "threshold": 1,
    },
    {
        "id": "guesser",
        "name": "猜謎達人",
        "desc": "猜數字猜中10次",
        "emoji": "🎮",
        "rarity": "稀有",
        "category": "遊戲",
        "condition": "guess_win",
        "threshold": 10,
    },
    {
        "id": "godlike_guess",
        "name": "神之一手",
        "desc": "猜數字1次猜中",
        "emoji": "⚡",
        "rarity": "傳說",
        "category": "遊戲",
        "condition": "guess_one_shot",
        "threshold": None,
    },
    {
        "id": "lucky_draw",
        "name": "小確幸",
        "desc": "抽獎中獎一次",
        "emoji": "🎟️",
        "rarity": "普通",
        "category": "遊戲",
        "condition": "lottery_win",
        "threshold": 1,
    },
    {
        "id": "euro_king",
        "name": "歐皇附身",
        "desc": "抽獎中獎3次",
        "emoji": "🎰",
        "rarity": "史詩",
        "category": "遊戲",
        "condition": "lottery_win",
        "threshold": 3,
    },
    {
        "id": "dice_master",
        "name": "骰子狂人",
        "desc": "擲骰子超過30次",
        "emoji": "🎲",
        "rarity": "普通",
        "category": "遊戲",
        "condition": "dice_count",
        "threshold": 30,
    },
    {
        "id": "max_roll",
        "name": "六六大順",
        "desc": "擲出三次6點",
        "emoji": "⚀",
        "rarity": "稀有",
        "category": "遊戲",
        "condition": "dice_six_count",
        "threshold": 3,
    },
    {
        "id": "fortune_seeker",
        "name": "問卦癡",
        "desc": "抽籤超過20次",
        "emoji": "🎋",
        "rarity": "普通",
        "category": "遊戲",
        "condition": "fortune_count",
        "threshold": 20,
    },

    # ── 積分類（5個）──
    {
        "id": "score_100",
        "name": "小有名氣",
        "desc": "累積積分達100分",
        "emoji": "🌟",
        "rarity": "普通",
        "category": "積分",
        "condition": "score",
        "threshold": 100,
    },
    {
        "id": "score_500",
        "name": "富甲一方",
        "desc": "累積積分達500分",
        "emoji": "💰",
        "rarity": "稀有",
        "category": "積分",
        "condition": "score",
        "threshold": 500,
    },
    {
        "id": "score_1000",
        "name": "傳說人物",
        "desc": "積分達到1000分",
        "emoji": "👑",
        "rarity": "傳說",
        "category": "積分",
        "condition": "score",
        "threshold": 1000,
    },
    {
        "id": "top_rank",
        "name": "王中之王",
        "desc": "登上伺服器排行第一",
        "emoji": "🏆",
        "rarity": "傳說",
        "category": "積分",
        "condition": "rank_first",
        "threshold": None,
    },
    {
        "id": "named",
        "name": "眾矢之的",
        "desc": "被點名超過10次",
        "emoji": "🎯",
        "rarity": "稀有",
        "category": "積分",
        "condition": "picked_count",
        "threshold": 10,
    },

    # ── 特殊/隱藏類（3個）──
    {
        "id": "cursed",
        "name": "嘴臭達人",
        "desc": "???",
        "emoji": "🤬",
        "rarity": "隱藏",
        "category": "特殊",
        "condition": "snark_trigger_count",
        "threshold": 30,
    },
    {
        "id": "quote_lover",
        "name": "語錄收集家",
        "desc": "???",
        "emoji": "📖",
        "rarity": "隱藏",
        "category": "特殊",
        "condition": "quote_count",
        "threshold": 20,
    },
    {
        "id": "ghost",
        "name": "幽靈成員",
        "desc": "???",
        "emoji": "👻",
        "rarity": "隱藏",
        "category": "特殊",
        "condition": "ghost",
        "threshold": None,
    },
]

# 方便用 id 查詢
ACH_BY_ID = {a["id"]: a for a in ALL_ACHIEVEMENTS}

# ==================== 資料管理 ====================

def load_ach_data() -> dict:
    """載入使用者成就與統計資料
    結構: {
      guild_id: {
        user_id: {
          "unlocked": {"ach_id": "YYYY-MM-DD", ...},
          "stats": {"message_count": 0, ...}
        }
      }
    }
    """
    try:
        if not ACH_FILE.exists():
            return {}
        with open(ACH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"載入成就資料失敗: {e}")
        return {}


def save_ach_data(data: dict) -> None:
    try:
        with open(ACH_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存成就資料失敗: {e}")


def get_user_data(data: dict, guild_id: int, user_id: int) -> dict:
    """取得（或初始化）使用者資料"""
    gid, uid = str(guild_id), str(user_id)
    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {"unlocked": {}, "stats": {}}
    return data[gid][uid]


def inc_stat(udata: dict, key: str, amount: int = 1) -> int:
    """增加統計數值，回傳新值"""
    udata["stats"][key] = udata["stats"].get(key, 0) + amount
    return udata["stats"][key]


def get_stat(udata: dict, key: str) -> int:
    return udata["stats"].get(key, 0)


def unlock(udata: dict, ach_id: str) -> bool:
    """解鎖成就，若已解鎖回傳 False，新解鎖回傳 True"""
    if ach_id in udata["unlocked"]:
        return False
    udata["unlocked"][ach_id] = datetime.now().strftime("%Y-%m-%d")
    return True


def load_scores() -> dict:
    try:
        if not SCORE_FILE.exists():
            return {}
        with open(SCORE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ==================== 圖片渲染 ====================

def render_achievement_card(
    username: str,
    avatar_bytes: Optional[bytes],
    page_achs: list,
    page: int,
    total_pages: int,
    unlocked_ids: set,
    unlock_dates: dict,
    total_unlocked: int,
    grand_total: int,
) -> io.BytesIO:
    """渲染成就卡片圖片，回傳 BytesIO"""

    W = MARGIN*2 + COLS*CARD_W + (COLS-1)*GAP
    H = HEADER_H + MARGIN + ROWS*(CARD_H+GAP) - GAP + FOOTER_H + MARGIN

    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # ── 棋盤底紋 ──
    GRID = 16
    for gy in range(0, H, GRID):
        for gx in range(0, W, GRID):
            shade = (25, 32, 54) if (gx//GRID + gy//GRID) % 2 == 0 else BG_DARK
            draw.rectangle([gx, gy, gx+GRID-1, gy+GRID-1], fill=shade)

    def pixel_border(x, y, w, h, outer, inner=BG_CARD, thick=2):
        draw.rectangle([x+3, y+3, x+w+2, y+h+2], fill=(8, 10, 20))
        draw.rectangle([x, y, x+w-1, y+h-1], fill=inner)
        for i in range(thick):
            frac = 1 - i * 0.35
            col = tuple(max(0, int(c * frac)) for c in outer)
            draw.rectangle([x+i, y+i, x+w-1-i, y+h-1-i], outline=col)

    def dot_corner(x, y, w, h, color, size=4):
        for dx, dy in [(0, 0), (w-size, 0), (0, h-size), (w-size, h-size)]:
            draw.rectangle([x+dx, y+dy, x+dx+size-1, y+dy+size-1], fill=color)

    # ── Header ──
    pixel_border(0, 0, W, HEADER_H, CYAN, BG_HEADER, thick=3)
    for lx in range(4, W-4, 8):
        draw.rectangle([lx, HEADER_H-6, lx+4, HEADER_H-4], fill=(40, 50, 80))
    draw.rectangle([4, 8, 8, HEADER_H-14], fill=CYAN)
    draw.rectangle([10, 12, 13, HEADER_H-18], fill=PURPLE_LIGHT)

    f_title  = ImageFont.truetype(FONT_BOLD,   28)
    f_sub    = ImageFont.truetype(FONT_NORMAL, 13)
    f_bar_lb = ImageFont.truetype(FONT_BOLD,   11)
    f_icon   = ImageFont.truetype(FONT_NORMAL, 26)

    with Pilmoji(img) as pilmoji:
        pilmoji.text((20, 10), "🏆", font=f_icon, fill=GOLD)
    draw.text((56, 13), "成就系統", font=f_title, fill=(20, 30, 60))
    draw.text((54, 11), "成就系統", font=f_title, fill=CYAN)

    # 頭像（若有）
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((36, 36))
            mask = Image.new("L", (36, 36), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 35, 35], fill=255)
            av_pos = (W - MARGIN - 36, 10)
            img.paste(av, av_pos, mask)
            draw.ellipse([av_pos[0]-1, av_pos[1]-1,
                          av_pos[0]+37, av_pos[1]+37], outline=CYAN)
        except Exception:
            pass

    pct = total_unlocked / grand_total if grand_total > 0 else 0
    draw.text((20, 52),
              f"{username}　解鎖進度：{total_unlocked} / {grand_total}",
              font=f_sub, fill=(160, 180, 230))

    bx, by, bw, bh = 20, 70, W-60, 14
    draw.rectangle([bx, by, bx+bw, by+bh], fill=(20, 24, 45))
    draw.rectangle([bx, by, bx+bw, by+bh], outline=(50, 60, 100))
    fill_w = int(bw * pct)
    for i in range(fill_w):
        ratio = i / max(bw, 1)
        r = int(80  + 175 * ratio)
        g = int(220 -  80 * ratio)
        b = int(220 -  80 * ratio)
        draw.line([(bx+i, by+1), (bx+i, by+bh-1)], fill=(r, g, b))
    for i in range(0, fill_w, 10):
        draw.rectangle([bx+i, by+2, bx+i+3, by+5], fill=(255, 255, 255))
    draw.text((bx+bw+6, by), f"{int(pct*100)}%", font=f_bar_lb, fill=GOLD)

    # ── 成就卡片 ──
    f_name  = ImageFont.truetype(FONT_BOLD,   13)
    f_desc  = ImageFont.truetype(FONT_NORMAL, 10)
    f_emoji = ImageFont.truetype(FONT_NORMAL, 26)
    f_rare  = ImageFont.truetype(FONT_BOLD,    9)
    f_date  = ImageFont.truetype(FONT_NORMAL,  9)
    f_lock  = ImageFont.truetype(FONT_NORMAL, 22)

    for i, ach in enumerate(page_achs):
        col = i % COLS
        row = i // COLS
        cx = MARGIN + col * (CARD_W + GAP)
        cy = HEADER_H + MARGIN + row * (CARD_H + GAP)

        is_unlocked = ach["id"] in unlocked_ids
        is_hidden   = ach["rarity"] == "隱藏" and not is_unlocked
        rcol = RARITY_COLOR[ach["rarity"]]
        rglow = RARITY_GLOW[ach["rarity"]]
        bc   = LOCKED_BORD if not is_unlocked else rcol
        bg   = LOCKED_BG   if not is_unlocked else rglow

        pixel_border(cx, cy, CARD_W, CARD_H, bc, bg, thick=2)
        dot_corner(cx, cy, CARD_W, CARD_H,
                   bc if not is_unlocked else rcol, size=4)

        if is_unlocked:
            # 稀有度頂條
            draw.rectangle([cx+2, cy+2, cx+CARD_W-3, cy+6], fill=rcol)
            for bx2 in range(cx+4, cx+CARD_W-4, 12):
                draw.rectangle([bx2, cy+3, bx2+5, cy+5], fill=(255, 255, 255))

            # emoji 底板
            ex, ey = cx+8, cy+12
            draw.ellipse([ex-2, ey-2, ex+38, ey+38],
                         fill=tuple(min(255, c+40) for c in rglow))
            draw.ellipse([ex-2, ey-2, ex+38, ey+38], outline=rcol)
            with Pilmoji(img) as pilmoji:
                pilmoji.text((ex+1, ey+1), ach["emoji"], font=f_emoji, fill=(20, 20, 30))
                pilmoji.text((ex,   ey  ), ach["emoji"], font=f_emoji, fill=(255, 255, 255))

            draw.text((cx+54, cy+14), ach["name"],  font=f_name, fill=(230, 235, 255))
            rl = f"◆ {ach['rarity']}"
            rw = len(rl)*7+8
            draw.rectangle([cx+52, cy+32, cx+52+rw, cy+44],
                           fill=tuple(min(255, c+20) for c in rglow), outline=rcol)
            draw.text((cx+55, cy+33), rl, font=f_rare, fill=rcol)

            desc = ach["desc"] if len(ach["desc"]) <= 14 else ach["desc"][:13]+"…"
            draw.text((cx+8, cy+64), desc, font=f_desc, fill=(170, 185, 225))

            for lxi in range(cx+8, cx+CARD_W-8, 6):
                draw.rectangle([lxi, cy+78, lxi+3, cy+79], fill=(60, 70, 110))

            date_str = unlock_dates.get(ach["id"], "")
            draw.text((cx+8, cy+CARD_H-22),
                      f"✓ {date_str}", font=f_date, fill=GREEN_BRIGHT)

        elif is_hidden:
            # 隱藏成就：完全遮蔽
            draw.text((cx+CARD_W//2-14, cy+18), "❓",
                      font=f_lock, fill=LOCKED_FG)
            draw.text((cx+8, cy+52), "隱藏成就",
                      font=f_name, fill=LOCKED_FG)
            draw.text((cx+8, cy+70), "解鎖條件未知",
                      font=f_desc, fill=LOCKED_FG)
            draw.text((cx+8, cy+CARD_H-22), "??? 尚未解鎖",
                      font=f_date, fill=LOCKED_FG)

        else:
            # 一般未解鎖
            draw.text((cx+CARD_W//2-14, cy+12), "🔒",
                      font=f_lock, fill=LOCKED_FG)
            draw.text((cx+8, cy+52), ach["name"],
                      font=f_name, fill=LOCKED_FG)
            desc = ach["desc"] if len(ach["desc"]) <= 14 else ach["desc"][:13]+"…"
            draw.text((cx+8, cy+70), desc,
                      font=f_desc, fill=LOCKED_FG)
            draw.text((cx+8, cy+CARD_H-22), "??? 尚未解鎖",
                      font=f_date, fill=LOCKED_FG)

    # ── Footer ──
    fy = H - FOOTER_H
    draw.rectangle([0, fy, W, H], fill=BG_HEADER)
    draw.line([(0, fy), (W, fy)], fill=CYAN, width=2)
    for fx2 in range(0, W, 8):
        draw.rectangle([fx2, fy+2, fx2+3, fy+4], fill=(40, 50, 90))

    f_footer = ImageFont.truetype(FONT_NORMAL, 11)
    f_page   = ImageFont.truetype(FONT_BOLD,   13)

    draw.text((MARGIN, fy+14),
              "◀ 玲奈寶寶應用  •  成就系統  ▶",
              font=f_footer, fill=(100, 120, 180))

    # 頁碼指示點
    dot_sz  = 10
    dot_gap = 6
    row_w   = total_pages * (dot_sz + dot_gap) - dot_gap
    dot_x   = W//2 - row_w//2
    dot_y   = fy + FOOTER_H//2 - dot_sz//2
    for p in range(total_pages):
        col = CYAN if p == page else (50, 60, 100)
        draw.rectangle(
            [dot_x + p*(dot_sz+dot_gap), dot_y,
             dot_x + p*(dot_sz+dot_gap)+dot_sz-1, dot_y+dot_sz-1],
            fill=col, outline=(80, 90, 130)
        )

    draw.text((W-MARGIN-50, fy+14),
              f"{page+1} / {total_pages}",
              font=f_page, fill=GOLD)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ==================== AchievementCog ====================

class AchievementCog(commands.Cog, name="AchievementCog"):
    """成就系統 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot  = bot
        self.data = load_ach_data()
        # 暫存翻頁會話: {message_id: {user_id, guild_id, page, total_pages}}
        self._sessions: dict = {}

    # ── 儲存 ──

    def _save(self):
        save_ach_data(self.data)

    # ── 取得用戶資料 ──

    def _udata(self, guild_id: int, user_id: int) -> dict:
        return get_user_data(self.data, guild_id, user_id)

    # ── 核心：檢查並解鎖成就，回傳新解鎖的成就列表 ──

    async def check_and_unlock(
        self,
        guild: discord.Guild,
        user: discord.Member,
        stat_key: str,
        new_value: int,
        channel: Optional[discord.TextChannel] = None,
    ) -> list:
        """
        給定 stat_key 與目前新值，檢查是否有成就達到門檻。
        回傳本次新解鎖的成就列表，並在頻道送出通知。
        """
        udata = self._udata(guild.id, user.id)
        newly_unlocked = []

        for ach in ALL_ACHIEVEMENTS:
            if ach["condition"] != stat_key:
                continue
            if ach["threshold"] is None:
                continue
            if ach["id"] in udata["unlocked"]:
                continue
            if new_value >= ach["threshold"]:
                if unlock(udata, ach["id"]):
                    newly_unlocked.append(ach)

        if newly_unlocked:
            self._save()
            if channel:
                for ach in newly_unlocked:
                    rcol = RARITY_COLOR[ach["rarity"]]
                    embed = discord.Embed(
                        title=f"🎉 成就解鎖！",
                        description=(
                            f"{user.mention} 解鎖了成就 "
                            f"**{ach['emoji']} {ach['name']}**\n"
                            f"*{ach['desc']}*"
                        ),
                        color=discord.Color.from_rgb(*rcol),
                    )
                    embed.set_footer(text=f"稀有度：{ach['rarity']}　分類：{ach['category']}")
                    await channel.send(embed=embed)

        return newly_unlocked

    async def unlock_special(
        self,
        guild: discord.Guild,
        user: discord.Member,
        ach_id: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> bool:
        """解鎖特殊（threshold=None）成就，回傳是否為新解鎖"""
        udata = self._udata(guild.id, user.id)
        if ach_id in udata["unlocked"]:
            return False
        if unlock(udata, ach_id):
            self._save()
            ach = ACH_BY_ID.get(ach_id)
            if ach and channel:
                rcol = RARITY_COLOR[ach["rarity"]]
                embed = discord.Embed(
                    title="🎉 成就解鎖！",
                    description=(
                        f"{user.mention} 解鎖了成就 "
                        f"**{ach['emoji']} {ach['name']}**\n"
                        f"*{ach['desc'] if ach['rarity'] != '隱藏' else '???'}*"
                    ),
                    color=discord.Color.from_rgb(*rcol),
                )
                embed.set_footer(text=f"稀有度：{ach['rarity']}　分類：{ach['category']}")
                await channel.send(embed=embed)
            return True
        return False

    # ── 公開 API：讓其他 Cog 呼叫 ──

    async def record_stat(
        self,
        guild: discord.Guild,
        user: discord.Member,
        stat_key: str,
        amount: int = 1,
        channel: Optional[discord.TextChannel] = None,
    ):
        """增加統計值並自動觸發成就檢查"""
        udata = self._udata(guild.id, user.id)
        new_val = inc_stat(udata, stat_key, amount)
        self._save()
        await self.check_and_unlock(guild, user, stat_key, new_val, channel)

    # ── 圖片生成 ──

    async def _build_card(
        self,
        member: discord.Member,
        guild: discord.Guild,
        page: int,
    ) -> tuple[io.BytesIO, int]:
        """生成指定頁的成就卡片，回傳 (BytesIO, total_pages)"""
        udata = self._udata(guild.id, member.id)
        unlocked_ids  = set(udata["unlocked"].keys())
        unlock_dates  = udata["unlocked"]
        total_unlocked = len(unlocked_ids)
        grand_total    = len(ALL_ACHIEVEMENTS)
        total_pages    = math.ceil(grand_total / PER_PAGE)
        page           = max(0, min(page, total_pages - 1))

        page_achs = ALL_ACHIEVEMENTS[page*PER_PAGE : (page+1)*PER_PAGE]

        # 嘗試下載頭像
        avatar_bytes = None
        try:
            av_url = member.display_avatar.replace(size=64, format="png").url
            async with self.bot.http._HTTPClient__session.get(av_url) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()
        except Exception:
            pass

        buf = await asyncio.get_event_loop().run_in_executor(
            None,
            render_achievement_card,
            member.display_name,
            avatar_bytes,
            page_achs,
            page,
            total_pages,
            unlocked_ids,
            unlock_dates,
            total_unlocked,
            grand_total,
        )
        return buf, total_pages

    # ── 翻頁 session ──

    async def _send_card(
        self,
        target: discord.abc.Messageable,
        member: discord.Member,
        guild: discord.Guild,
        page: int = 0,
        edit_msg: Optional[discord.Message] = None,
    ) -> discord.Message:
        buf, total_pages = await self._build_card(member, guild, page)
        file = discord.File(buf, filename="achievements.png")

        if edit_msg:
            # 無法直接 edit 附件，刪舊送新
            try:
                await edit_msg.delete()
            except Exception:
                pass

        msg = await target.send(
            content=f"**{member.display_name}** 的成就頁面　第 {page+1} / {total_pages} 頁",
            file=file,
        )

        if total_pages > 1:
            await msg.add_reaction("⬅️")
            await msg.add_reaction("➡️")
            self._sessions[msg.id] = {
                "user_id":     member.id,
                "viewer_id":   member.id,
                "guild_id":    guild.id,
                "page":        page,
                "total_pages": total_pages,
                "channel_id":  msg.channel.id,
            }
            # 60 秒後自動清理
            asyncio.get_event_loop().call_later(
                60, lambda mid=msg.id: self._sessions.pop(mid, None)
            )

        return msg

    # ── 事件：翻頁反應 ──

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return
        if payload.message_id not in self._sessions:
            return

        session = self._sessions[payload.message_id]
        if payload.user_id != session["viewer_id"]:
            return

        emoji = str(payload.emoji)
        if emoji not in ("⬅️", "➡️"):
            return

        page = session["page"]
        if emoji == "➡️":
            page = min(page + 1, session["total_pages"] - 1)
        else:
            page = max(page - 1, 0)

        if page == session["page"]:
            return

        session["page"] = page
        channel = self.bot.get_channel(session["channel_id"])
        if not channel:
            return

        guild  = self.bot.get_guild(session["guild_id"])
        member = guild.get_member(session["user_id"])
        if not guild or not member:
            return

        try:
            old_msg = await channel.fetch_message(payload.message_id)
            self._sessions.pop(payload.message_id, None)
            await self._send_card(channel, member, guild, page, edit_msg=old_msg)
        except Exception as e:
            logger.error(f"翻頁失敗: {e}")

    # ── 事件：自動統計 message_count ──

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.content.startswith(self.bot.command_prefix):
            return

        content = message.content.strip()

        # 發言計數
        await self.record_stat(
            message.guild, message.author,
            "message_count", 1, message.channel
        )

        # 深夜發言（0:00～5:00）
        if datetime.now().hour < 5:
            await self.record_stat(
                message.guild, message.author,
                "night_message_count", 1, message.channel
            )

        # 查詢觸發（無前綴）
        if content in ("成就", "我的成就"):
            await self._send_card(message.channel, message.author, message.guild)

    # ── 指令 ──

    @commands.command(name="成就")
    async def achievements_cmd(self, ctx: commands.Context,
                               member: discord.Member = None):
        """查看成就頁面（可指定其他成員）"""
        target = member or ctx.author
        await self._send_card(ctx.channel, target, ctx.guild)

    @commands.command(name="給予成就")
    @commands.has_permissions(administrator=True)
    async def grant_achievement(self, ctx: commands.Context,
                                member: discord.Member, ach_id: str):
        """[管理員] 手動給予成就"""
        if ach_id not in ACH_BY_ID:
            ids = ", ".join(ACH_BY_ID.keys())
            await ctx.send(f"❌ 找不到成就 `{ach_id}`\n可用 ID：{ids}")
            return
        result = await self.unlock_special(ctx.guild, member, ach_id, ctx.channel)
        if not result:
            await ctx.send(f"⚠️ {member.display_name} 已擁有此成就。")

    @commands.command(name="重置成就")
    @commands.has_permissions(administrator=True)
    async def reset_achievement(self, ctx: commands.Context,
                                member: discord.Member):
        """[管理員] 清除某成員的所有成就與統計"""
        gid, uid = str(ctx.guild.id), str(member.id)
        if gid in self.data and uid in self.data[gid]:
            self.data[gid][uid] = {"unlocked": {}, "stats": {}}
            self._save()
            await ctx.send(f"🗑️ 已清除 {member.display_name} 的所有成就與統計資料。")
        else:
            await ctx.send(f"⚠️ 找不到 {member.display_name} 的成就資料。")

    @commands.command(name="成就列表")
    async def list_achievements(self, ctx: commands.Context,
                                category: str = None):
        """列出所有成就 ID（可用分類篩選：社交/音樂/遊戲/積分/特殊）"""
        achs = ALL_ACHIEVEMENTS
        if category:
            achs = [a for a in achs if a["category"] == category]
        if not achs:
            await ctx.send(f"❌ 找不到分類 `{category}`")
            return
        lines = [f"📋 **成就列表**（共 {len(achs)} 個）\n"]
        for a in achs:
            rcol_name = a["rarity"]
            lines.append(
                f"`{a['id']:<22}` {a['emoji']} **{a['name']}**"
                f"　{rcol_name}　{a['category']}"
            )
        # 超過 2000 字分段送出
        msg = ""
        for line in lines:
            if len(msg) + len(line) > 1900:
                await ctx.send(msg)
                msg = ""
            msg += line + "\n"
        if msg:
            await ctx.send(msg)
