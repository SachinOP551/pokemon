"""
Optimized Drop Module
Enhanced performance with better memory management and reduced resource usage
"""

import random
import asyncio
from datetime import datetime, timedelta
from collections import defaultdict, deque
from functools import lru_cache
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from .logging_utils import send_drop_log
from .decorators import admin_only, is_owner, is_sudo, is_og, check_banned
import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
else:
    from .database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
from .tdgoal import track_collect_drop
import time
import string
from pyrogram.enums import ChatType
import weakref
import gc

DROPTIME_LOG_CHANNEL = -1002558794123
LOG_CHANNEL_ID = -1002836765689

# Optimized data structures with memory limits
active_drops = weakref.WeakValueDictionary()  # Use weak references to prevent memory leaks
user_msgs = defaultdict(lambda: deque(maxlen=5))  # Reduced from 10
banned_users = weakref.WeakValueDictionary()  # Use weak references
SPAM_LIMIT = 5    # Reduced from 6
SPAM_WINDOW = 1.5  # Reduced from 2 seconds
message_counts = defaultdict(int)  # Simplified counter
last_drop_time = weakref.WeakValueDictionary()
drop_settings_cache = weakref.WeakValueDictionary()
last_settings_update = weakref.WeakValueDictionary()
SETTINGS_CACHE_TIME = 30  # Reduced from 60 seconds
drop_locks = weakref.WeakValueDictionary()
drop_expiry_times = weakref.WeakValueDictionary()

# Preloaded character queue with size limit
preloaded_next_character = defaultdict(lambda: deque(maxlen=5))  # Limit to 5 characters
collect_locks = defaultdict(asyncio.Lock)
chat_locks = weakref.WeakValueDictionary()
collection_locks = defaultdict(asyncio.Lock)
collecting_characters = defaultdict(lambda: set())  # Use weak references
user_collecting = defaultdict(lambda: set())

# Performance tracking
performance_stats = {
    'drops_sent': 0,
    'collections_processed': 0,
    'cache_hits': 0,
    'cache_misses': 0,
    'last_cleanup': time.time()
}

# Epic drop captions (reduced set for memory efficiency)
DROP_CAPTIONS = [
    "👁️‍🗨️ Tʜᴇ Wᴀᴛᴄʜᴇʀs ʜᴀᴠᴇ ʀᴇᴠᴇᴀʟᴇᴅ ᴀ sɪʟʜᴏᴜᴇᴛᴛᴇ…\nA ғᴏʀᴄᴇ ᴏꜰ ᴘᴏᴡᴇʀ ᴀᴡᴀɪᴛs ɪᴛs ᴍᴀsᴛᴇʀ.\n✴️ /collect name ᴀɴᴅ sᴇᴀʟ ʏᴏᴜʀ ꜰᴀᴛᴇ.",
    "🕯️ Tʜᴇ sᴄʀᴏʟʟs ʜᴀᴠᴇ sᴘᴏᴋᴇɴ...\nA ᴡᴀʀʀɪᴏʀ ᴀʀɪsᴇs ꜰʀᴏᴍ ᴛʜᴇ ᴇᴛᴇʀɴᴀʟ ɢʀɪᴍᴏɪʀᴇ.\n🗝️ /collect name ᴛᴏ ꜰᴜʟꜰɪʟʟ ᴛʜᴇ ᴘʀᴏᴘʜᴇᴄʏ.",
    "🌌 A sᴛᴀʀ ʜᴀs ꜰᴀʟʟᴇɴ ꜰʀᴏᴍ ᴛʜᴇ ᴄᴏsᴍɪᴄ ʀɪᴠᴇʀs…\nA ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀᴡᴀɪᴛs ʏᴏᴜʀ sᴜᴍᴍᴏɴ.\n🪐 Wɪʟʟ ʏᴏᴜ ᴀɴsᴡᴇʀ ᴛʜᴇ ᴄᴀʟʟ? /collect name",
    "⚔️ Fᴀᴛᴇ ᴄᴀʟʟs, ᴀɴᴅ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ᴀɴsᴡᴇʀs.\nTʜᴇ ʙᴀᴛᴛʟᴇ ʙᴇᴛᴡᴇᴇɴ ʟɪɢʜᴛ ᴀɴᴅ sʜᴀᴅᴏᴡ ᴄᴏɴᴛɪɴᴜᴇs…\n✨ /collect name ᴛᴏ ᴄʟᴀɪᴍ ʏᴏᴜʀ ᴀʟʟɪᴇs.",
    "🔮 Tʜᴇ ᴛɪᴍᴇʟɪɴᴇ ᴛᴇᴀʀs ᴀᴘᴀʀᴛ…\nA sᴏᴜʟ sᴛᴇᴘs ꜰᴏʀᴛʜ ᴛᴏ ᴍᴇᴇᴛ ɪᴛs ᴅᴇsᴛɪɴʏ.\n🕰️ Wɪʟʟ ʏᴏᴜ /collect name ᴛʜᴇ ᴄʜᴀᴍᴘɪᴏɴ?"
]

# Jackpot feature with memory optimization
active_jackpots = weakref.WeakValueDictionary()
jackpot_counter = defaultdict(int)
jackpot_next_interval = defaultdict(int)

async def drop_jackpot(client, chat_id):
    """Optimized jackpot drop with memory management"""
    try:
        code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))  # Reduced from 10
        amount = random.randint(1000, 2000)
        msg = (
            f"🎰 ᴊᴀᴄᴋᴘᴏᴛ ᴄᴏᴅᴇ ɪs: <code>{code}</code>\n\n"
            f" ᴛᴏ ᴄʟᴀɪᴍ ᴛʜᴇ ᴊᴀᴄᴋᴘᴏᴛ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ: <code>/jackpot {code}</code>\n"
        )
        image_url = "https://ibb.co/TxnK47Sq"
        sent = await client.send_photo(chat_id, image_url, caption=msg)
        
        active_jackpots[chat_id] = {
            'code': code,
            'amount': amount,
            'claimed_by': None,
            'claimed_by_name': None,
            'message_id': sent.id if hasattr(sent, 'id') else sent.message_id,
            'created_at': time.time()
        }
        
        # Clean up old jackpots
        current_time = time.time()
        expired_jackpots = [cid for cid, data in active_jackpots.items() 
                           if current_time - data.get('created_at', 0) > 3600]  # 1 hour expiry
        for cid in expired_jackpots:
            del active_jackpots[cid]
            
    except Exception as e:
        print(f"Error in drop_jackpot: {e}")

async def jackpot_command(client: Client, message: Message):
    """Optimized jackpot claim command"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        db = get_database()
        args = message.text.split()
        
        if len(args) < 2:
            await message.reply_text("❌ Usage: /jackpot code")
            return
            
        code = args[1].strip()
        jackpot = active_jackpots.get(chat_id)
        
        if not jackpot or jackpot['code'] != code:
            await message.reply_text("❌ No active jackpot with this code in this group!")
            return
            
        if jackpot['claimed_by']:
            name = jackpot.get('claimed_by_name', 'someone else')
            await message.reply_text(f"❌ This jackpot was already claimed by {name}!", disable_web_page_preview=True)
            return
            
        # Mark as claimed
        jackpot['claimed_by'] = user_id
        jackpot['claimed_by_name'] = message.from_user.first_name
        
        # Add shards to user
        try:
            shards_amount = jackpot['amount']
            await db.users.update_one(
                {'user_id': user_id},
                {'$inc': {'shards': shards_amount}}
            )
            await db.log_user_transaction(user_id, "jackpot_claim", {
                "amount": shards_amount,
                "chat_id": chat_id,
                "code": code,
                "date": datetime.now().strftime('%Y-%m-%d %H:%M')
            })
        except Exception:
            pass
            
        await message.reply_text(
            f"🎉 Congratulations! You claimed the jackpot and won <b>{shards_amount}</b> 🎐 Shards!\n\n"
            f"Claimed by: <a href=\"tg://user?id={user_id}\">{message.from_user.first_name}</a>", 
            disable_web_page_preview=True
        )
        
    except Exception as e:
        print(f"Error in jackpot_command: {e}")

@lru_cache(maxsize=50)  # Reduced cache size
def get_drop_time(chat_id):
    """Get cached drop time for a chat"""
    return message_counts.get(chat_id, 0)

async def get_cached_drop_settings(db, chat_id):
    """Get cached drop settings with memory optimization"""
    current_time = datetime.now()
    
    if (chat_id not in drop_settings_cache or 
        chat_id not in last_settings_update or 
        (current_time - last_settings_update[chat_id]).total_seconds() > SETTINGS_CACHE_TIME):
        
        settings = await db.get_drop_settings()
        drop_settings_cache[chat_id] = settings
        last_settings_update[chat_id] = current_time
        
        # Clean up old cache entries
        expired_chats = [cid for cid, last_update in last_settings_update.items()
                        if (current_time - last_update).total_seconds() > SETTINGS_CACHE_TIME * 2]
        for cid in expired_chats:
            if cid in drop_settings_cache:
                del drop_settings_cache[cid]
            if cid in last_settings_update:
                del last_settings_update[cid]
    
    return drop_settings_cache[chat_id]

async def cleanup_expired_collecting_characters():
    """Clean up expired collecting characters with memory optimization"""
    current_time = time.time()
    expired_chars = []
    
    for chat_id, collecting_set in collecting_characters.items():
        expired_in_chat = []
        for char_id in collecting_set:
            if current_time - drop_expiry_times.get(char_id, 0) > 300:  # 5 minutes
                expired_in_chat.append(char_id)
        
        for char_id in expired_in_chat:
            collecting_set.discard(char_id)
            if char_id in drop_expiry_times:
                del drop_expiry_times[char_id]
    
    # Clean up empty sets
    empty_chats = [chat_id for chat_id, collecting_set in collecting_characters.items() 
                   if not collecting_set]
    for chat_id in empty_chats:
        del collecting_characters[chat_id]

async def check_and_remove_expired_bans():
    """Check and remove expired bans with memory optimization"""
    current_time = time.time()
    expired_bans = []
    
    for user_id, ban_data in banned_users.items():
        if current_time > ban_data.get('end_time', 0):
            expired_bans.append(user_id)
    
    for user_id in expired_bans:
        del banned_users[user_id]

async def is_user_banned(user_id):
    """Check if user is banned with memory optimization"""
    if user_id in banned_users:
        ban_data = banned_users[user_id]
        if time.time() > ban_data.get('end_time', 0):
            del banned_users[user_id]
            return False
        return True
    return False

async def handle_message(client: Client, message: Message):
    """Optimized message handler with reduced resource usage"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        current_time = time.time()
        
        # Skip if user is banned
        if await is_user_banned(user_id):
            return
        
        # Simplified spam detection
        user_msgs[user_id].append(current_time)
        recent_msgs = [msg_time for msg_time in user_msgs[user_id] 
                      if current_time - msg_time <= SPAM_WINDOW]
        
        if len(recent_msgs) > SPAM_LIMIT:
            await handle_spam_ban_pyrogram(message, client, user_id, current_time)
            return
        
        # Update message count
        message_counts[chat_id] = message_counts.get(chat_id, 0) + 1
        
        # Check if it's time for a drop
        db = get_database()
        settings = await get_cached_drop_settings(db, chat_id)
        
        if settings and settings.get('auto_drop', True):
            drop_time = settings.get('drop_time', 100)
            if message_counts[chat_id] >= drop_time:
                await process_drop(chat_id, client, current_time)
                message_counts[chat_id] = 0
        
        # Periodic cleanup
        if current_time - performance_stats['last_cleanup'] > 300:  # Every 5 minutes
            await cleanup_expired_collecting_characters()
            await check_and_remove_expired_bans()
            performance_stats['last_cleanup'] = current_time
            
            # Force garbage collection
            collected = gc.collect()
            if collected > 0:
                print(f"Garbage collection freed {collected} objects")
                
    except Exception as e:
        print(f"Error in handle_message: {e}")

async def handle_spam_and_bans_pyrogram(message, client, user_id, current_time):
    """Optimized spam handling"""
    try:
        # Clear user's message history
        user_msgs[user_id].clear()
        
        # Add temporary ban
        ban_duration = 300  # 5 minutes
        banned_users[user_id] = {
            'end_time': current_time + ban_duration,
            'reason': 'spam'
        }
        
        # Send warning message
        await message.reply_text("⚠️ You are temporarily banned for spam. Please wait 5 minutes.")
        
    except Exception as e:
        print(f"Error in handle_spam_and_bans_pyrogram: {e}")

async def handle_spam_ban_pyrogram(message, client, user_id, current_time):
    """Optimized spam ban handling"""
    await handle_spam_and_bans_pyrogram(message, client, user_id, current_time)

async def process_drop(chat_id, client, current_time):
    """Optimized drop processing"""
    try:
        if chat_id in drop_locks:
            return  # Drop already in progress
        
        drop_locks[chat_id] = True
        
        db = get_database()
        settings = await get_cached_drop_settings(db, chat_id)
        
        if not settings:
            del drop_locks[chat_id]
            return
        
        # Get random character
        character = await db.get_random_character(settings.get('locked_rarities', []))
        
        if character:
            await send_drop_message(client, chat_id, character, current_time)
            performance_stats['drops_sent'] += 1
        
        del drop_locks[chat_id]
        
    except Exception as e:
        print(f"Error in process_drop: {e}")
        if chat_id in drop_locks:
            del drop_locks[chat_id]

async def send_drop_message(client, chat_id, character, current_time):
    """Optimized drop message sending"""
    try:
        caption = random.choice(DROP_CAPTIONS)
        caption = caption.replace("name", character.get('name', 'Unknown'))
        
        # Add collection button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Collect", callback_data=f"collect_{character['character_id']}")]
        ])
        
        # Send message
        if character.get('is_video', False):
            sent = await client.send_video(
                chat_id,
                character.get('file_id'),
                caption=caption,
                reply_markup=keyboard
            )
        else:
            sent = await client.send_photo(
                chat_id,
                character.get('file_id'),
                caption=caption,
                reply_markup=keyboard
            )
        
        # Track drop
        active_drops[chat_id] = {
            'character_id': character['character_id'],
            'message_id': sent.id,
            'expires_at': current_time + 300  # 5 minutes
        }
        
        drop_expiry_times[character['character_id']] = current_time + 300
        
        # Log drop
        await send_drop_log(client, character, chat_id)
        
    except Exception as e:
        print(f"Error in send_drop_message: {e}")

async def collect_command(client: Client, message: Message):
    """Optimized collect command"""
    try:
        chat_id = message.chat.id
        user_id = message.from_user.id
        current_time = time.time()
        
        # Check if user is banned
        if await is_user_banned(user_id):
            await message.reply_text("❌ You are banned from collecting characters.")
            return
        
        # Parse character name
        args = message.text.split(maxsplit=1)
        if len(args) < 2:
            await message.reply_text("❌ Usage: /collect character_name")
            return
        
        character_name = args[1].strip().lower()
        
        # Check if there's an active drop
        active_drop = active_drops.get(chat_id)
        if not active_drop:
            await message.reply_text("❌ No active drop in this chat!")
            return
        
        # Check if character is already being collected
        if active_drop['character_id'] in collecting_characters.get(chat_id, set()):
            await message.reply_text("❌ This character is already being collected!")
            return
        
        # Check if user is already collecting
        if user_id in user_collecting.get(chat_id, set()):
            await message.reply_text("❌ You are already collecting a character!")
            return
        
        # Get character details
        db = get_database()
        character = await db.get_character(active_drop['character_id'])
        
        if not character:
            await message.reply_text("❌ Character not found!")
            return
        
        # Check name match
        actual_name = character.get('name', '').lower()
        if character_name != actual_name:
            await message.reply_text(f"❌ Wrong character name! Try again.")
            return
        
        # Mark as collecting
        if chat_id not in collecting_characters:
            collecting_characters[chat_id] = set()
        collecting_characters[chat_id].add(active_drop['character_id'])
        
        if chat_id not in user_collecting:
            user_collecting[chat_id] = set()
        user_collecting[chat_id].add(user_id)
        
        # Add character to user's collection
        success = await db.add_character_to_user(user_id, active_drop['character_id'])
        
        if success:
            # Remove from active drops
            del active_drops[chat_id]
            
            # Remove from collecting sets
            collecting_characters[chat_id].discard(active_drop['character_id'])
            user_collecting[chat_id].discard(user_id)
            
            # Send success message
            rarity_display = get_rarity_display(character.get('rarity', 'Unknown'))
            await message.reply_text(
                f"🎉 Congratulations! You collected {character.get('name', 'Unknown')} ({rarity_display})!"
            )
            
            performance_stats['collections_processed'] += 1
            
            # Track for goals
            await track_collect_drop(client, message, character)
            
        else:
            # Remove from collecting sets on failure
            collecting_characters[chat_id].discard(active_drop['character_id'])
            user_collecting[chat_id].discard(user_id)
            await message.reply_text("❌ Failed to collect character. Please try again.")
            
    except Exception as e:
        print(f"Error in collect_command: {e}")
        # Clean up on error
        if chat_id in collecting_characters and active_drop['character_id'] in collecting_characters[chat_id]:
            collecting_characters[chat_id].discard(active_drop['character_id'])
        if chat_id in user_collecting and user_id in user_collecting[chat_id]:
            user_collecting[chat_id].discard(user_id)

# Additional optimized functions...
async def droptime_command(client: Client, message: Message):
    """Optimized droptime command"""
    try:
        chat_id = message.chat.id
        db = get_database()
        settings = await get_cached_drop_settings(db, chat_id)
        
        current_count = message_counts.get(chat_id, 0)
        drop_time = settings.get('drop_time', 100) if settings else 100
        
        remaining = max(0, drop_time - current_count)
        
        await message.reply_text(
            f"📊 **Drop Progress**\n\n"
            f"Messages sent: {current_count}/{drop_time}\n"
            f"Remaining: {remaining} messages\n\n"
            f"Next drop in: {remaining} messages"
        )
        
    except Exception as e:
        print(f"Error in droptime_command: {e}")

async def drop_command(client: Client, message: Message):
    """Optimized manual drop command"""
    try:
        chat_id = message.chat.id
        current_time = time.time()
        
        if chat_id in drop_locks:
            await message.reply_text("⏳ A drop is already in progress!")
            return
        
        await process_drop(chat_id, client, current_time)
        await message.reply_text("🎯 Manual drop triggered!")
        
    except Exception as e:
        print(f"Error in drop_command: {e}")

async def free_command(client: Client, message: Message):
    """Optimized free command - Owner only"""
    try:
        user_id = message.from_user.id
        
        # Check if user is owner
        from config import OWNER_ID
        if user_id != OWNER_ID:
            # Silently ignore non-owner users
            return
        
        # Only owner can proceed
        chat_id = message.chat.id
        current_time = time.time()
        
        # Check if user is banned (shouldn't happen for owner, but safety check)
        if await is_user_banned(user_id):
            await message.reply_text("❌ You are banned from using free commands.")
            return
        
        # Get random character
        db = get_database()
        character = await db.get_random_character()
        
        if character:
            # Add to user's collection
            success = await db.add_character_to_user(user_id, character['character_id'])
            
            if success:
                rarity_display = get_rarity_display(character.get('rarity', 'Unknown'))
                await message.reply_text(
                    f"🎉 You got {character.get('name', 'Unknown')} ({rarity_display}) for free!"
                )
                
                # Track for goals
                await track_collect_drop(client, message, character)
            else:
                await message.reply_text("❌ Failed to add character to collection.")
        else:
            await message.reply_text("❌ No characters available.")
            
    except Exception as e:
        print(f"Error in free_command: {e}")

# Performance monitoring functions
def get_performance_stats():
    """Get drop performance statistics"""
    return {
        'drops_sent': performance_stats['drops_sent'],
        'collections_processed': performance_stats['collections_processed'],
        'cache_hits': performance_stats['cache_hits'],
        'cache_misses': performance_stats['cache_misses'],
        'active_drops': len(active_drops),
        'banned_users': len(banned_users),
        'collecting_characters': sum(len(chars) for chars in collecting_characters.values())
    }

async def cleanup_all():
    """Clean up all drop-related data"""
    try:
        active_drops.clear()
        banned_users.clear()
        drop_settings_cache.clear()
        last_settings_update.clear()
        drop_locks.clear()
        drop_expiry_times.clear()
        collecting_characters.clear()
        user_collecting.clear()
        message_counts.clear()
        user_msgs.clear()
        
        # Force garbage collection
        gc.collect()
        
        print("All drop data cleaned up")
        
    except Exception as e:
        print(f"Error in cleanup_all: {e}") 