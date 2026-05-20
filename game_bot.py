import telebot
import sqlite3
import random
import time
from datetime import datetime, timedelta

# Importing credentials directly from your config.py
from config import API_TOKEN, OWNER_ID

# Using the existing bot instance configured via config
bot = telebot.TeleBot(API_TOKEN)

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
    conn.commit()
    conn.close()

# Logs group ID when bot is added to a new group
@bot.message_handler(content_types=['new_chat_members'])
def log_group(message):
    for user in message.new_chat_members:
        if user.id == bot.get_me().id:
            conn = sqlite3.connect('game_bot.db')
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO active_groups VALUES (?)", (message.chat.id,))
            conn.commit()
            conn.close()

def get_player(user_id, username="Player"):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    player = cursor.fetchone()
    if not player:
        cursor.execute("INSERT INTO players (user_id, username, last_daily) VALUES (?, ?, ?)", (user_id, username, "2000-01-01 00:00:00"))
        conn.commit()
        cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        player = cursor.fetchone()
    conn.close()
    return player

def update_player(user_id, **kwargs):
    if user_id == OWNER_ID and 'coins' in kwargs:
        pass
        
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
    
    # Check 24 hours cooldown
    last_daily_str = player[7] if player[7] else "2000-01-01 00:00:00"
    last_daily_time = datetime.strptime(last_daily_str, "%Y-%m-%d %H:%M:%S")
    
    current_time = datetime.now()
    time_difference = current_time - last_daily_time
    
    if time_difference < timedelta(hours=24):
        time_left = timedelta(hours=24) - time_difference
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        bot.reply_to(message, f"⏳ *Cooldown:* You already claimed your daily reward! Try again after `{hours}h {minutes}m {seconds}s`.")
        return

    # Add 100 coins and update timestamp
    new_coins = player[2] + 100
    current_time_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
    
    update_player(user_id, coins=new_coins, last_daily=current_time_str)
    
    coins_display = "♾️ Unlimited" if user_id == OWNER_ID else f"{new_coins}"
    bot.reply_to(message, f"🎁 *DAILY REWARD:* You claimed your daily `100` Z-Coins!\nYour Current Balance: `{coins_display}` Z-Coins.")

# --- 👑 OWNER MASTER COMMANDS ---

@bot.message_handler(commands=['addcoins'])
def add_coins_to_user(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Only the Bot Owner can use this command!")
        return

    if not message.reply_to_message:
        bot.reply_to(message, "❌ Reply to someone's message with `/addcoins [amount]` to give them coins.")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "❌ Format: `/addcoins [amount]`")
        return

    amount_to_add = int(args[1])
    target_user = message.reply_to_message.from_user
    
    player_data = get_player(target_user.id, target_user.first_name)
    new_balance = player_data[2] + amount_to_add
    
    update_player(target_user.id, coins=new_balance)
    bot.reply_to(message, f"💰 *SUCCESS:* Added `{amount_to_add}` Z-Coins to *{target_user.first_name}*'s account!\nNew Balance: `{new_balance}` Z-Coins.")

# --- 💸 USER COIN TRANSFER SYSTEM ---

@bot.message_handler(commands=['paycoin'])
def pay_coin_to_user(message):
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Reply to someone's message with `/paycoin [amount]` to transfer coins.")
        return

    if message.reply_to_message.from_user.is_bot:
        bot.reply_to(message, "🤖 *Error:* You cannot transfer coins to a bot!")
        return

    sender_id = message.from_user.id
    receiver_id = message.reply_to_message.from_user.id

    if sender_id == receiver_id:
        bot.reply_to(message, "❌ You cannot transfer coins to yourself!")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "❌ Format: `/paycoin [amount]` (Example: `/paycoin 100`)")
        return

    amount_to_pay = int(args[1])
    if amount_to_pay <= 0:
        bot.reply_to(message, "❌ Amount must be greater than 0!")
        return

    sender = get_player(sender_id, message.from_user.first_name)
    receiver = get_player(receiver_id, message.reply_to_message.from_user.first_name)

    if sender_id != OWNER_ID and sender[2] < amount_to_pay:
        bot.reply_to(message, f"❌ Transaction Failed! You don't have enough balance. Your balance: `{sender[2]}` Z-Coins.")
        return

    if sender_id != OWNER_ID:
        update_player(sender_id, coins=sender[2] - amount_to_pay)
        
    update_player(receiver_id, coins=receiver[2] + amount_to_pay)

    sender_bal = "♾️ Unlimited" if sender_id == OWNER_ID else f"{sender[2] - amount_to_pay}"
    receiver_bal = f"{receiver[2] + amount_to_pay}"

    success_msg = f"💸 *TRANSACTION SUCCESSFUL!*\n\n"
    success_msg += f"👤 *From:* {sender[1]}\n"
    success_msg += f"👤 *To:* {receiver[1]}\n"
    success_msg += f"💰 *Amount Sent:* `{amount_to_pay}` Z-Coins\n\n"
    success_msg += f"📊 *New Balances:*\n"
    success_msg += f"• {sender[1]}: `{sender_bal}` Z-Coins\n"
    success_msg += f"• {receiver[1]}: `{receiver_bal}` Z-Coins"

    bot.reply_to(message, success_msg, parse_mode="Markdown")

# --- 📊 STATS & RANK COMMANDS ---

@bot.message_handler(commands=['bal'])
def view_profile(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    
    if message.from_user.id == OWNER_ID:
        status = "🧘 God Mode"
        coins_display = "♾️ Unlimited"
    else:
        status = "❤️ ALIVE" if p[5] == 1 else "💀 DEAD"
        coins_display = f"{p[2]}"
        
    armor = "🛡️ YES" if p[6] == 1 else "❌ NO"
    
    msg = f"👤 *PROFILE: {p[1]}*\n\n"
    msg += f"ℹ️ Status: {status}\n"
    msg += f"💰 Z-Coins: {coins_display}\n"
    msg += f"⭐ EXP: {p[3]}\n"
    msg += f"⚔️ Kills: {p[4]}\n"
    msg += f"🛡️ Armor: {armor}"
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['topkills'])
def top_kills(message):
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT username, kills FROM players ORDER BY kills DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    
    msg = "💀 *DEADLIEST PLAYERS*\n\n"
    for i, row in enumerate(rows, 1):
        msg += f"{i}. {row[0]} - {row[1]} kills\n"
    bot.reply_to(message, msg, parse_mode="Markdown")

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
    bot.reply_to(message, msg, parse_mode="Markdown")

# --- ⚔️ COMBAT COMMANDS ---

@bot.message_handler(commands=['kill'])
def kill_user(message):
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Who do you want to kill? Reply to their message with this command.")
        return
        
    if message.reply_to_message.from_user.is_bot:
        bot.reply_to(message, "🤖 *Error:* Bots cannot participate in combat! You can only attack real users.")
        return

    attacker_id = message.from_user.id
    attacker = get_player(attacker_id, message.from_user.first_name)
    victim = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)
    
    if attacker_id == victim[0]:
        bot.reply_to(message, "❌ You cannot kill yourself!")
        return

    # 🧘‍♂️👑 OWNER ULTIMATE ANTI-KILL REVERSE MECHANISM (GOD WRATH)
    if victim[0] == OWNER_ID:
        # The foolish attacker who tried to kill the God/Owner dies instantly!
        update_player(attacker_id, is_alive=0, has_armor=0)
        bot.reply_to(message, f"⚡ *GOD'S WRATH:* *{attacker[1]}* foolishly tried to attack the Creator / God (*{victim[1]}*)! The attack backfired instantly, striking *{attacker[1]}* dead! 💀🪦")
        return

    # 👑 OWNER ATTACKING OTHERS: ULTIMATE ONE-HIT KILL BYPASS
    if attacker_id == OWNER_ID:
        update_player(victim[0], is_alive=0, has_armor=0)
        update_player(attacker_id, kills=attacker[4]+1, exp=attacker[3]+100)
        bot.reply_to(message, f"⚡ *GOD STRIKE:* Owner *{attacker[1]}* instantly annihilated *{victim[1]}*, bypassing all shields and armor! 💀 (+100 EXP)")
        return

    # Normal player combat logic
    if attacker[5] == 0:
        bot.reply_to(message, "❌ You are dead! Use `/revive` first.")
        return
    if victim[5] == 0:
        bot.reply_to(message, "❌ They are already dead!")
        return

    if victim[6] == 1:
        update_player(victim[0], has_armor=0)
        bot.reply_to(message, f"🛡️ *{victim[1]}* survived because of Armor! But their armor broke.")
        return
        
    if random.choice([True, False]):
        update_player(victim[0], is_alive=0)
        update_player(attacker_id, kills=attacker[4]+1, exp=attacker[3]+50)
        bot.reply_to(message, f"⚔️ *{attacker[1]}* hunted down and killed *{victim[1]}*! (+50 EXP)")
    else:
        bot.reply_to(message, f"🏃 *{victim[1]}* managed to escape the attack!")

@bot.message_handler(commands=['rob'])
def rob_user(message):
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Who do you want to rob? Reply to their message.")
        return
        
    if message.reply_to_message.from_user.is_bot:
        bot.reply_to(message, "🤖 *Error:* You cannot rob a bot!")
        return

    robber_id = message.from_user.id
    victim_id = message.reply_to_message.from_user.id
    
    # Anti-Rob Protection for Owner
    if victim_id == OWNER_ID:
        bot.reply_to(message, "⚡ *Error:* You cannot rob the Creator / God! Keep your hands off.")
        return
        
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "❌ Format: /rob [amount]")
        return
        
    amount = int(args[1])
    robber = get_player(robber_id, message.from_user.first_name)
    victim = get_player(victim_id, message.reply_to_message.from_user.first_name)
    
    if robber[5] == 0:
        bot.reply_to(message, "❌ Dead players cannot rob anyone!")
        return
        
    if victim[2] < amount:
        bot.reply_to(message, "❌ They don't have that many Z-Coins!")
        return
        
    if random.choice([True, False]):
        update_player(robber[0], coins=robber[2]+amount)
        update_player(victim[0], coins=victim[2]-amount)
        bot.reply_to(message, f"💰 *{robber[1]}* successfully robbed {amount} Z-Coins from *{victim[1]}*!")
    else:
        penalty = int(amount * 0.5)
        update_player(robber[0], coins=max(0, robber[2]-penalty))
        bot.reply_to(message, f"👮 *{robber[1]}* got caught while robbing! Fined {penalty} Z-Coins.")

@bot.message_handler(commands=['revive'])
def revive_user(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p[5] == 1:
        bot.reply_to(message, "❤️ You are already alive!")
        return
        
    if message.from_user.id != OWNER_ID:
        if p[2] < 200:
            bot.reply_to(message, "❌ You need 200 Z-Coins to revive. You don't have enough balance!")
            return
        update_player(message.from_user.id, is_alive=1, coins=p[2]-200)
    else:
        update_player(message.from_user.id, is_alive=1)
        
    bot.reply_to(message, "✨ You resurrected back to life! Let's fight!")

@bot.message_handler(commands=['protect'])
def buy_armor(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    if p[6] == 1:
        bot.reply_to(message, "🛡️ You already have armor protection active!")
        return
        
    if message.from_user.id != OWNER_ID:
        if p[2] < 300:
            bot.reply_to(message, "❌ You need 300 Z-Coins to hire armor!")
            return
        update_player(message.from_user.id, has_armor=1, coins=p[2]-300)
    else:
        update_player(message.from_user.id, has_armor=1)
        
    bot.reply_to(message, "🛡️ You bought armor! This will protect you from your next death attack.")

# --- 🎮 WORD GAME SYSTEM ---

@bot.message_handler(commands=['words'])
def host_word_game(message):
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Only the Bot Owner can start a New Word Game!")
        return

    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit():
        bot.reply_to(message, "❌ Format: /words [bet_amt] [secret_word]")
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
    
    game_msg = f"🎮 *GLOBAL WORD GAME STARTED!*\n\nHost: {message.from_user.first_name}\nBet Amount: {amt} Z-Coins\nScrambled Letters: `{scrambled}`\n\nType `/bet {amt}` to join the game here and guess the word!"
    
    for group in groups:
        g_id = group[0]
        try:
            cursor.execute("REPLACE INTO word_games VALUES (?, ?, ?, ?, ?, ?)", 
                           (g_id, message.from_user.id, amt, secret_word, scrambled, str(message.from_user.id)))
            bot.send_message(g_id, game_msg, parse_mode="Markdown")
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
        bot.reply_to(message, "❌ No active word game running in this group.")
        return
        
    player = get_player(message.from_user.id, message.from_user.first_name)
    bet_amt = game[2]
    
    if message.from_user.id != OWNER_ID and player[2] < bet_amt:
        bot.reply_to(message, "❌ You don't have enough Z-Coins to join this bet!")
        return
        
    joined_players = game[5].split(',')
    if str(message.from_user.id) in joined_players:
        bot.reply_to(message, "❌ You have already joined this game! Try to solve the word.")
        return
        
    joined_players.append(str(message.from_user.id))
    new_players_str = ",".join(joined_players)
    
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE word_games SET players_joined = ? WHERE chat_id = ?", (new_players_str, message.chat.id))
    conn.commit()
    conn.close()
    
    update_player(message.from_user.id, coins=player[2]-bet_amt)
    bot.reply_to(message, f"✅ You joined the game for {bet_amt} Z-Coins! Guess the word and type it in chat.")

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
        
        bot.send_message(message.chat.id, f"🎉 *GROUP WINNER!*\n\n*{message.from_user.first_name}* guessed the correct word (`{game[3]}`).\n💰 Reward: Received {total_pool} Z-Coins and +30 EXP!")

# --- 🚀 RUNNING THE BOT LOOP KEEP-ALIVE ---
if __name__ == '__main__':
    init_db()
    print("Davi Game Bot Started Successfully with PayCoin & Ultimate Owner Protection...")
    bot.infinity_polling()
