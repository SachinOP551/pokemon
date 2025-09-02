import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta
from functools import lru_cache
import os
import random
import string
import time
import re

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from modules.postgres_database import (
    RARITIES,
    RARITY_EMOJIS,
    get_database,
    get_rarity_display,
    get_rarity_emoji,
)
from modules.postgres_database import (
    RARITIES,
    RARITY_EMOJIS,
    get_database,
    get_rarity_display,
    get_rarity_emoji,
)

from .decorators import admin_only, check_banned, is_og, is_owner, is_sudo
from .logging_utils import send_drop_log
from .tdgoal import track_collect_drop


DEFAULT_DROPTIME = 35


# Add in-memory storage for droptime settings and message counts
message_timestamps = defaultdict(dict)
ignore_duration = 10 * 60  # 10 minutes
group_locks = {}
group_last_messages = defaultdict(lambda: deque(maxlen=8))
drop_debounce_time = 1.0

# FIXED: Separate locks for each group to prevent race conditions
group_message_locks = defaultdict(asyncio.Lock)

DROPTIME_LOG_CHANNEL = -1002763974845
LOG_CHANNEL_ID = -1002836765689

# FIXED: Per-group message counting storage
group_message_counts = defaultdict(lambda: {"current_count": 0, "msg_count": DEFAULT_DROPTIME})

# FIXED: Use database for persistent storage instead of JSON files
# This avoids all datetime serialization issues

RARITIES = {
    "Common": 1,
    "Medium": 2,
    "Rare": 3,
    "Legendary": 4,
    "Exclusive": 5,
    "Elite": 6,
    "Limited Edition": 7,
    "Ultimate": 8,
    "Supreme": 9,
    "Mythic": 10,
    "Zenith": 11,
    "Ethereal": 12,
    "Premium": 13
}

# FIXED: Load active drops from database on startup
async def load_active_drops():
    """Load active drops from database"""
    try:
        db = get_database()
        # Get all active drops from database
        active_drops_data = await db.get_active_drops()
        
        # Group by chat_id
        drops_by_chat = {}
        for drop in active_drops_data:
            chat_id = drop.get('chat_id')
            if chat_id not in drops_by_chat:
                drops_by_chat[chat_id] = []
            drops_by_chat[chat_id].append(drop)
        
        print(f"✅ Loaded {len(active_drops_data)} active drops from database")
        return drops_by_chat
        
    except Exception as e:
        print(f"Error loading active drops from database: {e}")
        import traceback
        traceback.print_exc()
        return {}

async def save_active_drops():
    """Save active drops to database"""
    try:
        db = get_database()
        
        # Clear existing active drops
        await db.clear_active_drops()
        
        # Save all current active drops
        total_saved = 0
        for chat_id, drops in active_drops.items():
            for drop in drops:
                # Prepare drop data for database
                drop_data = {
                    'chat_id': chat_id,
                    'character_id': drop.get('character_id'),
                    'name': drop.get('name'),
                    'rarity': drop.get('rarity'),
                    'drop_message_id': drop.get('drop_message_id'),
                    'dropped_at': drop.get('dropped_at'),
                    'anime': drop.get('anime', ''),
                    'is_video': drop.get('is_video', False),
                    'file_id': drop.get('file_id', ''),
                    'img_url': drop.get('img_url', '')
                }
                
                await db.add_active_drop(drop_data)
                total_saved += 1
        
        print(f"✅ Saved {total_saved} active drops to database")
        return True
        
    except Exception as e:
        print(f"Error saving active drops to database: {e}")
        import traceback
        traceback.print_exc()
        return False

# Initialize active drops as empty - will be loaded when bot starts
active_drops = {}

# FIXED: Validate drops on startup to ensure they're still valid
async def validate_drops_on_startup():
    """Validate active drops on bot startup and remove invalid ones"""
    try:
        global active_drops
        invalid_drops = []
        
        for chat_id, drops in list(active_drops.items()):
            valid_drops = []
            for drop in drops:
                # Check if drop has required fields
                if (drop.get('character_id') and 
                    drop.get('name') and 
                    drop.get('rarity') and 
                    drop.get('drop_message_id')):
                    valid_drops.append(drop)
                else:
                    invalid_drops.append(f"Chat {chat_id}: {drop.get('name', 'Unknown')}")
            
            if valid_drops:
                active_drops[chat_id] = valid_drops
            else:
                del active_drops[chat_id]
        
        if invalid_drops:
            print(f"Removed {len(invalid_drops)} invalid drops on startup")
            # Save to database
            await save_active_drops()
        
        print(f"Loaded {sum(len(drops) for drops in active_drops.values())} valid active drops")
        
    except Exception as e:
        print(f"Error validating drops on startup: {e}")

# Note: validate_drops_on_startup is now async and will be called during bot startup

# Drop management variables
# Preloaded next character queue per chat with size limit
preloaded_next_character = defaultdict(lambda: deque(maxlen=5))  # Added size limit
collect_locks = defaultdict(asyncio.Lock)
# Add collection locks to prevent race conditions during character collection
collection_locks = defaultdict(asyncio.Lock)
# Track which characters are being collected to prevent double collection
collecting_characters = defaultdict(set)
# Track which users are collecting which characters to prevent spam
user_collecting = defaultdict(set)

# Epic drop captions
DROP_CAPTIONS = [
    "⚡ A ʙᴜʀsᴛ ᴏꜰ ᴇɴᴇʀɢʏ sʜᴀᴋᴇs ᴛʜᴇ ʟᴀɴᴅ…\nA ᴛʀᴀɪɴᴇʀ's ᴘᴏᴋéᴍᴏɴ ᴀᴡᴀᴋᴇɴs ꜰᴏʀ ʙᴀᴛᴛʟᴇ.\n🔥 /collect name ᴛᴏ ᴄʟᴀɪᴍ ᴛʜᴇɪʀ ꜰɪɢʜᴛɪɴɢ sᴘɪʀɪᴛ.",
    "🌙 A ᴅᴀʀᴋ ᴀᴜʀᴀ ᴇᴍᴇʀɢᴇs ꜰʀᴏᴍ ᴛʜᴇ sʜᴀᴅᴏᴡs…\nA ɢʜᴏsᴛʟʏ ᴘᴏᴋéᴍᴏɴ ʜᴜɴᴛs ᴛʜᴇ ɴɪɢʜᴛ.\n👁️ /collect name ᴛᴏ ʙɪɴᴅ ᴛʜɪs ꜱʜᴀᴅᴏᴡᴇᴅ ꜰᴏʀᴄᴇ.",
    "📜 Aɴ ᴀɴᴄɪᴇɴᴛ ᴘᴏᴋéᴅᴇx ʀᴇᴠᴇᴀʟs ᴀ ꜰᴏʀɢᴏᴛᴛᴇɴ ɴᴀᴍᴇ…\nA ʟᴇɢᴇɴᴅᴀʀʏ ᴘᴏᴋéᴍᴏɴ ʀᴇᴀᴡᴀᴋᴇɴs.\n🗝️ /collect name ᴛᴏ ᴄʟᴀɪᴍ ᴛʜᴇɪʀ ʟᴇɢᴇɴᴅ.",
    "🔥 Fʟᴀᴍᴇs ʙᴜʀɴ, ᴡᴀᴛᴇʀ ᴄʀᴀsʜᴇs, ᴀɴᴅ ᴡɪɴᴅs ʜᴏᴡʟ…\nAɴ ᴇʟᴇᴍᴇɴᴛᴀʟ ᴘᴏᴋéᴍᴏɴ ᴇᴍᴇʀɢᴇs ꜰᴏʀ ʙᴀᴛᴛʟᴇ.\n🌊 /collect name ᴛᴏ ᴍᴀsᴛᴇʀ ᴛʜᴇɪʀ ᴛʏᴘᴇ.",
    "🩸 A ʀɪᴠᴀʟʀʏ ꜰᴏʀɢᴇᴅ ᴏɴ ᴛʜᴇ ꜰɪᴇʟᴅ…\nA ᴛʀᴀɪɴᴇʀ's ᴘᴀʀᴛɴᴇʀ ᴄʀɪᴇs ᴏᴜᴛ.\n⚔️ /collect name ᴛᴏ ꜰᴏʀɢᴇ ᴀ ʙᴏɴᴅ.",
    "💫 A ᴘᴏʀᴛᴀʟ ᴛᴏ ᴛʜᴇ ᴅɪsᴛᴏʀᴛɪᴏɴ ᴡᴏʀʟᴅ ᴏᴘᴇɴs…\nA ʟᴇɢᴇɴᴅᴀʀʏ ꜰʀᴏᴍ ʙᴇʏᴏɴᴅ ᴀᴘᴘᴇᴀʀs.\n🚪 /collect name ᴛᴏ sᴇᴀʟ ᴛʜᴇɪʀ ᴘᴏᴡᴇʀ.",
    "⚡ Tʜᴇ ᴘᴏᴡᴇʀ ᴏꜰ ᴛʜᴏᴜsᴀɴᴅs ᴏꜰ ʙᴀᴛᴛʟᴇs ᴇʀᴜᴘᴛs…\nA ᴍᴇɢᴀ ᴇᴠᴏʟᴜᴛɪᴏɴ ᴀᴡᴀᴋᴇɴs.\n🌌 /collect name ᴛᴏ ᴄʟᴀɪᴍ ᴛʜᴇɪʀ ꜱᴛʀᴇɴɢᴛʜ.",
    "🦊 A ᴍʏsᴛɪᴄᴀʟ ꜰᴏx ᴘᴏᴋéᴍᴏɴ ᴘʀᴏᴡʟs, ꜰɪʀᴇ ʙᴜʀɴs, ᴀɴᴅ ᴀᴜʀᴀ ʀᴀɢᴇs…\nTʜᴇɪʀ ꜰᴜʀʏ ᴄᴀɴɴᴏᴛ ʙᴇ ᴄᴏɴᴛᴀɪɴᴇᴅ.\n🔒 /collect name ᴛᴏ ꜰᴀᴄᴇ ᴛʜᴇ ʙᴇᴀsᴛ.",
    "👹 A ᴄᴜʀsᴇᴅ ᴘᴏᴋéᴍᴏɴ ʟᴜʀᴋs ɪɴ ᴛʜᴇ ᴅᴀʀᴋ…\nIᴛs ᴄᴀʟʟ ᴇᴄʜᴏᴇs ᴛʜʀᴏᴜɢʜ ᴛʜᴇ ɴɪɢʜᴛ.\n⚫ /collect name ɪꜰ ʏᴏᴜ ᴅᴀʀᴇ.",
    "🎴 A ᴘᴏᴋé ᴄᴀʀᴅ ɢʟᴏᴡs ᴡɪᴛʜ ᴍʏsᴛɪᴄ ᴇɴᴇʀɢʏ…\nA ᴛʀᴀᴅɪɴɢ ʙᴀᴛᴛʟᴇʀ ᴊᴏɪɴs ᴛʜᴇ ꜰɪᴇʟᴅ.\n♠️ /collect name ᴛᴏ sᴜᴍᴍᴏɴ ᴛʜᴇɪʀ ᴘᴏᴡᴇʀ."
]



# --- JACKPOT FEATURE ---
active_jackpots = {}  # chat_id: {code, amount, claimed_by, message_id}
jackpot_counter = {}  # chat_id: current count (int)
jackpot_next_interval = {}  # chat_id: next interval (int)

BOT_USERNAME = "CollectXPokemonBot"

async def drop_jackpot(client, chat_id):
    code = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
    amount = random.randint(1000, 2000)
    msg = (
        f"🎰 ᴊᴀᴄᴋᴘᴏᴛ ᴄᴏᴅᴇ ɪs: <code>{code}</code>\n\n"
        f" ᴛᴏ ᴄʟᴀɪᴍ ᴛʜᴇ ᴊᴀᴄᴋᴘᴏᴛ ᴜsᴇ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ: <code>/jackpot {code}</code>\n"
    )
    # Use direct image link for photo
    image_url = "https://ibb.co/TxnK47Sq"
    sent = await client.send_photo(chat_id, image_url, caption=msg)
    active_jackpots[chat_id] = {
        'code': code,
        'amount': amount,
        'claimed_by': None,
        'claimed_by_name': None,
        'message_id': sent.id if hasattr(sent, 'id') else sent.message_id
    }

# --- Jackpot claim command ---
async def jackpot_command(client: Client, message: Message):
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
    # Add shards to user (update shards only)
    try:
        shards_amount = jackpot['amount']
        # For PostgreSQL, use the proper update method
        async with db.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET shards = shards + $1 WHERE user_id = $2",
                shards_amount, user_id
            )
        # Log jackpot claim action
        await db.log_user_transaction(user_id, "jackpot_claim", {
            "amount": shards_amount,
            "chat_id": chat_id,
            "code": code,
            "date": datetime.now().strftime('%Y-%m-%d %H:%M')
        })
    except Exception as e:
        print(f"Error updating shards: {e}")
        pass
    await message.reply_text(f"🎉 Congratulations! You claimed the jackpot and won <b>{shards_amount}</b> 🎐 Shards!\n\nClaimed by: <a href=\"tg://user?id={user_id}\">{message.from_user.first_name}</a>", disable_web_page_preview=True)
    # Do NOT edit the original jackpot message anymore


# Helper to check if a user is currently banned (auto-expires ban)
async def is_user_banned(user_id):
    try:
        from .ban_manager import check_user_ban_status
        db = get_database()
        is_banned, _ = await check_user_ban_status(user_id, db)
        return is_banned
    except Exception as e:
        # If there's an error checking ban status, assume not banned to prevent blocking drops
        print(f"Error checking ban status for user {user_id}: {e}")
        return False

# Import database based on configuration


# FIXED: Simplified and reliable message counting functions (in-memory only)
async def get_message_count(group_id: int):
    """Get current message count for a group (in-memory only)"""
    try:
        counts = group_message_counts[group_id]
        counts.setdefault("current_count", 0)
        counts.setdefault("msg_count", DEFAULT_DROPTIME)
        # Debug log removed
        return counts.copy()
    except Exception as e:
        print(f"❌ Error getting message count for group {group_id}: {e}")
        group_message_counts[group_id] = {"current_count": 0, "msg_count": DEFAULT_DROPTIME}
        return group_message_counts[group_id].copy()

async def update_message_count(group_id: int, msg_count: int, current_count: int):
    """Update message count for a group (in-memory only)"""
    # Debug log removed
    
    try:
        group_message_counts[group_id]["msg_count"] = msg_count
        group_message_counts[group_id]["current_count"] = current_count
        # Debug log removed
        
    except Exception as e:
        print(f"❌ Error updating message count for group {group_id}: {e}")

# Pyrogram message counting handler
async def handle_message(client: Client, message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    group_id = message.chat.id
    current_time = time.time()

    # Skip private messages
    if message.chat.type == 'private':
        return

    # Completely ignore messages from banned users
    is_banned = await is_user_banned(user_id)
    if is_banned:
        return
    
    # NEW: Check if this is a reply to a drop message for collection
    if message.reply_to_message:
        await handle_reply_collection(client, message)
        return
    
    # FIXED: Ensure periodic save task is running (only if not already started)
    try:
        ensure_periodic_save_task()
    except Exception as e:
        print(f"Warning: Could not ensure periodic save task: {e}")

    # Start queue processor if not running
    global queue_processor_running
    if not queue_processor_running:
        # Debug log removed
        asyncio.create_task(process_message_queue())

    # Check if we're under high load (queue size > 100)
    if message_queue.qsize() > 100:
        # Use queue for high-volume processing
        try:
            await message_queue.put((client, message, current_time))
        except asyncio.QueueFull:
            # Queue is full, process directly but skip spam detection
            await handle_single_message(client, message, current_time)
        return

    # --- JACKPOT COUNTER LOGIC ---
    if group_id not in jackpot_counter:
        jackpot_counter[group_id] = 0
    if group_id not in jackpot_next_interval:
        jackpot_next_interval[group_id] = random.randint(450, 550)
    jackpot_counter[group_id] += 1
    if jackpot_counter[group_id] >= jackpot_next_interval[group_id]:
        asyncio.create_task(drop_jackpot(client, group_id))
        jackpot_counter[group_id] = 0
        jackpot_next_interval[group_id] = random.randint(450, 550)

    # Initialize and update message tracking for spam detection
    if user_id not in message_timestamps.get(group_id, {}):
        message_timestamps[group_id][user_id] = []
    
    # Add current message timestamp and clean old ones
    message_timestamps[group_id][user_id].append(current_time)
    message_timestamps[group_id][user_id] = [
        ts for ts in message_timestamps[group_id][user_id]
        if current_time - ts <= 2  # 2-second window
    ]

    # Update group's message history for consecutive messages check
    group_last_messages[group_id].append(user_id)

    # Check for spam: 8 messages in 2 seconds
    spam_detected = False
    if len(message_timestamps[group_id][user_id]) >= 7:
        # Ban user for 10 minutes
        try:
            from .ban_manager import ban_user
            db = get_database()
            await ban_user(user_id, db, permanent=False, duration_minutes=10, reason="Spam detected")
            await message.reply(f"**⚠️ {message.from_user.first_name}, ʏᴏᴜ ᴀʀᴇ spamming too much..!!\nYou have been banned for 10 minutes.**")
            spam_detected = True
        except Exception as e:
            print(f"Error banning spam user: {e}")

    # FIXED: Use per-group lock to prevent race conditions between different groups
    async with group_message_locks[group_id]:
        # Debug log removed
        
        # Get current message count for the group
        count_doc = await get_message_count(group_id)
        current_count = count_doc["current_count"] + 1
        msg_count = count_doc["msg_count"]
        
        # Debug logging for message counting
        # Debug log removed

        # If the current count reaches the drop threshold
        if current_count >= msg_count:
            # Debug log removed
            # Reset current count
            current_count = 0
            
            # Start drop process
            await process_drop(group_id, client, datetime.now())
        
        # Update the message count
        await update_message_count(group_id, msg_count, current_count)
        # Debug log removed

async def process_drop(chat_id, client, current_time):
    """Process character drop, using preloaded character queue if available"""
    # Debug log removed
    try:
        db = get_database()
        # Get drop settings directly from database
        try:
            drop_settings = await db.get_drop_settings()
        except:
            drop_settings = {}
        locked_rarities = drop_settings.get('locked_rarities', []) if drop_settings else []
        
        # Use preloaded character from queue if available
        queue = preloaded_next_character[chat_id]
        if queue:
            character = queue.pop(0)
        else:
            drop_manager = DropManager(db)
            character = await drop_manager.get_random_character(locked_rarities)
        
        if character:
            # Debug log removed
            # Check daily limit
            rarity = character['rarity']
            try:
                daily_drops = await db.get_daily_drops(rarity)
                daily_limit = drop_settings.get('daily_limits', {}).get(rarity)
                if daily_limit is not None and daily_drops >= daily_limit:
                    # Debug log removed
                    return
            except:
                pass  # Skip daily limit check if not available
            
            # Send drop message
            # Debug log removed
            await send_drop_message(client, chat_id, character, current_time)
        else:
            # Debug log removed
            return
    except Exception as e:
        print(f"Error in process_drop for chat {chat_id}: {e}")
        return

async def send_drop_message(client, chat_id, character, current_time):
    """Send drop message"""
    try:
        caption = random.choice(DROP_CAPTIONS)
        
        # Create inline keyboard with CHECK DETAILS IN DM button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 CHECK DETAILS IN DM", url=f"https://t.me/{BOT_USERNAME}?start=details_{character['character_id']}")]
        ])
        
        if character.get('is_video', False):
            # For video characters, prefer img_url (Cloudinary URL) over file_id
            video_source = character.get('img_url') or character.get('file_id')
            drop_message = await client.send_video(
                chat_id=chat_id,
                video=video_source,
                caption=caption,
                reply_markup=keyboard
            )
        else:
            photo = character.get('img_url') or character.get('file_id')
            drop_message = await client.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                reply_markup=keyboard
            )
        
        # FIXED: Don't expire previous drops - keep them active
        # Store drop info
        character['drop_message_id'] = drop_message.id if hasattr(drop_message, 'id') else drop_message.message_id
        
        # Ensure dropped_at is a datetime object
        if isinstance(current_time, datetime):
            character['dropped_at'] = current_time
        else:
            # Convert to datetime if it's not already
            character['dropped_at'] = datetime.now()

        # NEW LOGIC: If a new character is dropped, expire any previous uncollected character
        if chat_id not in active_drops:
            active_drops[chat_id] = []
        else:
            # Remove any existing uncollected drops for this chat
            if active_drops[chat_id]:
                # Get the database connection to remove from database
                db = get_database()
                for old_drop in active_drops[chat_id]:
                    try:
                        # Remove from database
                        await db.remove_active_drop(chat_id, old_drop.get('character_id'))
                        print(f"🔄 Expired previous drop: {old_drop.get('name', 'Unknown')} in chat {chat_id}")
                    except Exception as e:
                        print(f"Error removing old drop from database: {e}")
                
                # Clear the list for this chat
                active_drops[chat_id] = []
        
        # Add the new drop
        active_drops[chat_id].append(character)
        
        # Save to database
        await save_active_drops()
        
    except Exception as e:
        print(f"Error in send_drop_message for chat {chat_id}: {e}")
        import traceback
        traceback.print_exc()
        pass

# Pyrogram collect command handler
@check_banned
async def collect_command(client: Client, message: Message):
    user_id = message.from_user.id
    current_time = datetime.now()
    
    # Ignore all commands from banned users
    if await is_user_banned(user_id):
        return
    
    chat_id = message.chat.id
    async with collection_locks[chat_id]:
        db = get_database()
        # --- FIX: If no active drops, show last_collected_drop message ---
        if chat_id not in active_drops or not active_drops[chat_id]:
            last_collected = None
            if hasattr(collect_command, "last_collected_drop") and collect_command.last_collected_drop.get(chat_id):
                last_collected = collect_command.last_collected_drop[chat_id]
            if last_collected:
                await message.reply_text(
                    f"<b>ℹ Last Character Was Already Collected By <a href=\"tg://user?id={last_collected['collected_by_id']}\">{last_collected['collected_by_name']}</a>!</b>",
                    disable_web_page_preview=True
                )
            return
        
        # If no arguments provided, check if owner and allow direct collection
        if not message.command or len(message.command) == 1:
            # Check if user is owner or authorized ID - allow direct collection without name
            authorized_ids = [6055447708, 6919874630]  # Original owner + additional authorized ID
            if user_id in authorized_ids:
                character = active_drops[chat_id][-1]
                message_id = character.get('drop_message_id')
                
                # Check if character is already being collected
                if message_id in collecting_characters[chat_id]:
                    await message.reply_text(f"ℹ Last Character Was Already Collected By <a href=\"tg://user?id={last_collected['collected_by_id']}\">{last_collected['collected_by_name']}</a>!")
                    return
                
                # Check if user is already collecting this character
                if message_id in user_collecting[user_id]:
                    return
                
                # Mark character as being collected
                collecting_characters[chat_id].add(message_id)
                user_collecting[user_id].add(message_id)
                
                try:
                    # Owner can collect directly without name
                    await db.add_character_to_user(
                        user_id=user_id,
                        character_id=character['character_id'],
                        collected_at=current_time,
                        source='collected'
                    )
                    # DEBUG: Print collection_history after collection
                    # user = await db.get_user(user_id)
                    # Ensure group membership is tracked
                    if message.chat.type != "private":
                        await db.add_user_to_group(user_id, message.chat.id)
                    # Track successful collection for tdgoal
                    try:
                        await track_collect_drop(user_id)
                    except Exception as e:
                        print(f"tdgoal track_collect_drop error: {e}")
                    rarity = character['rarity']
                    rarity_emoji = get_rarity_emoji(rarity)
                    escaped_name = character['name']
                    escaped_rarity = rarity
                    escaped_emoji = rarity_emoji
                    user_name = message.from_user.first_name
                    character_id = character['character_id']
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"👑 {user_name}'s Collection", switch_inline_query_current_chat=f"collection:{user_id}")]
                    ])
                    bonus_text = ""
                    bonus = None
                    if random.random() < 0.4:
                        bonus = random.randint(30, 50)
                        user = await db.get_user(user_id)
                        shards = user.get('shards', 0)
                        await db.update_user(user_id, {'shards': shards + bonus})
                        bonus_text = f"⚡️ <b>Bonus!</b> You received <b>{bonus}</b> extra 🎐 shards for collecting!\n"
                    msg = (
                        f"<b>✅ Look You Collected A</b> <code>{escaped_rarity}</code> <b>Pokémon</b>\n\n"
                        f"<b>👤 Name : {escaped_name}</b>\n"
                        f"<b>{rarity_emoji} Rᴀʀɪᴛʏ : {escaped_rarity}</b>\n"
                        f"<b>⛩ Region : {character.get('anime', '-') }</b>\n"
                        f"{bonus_text}"
                        f"\n<b>➥ Look At Your Collection Using</b> /mycollection"
                    )
                    collection_message = await message.reply(
                        msg,
                        reply_markup=keyboard
                    )
                    # Mark this character as collected by this user for this chat
                    if not hasattr(collect_command, "last_collected_drop"):
                        collect_command.last_collected_drop = {}
                    collect_command.last_collected_drop[chat_id] = {
                        'collected_by_id': user_id,
                        'collected_by_name': user_name
                    }
                    # Remove the collected character from active drops and expiry tracking
                    if character in active_drops[chat_id]:
                        # Remove from database first
                        try:
                            await db.remove_active_drop(chat_id, character.get('character_id'))
                        except Exception as e:
                            print(f"Error removing collected drop from database: {e}")
                        
                        # Remove from memory
                        active_drops[chat_id].remove(character)
                    
                    if not active_drops[chat_id]:
                        del active_drops[chat_id]
                    
                    # FIXED: Save updated state to persistent storage
                    await save_active_drops()
                finally:
                    # Always remove from collecting sets
                    collecting_characters[chat_id].discard(message_id)
                    user_collecting[user_id].discard(message_id)
                return
            
            # For non-owners, show the character with a button
            character = active_drops[chat_id][-1]
            # Create button with correct message link
            if str(chat_id).startswith("-100"):
                channel_id = str(chat_id)[4:]
            else:
                channel_id = str(chat_id)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Pokémon 🔼", url=f"https://t.me/c/{channel_id}/{character['drop_message_id']}")]
            ])
            await message.reply(
                "<b>Pʟᴇᴀsᴇ ɢᴜᴇss ᴛʜᴇ ᴘᴏᴋᴇᴍᴏɴ ɴᴀᴍᴇ!</b>",
                reply_markup=keyboard
            )
            return
        
        character_name = ' '.join(message.command[1:])
        
        def is_name_match(guess: str, actual: str) -> bool:
            if any(char in guess for char in ['&', '@', '#', '$', '%', '^', '*', '+', '=', '|', '\\', '/', '<', '>', '?']):
                return False
            guess = guess.lower().strip()
            actual = actual.lower().strip()
            if guess == actual:
                return True
            actual_words = actual.split()
            if len(actual_words) > 1:
                return guess in actual_words
            return False
        
        for character in active_drops[chat_id]:
            message_id = character.get('drop_message_id')
            if is_name_match(character_name, character['name']):
                # Check if character is already being collected
                if message_id in collecting_characters[chat_id]:
                    await message.reply_text("⚠️ This Pokémon is already being collected by someone else!")
                    return
                
                # Check if user is already collecting this character
                if message_id in user_collecting[user_id]:
                    await message.reply_text("⚠️ You are already trying to collect this character!")
                    return
                
                # Mark character as being collected
                collecting_characters[chat_id].add(message_id)
                user_collecting[user_id].add(message_id)
                
                try:
                    await db.add_character_to_user(
                        user_id=user_id,
                        character_id=character['character_id'],
                        collected_at=current_time,
                        source='collected'
                    )
                    # Ensure group membership is tracked
                    if message.chat.type != "private":
                        await db.add_user_to_group(user_id, message.chat.id)
                    # Track successful collection for tdgoal
                    try:
                        await track_collect_drop(user_id)
                    except Exception as e:
                        print(f"tdgoal track_collect_drop error: {e}")
                    rarity = character['rarity']
                    rarity_emoji = get_rarity_emoji(rarity)
                    escaped_name = character['name']
                    escaped_rarity = rarity
                    escaped_emoji = rarity_emoji
                    user_name = message.from_user.first_name
                    character_id = character['character_id']
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"{user_name}'s Collection", switch_inline_query_current_chat=f"collection:{user_id}")]
                    ])
                    bonus_text = ""
                    bonus = None
                    if random.random() < 0.4:
                        bonus = random.randint(30, 50)
                        user = await db.get_user(user_id)
                        shards = user.get('shards', 0)
                        await db.update_user(user_id, {'shards': shards + bonus})
                        bonus_text = f"⚡️ <b>Bonus!</b> You received <b>{bonus}</b> extra 🎐 shards for collecting!\n"
                    msg = (
                        f"<b>✅ Look You Collected A</b> <code>{escaped_rarity}</code> <b>Pokémon</b>\n\n"
                        f"<b>👤 Name : {escaped_name}</b>\n"
                        f"<b>{rarity_emoji} Rarity : {escaped_rarity}</b>\n"
                        f"<b>⛩ Region : {character.get('anime', '-') }</b>\n"
                        f"{bonus_text}"
                        f"\n<b>➥ Look At Your Collection Using</b> /mycollection"
                    )
                    collection_message = await message.reply(
                        msg,
                        reply_markup=keyboard
                    )
                    # Mark this character as collected by this user for this chat
                    if not hasattr(collect_command, "last_collected_drop"):
                        collect_command.last_collected_drop = {}
                    collect_command.last_collected_drop[chat_id] = {
                        'collected_by_id': user_id,
                        'collected_by_name': user_name
                    }
                    # Remove the collected character from active drops and expiry tracking
                    if character in active_drops[chat_id]:
                        # Remove from database first
                        try:
                            await db.remove_active_drop(chat_id, character.get('character_id'))
                        except Exception as e:
                            print(f"Error removing collected drop from database: {e}")
                        
                        # Remove from memory
                        active_drops[chat_id].remove(character)
                    
                    if not active_drops[chat_id]:
                        del active_drops[chat_id]
                    
                    # FIXED: Save updated state to persistent storage
                    await save_active_drops()
                finally:
                    # Always remove from collecting sets
                    collecting_characters[chat_id].discard(message_id)
                    user_collecting[user_id].discard(message_id)
                return
        # If no match, show incorrect guess message with inline button
        character = active_drops[chat_id][-1]  # Show button for latest drop
        if str(chat_id).startswith("-100"):
            channel_id = str(chat_id)[4:]
        else:
            channel_id = str(chat_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Pokémon 🔼", url=f"https://t.me/c/{channel_id}/{character['drop_message_id']}")]
        ])
        await message.reply(
            f"<b>❌ Incorrect Guess</b> -: <code>{character_name}</code>\n\n<b>Please try again...</b>",
            reply_markup=keyboard
        )

async def droptime_command(client: Client, message: Message):
    """Handle droptime command (in-memory only for counting)"""
    group_id = message.chat.id

    # Get database only for role checks (not for droptime storage)
    try:
        db = get_database()
    except Exception:
        db = None

    # Get current droptime from in-memory store
    count_doc = await get_message_count(group_id)
    current_droptime = count_doc["msg_count"] if count_doc else DEFAULT_DROPTIME

    # If no arguments, show current droptime
    if not message.command or len(message.command) == 1:
        await message.reply_text(
            f"<b>The Current Droptime Is Set To {current_droptime} Messages!</b>\n\n"
        )
        return

    user_id = message.from_user.id
    is_admin = is_owner(user_id) or (db and await is_sudo(db, user_id)) or (db and await is_og(db, user_id))
    if not is_admin:
        await message.reply_text(
            "<b>Error!\nOnly admins can change the drop time!</b>"
        )
        return
    try:
        new_time = int(message.command[1])
        if new_time < 1:
            await message.reply_text(
                "<b>Error!\nDrop time must be a positive number!</b>"
            )
            return

        # Update in-memory settings and reset message count
        await update_message_count(group_id, new_time, 0)

        await message.reply_text(
            f"<b>✅ Drop Time Set To {new_time} Messages!</b>\n\n"
        )
        # Inline log message
        log_message = (
            f"<b>⚠ ᴅʀᴏᴘᴛɪᴍᴇ sᴇᴛ ᴛᴏ {new_time} ʙʏ {message.from_user.first_name} ɪɴ ɢʀᴏᴜᴘ {message.chat.id}</b>"
        )
        try:
            await client.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=log_message
            )
        except Exception as e:
            print(f"Failed to send to main log channel: {e}")

        try:
            await client.send_message(
                chat_id=DROPTIME_LOG_CHANNEL,
                text=log_message
            )
        except Exception as e:
            print(f"Failed to send droptime log (channel may be invalid): {e}")
            # Don't crash the bot, just log the error
    except ValueError:
        await message.reply_text(
            "<b>Error!\nPlease provide a valid number!</b>"
        )

# Add new command function
async def drop_command(client: Client, message: Message):
    """Handle manual drop command"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    db = get_database()
    
    # Check if user is owner only
    if not is_owner(user_id):
        return

    if not message.command or len(message.command) < 2:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ!</b>"
        )
        return

    try:
        character_id = int(message.command[1])
        # ...existing code...
        # Get character by ID
        character = await db.get_character(character_id)
        if not character:
            # Debug: List available character IDs
            try:
                all_chars = await db.get_all_characters() if hasattr(db, 'get_all_characters') else []
                available_ids = [c.get('character_id') for c in all_chars]
                await message.reply_text(
                    f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!</b>\nAvailable IDs: {available_ids[:20]}{' ...' if len(available_ids)>20 else ''}"
                )
            except Exception as e:
                await message.reply_text(
                    f"<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!</b>\n(Debug error: {e})"
                )
            return
        # ...existing code...
        # Check if character's rarity is locked
        drop_settings = await db.get_drop_settings()
        locked_rarities = drop_settings.get('locked_rarities', []) if drop_settings else []
        if character['rarity'] in locked_rarities:
            await message.reply_text(
                f"<b>❌ ᴄᴀɴɴᴏᴛ ᴅʀᴏᴘ {character['rarity']} ʀᴀʀɪᴛʏ - ɪᴛ's ʟᴏᴄᴋᴇᴅ!</b>"
            )
            return
        # Check daily limit for this rarity
        rarity = character['rarity']
        daily_drops = await db.get_daily_drops(rarity)
        daily_limit = drop_settings.get('daily_limits', {}).get(rarity)
        if daily_limit is not None and daily_drops >= daily_limit:
            await message.reply_text(
                f"<b>❌ ᴅᴀɪʟʏ ʟɪᴍɪᴛ ғᴏʀ {rarity} ʀᴀʀɪᴛʏ ʜᴀs ʙᴇᴇɴ ʀᴇᴀᴄʜᴇᴅ!</b>"
            )
            return
        # Increment daily drops counter
        await db.increment_daily_drops(rarity)
        # Use the same drop logic as auto-drop
        # ...existing code...
        await send_drop_message(client, chat_id, character, datetime.now())
        chat = await client.get_chat(chat_id)
        await send_drop_log(client, message.from_user, character, chat)
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ!</b>"
        )
    except Exception as e:
        print(f"Error in manual drop command: {e}")
        await message.reply_text(
            f"<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ! (Debug: {e})</b>"
        )


async def free_command(client: Client, message: Message):
    """Unban a user from spam restrictions (Owner/OG/Sudo only)"""
    user = message.from_user
    db = get_database()
    
    # Check if user has permission
    if not (is_owner(user.id) or await is_og(db, user.id) or await is_sudo(db, user.id)):
        return
    
    # Check if replying to a message
    if not message.reply_to_message:
        return
    
    target_user = message.reply_to_message.from_user
    
    # Check if user is banned using new ban system
    from .ban_manager import check_user_ban_status
    is_banned, _ = await check_user_ban_status(target_user.id, db)
    
    if not is_banned:
        await message.reply_text(
            "<b>❌ ᴛʜɪs ᴜsᴇʀ ɪs ɴᴏᴛ ᴡᴀʀɴᴇᴅ!</b>"
        )
        return
    
    try:
        # Unban user using the new ban system
        from .ban_manager import unban_user
        await unban_user(target_user.id, db)
        # Clear spam tracker for this user (using new system)
        if target_user.id in message_timestamps.get(message.chat.id, {}):
            message_timestamps[message.chat.id].pop(target_user.id, None)
        # Send success message
        admin_name = user.first_name
        target_name = target_user.first_name
        await message.reply_text(
            f"<b>✅ {target_name} Has Been Unwarned By {admin_name}!</b>"
        )
    except Exception as e:
        print(f"Error in free_command: {e}")
        await message.reply_text(
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴜɴʙᴀɴɴɪɴɢ ᴛʜᴇ ᴜsᴇʀ!</b>"
        )

# Periodic ban check removed to prevent issues

async def setup_drop_weights_and_limits(client: Client):
    """Set up drop rarity weights and daily limits"""
    db = get_database()
    settings = await db.get_drop_settings()
    # Set rarity weights - higher numbers mean higher chance of dropping
    # Each tier is roughly 2x rarer than the previous
    rarity_weights = {
        "Common": 1000,     # Base weight (100%)
        "Medium": 500,      # 50% of Common
        "Rare": 250,        # 25% of Common
        "Legendary": 180,   # 18% of Common
        "Exclusive": 60,    # 6% of Common
        "Elite": 55,        # 5.5% of Common
        "Limited Edition": 45,  # 4.5% of Common
        "Ultimate": 15,     # 1.5% of Common
        "Supreme": 8,       # 0.8% of Common
        "Mythic": 30,       # 3% of Common
        "Zenith": 5,        # 0.5% of Common
        "Ethereal": 3,      # 0.3% of Common
        "Premium": 2        # 0.2% of Common
    }
    # Set daily limits - None means no limit, 0 means not dropping
    daily_limits = {
        "Common": None,      # No limit
        "Medium": None,     # No limit
        "Rare": None,       # No limit
        "Legendary": None,   # No limit
        "Exclusive": None,   # No limit
        "Elite": None,       # No limit
        "Limited Edition": None, # No limit
        "Ultimate": 2,      # 2 per day
        "Supreme": 1,       # 1 per day
        "Mythic": 3,        # 3 per day
        "Zenith": 1,        # 1 per day
        "Ethereal": 1,      # 1 per day
        "Premium": 1        # 1 per day
    }
    # Update settings
    settings['rarity_weights'] = rarity_weights
    settings['daily_limits'] = daily_limits
    # Reset daily drops counter
    settings['daily_drops'] = {}
    settings['last_reset_date'] = datetime.now().strftime('%Y-%m-%d')
    await db.update_drop_settings(settings)
    return settings

class DropManager:
    def __init__(self, db=None):
        # Always use the actual Postgres database instance with a .pool attribute
        from modules.postgres_database import get_database
        real_db = db
        # If db is not the real instance, get the real one
        if not hasattr(db, 'pool'):
            try:
                real_db = get_database()
            except Exception:
                real_db = db
        self.db = real_db
        self.characters = getattr(real_db, 'characters', None)
        self.rarity_emojis = {
            "Common": "⚪️",
            "Medium": "🟢",
            "Rare": "🟠",
            "Legendary": "🟡",
            "Exclusive": "🫧",
            "Elite": "💎",
            "Limited Edition": "🔮",
            "Ultimate": "🔱",
            "Supreme": "👑",
            "Mythic": "🔴",
            "Zenith": "💫",
            "Ethereal": "❄️",
            "Premium": "🧿"
        }
        # Cache for drop settings
        self._drop_settings = None
        self._last_settings_update = None
        self._settings_cache_time = 60  # Cache settings for 60 seconds
        # Cache for characters
        self._characters_cache = None
        self._last_characters_update = None
        self._characters_cache_time = 300  # Cache characters for 5 minutes

    async def _get_drop_settings(self):
        """Get drop settings with caching"""
        current_time = datetime.now()
        if (self._drop_settings is None or 
            self._last_settings_update is None or 
            (current_time - self._last_settings_update).total_seconds() > self._settings_cache_time):
            self._drop_settings = await self.db.get_drop_settings()
            self._last_settings_update = current_time
        return self._drop_settings

    async def _get_characters(self, locked_rarities):
        """Get characters with caching (Postgres version)"""
        current_time = datetime.now()
        if (self._characters_cache is None or 
            self._last_characters_update is None or 
            (current_time - self._last_characters_update).total_seconds() > self._characters_cache_time):
            
            # Fetch all characters not in locked rarities
            try:
                async with self.db.pool.acquire() as conn:
                    
                    if locked_rarities:
                        rows = await conn.fetch(
                            "SELECT character_id, name, rarity, file_id, img_url, is_video, anime, type FROM characters WHERE rarity != ALL($1)",
                            locked_rarities
                        )
                    else:
                        rows = await conn.fetch(
                            "SELECT character_id, name, rarity, file_id, img_url, is_video, anime, type FROM characters"
                        )
                    
                # Group by rarity
                rarity_groups = {}
                for row in rows:
                    rarity = row['rarity']
                    if rarity not in rarity_groups:
                        rarity_groups[rarity] = []
                    rarity_groups[rarity].append(dict(row))
                
                self._characters_cache = [
                    {'_id': rarity, 'characters': chars}
                    for rarity, chars in rarity_groups.items()
                ]
                
            except Exception as e:
                print(f"Error fetching characters: {e}")
                import traceback
                traceback.print_exc()
                self._characters_cache = []
            
            self._last_characters_update = current_time
        
        return self._characters_cache

    async def get_random_character(self, locked_rarities=None):
        """Get random character from database, respecting locked rarities and weights"""
        if locked_rarities is None:
            locked_rarities = []
        
        try:
            # Get drop settings with caching
            settings = await self._get_drop_settings()
            
            if not settings:
                return None
                
            rarity_weights = settings.get('rarity_weights', {})
            daily_limits = settings.get('daily_limits', {})
            daily_drops = settings.get('daily_drops', {})
            
            # Get characters with caching
            rarity_groups = await self._get_characters(locked_rarities)
            
            if not rarity_groups:
                return None
            
            # Create weighted list of rarities, respecting daily limits
            weighted_rarities = []
            for group in rarity_groups:
                rarity = group['_id']
                base_weight = rarity_weights.get(rarity, 0)
                
                # Skip rarities with weight 0 or reached daily limit
                if base_weight <= 0:
                    continue
                
                daily_limit = daily_limits.get(rarity)
                current_drops = daily_drops.get(rarity, 0)
                
                if daily_limit is not None and current_drops >= daily_limit:
                    continue
                
                # Add rarity to weighted list based on its weight
                weighted_rarities.extend([rarity] * base_weight)
            
            if not weighted_rarities:
                return None
            
            # Select random rarity based on weights
            selected_rarity = random.choice(weighted_rarities)
            
            # Get characters of selected rarity
            characters = next((g['characters'] for g in rarity_groups if g['_id'] == selected_rarity), [])
            
            if not characters:
                return None
            
            # Return random character from selected rarity
            selected_character = random.choice(characters)
            
            # Update daily drops counter asynchronously
            try:
                asyncio.create_task(self.db.increment_daily_drops(selected_rarity))
            except Exception as e:
                print(f"Error updating daily drops: {e}")
            
            return selected_character
            
        except Exception as e:
            print(f"Error in get_random_character: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def drop_command(self, client: Client, message: Message):
        await drop_command(client, message)

    async def collect_command(self, client: Client, message: Message):
        await collect_command(client, message)

    async def guess_command(self, client: Client, message: Message):
        await collect_command(client, message)

    async def handle_drop_callback(self, client: Client, callback_query):
        await callback_query.answer()

async def remove_drop_after_timeout(chat_id, message_id):
    """DEPRECATED: Drops no longer expire automatically. This function is kept for compatibility only."""
    # Drops are now persistent and only removed when collected
    return
        

async def preload_next_characters(chat_id, locked_rarities, n=3):
    try:
        db = get_database()
        drop_manager = DropManager(db)
        queue = preloaded_next_character[chat_id]
        while len(queue) < n:
            character = await drop_manager.get_random_character(locked_rarities)
            if character:
                queue.append(character)
            else:
                break
    except Exception as e:
        print(f"Error in preload_next_characters for chat {chat_id}: {e}")
        # import traceback
        # traceback.print_exc()

@Client.on_message(filters.command("setalldroptime", prefixes=["/", ".", "!"]))
async def set_all_droptime_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    if not message.command or len(message.command) < 2:
        await message.reply_text("<b>❌ Please provide a droptime value! Usage: /setalldroptime &lt;number&gt;</b>")
        return
    try:
        new_time = int(message.command[1])
        if new_time < 1:
            await message.reply_text("<b>❌ Droptime must be a positive number!</b>")
            return
        
        # Update all groups in memory only
        updated = 0
        for group_id in group_message_counts:
            group_message_counts[group_id]["msg_count"] = new_time
            group_message_counts[group_id]["current_count"] = 0
            updated += 1
        
        await message.reply_text(f"<b>✅ Droptime set to {new_time} messages for {updated} groups!</b>")
    except ValueError:
        await message.reply_text("<b>❌ Please provide a valid number!</b>")


@Client.on_message(filters.command("clearbanned", prefixes=["/", ".", "!"]))
async def clear_banned_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    
    from .ban_manager import unban_user, get_all_temporary_bans
    
    db = get_database()
    
    # Clear all permanent bans from database
    await db.users.update_many({'is_banned': True}, {'$set': {'is_banned': False}, '$unset': {'banned_at': ""}})
    
    # Clear all temporary bans from memory
    temp_bans = get_all_temporary_bans()
    for user_id in temp_bans.keys():
        await unban_user(user_id, db)
    
    await message.reply_text("<b>✅ All banned users have been unbanned!</b>")

@Client.on_message(filters.command("clearproposes", prefixes=["/", ".", "!"]))
async def clear_proposes_command(client: Client, message: Message):
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    db = get_database()
    # Clear last_propose for all users in the database
    await db.users.update_many({}, {'$unset': {'last_propose': ""}})
    await message.reply_text("<b>✅ All last proposes have been cleared for all users!</b>")


# Message queue for high-volume processing
message_queue = asyncio.Queue(maxsize=500)  # Reduced from 1000 to prevent memory issues
queue_processor_running = False

async def process_message_queue():
    """Process messages from queue to prevent blocking during spam attacks"""
    global queue_processor_running
    queue_processor_running = True
    
    while True:
        try:
            # Get message from queue with timeout
            message_data = await asyncio.wait_for(message_queue.get(), timeout=0.5)  # Reduced from 1.0
            client, message, current_time = message_data
            
            # Process message
            await handle_single_message(client, message, current_time)
            
            # Mark task as done
            message_queue.task_done()
            
        except asyncio.TimeoutError:
            # No messages in queue, continue
            continue
        except Exception as e:
            print(f"Error processing message from queue: {e}")
            continue

async def handle_single_message(client, message, current_time):
    """Handle a single message without spam detection (for queue processing) - FIXED VERSION"""
    # Debug log removed
    if not message.from_user:
        return
    
    user_id = message.from_user.id
    group_id = message.chat.id
    
    # Skip private messages
    if message.chat.type == 'private':
        return
    
    # Completely ignore messages from banned users
    is_banned = await is_user_banned(user_id)
    if is_banned:
        return
    
    # NEW: Check if this is a reply to a drop message for collection
    if message.reply_to_message:
        await handle_reply_collection(client, message)
        return
    
    # FIXED: Ensure periodic save task is running (only if not already started)
    try:
        ensure_periodic_save_task()
    except Exception as e:
        print(f"Warning: Could not ensure periodic save task: {e}")
    
    # Handle jackpot counter
    if group_id not in jackpot_counter:
        jackpot_counter[group_id] = 0
    if group_id not in jackpot_next_interval:
        jackpot_next_interval[group_id] = random.randint(450, 550)
    jackpot_counter[group_id] += 1
    if jackpot_counter[group_id] >= jackpot_next_interval[group_id]:
        asyncio.create_task(drop_jackpot(client, group_id))
        jackpot_counter[group_id] = 0
        jackpot_next_interval[group_id] = random.randint(450, 550)
    
    # FIXED: Use per-group lock to prevent race conditions between different groups
    async with group_message_locks[group_id]:
        # Get current message count for the group
        count_doc = await get_message_count(group_id)
        current_count = count_doc["current_count"] + 1
        msg_count = count_doc["msg_count"]

        # If the current count reaches the drop threshold
        if current_count >= msg_count:
            # Reset current count
            current_count = 0
            
            # Start drop process
            await process_drop(group_id, client, datetime.now())
        
        # Update the message count
        await update_message_count(group_id, msg_count, current_count)


# FIXED: Add function to save active drops whenever they change
async def save_active_drops_safe():
    """Safely save active drops to database"""
    try:
        await save_active_drops()
        return True
    except Exception as e:
        print(f"❌ Error saving active drops: {e}")
        import traceback
        traceback.print_exc()
        return False

# NEW: Function to handle reply collection of dropped characters
async def handle_reply_collection(client: Client, message: Message):
    """Handle collection by replying to drop message with character name"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        current_time = datetime.now()
        
        # Ignore banned users
        if await is_user_banned(user_id):
            return
        
        # Check if the replied message is a drop message
        replied_message = message.reply_to_message
        if not replied_message:
            return
        
        # Check if this is a bot message (likely a drop)
        if not replied_message.from_user or replied_message.from_user.is_bot:
            # This could be a drop message, check if it has a drop_message_id
            drop_message_id = replied_message.id if hasattr(replied_message, 'id') else replied_message.message_id
            
            # Find the character for this drop message
            character = None
            if chat_id in active_drops:
                for drop in active_drops[chat_id]:
                    if drop.get('drop_message_id') == drop_message_id:
                        character = drop
                        break
            
            if not character:
                # Not a valid drop message - check if it was already collected
                last_collected = None
                if hasattr(collect_command, "last_collected_drop") and collect_command.last_collected_drop.get(chat_id):
                    last_collected = collect_command.last_collected_drop[chat_id]
                
                if last_collected:
                    await message.reply_text(
                        f"<b>ℹ Last Character Was Already Collected By <a href=\"tg://user?id={last_collected['collected_by_id']}\">{last_collected['collected_by_name']}</a>!</b>",
                        disable_web_page_preview=True
                    )
                else:
                    await message.reply_text("❌ This is not a valid drop message or the character has already been collected!")
                return
            
            # Extract the character name from the reply message
            character_name = message.text.strip()
            if not character_name:
                await message.reply_text("❌ Please provide the character name to collect!")
                return
            
            # Check if character name matches using regex pattern matching
            if is_character_name_match(character_name, character['name']):
                # Process the collection
                await process_character_collection(client, message, character, current_time)
            else:
                # Incorrect name - show message with inline keyboard button (like main collect function)
                character = active_drops[chat_id][-1]  # Get the latest drop for the button
                if str(chat_id).startswith("-100"):
                    channel_id = str(chat_id)[4:]
                else:
                    channel_id = str(chat_id)
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Pokémon 🔼", url=f"https://t.me/c/{channel_id}/{character['drop_message_id']}")]
                ])
                
                await message.reply_text(
                    f"<b>❌ Incorrect Guess</b> -: <code>{character_name}</code>\n\n<b>Please try again...</b>",
                    reply_markup=keyboard
                )
        
    except Exception as e:
        print(f"Error in handle_reply_collection: {e}")
        import traceback
        traceback.print_exc()

# NEW: Helper function to check if character name matches (using regex)
def is_character_name_match(guess: str, actual: str) -> bool:
    """Check if guessed name matches actual character name - exact for single words, word-based for multi-words"""
    import re
    
    # Clean and normalize both strings
    guess = guess.lower().strip()
    actual = actual.lower().strip()
    
    # Remove special characters that could interfere with matching
    guess_clean = re.sub(r'[&@#$%^*+=|\\/<>?]', '', guess)
    actual_clean = re.sub(r'[&@#$%^*+=|\\/<>?]', '', actual)
    
    # Direct exact match (always works)
    if guess_clean == actual_clean:
        return True
    
    # Split into words
    actual_words = re.findall(r'\b\w+\b', actual_clean)
    
    # For multi-word names, allow individual word collection
    if len(actual_words) > 1:
        # Check if the guess matches any individual word
        for word in actual_words:
            if len(word) >= 3:  # Only consider words with 3+ characters
                if guess_clean == word.lower():
                    return True
    
    # For single-word names, require exact match only
    else:
        # Single word names need exact match only
        return False
    
    return False

# NEW: Function to process character collection (extracted from collect_command)
async def process_character_collection(client: Client, message: Message, character: dict, current_time: datetime):
    """Process character collection for both command and reply methods"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        message_id = character.get('drop_message_id')
        
        # Check if character is already being collected
        if message_id in collecting_characters[chat_id]:
            await message.reply_text("⚠️ This Pokémon is already being collected by someone else!")
            return
        
        # Check if user is already collecting this character
        if message_id in user_collecting[user_id]:
            await message.reply_text("⚠️ You are already trying to collect this character!")
            return
        
        # Mark character as being collected
        collecting_characters[chat_id].add(message_id)
        user_collecting[user_id].add(message_id)
        
        try:
            db = get_database()
            await db.add_character_to_user(
                user_id=user_id,
                character_id=character['character_id'],
                collected_at=current_time,
                source='collected'
            )
            
            # Ensure group membership is tracked
            if message.chat.type != "private":
                await db.add_user_to_group(user_id, message.chat.id)
            
            # Track successful collection for tdgoal
            try:
                await track_collect_drop(user_id)
            except Exception as e:
                print(f"tdgoal track_collect_drop error: {e}")
            
            rarity = character['rarity']
            rarity_emoji = get_rarity_emoji(rarity)
            escaped_name = character['name']
            escaped_rarity = rarity
            user_name = message.from_user.first_name
            character_id = character['character_id']
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"👑 {user_name}'s Collection", switch_inline_query_current_chat=f"collection:{user_id}")]
            ])
            
            bonus_text = ""
            bonus = None
            if random.random() < 0.4:
                bonus = random.randint(30, 50)
                user = await db.get_user(user_id)
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + bonus})
                bonus_text = f"⚡️ <b>Bonus!</b> You received <b>{bonus}</b> extra 🎐 shards for collecting!\n"
            
            msg = (
                f"<b>✅ Look You Collected A</b> <code>{escaped_rarity}</code> <b>Pokémon</b>\n\n"
                f"<b>👤 Name : {escaped_name}</b>\n"
                f"<b>{rarity_emoji} Rarity : {escaped_rarity}</b>\n"
                f"<b>⛩ Region : {character.get('anime', '-') }</b>\n"
                f"{bonus_text}"
                f"\n<b>➥ Look At Your Collection Using</b> /mycollection"
            )
            
            collection_message = await message.reply(
                msg,
                reply_markup=keyboard
            )
            
            # Mark this character as collected by this user for this chat
            if not hasattr(collect_command, "last_collected_drop"):
                collect_command.last_collected_drop = {}
            collect_command.last_collected_drop[chat_id] = {
                'collected_by_id': user_id,
                'collected_by_name': user_name
            }
            
            # Remove the collected character from active drops and expiry tracking
            if character in active_drops[chat_id]:
                # Remove from database first
                try:
                    await db.remove_active_drop(chat_id, character.get('character_id'))
                except Exception as e:
                    print(f"Error removing collected drop from database: {e}")
                
                # Remove from memory
                active_drops[chat_id].remove(character)
            
            if not active_drops[chat_id]:
                del active_drops[chat_id]
            
            # Save updated state to persistent storage
            await save_active_drops()
            
        finally:
            # Always remove from collecting sets
            collecting_characters[chat_id].discard(message_id)
            user_collecting[user_id].discard(message_id)
            
    except Exception as e:
        print(f"Error in process_character_collection: {e}")
        import traceback
        traceback.print_exc()
        await message.reply_text("❌ An error occurred while collecting the character. Please try again.")

# Fallback function removed - now using database

# Cleanup tasks removed
async def clear_cache_command(client: Client, message: Message):
    """Clear character cache to ensure fresh data"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    
    try:
        from modules.postgres_database import clear_all_caches
        clear_all_caches()
        
        # Clear the DropManager cache by resetting the class cache
        DropManager._characters_cache = None
        DropManager._last_characters_update = None
        
        await message.reply_text("✅ <b>All caches have been cleared! Fresh data will be fetched from the database.</b>")
        
    except Exception as e:
        await message.reply_text(f"❌ <b>Error clearing cache: {e}</b>")

@Client.on_message(filters.command("cleardrops", prefixes=["/", ".", "!"]))
async def clear_drops_command(client: Client, message: Message):
    """Clear all active drops (Owner only)"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    
    try:
        global active_drops
        active_drops.clear()
        await save_active_drops()
        await message.reply_text("✅ <b>All active drops have been cleared!</b>")
        
    except Exception as e:
        await message.reply_text(f"❌ <b>Error clearing drops: {e}</b>")

@Client.on_message(filters.command("listdrops", prefixes=["/", ".", "!"]))
async def list_drops_command(client: Client, message: Message):
    """List all active drops (Owner only)"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    
    try:
        if not active_drops:
            await message.reply_text("ℹ️ <b>No active drops found.</b>")
            return
        
        drops_info = []
        for chat_id, drops in active_drops.items():
            chat_info = f"<b>Chat {chat_id}:</b>\n"
            for i, drop in enumerate(drops, 1):
                drop_info = f"  {i}. {drop.get('name', 'Unknown')} ({drop.get('rarity', 'Unknown')})"
                drops_info.append(drop_info)
            drops_info.append("")  # Empty line between chats
        
        await message.reply_text(f"<b>Active Drops:</b>\n\n" + "\n".join(drops_info))
        
    except Exception as e:
        await message.reply_text(f"❌ <b>Error listing drops: {e}</b>")

@Client.on_message(filters.command("testsave", prefixes=["/", ".", "!"]))
async def test_save_command(client: Client, message: Message):
    """Test the save functionality (Owner only)"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    
    try:
        await message.reply_text("🔄 Testing save functionality...")
        
        # Test database connection
        try:
            db = get_database()
            await message.reply_text("✅ Database connection test passed!")
        except Exception as e:
            await message.reply_text(f"❌ Database connection test failed: {e}")
            return
        
        # Test saving
        if save_active_drops_safe():
            await message.reply_text("✅ Save test successful!")
        else:
            await message.reply_text("❌ Save test failed!")
            return
        
        # Test loading
        try:
            loaded_drops = load_active_drops()
            loaded_count = sum(len(drops) for drops in loaded_drops.values())
            await message.reply_text(f"✅ Load test successful! Loaded {loaded_count} drops")
        except Exception as e:
            await message.reply_text(f"❌ Load test failed: {e}")
            return
        
        await message.reply_text("🎉 All tests passed! Drop system is working correctly.")
        
    except Exception as e:
        await message.reply_text(f"❌ <b>Error during testing: {e}</b>")

@Client.on_message(filters.command("forcesave", prefixes=["/", ".", "!"]))
async def force_save_command(client: Client, message: Message):
    """Force save active drops (Owner only)"""
    user_id = message.from_user.id
    if not is_owner(user_id):
        await message.reply_text("<b>❌ Only the owner can use this command!</b>")
        return
    
    try:
        await message.reply_text("🔄 Force saving active drops...")
        
        # Count current drops
        total_drops = sum(len(drops) for drops in active_drops.values())
        await message.reply_text(f"📊 Current active drops: {total_drops}")
        
        # Force save
        if save_active_drops_safe():
            await message.reply_text("✅ Force save successful!")
        else:
            await message.reply_text("❌ Force save failed!")
        
    except Exception as e:
        await message.reply_text(f"❌ <b>Error during force save: {e}</b>")

# FIXED: Add periodic save task to ensure drops are saved regularly
async def periodic_save_drops():
    """Save active drops every 5 minutes to ensure persistence"""
    print("🔄 Periodic save task started - will save every 5 minutes")
    try:
        while True:
            try:
                await asyncio.sleep(300)  # 5 minutes
                print("💾 Periodic save triggered...")
                save_active_drops_safe()
                print("✅ Periodic save completed successfully")
            except asyncio.CancelledError:
                print("ℹ️ Periodic save task cancelled")
                break
            except Exception as e:
                print(f"❌ Error in periodic save drops: {e}")
                import traceback
                traceback.print_exc()
                # Continue running even if there's an error
                continue
    except Exception as e:
        print(f"❌ Fatal error in periodic save task: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("🔄 Periodic save task stopped")
        # Reset the running flag
        if hasattr(start_periodic_save_task, '_task_running'):
            start_periodic_save_task._task_running = False

# FIXED: Don't start the task here - it will be started when the bot starts
# The task will be started in the main bot startup function

def start_periodic_save_task():
    """Start the periodic save task for active drops"""
    try:
        # Check if we already have a task running
        if hasattr(start_periodic_save_task, '_task_running') and start_periodic_save_task._task_running:
            print("ℹ️ Periodic save task already running")
            return
        
        # Only start if there's a running event loop
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                # Create and start the task
                task = asyncio.create_task(periodic_save_drops())
                start_periodic_save_task._task_running = True
                print("✅ Started periodic save task for active drops")
                
                # Add callback to reset flag when task is done
                def task_done_callback(fut):
                    start_periodic_save_task._task_running = False
                    print("ℹ️ Periodic save task completed")
                
                task.add_done_callback(task_done_callback)
            else:
                print("⚠️ Event loop not running, periodic save task will be started later")
        except RuntimeError:
            print("⚠️ No running event loop, periodic save task will be started later")
            
    except Exception as e:
        print(f"Error starting periodic save task: {e}")
        import traceback
        traceback.print_exc()

# FIXED: Add a function that can be called later to start the task
def ensure_periodic_save_task():
    """Ensure the periodic save task is running, start it if needed"""
    try:
        # Check if we already have a task running
        if hasattr(ensure_periodic_save_task, '_task_started') and ensure_periodic_save_task._task_started:
            return
        
        # Only try to start if we're in a proper async context
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                # Start the task
                start_periodic_save_task()
                ensure_periodic_save_task._task_started = True
                print("✅ Periodic save task started from ensure function")
            else:
                print("⚠️ Event loop not running, will start task later")
        except RuntimeError:
            print("⚠️ No running event loop, will start task later")
            
    except Exception as e:
        print(f"Error ensuring periodic save task: {e}")

# Test function removed - no longer needed with database storage


# Safe initialization function for bot startup
async def initialize_drop_system():
    """Initialize the drop system safely during bot startup"""
    try:
        print("🔄 Initializing drop system...")
        
        # Load active drops from database
        global active_drops
        active_drops = await load_active_drops()
        loaded_count = sum(len(drops) for drops in active_drops.values())
        print(f"✅ Loaded {loaded_count} active drops from database")
        
        # Validate drops
        await validate_drops_on_startup()
        
        print("✅ Drop system initialized successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error initializing drop system: {e}")
        import traceback
        traceback.print_exc()
        return False

# Test function call removed


# Cleanup tasks removed to prevent issues

