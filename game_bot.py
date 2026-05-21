import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
import sqlite3
import random
import time
import io
import requests
from PIL import Image, ImageDraw, ImageOps
from datetime import datetime, timedelta

# Importing credentials directly from your config.py
from config import BOT_TOKEN, OWNER_ID

# Using the existing bot instance configured via config
bot = telebot.TeleBot(BOT_TOKEN)

# Database Setup
def init_db():
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            coins INTEGER DEFAULT 500,
            exp INTEGER DEFAULT 0,
            kills INTEGER DEFAULT 0,
            is_alive INTEGER DEFAULT 1,
            has_armor INTEGER DEFAULT 0,
            last_daily TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word_games (
            chat_id INTEGER PRIMARY KEY,
            host_id INTEGER,
            bet_amount INTEGER,
            secret_word TEXT,
            letters TEXT,
            players_joined TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_groups (
            chat_id INTEGER PRIMARY KEY
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS welcome_settings (
            chat_id INTEGER PRIMARY KEY,
            welcome_enabled INTEGER DEFAULT 0
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_settings (
            chat_id INTEGER PRIMARY KEY,
            request_enabled INTEGER DEFAULT 0
        )
    ''')
    # Dynamic column addition for backward compatibility
    try:
        cursor.execute("ALTER TABLE players ADD COLUMN is_angel INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
        
    conn.commit()
    conn.close()

# Helper function to check if Auto Request Accept is enabled in a chat
def is_request_enabled(chat_id):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT request_enabled FROM request_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] == 1:
        return True
    return False

# Helper function to check if welcome message is enabled in a chat
def is_welcome_enabled(chat_id):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT welcome_enabled FROM welcome_settings WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] == 1:
        return True
    return False

# Helper function to verify if a user is Admin or Owner
def is_user_admin(chat_id, user_id):
    if user_id == OWNER_ID:
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        if member.status in ['administrator', 'creator']:
            return True
    except Exception:
        pass
    return False

# Helper function to check if a user is a certified Angel/God Mode privileges
def has_angel_privileges(user_id):
    if user_id == OWNER_ID:
        return True
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_angel FROM players WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] == 1:
        return True
    return False


# --- 📝 OWNER DM LOGGING FUNCTIONS ---

def log_new_group_to_owner(chat):
    try:
        try:
            group_link = chat.invite_link
            if not group_link:
                group_link = bot.export_chat_invite_link(chat.id)
        except Exception:
            group_link = "NOT AN ADMIN / NO PERMISSION TO GET LINK"

        log_text = (
            "📥 *BOT ADDED TO NEW GROUP*\n\n"
            f"• GROUP NAME: {chat.title}\n"
            f"• GROUP ID: `{chat.id}`\n"
            f"• LINK: {group_link}"
        )
        bot.send_message(OWNER_ID, log_text.upper(), parse_mode="Markdown")
    except Exception:
        pass


# --- 🎨 DYNAMIC IMAGE GENERATOR (ROUND USER PHOTO + UNIX THEME) ---

def generate_welcome_image(bot_instance, user_id):
    try:
        base_img = Image.new("RGB", (800, 400), color=(10, 12, 22))
        draw = ImageDraw.Draw(base_img)
        
        draw.ellipse([(-50, -50), (250, 250)], fill=(24, 28, 50))
        draw.ellipse([(650, 250), (850, 450)], fill=(18, 22, 40))
        
        draw.text((40, 160), "UNIX", fill=(100, 110, 160))
        draw.text((40, 200), "WELCOME TO THE GROUP", fill=(255, 255, 255))

        user_photos = bot_instance.get_user_profile_photos(user_id, limit=1)
        if user_photos.total_count > 0:
            file_id = user_photos.photos[0][-1].file_id
            file_info = bot_instance.get_file(file_id)
            img_url = f"https://api.telegram.org/file/bot{bot_instance.token}/{file_info.file_path}"
            
            response = requests.get(img_url)
            pfp = Image.open(io.BytesIO(response.content)).convert("RGBA")
            pfp = pfp.resize((200, 200))
            
            mask = Image.new("L", (200, 200), 0)
            draw_mask = ImageDraw.Draw(mask)
            draw_mask.ellipse((0, 0, 200, 200), fill=255)
            
            base_img.paste(pfp, (520, 100), mask=mask)
            draw.ellipse([(515, 95), (725, 305)], outline=(75, 100, 230), width=4)
        else:
            draw.ellipse([(520, 100), (720, 300)], fill=(40, 45, 75))
            draw.text((585, 185), "AVATAR", fill=(150, 160, 190))
            
        bio = io.BytesIO()
        bio.name = 'welcome.png'
        base_img.save(bio, 'PNG')
        bio.seek(0)
        return bio
    except Exception:
        return None


# --- 😇 ANGEL COMMAND SETUP ---

@bot.message_handler(commands=['angel'])
def grant_angel_status(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ ACCESS DENIED! ONLY THE SUPREME BOT OWNER CAN BECOME AN ANGEL.")
        return
        
    user_id = message.from_user.id
    get_player(user_id, message.from_user.first_name)
    update_player(user_id, is_angel=1, is_alive=1)
    
    reply_text = "👼 *ANGEL MODE ACTIVATED!*\n\n✨ STATUS: ANGEL\n💰 Z-COINS: UNLIMITED\n🛡️ SAFEGUARD PROTECT SYSTEM ACCESSED!"
    bot.reply_to(message, reply_text.upper(), parse_mode="Markdown")


# --- 🎯 AUTO JOIN REQUEST HANDLER ---

@bot.chat_join_request_handler(func=lambda request: True)
def auto_accept_requests(request):
    chat_id = request.chat.id
    user_id = request.from_user.id
    user_name = request.from_user.first_name
    
    if is_request_enabled(chat_id):
        try:
            bot.approve_chat_join_request(chat_id, user_id)
            notification = f"✅ *AUTO ACCEPT:* APPROVED JOIN REQUEST FOR {user_name}! WELCOME TO THE ARENA! ⚔️"
            bot.send_message(chat_id, notification.upper(), parse_mode="Markdown")
        except Exception:
            pass


# --- 🚀 WELCOME & REQUEST TOGGLE COMMANDS ---

@bot.message_handler(commands=['requeston'])
def turn_request_on(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY GROUP ADMINS OR THE BOT OWNER CAN ACTIVATE AUTO REQUEST ACCEPTS!")
        return

    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO request_settings (chat_id, request_enabled) VALUES (?, 1)", (message.chat.id,))
    conn.commit()
    conn.close()
    
    reply_msg = "✅ *SUCCESS:* AUTO JOIN REQUEST ACCEPTANCE HAS BEEN ENABLED FOR THIS GROUP!"
    bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")

@bot.message_handler(commands=['requestoff'])
def turn_request_off(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY GROUP ADMINS OR THE BOT OWNER CAN DEACTIVATE AUTO REQUEST ACCEPTS!")
        return

    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO request_settings (chat_id, request_enabled) VALUES (?, 0)", (message.chat.id,))
    conn.commit()
    conn.close()
    
    reply_msg = "❌ *DISABLED:* AUTOMATIC JOIN REQUEST APPROVALS HAVE BEEN MUTED."
    bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")


@bot.message_handler(content_types=['new_chat_members'])
def log_group_and_welcome(message):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    
    for user in message.new_chat_members:
        if user.id == bot.get_me().id:
            cursor.execute("INSERT OR IGNORE INTO active_groups VALUES (?)", (message.chat.id,))
            conn.commit()
            log_new_group_to_owner(message.chat)
        else:
            if is_welcome_enabled(message.chat.id):
                member_count = bot.get_chat_member_count(message.chat.id)
                try:
                    group_link = message.chat.invite_link
                    if not group_link:
                        group_link = bot.export_chat_invite_link(message.chat.id)
                except Exception:
                    group_link = "NO LINK PERMISSION"

                markup = InlineKeyboardMarkup()
                bot_username = bot.get_me().username
                add_me_url = f"https://t.me/{bot_username}?startgroup=true"
                markup.add(InlineKeyboardButton("➕ ADD ME TO YOUR GROUP", url=add_me_url))
                
                username_str = f"@{user.username}" if user.username else "NO USERNAME"
                
                welcome_caption = (
                    "✨ *WELCOME TO MY GROUP!*\n\n"
                    f"👤 *USER NAME:* {user.first_name}\n"
                    f"🆔 *USER ID:* `{user.id}`\n"
                    f"🏷️ *USERNAME:* {username_str}\n"
                    f"🔢 *JOIN MEMBER NUMBER:* #{member_count}\n"
                    f"🔗 *GROUP LINK:* {group_link}"
                )
                
                img_data = generate_welcome_image(bot, user.id)
                
                if img_data:
                    bot.send_photo(message.chat.id, img_data, caption=welcome_caption.upper(), parse_mode="Markdown", reply_markup=markup)
                else:
                    bot.send_message(message.chat.id, welcome_caption.upper(), parse_mode="Markdown", reply_markup=markup)
                
    conn.close()

@bot.message_handler(commands=['welcomeon'])
def turn_welcome_on(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY GROUP ADMINS OR THE BOT OWNER CAN ACTIVATE WELCOME MESSAGES!")
        return

    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO welcome_settings (chat_id, welcome_enabled) VALUES (?, 1)", (message.chat.id,))
    conn.commit()
    conn.close()
    
    reply_msg = "✅ *SUCCESS:* AUTOMATED WELCOME MESSAGES HAVE BEEN ENABLED FOR THIS GROUP!"
    bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")

@bot.message_handler(commands=['welcomeoff'])
def turn_welcome_off(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY GROUP ADMINS OR THE BOT OWNER CAN DEACTIVATE WELCOME MESSAGES!")
        return

    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO welcome_settings (chat_id, welcome_enabled) VALUES (?, 0)", (message.chat.id,))
    conn.commit()
    conn.close()
    
    reply_msg = "❌ *DISABLED:* AUTOMATED WELCOME MESSAGES HAVE BEEN MUTED FOR THIS GROUP."
    bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")


# --- 🛡️ GROUP BAN, KICK, MUTE MANAGEMENT COMMANDS ---

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if message.chat.type == 'private': return
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY ADMINS CAN USE THIS COMMAND!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ REPLY TO THE USER YOU WANT TO BAN.")
        return
    
    target_user = message.reply_to_message.from_user
    try:
        bot.ban_chat_member(message.chat.id, target_user.id)
        bot.reply_to(message, f"⚡ *BANNED:* {target_user.first_name} HAS BEEN BANISHED FROM THE GROUP! 🛑".upper(), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ FAILED TO BAN USER: {str(e)}")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if message.chat.type == 'private': return
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY ADMINS CAN USE THIS COMMAND!")
        return
        
    target_user_id = None
    target_name = "USER"
    
    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
    else:
        args = message.text.split()
        if len(args) > 1 and args[1].isdigit():
            target_user_id = int(args[1])
            
    if not target_user_id:
        bot.reply_to(message, "❌ REPLY TO A MESSAGE OR PROVIDE A USER ID TO UNBAN.")
        return
        
    try:
        bot.unban_chat_member(message.chat.id, target_user_id, only_if_banned=True)
        bot.reply_to(message, f"✅ *UNBANNED:* {target_name} (`{target_user_id}`) HAS BEEN UNBANNED COMPLETED!".upper(), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ FAILED TO UNBAN USER: {str(e)}")

@bot.message_handler(commands=['kick'])
def kick_user(message):
    if message.chat.type == 'private': return
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY ADMINS CAN USE THIS COMMAND!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ REPLY TO THE USER YOU WANT TO KICK.")
        return
        
    target_user = message.reply_to_message.from_user
    try:
        bot.ban_chat_member(message.chat.id, target_user.id)
        bot.unban_chat_member(message.chat.id, target_user.id)
        bot.reply_to(message, f"🏃 *KICKED:* {target_user.first_name} HAS BEEN REMOVED FROM THE CHAT!".upper(), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ FAILED TO KICK USER: {str(e)}")

@bot.message_handler(commands=['mute'])
def mute_user(message):
    if message.chat.type == 'private': return
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY ADMINS CAN USE THIS COMMAND!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ REPLY TO THE USER YOU WANT TO MUTE.")
        return
        
    target_user = message.reply_to_message.from_user
    try:
        bot.restrict_chat_member(message.chat.id, target_user.id, permissions=ChatPermissions(can_send_messages=False))
        bot.reply_to(message, f"🔇 *MUTED:* {target_user.first_name} HAS BEEN SILENCED IN THIS CHAT!".upper(), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ FAILED TO MUTE USER: {str(e)}")

@bot.message_handler(commands=['unmute'])
def unmute_user(message):
    if message.chat.type == 'private': return
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ ONLY ADMINS CAN USE THIS COMMAND!")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "❌ REPLY TO THE USER YOU WANT TO UNMUTE.")
        return
        
    target_user = message.reply_to_message.from_user
    try:
        bot.restrict_chat_member(message.chat.id, target_user.id, permissions=ChatPermissions(
            can_send_messages=True, can_send_media_messages=True, 
            can_send_polls=True, can_add_web_page_previews=True
        ))
        bot.reply_to(message, f"🔊 *UNMUTED:* {target_user.first_name} CAN SPEAK IN CHAT AGAIN!".upper(), parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ FAILED TO UNMUTE USER: {str(e)}")

@bot.message_handler(commands=['kickme'])
def self_kick(message):
    if message.chat.type == 'private': return
    try:
        bot.reply_to(message, f"👋 *GOODBYE:* {message.from_user.first_name} HAS LEFT THE ARENA SYSTEM BY SELF-KICK!".upper(), parse_mode="Markdown")
        bot.ban_chat_member(message.chat.id, message.from_user.id)
        bot.unban_chat_member(message.chat.id, message.from_user.id)
    except Exception as e:
        bot.reply_to(message, f"❌ FAILED TO EXECUTE SELF-KICK: {str(e)}")


def get_player(user_id, username="Player"):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    player = cursor.fetchone()
    if not player:
        cursor.execute("INSERT INTO players (user_id, username, coins, exp, kills, is_alive, has_armor, last_daily, is_angel) VALUES (?, ?, 500, 0, 0, 1, 0, ?, 0)", (user_id, username, "2000-01-01 00:00:00"))
        conn.commit()
        cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        player = cursor.fetchone()
    conn.close()
    return player

def update_player(user_id, **kwargs):
    if kwargs:
        conn = sqlite3.connect('game_bot.db')
        cursor = conn.cursor()
        for key, value in kwargs.items():
            cursor.execute(f"UPDATE players SET {key} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()
        conn.close()

# --- 🎁 DAILY REWARD COMMAND (24h Cooldown) ---

@bot.message_handler(commands=['daily'])
def get_daily_reward(message):
    user_id = message.from_user.id
    player = get_player(user_id, message.from_user.first_name)
    
    last_daily_str = player[7] if player[7] else "2000-01-01 00:00:00"
    last_daily_time = datetime.strptime(last_daily_str, "%Y-%m-%d %H:%M:%S")
    
    current_time = datetime.now()
    time_difference = current_time - last_daily_time
    
    if time_difference < timedelta(hours=24):
        time_left = timedelta(hours=24) - time_difference
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        reply_msg = f"⏳ *COOLDOWN:* YOU ALREADY CLAIMED YOUR DAILY REWARD! TRY AGAIN AFTER `{hours}H {minutes}M {seconds}S`."
        bot.reply_to(message, reply_msg.upper())
        return

    new_coins = player[2] + 100
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    update_player(user_id, coins=new_coins, last_daily=current_time_str)
    
    coins_display = "UNLIMITED" if has_angel_privileges(user_id) else f"{new_coins}"
    reply_msg = f"🎁 *DAILY REWARD:* YOU CLAIMED YOUR DAILY `100` Z-COINS!\nYOUR CURRENT BALANCE: `{coins_display}` Z-COINS."
    bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")

# --- 👑 OWNER MASTER COMMANDS ---

@bot.message_handler(commands=['addcoins'])
def add_coins_to_user(message):
    if not has_angel_privileges(message.from_user.id):
        reply_msg = "❌ ONLY THE BOT OWNER OR CERTIFIED ANGELS CAN USE THIS COMMAND!"
        bot.reply_to(message, reply_msg.upper())
        return

    if not message.reply_to_message:
        reply_msg = "❌ REPLY TO SOMEONE'S MESSAGE WITH `/addcoins [amount]` TO GIVE THEM COINS."
        bot.reply_to(message, reply_msg.upper())
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        reply_msg = "❌ FORMAT: `/addcoins [amount]`"
        bot.reply_to(message, reply_msg.upper())
        return

    amount_to_add = int(args[1])
    target_user = message.reply_to_message.from_user
    
    player_data = get_player(target_user.id, target_user.first_name)
    new_balance = player_data[2] + amount_to_add
    
    update_player(target_user.id, coins=new_balance)
    reply_msg = f"💰 *SUCCESS:* ADDED `{amount_to_add}` Z-COINS TO *{target_user.first_name}*'S ACCOUNT!\nNEW BALANCE: `{new_balance}` Z-COINS."
    bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")

# --- 💸 USER COIN TRANSFER SYSTEM ---

@bot.message_handler(commands=['paycoin'])
def pay_coin_to_user(message):
    if not message.reply_to_message:
        reply_msg = "❌ REPLY TO SOMEONE'S MESSAGE WITH `/paycoin [amount]` TO TRANSFER COINS."
        bot.reply_to(message, reply_msg.upper())
        return

    if message.reply_to_message.from_user.is_bot:
        reply_msg = "🤖 *ERROR:* YOU CANNOT TRANSFER COINS TO A BOT!"
        bot.reply_to(message, reply_msg.upper())
        return

    sender_id = message.from_user.id
    receiver_id = message.reply_to_message.from_user.id

    if sender_id == receiver_id:
        reply_msg = "❌ YOU CANNOT TRANSFER COINS TO YOURSELF!"
        bot.reply_to(message, reply_msg.upper())
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        reply_msg = "❌ FORMAT: `/paycoin [amount]` (EXAMPLE: `/paycoin 100`)"
        bot.reply_to(message, reply_msg.upper())
        return

    amount_to_pay = int(args[1])
    if amount_to_pay <= 0:
        reply_msg = "❌ AMOUNT MUST BE GREATER THAN 0!"
        bot.reply_to(message, reply_msg.upper())
        return

    sender = get_player(sender_id, message.from_user.first_name)
    receiver = get_player(receiver_id, message.reply_to_message.from_user.first_name)

    if not has_angel_privileges(sender_id) and sender[2] < amount_to_pay:
        reply_msg = f"❌ TRANSACTION FAILED! YOU DON'T HAVE ENOUGH BALANCE. YOUR BALANCE: `{sender[2]}` Z-COINS."
        bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")
        return

    if not has_angel_privileges(sender_id):
        update_player(sender_id, coins=sender[2] - amount_to_pay)
        
    update_player(receiver_id, coins=receiver[2] + amount_to_pay)

    sender_bal = "UNLIMITED" if has_angel_privileges(sender_id) else f"{sender[2] - amount_to_pay}"
    receiver_bal = f"{receiver[2] + amount_to_pay}"

    success_msg = f"💸 *TRANSACTION SUCCESSFUL!*\n\n"
    success_msg += f"👤 *FROM:* {sender[1]}\n"
    success_msg += f"👤 *TO:* {receiver[1]}\n"
    success_msg += f"💰 *AMOUNT SENT:* `{amount_to_pay}` Z-COINS\n\n"
    success_msg += f"📊 *NEW BALANCES:*\n"
    success_msg += f"• {sender[1]}: `{sender_bal}` Z-COINS\n"
    success_msg += f"• {receiver[1]}: `{receiver_bal}` Z-COINS"

    bot.reply_to(message, success_msg.upper(), parse_mode="Markdown")

# --- 📊 STATS & RANK COMMANDS ---

@bot.message_handler(commands=['bal'])
def view_profile(message):
    user_id = message.from_user.id
    p = get_player(user_id, message.from_user.first_name)
    
    if has_angel_privileges(user_id):
        status = "ANGEL"
        coins_display = "UNLIMITED"
    else:
        status = "ALIVE" if p[5] == 1 else "DEAD"
        coins_display = f"{p[2]}"
        
    armor = "YES" if p[6] == 1 else "NO"
    
    msg = f"👤 *PROFILE: {p[1]}*\n\n"
    msg += f"ℹ️ STATUS: {status}\n"
    msg += f"💰 Z-COINS: {coins_display}\n"
    msg += f"⭐ EXP: {p[3]}\n"
    msg += f"⚔️ KILLS: {p[4]}\n"
    msg += f"🛡️ ARMOR: {armor}"
    
    msg_upper = msg.upper()
    
    try:
        user_photos = bot.get_user_profile_photos(user_id)
        if user_photos.total_count > 0:
            photo_id = user_photos.photos[0][-1].file_id
            bot.send_photo(message.chat.id, photo_id, caption=msg_upper, parse_mode="Markdown")
        else:
            bot.reply_to(message, msg_upper, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, msg_upper, parse_mode="Markdown")

@bot.message_handler(commands=['topkills'])
def top_kills(message):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, kills FROM players ORDER BY kills DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    
    msg = "💀 *DEADLIEST PLAYERS*\n\n"
    for i, row in enumerate(rows, 1):
        msg += f"{i}. {row[0]} - {row[1]} KILLS\n"
    bot.reply_to(message, msg.upper(), parse_mode="Markdown")

@bot.message_handler(commands=['rankers'])
def global_rankers(message):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, exp FROM players ORDER BY exp DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    
    msg = "⭐ *GLOBAL EXP RANKINGS*\n\n"
    for i, row in enumerate(rows, 1):
        msg += f"{i}. {row[0]} - {row[1]} EXP\n"
    bot.reply_to(message, msg.upper(), parse_mode="Markdown")

# --- ⚔️ COMBAT COMMANDS ---

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if not message.reply_to_message:
        reply_msg = "❌ WHO DO YOU WANT TO KILL? REPLY TO THEIR MESSAGE WITH THIS COMMAND."
        bot.reply_to(message, reply_msg.upper())
        return
        
    if message.reply_to_message.from_user.is_bot:
        reply_msg = "🤖 *ERROR:* BOTS CANNOT PARTICIPATE IN COMBAT! YOU CAN ONLY ATTACK REAL USERS."
        bot.reply_to(message, reply_msg.upper())
        return

    attacker_id = message.from_user.id
    attacker = get_player(attacker_id, message.from_user.first_name)
    victim_id = message.reply_to_message.from_user.id
    victim = get_player(victim_id, message.reply_to_message.from_user.first_name)
    
    if attacker_id == victim_id:
        reply_msg = "❌ YOU CANNOT KILL YOURSELF!"
        bot.reply_to(message, reply_msg.upper())
        return

    # Anti-Kill Shield: Triggered if victim has Angel status active
    if has_angel_privileges(victim_id):
        update_player(attacker_id, is_alive=0, has_armor=0)
        reply_msg = f"👼 *ANGEL SHIELD:* SORRY YOU CANNOT KILL OWNER BABY! ⚡\n\nTHE ATTACK REFLECTED AND STRUCK *{attacker[1]}* DEAD INSTANTLY! 💀🪦"
        bot.reply_to(message, reply_msg.upper())
        return

    if has_angel_privileges(attacker_id):
        update_player(victim_id, is_alive=0, has_armor=0)
        update_player(attacker_id, kills=attacker[4]+1, exp=attacker[3]+100)
        reply_msg = f"⚡ *ANGEL STRIKE:* SUPREME ANGEL *{attacker[1]}* INSTANTLY ANNIHILATED *{victim[1]}*, BYPASSING ALL SHIELDS AND ARMOR! 💀 (+100 EXP)"
        bot.reply_to(message, reply_msg.upper())
        return

    if attacker[5] == 0:
        reply_msg = "❌ YOU ARE DEAD! USE `/REVIVE` FIRST."
        bot.reply_to(message, reply_msg.upper())
        return
    if victim[5] == 0:
        reply_msg = "❌ THEY ARE ALREADY DEAD!"
        bot.reply_to(message, reply_msg.upper())
        return

    if victim[6] == 1:
        update_player(victim_id, has_armor=0)
        reply_msg = f"🛡️ *{victim[1]}* SURVIVED BECAUSE OF ARMOR! BUT THEIR ARMOR BROKE."
        bot.reply_to(message, reply_msg.upper())
        return
        
    if random.choice([True, False]):
        update_player(victim_id, is_alive=0)
        update_player(attacker_id, coins=attacker[2]+500, kills=attacker[4]+1, exp=attacker[3]+50)
        reply_msg = f"⚔️ *{attacker[1]}* HUNTED DOWN AND KILLED *{victim[1]}*! (+500 Z-COINS & +50 EXP)"
        bot.reply_to(message, reply_msg.upper())
    else:
        if not has_angel_privileges(attacker_id):
            new_attacker_coins = max(0, attacker[2] - 100)
            update_player(attacker_id, coins=new_attacker_coins)
            coin_msg = f" ALSO, YOU WERE INJURED DURING THE ATTACK AND PAID A *HOSPITAL BILL* OF `100` Z-COINS! (REMAINING: `{new_attacker_coins}` Z-COINS)"
        else:
            coin_msg = ""
            
        reply_msg = f"🏃 *{victim[1]}* MANAGED TO ESCAPE THE ATTACK!{coin_msg}"
        bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")

@bot.message_handler(commands=['rob'])
def rob_user(message):
    if not message.reply_to_message:
        reply_msg = "❌ WHO DO YOU WANT TO ROB? REPLY TO THEIR MESSAGE."
        bot.reply_to(message, reply_msg.upper())
        return
        
    if message.reply_to_message.from_user.is_bot:
        reply_msg = "🤖 *ERROR:* YOU CANNOT ROB A BOT!"
        bot.reply_to(message, reply_msg.upper())
        return

    robber_id = message.from_user.id
    victim_id = message.reply_to_message.from_user.id
    
    if has_angel_privileges(victim_id):
        reply_msg = "⚡ *ERROR:* YOU CANNOT ROB AN ANGEL! KEEP YOUR HANDS OFF OWNER BABY."
        bot.reply_to(message, reply_msg.upper())
        return
        
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        reply_msg = "❌ FORMAT: /ROB [AMOUNT]"
        bot.reply_to(message, reply_msg.upper())
        return
        
    amount = int(args[1])
    robber = get_player(robber_id, message.from_user.first_name)
    victim = get_player(victim_id, message.reply_to_message.from_user.first_name)
    
    if robber[5] == 0:
        reply_msg = "❌ DEAD PLAYERS CANNOT ROB ANYONE!"
        bot.reply_to(message, reply_msg.upper())
        return
        
    if victim[2] < amount and not has_angel_privileges(victim_id):
        reply_msg = "❌ THEY DON'T HAVE THAT MANY Z-COINS!"
        bot.reply_to(message, reply_msg.upper())
        return
        
    if random.choice([True, False]):
        update_player(robber[0], coins=robber[2]+amount)
        if not has_angel_privileges(victim_id):
            update_player(victim_id, coins=victim[2]-amount)
        reply_msg = f"💰 *{robber[1]}* SUCCESSFULLY ROBBED {amount} Z-COINS FROM *{victim[1]}*!"
        bot.reply_to(message, reply_msg.upper())
    else:
        penalty = int(amount * 0.5)
        if not has_angel_privileges(robber_id):
            update_player(robber[0], coins=max(0, robber[2]-penalty))
        reply_msg = f"👮 *{robber[1]}* GOT CAUGHT WHILE ROBBING! FINED {penalty} Z-COINS."
        bot.reply_to(message, reply_msg.upper())

@bot.message_handler(commands=['revive'])
def revive_user(message):
    user_id = message.from_user.id
    p = get_player(user_id, message.from_user.first_name)
    
    if p[5] == 1:
        reply_msg = "❤️ YOU ARE ALREADY ALIVE!"
        bot.reply_to(message, reply_msg.upper())
        return
        
    if not has_angel_privileges(user_id):
        if p[2] < 200:
            reply_msg = "❌ *REVIVE FAILED!* YOU NEED AT LEAST `200` Z-COINS TO PAY THE REVIVE BILL. ASK ANOTHER PLAYER TO SEND YOU COINS USING `/PAYCOIN`!"
            bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")
            return
        
        new_coins = p[2] - 200
        update_player(user_id, is_alive=1, coins=new_coins)
        reply_msg = f"✨ *RESURRECTED!* YOU PAID A *REVIVE BILL* OF `200` Z-COINS AND RETURNED TO LIFE! LET'S FIGHT!\nREMAINING BALANCE: `{new_coins}` Z-COINS."
        bot.reply_to(message, reply_msg.upper(), parse_mode="Markdown")
    
    else:
        update_player(user_id, is_alive=1)
        reply_msg = "🧘 *ANGEL REVIVE:* ANGEL RESURRECTED BACK TO LIFE INSTANTLY WITHOUT ANY COST!"
        bot.reply_to(message, reply_msg.upper())

@bot.message_handler(commands=['protect'])
def buy_armor(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p[6] == 1:
        reply_msg = "🛡️ YOU ALREADY HAVE ARMOR PROTECTION ACTIVE!"
        bot.reply_to(message, reply_msg.upper())
        return
        
    if not has_angel_privileges(message.from_user.id):
        if p[2] < 300:
            reply_msg = "❌ YOU NEED 300 Z-COINS TO HIRE ARMOR!"
            bot.reply_to(message, reply_msg.upper())
            return
        update_player(message.from_user.id, has_armor=1, coins=p[2]-300)
    else:
        update_player(message.from_user.id, has_armor=1)
        
    reply_msg = "🛡️ YOU BOUGHT ARMOR! THIS WILL PROTECT YOU FROM YOUR NEXT DEATH ATTACK."
    bot.reply_to(message, reply_msg.upper())

# --- 🎮 WORD GAME SYSTEM ---

@bot.message_handler(commands=['words'])
def host_word_game(message):
    if not has_angel_privileges(message.from_user.id):
        reply_msg = "❌ ONLY THE BOT OWNER OR ANGELS CAN START A NEW WORD GAME!"
        bot.reply_to(message, reply_msg.upper())
        return

    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit():
        reply_msg = "❌ FORMAT: /WORDS [BET_AMT] [SECRET_WORD]"
        bot.reply_to(message, reply_msg.upper())
        return
        
    amt = int(args[1])
    secret_word = args[2].lower()
    
    letters_list = list(secret_word)
    random.shuffle(letters_list)
    scrambled = "".join(letters_list)
    
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO active_groups VALUES (?)", (message.chat.id,))
    cursor.execute("SELECT chat_id FROM active_groups")
    groups = cursor.fetchall()
    
    game_msg = f"🎮 *GLOBAL WORD GAME STARTED!*\n\nHOST: {message.from_user.first_name}\nBET AMOUNT: {amt} Z-COINS\nSCRAMBLED LETTERS: `{scrambled}`\n\nTYPE `/BET {amt}` TO JOIN THE GAME HERE AND GUESS THE WORD!"
    
    for group in groups:
        g_id = group[0]
        try:
            cursor.execute("REPLACE INTO word_games VALUES (?, ?, ?, ?, ?, ?)", 
                           (g_id, message.from_user.id, amt, secret_word, scrambled, str(message.from_user.id)))
            bot.send_message(g_id, game_msg.upper(), parse_mode="Markdown")
        except Exception:
            continue
            
    conn.commit()
    conn.close()

@bot.message_handler(commands=['bet'])
def join_bet(message):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM word_games WHERE chat_id = ?", (message.chat.id,))
    game = cursor.fetchone()
    conn.close()
    
    if not game:
        reply_msg = "❌ NO ACTIVE WORD GAME RUNNING IN THIS GROUP."
        bot.reply_to(message, reply_msg.upper())
        return
        
    player = get_player(message.from_user.id, message.from_user.first_name)
    bet_amt = game[2]
    
    if not has_angel_privileges(message.from_user.id) and player[2] < bet_amt:
        reply_msg = "❌ YOU DON'T HAVE ENOUGH Z-COINS TO JOIN THIS BET!"
        bot.reply_to(message, reply_msg.upper())
        return
        
    joined_players = game[5].split(',')
    if str(message.from_user.id) in joined_players:
        reply_msg = "❌ YOU HAVE ALREADY JOINED THIS GAME! TRY TO SOLVE THE WORD."
        bot.reply_to(message, reply_msg.upper())
        return
        
    joined_players.append(str(message.from_user.id))
    new_players_str = ",".join(joined_players)
    
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE word_games SET players_joined = ? WHERE chat_id = ?", (message.chat.id,))
    conn.commit()
    conn.close()
    
    if not has_angel_privileges(message.from_user.id):
        update_player(message.from_user.id, coins=player[2]-bet_amt)
    reply_msg = f"✅ YOU JOINED THE GAME FOR {bet_amt} Z-COINS! GUESS THE WORD AND TYPE IT IN CHAT."
    bot.reply_to(message, reply_msg.upper())

@bot.message_handler(func=lambda m: True)
def check_word_winner(message):
    if message.from_user.is_bot:
        return

    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM word_games WHERE chat_id = ?", (message.chat.id,))
    game = cursor.fetchone()
    conn.close()
    
    if game and message.text.strip().lower() == game[3]:
        joined_players = game[5].split(',')
        if str(message.from_user.id) not in joined_players:
            return 
            
        bet_amt = game[2]
        total_pool = bet_amt * len(joined_players)
        winner = get_player(message.from_user.id, message.from_user.first_name)
        
        update_player(message.from_user.id, coins=winner[2]+total_pool, exp=winner[3]+30)
        
        conn = sqlite3.connect('game_bot.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM word_games WHERE chat_id = ?", (message.chat.id,))
        conn.commit()
        conn.close()
        
        win_msg = f"🎉 *GROUP WINNER!*\n\n*{message.from_user.first_name}* GUESSED THE CORRECT WORD (`{game[3]}`).\n💰 REWARD: RECEIVED {total_pool} Z-COINS AND +30 EXP!"
        bot.send_message(message.chat.id, win_msg.upper(), parse_mode="Markdown")

# --- 🚀 RUNNING THE BOT LOOP KEEP-ALIVE ---
if __name__ == '__main__':
    init_db()
    print("Davi Game Bot Started Successfully with PayCoin & Ultimate Owner Protection...")
    bot.infinity_polling()
