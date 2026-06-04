import discord
from discord.ext import commands, tasks
import json
import os
import datetime
import threading
from flask import Flask

app = Flask('')
@app.route('/')
def home(): return "Bot is alive!"
def run_flask(): 
    port = int(os.environ.get("PORT", 8080))
    try:
        app.run(host="0.0.0.0", port=port, use_reloader=False)
    except Exception as e:
        print(f"Flask 啟動失敗 (可能已在運行): {e}")

# 在啟動機器人前先啟動 Flask 執行緒
web_thread = threading.Thread(target=run_flask, daemon=True)
web_thread.start()

# 設定機器人
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# --- 🛠️ 絕對路徑防禦存檔區塊 ---
# 自動抓取這個 python 檔案所在的資料夾位置
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 在同一個地方創立一個叫 bot_data 的資料夾（避免路徑迷路）
DATA_FOLDER = os.path.join(BASE_DIR, "bot_data")
if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# 最終的存檔路徑 (會鎖在 bot_data/user_stats.json)
DATA_FILE = os.path.join(DATA_FOLDER, "user_stats.json")

# 讀取或初始化資料（加入 utf-8 確保中文字與資料安全）
if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            user_data = json.load(f)
        print(f"【系統】成功載入舊數據！目前已記錄 {len(user_data)} 個使用者的資料。")
    except Exception as e:
        print(f"【警告】讀取檔案失敗：{e}。將初始化新資料。")
        user_data = {}
else:
    print("【系統】未發現舊存檔，已自動建立全新的資料庫。")
    user_data = {}

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(user_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"【嚴重錯誤】無法寫入檔案！錯誤訊息：{e}")
# -------------------------------------

# 升級所需訊息量公式
def messages_needed_for_level(level):
    return int(5 * (level ** 2) + 5 * level + 5)

# --- 1. 每日午夜自動重設「本日訊息量」的排程任務 ---
@tasks.loop(time=datetime.time(hour=0, minute=0)) # 每天 00:00 執行
async def reset_daily_stats():
    for user_id in user_data:
        user_data[user_id]["daily_msg"] = 0
    save_data()
    print("【系統通知】每日午夜已重設所有人本日訊息量。")

# --- 2. 監聽發言並直接加分 ---
@bot.event
async def on_message(message):
    if message.author.bot or message.guild is None:
        return

    user_id = str(message.author.id)

    # 如果是新使用者，初始化資料
    if user_id not in user_data:
        user_data[user_id] = {
            "total_msg": 0,    # 總訊息量
            "daily_msg": 0,    # 本日訊息量
            "level": 0,        # 目前等級
            "current_xp": 0    # 當前等級累積的訊息量
        }
    
    # 安全補齊欄位
    if "daily_msg" not in user_data[user_id]: user_data[user_id]["daily_msg"] = 0
    if "current_xp" not in user_data[user_id]: user_data[user_id]["current_xp"] = user_data[user_id]["total_msg"]

    # 訊息量 +1
    user_data[user_id]["total_msg"] += 1
    user_data[user_id]["daily_msg"] += 1
    user_data[user_id]["current_xp"] += 1

    current_lvl = user_data[user_id]["level"]
    needed_msg = messages_needed_for_level(current_lvl)

    # 檢查是否升級
    if user_data[user_id]["current_xp"] >= needed_msg:
        user_data[user_id]["level"] += 1
        user_data[user_id]["current_xp"] = 0 # 升級後該級進度歸零
        new_lvl = user_data[user_id]["level"]
        
        embed = discord.Embed(
            title="🎉 恭喜升級！",
            description=f"{message.author.mention} 剛剛等級提升到了 **Level {new_lvl}**！",
            color=discord.Color.from_rgb(255, 215, 0)
        )
        await message.channel.send(embed=embed)

    save_data()
    await bot.process_commands(message)

# --- 3. 升級版 !rank 指令 ---
@bot.command(name="rank")
async def rank(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_id = str(target.id)

    if user_id not in user_data or user_data[user_id]["total_msg"] == 0:
        embed = discord.Embed(description=f"❓ {target.mention} 目前還沒有發言紀錄。", color=discord.Color.red())
        await ctx.send(embed=embed)
        return

    lvl = user_data[user_id]["level"]
    current_xp = user_data[user_id]["current_xp"]
    needed_msg = messages_needed_for_level(lvl)
    total_msg = user_data[user_id]["total_msg"]
    daily_msg = user_data[user_id]["daily_msg"]

    # 進度條
    progress_percentage = min(int((current_xp / needed_msg) * 10), 10)
    bar = "■" * progress_percentage + "□" * (10 - progress_percentage)

    embed = discord.Embed(title=f"🔰 {target.display_name} 的成就卡片", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="目前等級", value=f"🆙 **Level {lvl}**", inline=True)
    embed.add_field(name="本日發言", value=f"💬 `{daily_msg}` 則", inline=True)
    embed.add_field(name="總訊息量", value=f"📊 `{total_msg}` 則", inline=True)
    embed.add_field(name="升級進度", value=f"`{bar}` ({current_xp}/{needed_msg})", inline=False)
    
    await ctx.send(embed=embed)

# --- 4. 新增指令：!leaderboard (查看排名) ---
@bot.command(name="leaderboard", aliases=["lb", "排名"])
async def leaderboard(ctx, scope="total"):
    if scope not in ["total", "daily", "本日", "總共"]:
        await ctx.send("❌ 請輸入正確的範圍：`!leaderboard 總共` 或 `!leaderboard 本日`")
        return

    is_daily = scope in ["daily", "本日"]
    sort_key = "daily_msg" if is_daily else "total_msg"
    title_text = "📅 本日活躍度排行" if is_daily else "🏆 伺服器總訊息量排行"

    # 排序資料
    sorted_users = sorted(user_data.items(), key=lambda x: x[1].get(sort_key, 0), reverse=True)
    
    embed = discord.Embed(title=title_text, color=discord.Color.orange(), timestamp=datetime.datetime.now())
    
    count = 0
    for u_id, stats in sorted_users:
        if count >= 10: # 只顯示前 10 名
            break
        
        member = ctx.guild.get_member(int(u_id))
        if member is None: # 如果成員已經離開伺服器就跳過
            continue
            
        count += 1
        msg_count = stats.get(sort_key, 0)
        lvl_text = f" (Lvl {stats['level']})" if not is_daily else ""
        
        # 前三名給皇冠或獎牌
        medal = "🥇" if count == 1 else "🥈" if count == 2 else "🥉" if count == 3 else f"`#{count}`"
        embed.add_field(
            name=f"{medal} {member.display_name}{lvl_text}",
            value=f"發言 `{msg_count}` 則",
            inline=False
        )

    if count == 0:
        embed.description = "目前尚無排名數據。"

    await ctx.send(embed=embed)

# --- 5. 機器人上線通知 ---
@bot.event
async def on_ready():
    print(f"新版等級與排名機器人已上線：{bot.user.name}")
    if not reset_daily_stats.is_running():
        reset_daily_stats.start()

# 執行機器人 (已放入你的 Token)
if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ 錯誤：請在環境變數中設置 DISCORD_TOKEN")
