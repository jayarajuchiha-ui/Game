import telebot
import sqlite3
import random
import time

# Put your bot token here
API_TOKEN = 'YOUR_BOT_TOKEN_HERE'
bot = telebot.TeleBot('8793834902:AAEUH8NxVY2J00vepALQw5WSivD4Pmi6IB8')

# 👑 ENTER YOUR TELEGRAM USER ID HERE
OWNER_ID = 8425183548   # <- Replace with your actual Telegram User ID

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
            has_armor INTEGER DEFAULT 0
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
        cursor.execute("INSERT INTO players (user_id, username) VALUES (?, ?)", (user_id, username))
        conn.commit()
        cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
        player = cursor.fetchone()
    conn.close()
    return player

def update_player(user_id, **kwargs):
    # Owner has unlimited coins, so do not decrease coins in database for Owner
    if user_id == OWNER_ID and 'coins' in kwargs:
        del kwargs['coins']
        
    if kwargs:
        conn = sqlite3.connect('game_bot.db')
        cursor = conn.cursor()
        for key, value in kwargs.items():
            cursor.execute(f"UPDATE players SET {key} = ? WHERE user_id = ?", (value, user_id))
        conn.commit()
        conn.close()

# --- 📊 STATS & RANK COMMANDS ---

@bot.message_handler(commands=['bal'])
def view_profile(message):
    p = get_player(message.from_user.id, message.from_user.first_name)
    status = "❤️ ALIVE" if p[5] == 1 else "💀 DEAD"
    armor = "🛡️ YES" if p[6] == 1 else "❌ NO"
    coins_display = "♾️ Unlimited" if message.from_user.id == OWNER_ID else f"{p[2]}"
    
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
        
    attacker = get_player(message.from_user.id, message.from_user.first_name)
    victim = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)
    
    # RULE 1: Owner cannot be killed (God Mode)
    if victim[0] == OWNER_ID:
        bot.reply_to(message, "⚡ *Error:* You cannot kill the Creator / God! 🧘‍♂️")
        return
        
    if attacker[5] == 0:
        bot.reply_to(message, "❌ You are dead! Use `/revive` first.")
        return
    if victim[5] == 0:
        bot.reply_to(message, "❌ They are already dead!")
        return
    if attacker[0] == victim[0]:
        bot.reply_to(message, "❌ You cannot kill yourself!")
        return

    if victim[6] == 1:
        update_player(victim[0], has_armor=0)
        bot.reply_to(message, f"🛡️ *{victim[1]}* survived because of Armor! But their armor broke.")
        return
        
    if random.choice([True, False]):
        update_player(victim[0], is_alive=0)
        update_player(attacker[0], kills=attacker[4]+1, exp=attacker[3]+50)
        bot.reply_to(message, f"⚔️ *{attacker[1]}* hunted down and killed *{victim[1]}*! (+50 EXP)")
    else:
        bot.reply_to(message, f"🏃 *{victim[1]}* managed to escape the attack!")

@bot.message_handler(commands=['rob'])
def rob_user(message):
    if not message.reply_to_message:
        bot.reply_to(message, "❌ Who do you want to rob? Reply to their message.")
        return
        
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        bot.reply_to(message, "❌ Format: /rob [amount] (Must be a reply)")
        return
        
    amount = int(args[1])
    robber = get_player(message.from_user.id, message.from_user.first_name)
    victim = get_player(message.reply_to_message.from_user.id, message.reply_to_message.from_user.first_name)
    
    if robber[5] == 0:
        bot.reply_to(message, "❌ Dead players cannot rob anyone!")
        return
        
    if victim[0] != OWNER_ID and victim[2] < amount:
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
    # RULE 2: Only the Bot Owner can start a New Word Game
    if message.from_user.id != OWNER_ID:
        bot.reply_to(message, "❌ Only the Bot Owner can start a New Word Game!")
        return

    args = message.text.split()
    if len(args) < 3 or not args[1].isdigit():
        bot.reply_to(message, "❌ Format: /words [bet_amt] [secret_word]")
        return
        
    amt = int(args[1])
    secret_word = args[2].lower()
    
    # Scramble the word
    letters_list = list(secret_word)
    random.shuffle(letters_list)
    scrambled = "".join(letters_list)
    
    conn = sqlite3.connect('game_bot.db')
    cursor = conn.cursor()
    
    # Add current chat ID to active groups list for broadcasting
    cursor.execute("INSERT OR IGNORE INTO active_groups VALUES (?)", (message.chat.id,))
    
    # Fetch all active group IDs
    cursor.execute("SELECT chat_id FROM active_groups")
    groups = cursor.fetchall()
    
    # RULE 3: Global Broadcast - Register game and send alert to all groups
    game_msg = f"🎮 *GLOBAL WORD GAME STARTED!*\n\nHost: {message.from_user.first_name}\nBet Amount: {amt} Z-Coins\nScrambled Letters: `{scrambled}`\n\nType `/bet {amt}` to join the game here and guess the word!"
    
    for group in groups:
        g_id = group[0]
        try:
            cursor.execute("REPLACE INTO word_games VALUES (?, ?, ?, ?, ?, ?)", 
                           (g_id, message.from_user.id, amt, secret_word, scrambled, str(message.from_user.id)))
            bot.send_message(g_id, game_msg, parse_mode="Markdown")
        except Exception:
            continue # Skip groups where the bot might have been removed
            
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
        
        # RULE 4: One winner per group - Delete game entry only for this specific chat
        conn = sqlite3.connect('game_bot.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM word_games WHERE chat_id = ?", (message.chat.id,))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, f"🎉 *GROUP WINNER!*\n\n*{message.from_user.first_name}* guessed the correct word (`{game[3]}`).\n💰 Reward: Received {total_pool} Z-Coins and +30 EXP!")

if __name__ == '__main__':
    init_db()
    print("Game Bot Started Successfully...")
    bot.infinity_polling()
