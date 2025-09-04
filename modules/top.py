from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ChatType
from datetime import datetime, timedelta
from .decorators import is_owner, is_og, check_banned
from config import OWNER_ID, DROPTIME_LOG_CHANNEL
import os

# Import database based on configuration
from modules.postgres_database import get_database
import time

# NOTE: Telegram API Limitation
# The bot can only fetch user information for users it has previously interacted with.
# Users who haven't used the bot before will show their database names (which may be outdated).
# 
# LONG-TERM SOLUTION: To keep names updated, implement a system that:
# 1. Updates user names in database whenever they interact with the bot (commands, drops, etc.)
# 2. Periodically syncs names from active users
# 3. Uses cached names for better performance
#
# CURRENT SOLUTION: Try to fetch from Telegram, fallback to database names with smart error handling.

# Helper for markdown v2 escaping (minimal)
def escape_markdown(text, version=2):
    if not text:
        return ''
    return str(text).replace('_', '\_').replace('*', '\*').replace('[', '\[').replace('`', '\`')

# Reward amounts for top collectors (in Grab Tokens)
REWARDS = {
    1: 300000,  # 1st place: 300K tokens
    2: 275000,  # 2nd place: 275K tokens
    3: 250000,  # 3rd place: 250K tokens
    4: 225000,  # 4th place: 225K tokens
    5: 200000,  # 5th place: 200K tokens
    6: 175000,  # 6th place: 175K tokens
    7: 150000,  # 7th place: 150K tokens
    8: 125000,  # 8th place: 125K tokens
    9: 100000,  # 9th place: 100K tokens
    10: 75000   # 10th place: 75K tokens
}

# Simple in-memory cache for leaderboard results
_leaderboard_cache = {}
_CACHE_TTL = 60  # seconds

def get_cached_leaderboard(key):
    entry = _leaderboard_cache.get(key)
    if entry and time.time() - entry['time'] < _CACHE_TTL:
        return entry['data']
    return None

def set_cached_leaderboard(key, data):
    _leaderboard_cache[key] = {'data': data, 'time': time.time()}

async def distribute_daily_rewards(client: Client):
    """Distribute rewards to top collectors based on UTC daily reset"""
    try:
        db = get_database()
        
        # Use the optimized database method
        top_collectors = await db.get_todays_top_collectors(10)
        
        if not top_collectors:
            return
        
        # Distribute rewards
        for idx, collector in enumerate(top_collectors, 1):
            if idx in REWARDS:
                reward = REWARDS[idx]
                await db.users.update_one(
                    {'user_id': collector['user_id']},
                    {'$inc': {'wallet': reward}}
                )
        
        message = "🎉 <b>Daily Leaderboard Results</b> 🎉\n\n<b>Top Collectors of the Day:</b>\n\n"
        for idx, collector in enumerate(top_collectors, 1):
            if idx in REWARDS:
                reward = REWARDS[idx]
                user_id = collector['user_id']
                fallback_name = collector.get('first_name', 'Unknown')
                
                # Get current name from Telegram using our helper function
                current_name = await _get_user_display_name(client, user_id, fallback_name)
                
                user_link = f"tg://user?id={user_id}"
                escaped_name = escape_markdown(current_name, version=2)
                message += (
                    f"🏅 <b>{idx}</b> Place: <a href='{user_link}'>{escaped_name}</a> - <b>{reward:,}  Tokens</b>\n"
                )
        message += "\n<b>Congratulations to the winners!</b> 🎊\nYour rewards have been added to your balances!"
        
        try:
            sent_message = await client.send_message(
                chat_id=DROPTIME_LOG_CHANNEL,
                text=message,
                disable_web_page_preview=True
            )
            await client.pin_chat_message(
                chat_id=DROPTIME_LOG_CHANNEL,
                message_id=sent_message.id,
                disable_notification=False
            )
        except Exception as e:
            print(f"Error sending/pinning message: {e}")
    except Exception as e:
        print(f"Error in distribute_daily_rewards: {e}")

async def _fetch_display_name(client: Client, user_id: int, cache: dict | None = None) -> str:
    """Fetch the user's display name from Telegram using user_id, with optional per-call cache."""
    if cache is not None and user_id in cache:
        return cache[user_id]
    try:
        user = await client.get_users(user_id)
        if user and hasattr(user, 'first_name') and user.first_name:
            name = user.first_name
        else:
            name = "Unknown"
    except Exception as e:
        print(f"Error fetching user {user_id}: {e}")
        name = "Unknown"
    if cache is not None:
        cache[user_id] = name
    return name

async def _get_user_display_name(client: Client, user_id: int, fallback_name: str = "Unknown") -> str:
    """Get user's current display name with better error handling and fallback."""
    try:
        # Try to get current user info from Telegram
        user_info = await client.get_users(user_id)
        if user_info and hasattr(user_info, 'first_name') and user_info.first_name:
            return user_info.first_name
        else:
            print(f"User {user_id} has no first_name attribute or it's empty")
            return fallback_name
    except Exception as e:
        # Handle specific Telegram API errors
        if "PEER_ID_INVALID" in str(e):
            print(f"User {user_id}: Bot hasn't interacted with this user yet, using database name")
            return fallback_name
        elif "USER_DEACTIVATED" in str(e):
            print(f"User {user_id}: User account is deactivated, using database name")
            return fallback_name
        else:
            print(f"Failed to fetch user {user_id} from Telegram: {e}")
            return fallback_name

async def _get_user_display_name_smart(client: Client, user_id: int, fallback_name: str = "Unknown") -> str:
    """Smart user name fetching that handles various Telegram API limitations."""
    try:
        # Try to get current user info from Telegram
        user_info = await client.get_users(user_id)
        if user_info and hasattr(user_info, 'first_name') and user_info.first_name:
            # Successfully got current name
            if user_info.first_name != fallback_name:
                print(f"User {user_id}: Updated name from '{fallback_name}' to '{user_info.first_name}'")
                # Try to update the database with the new name
                try:
                    db = get_database()
                    await db.users.update_one(
                        {'user_id': user_id},
                        {'$set': {'first_name': user_info.first_name}}
                    )
                    print(f"User {user_id}: Database updated with new name '{user_info.first_name}'")
                except Exception as db_error:
                    print(f"User {user_id}: Failed to update database: {db_error}")
            return user_info.first_name
        else:
            print(f"User {user_id}: No first_name attribute, using database name")
            return fallback_name
    except Exception as e:
        error_str = str(e)
        if "PEER_ID_INVALID" in error_str:
            print(f"User {user_id}: Bot hasn't met this user yet (PEER_ID_INVALID), using database name: '{fallback_name}'")
        elif "USER_DEACTIVATED" in error_str:
            print(f"User {user_id}: User account deactivated, using database name: '{fallback_name}'")
        elif "USER_NOT_FOUND" in error_str:
            print(f"User {user_id}: User not found, using database name: '{fallback_name}'")
        else:
            print(f"User {user_id}: Unknown error '{error_str}', using database name: '{fallback_name}'")
        return fallback_name

async def update_user_name_in_database(user_id: int, new_name: str):
    """Update user's name in the database when they interact with the bot."""
    try:
        db = get_database()
        await db.users.update_one(
            {'user_id': user_id},
            {'$set': {'first_name': new_name}}
        )
        print(f"User {user_id}: Database updated with new name '{new_name}'")
        return True
    except Exception as e:
        print(f"User {user_id}: Failed to update database name: {e}")
        return False

@check_banned
async def tdtop_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Today's Leaderboard Details")
    try:
        db = get_database()
        # Use UTC timezone for consistency
        now_utc = datetime.utcnow()
        today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_utc = today_utc + timedelta(days=1)
        
        # Use the optimized database method
        top_collectors = await db.get_todays_top_collectors(10)
        
        if not top_collectors:
            await fetching_msg.delete()
            time_remaining = tomorrow_utc - now_utc
            hours = time_remaining.seconds // 3600
            minutes = (time_remaining.seconds % 3600) // 60
            await client.send_message(
                message.chat.id,
                f"<b>❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛᴏʀs ғᴏᴜɴᴅ ғᴏʀ ᴛᴏᴅᴀʏ!</b>\n\n"
                f"<b>⏰ ɴᴇxᴛ ʀᴇsᴇᴛ ɪɴ:</b> <code>{hours}h {minutes}m</code>"
            )
            return
        
        time_remaining = tomorrow_utc - now_utc
        hours = time_remaining.seconds // 3600
        minutes = (time_remaining.seconds % 3600) // 60
        message_text = (
            "🌟 <b>Today's Top 10 Collectors</b> 🌟\n\n"
            f"<b>⏰ ɴᴇxᴛ ʀᴇsᴇᴛ ɪɴ:</b> <code>{hours}h {minutes}m</code>\n\n"
        )
        medals = ["🥇", "🥈", "🥉"]
        
        # Fetch current user information from Telegram for updated names
        name_cache = {}  # Cache for this command execution
        for idx, collector in enumerate(top_collectors, 1):
            user_id = collector['user_id']
            fallback_name = collector.get('first_name', 'Unknown')
            
            # Get current name from Telegram using our smart helper function
            current_name = await _get_user_display_name_smart(client, user_id, fallback_name)
            
            # Store in cache for this execution
            name_cache[user_id] = current_name
            
            user_link = f"tg://user?id={user_id}"
            escaped_name = escape_markdown(current_name, version=2)
            if idx <= 3:
                message_text += f"{medals[idx-1]} <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['count']} Collected</b>\n"
            else:
                message_text += f"{idx}. <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['count']} Collected</b>\n"
        
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            message_text,
            disable_web_page_preview=True
        )
    except Exception as e:
        import traceback
        print(f"Error in tdtop_command: {e}")
        print(traceback.format_exc())
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            f"<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!</b>\n<code>{e}</code>"
        )

@check_banned
async def gtop_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Global Leaderboard Details")
    db = get_database()
    cache_key = 'gtop'
    cached = get_cached_leaderboard(cache_key)
    if cached:
        await fetching_msg.delete()
        await client.send_message(message.chat.id, cached, disable_web_page_preview=True)
        return
    try:
        collectors = []
        cursor = await db.users.find({})
        users = await cursor.to_list(length=None)
        for user in users:
            try:
                characters = user.get('characters', [])
                if characters:
                    unique_chars = len(set(characters))
                    total_chars = len(characters)
                    collectors.append({
                        'first_name': user.get('first_name', 'Unknown'),
                        'user_id': user['user_id'],
                        'total_count': total_chars,
                        'unique_count': unique_chars
                    })
            except Exception:
                continue
        top_collectors = sorted(collectors, key=lambda x: x['total_count'], reverse=True)[:10]
        if not top_collectors:
            await fetching_msg.delete()
            await client.send_message(
                message.chat.id,
                "<b>❌ ɴᴏ ᴄᴏʟʟᴇᴛᴏʀs ғᴏᴜɴᴅ!</b>"
            )
            return
        message_text = "<b>🌍 ɢʟᴏʙᴀʟ ᴛᴏᴘ 10 ᴄᴏʟʟᴇᴄᴛᴏʀs 🌍</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for idx, collector in enumerate(top_collectors, 1):
            user_id = collector['user_id']
            fallback_name = collector.get('first_name', 'Unknown')
            
            # Get current name from Telegram using our smart helper function
            current_name = await _get_user_display_name_smart(client, user_id, fallback_name)
            
            user_link = f"tg://user?id={user_id}"
            escaped_name = escape_markdown(current_name, version=2)
            prefix = medals[idx-1] if idx <= 3 else f"{idx}"
            message_text += (
                f"<b>{prefix}</b> <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['total_count']} | ({collector['unique_count']})</b>\n"
            )
        set_cached_leaderboard(cache_key, message_text)
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            message_text,
            disable_web_page_preview=True
        )
    except Exception as e:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!</b>"
        )

@check_banned
async def top_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Group Leaderboard Details")
    db = get_database()
    chat = message.chat
    if chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ᴄᴀɴ ᴏɴʟʏ ʙᴇ ᴜsᴇᴅ ɪɴ ɢʀᴏᴜᴘs!</b>"
        )
        return
    try:
        # First, ensure the current user is added to this group
        await db.add_user_to_group(message.from_user.id, chat.id)
        
        # Get all users who are members of this specific group
        cursor = await db.users.find({"groups": chat.id})
        group_users = await cursor.to_list(length=None)

        # Get actual current group members from Telegram
        current_members = set()
        try:
            async for member in client.get_chat_members(chat.id):
                if hasattr(member, 'user') and hasattr(member.user, 'id'):
                    current_members.add(member.user.id)
        except Exception as e:
            # If we can't fetch members, fallback to old behavior
            current_members = None

        # Filter group_users to only those who are still in the group
        if current_members is not None:
            group_users = [user for user in group_users if user.get('user_id') in current_members]
        
        if not group_users:
            await fetching_msg.delete()
            await client.send_message(
                message.chat.id,
                "<b>❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛᴏʀs ғᴏᴜɴᴅ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ!</b>"
            )
            return
        
        # Process users and their collections
        collectors = []
        for user in group_users:
            characters = user.get('characters', [])
            if characters:
                unique_chars = len(set(characters))
                total_chars = len(characters)
                collectors.append({
                    'first_name': user.get('first_name', 'Unknown'),
                    'user_id': user['user_id'],
                    'total_count': total_chars,
                    'unique_count': unique_chars
                })
        
        # Sort by total characters collected and take top 10
        top_collectors = sorted(collectors, key=lambda x: x['total_count'], reverse=True)[:10]
        
        if not top_collectors:
            await fetching_msg.delete()
            await client.send_message(
                message.chat.id,
                "<b>❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛᴏʀs ғᴏᴜɴᴅ ɪɴ ᴛʜɪs ɢʀᴏᴜᴘ!</b>"
            )
            return
        
        message_text = f"<b>📊 ᴛᴏᴘ 10 ᴄᴏʟʟᴇᴄᴛᴏʀs ɪɴ {escape_markdown(chat.title, version=2)} 📊</b>\n\n"
        medals = ["🥇", "🥈", "🥉"]
        for idx, collector in enumerate(top_collectors, 1):
            user_id = collector['user_id']
            fallback_name = collector.get('first_name', 'Unknown')
            
            # Get current name from Telegram using our smart helper function
            current_name = await _get_user_display_name_smart(client, user_id, fallback_name)
            
            user_link = f"tg://user?id={user_id}"
            escaped_name = escape_markdown(current_name, version=2)
            prefix = medals[idx-1] if idx <= 3 else f"{idx}"
            message_text += (
                f"<b>{prefix}</b> <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['total_count']} | ({collector['unique_count']})</b>\n"
            )
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            message_text,
            disable_web_page_preview=True
        )
    except Exception as e:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ғᴇᴛᴄʜɪɴɢ ᴛᴏᴘ ᴄᴏʟʟᴇᴄᴛᴏʀs!</b>"
        )

@check_banned
async def rgtop_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Richest Collectors Leaderboard")
    db = get_database()
    rich_users = []
    cursor = await db.users.find({})
    users = await cursor.to_list(length=None)
    for user in users:
        wallet = user.get('wallet', 0)
        if wallet > 0:
            rich_users.append({
                'first_name': user['first_name'],
                'user_id': user['user_id'],
                'wallet': wallet
            })
    top_rich = sorted(rich_users, key=lambda x: x['wallet'], reverse=True)[:10]
    if not top_rich:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ!</b>"
        )
        return
    message_text = "<b>💰 ɢʟᴏʙᴀʟ ᴛᴏᴘ 10 ʀɪᴄʜᴇsᴛ ᴄᴏʟʟᴇᴄᴛᴏʀs 💰</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for idx, user in enumerate(top_rich, 1):
        user_id = user['user_id']
        fallback_name = user.get('first_name', 'Unknown')
        
        # Get current name from Telegram using our helper function
        current_name = await _get_user_display_name(client, user_id, fallback_name)
        
        user_link = f"tg://user?id={user_id}"
        escaped_name = escape_markdown(current_name, version=2)
        prefix = medals[idx-1] if idx <= 3 else f"{idx}"
        wallet = f"{user['wallet']:,}"
        message_text += (
            f"<b>{prefix}</b> <a href='{user_link}'>{escaped_name}</a> ➣ <b>{wallet} Tokens</b>\n"
        )
    await fetching_msg.delete()
    await client.send_message(
        message.chat.id,
        message_text,
        disable_web_page_preview=True
    )

@check_banned
async def btop_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Top Bank Balances")
    db = get_database()
    user_id = message.from_user.id
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴏᴡɴᴇʀ ᴀɴᴅ ᴏɢs ᴏɴʟʏ!</b>"
        )
        return
    bank_users = []
    cursor = await db.users.find({})
    users = await cursor.to_list(length=None)
    for user in users:
        bank = user.get('bank') or 0
        if bank > 0:
            bank_users.append({
                'first_name': user['first_name'],
                'user_id': user['user_id'],
                'bank': bank
            })
    top_bank = sorted(bank_users, key=lambda x: x['bank'], reverse=True)[:25]
    if not top_bank:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ɴᴏ ᴜsᴇʀs ᴡɪᴛʜ ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇ ғᴏᴜɴᴅ!</b>"
        )
        return
    message_text = "<b>🏦 ᴛᴏᴘ 25 ʙᴀɴᴋ ʙᴀʟᴀɴᴄᴇs 🏦</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for idx, user in enumerate(top_bank, 1):
        user_id = user['user_id']
        fallback_name = user.get('first_name', 'Unknown')
        
        # Get current name from Telegram using our helper function
        current_name = await _get_user_display_name(client, user_id, fallback_name)
        
        user_link = f"tg://user?id={user_id}"
        escaped_name = escape_markdown(current_name, version=2)
        prefix = medals[idx-1] if idx <= 3 else f"{idx}"
        bank = f"{user['bank']:,}"
        message_text += (
            f"<b>{prefix}</b> <a href='{user_link}'>{escaped_name}</a> ➣ <b>{bank} Tokens</b>\n"
        )
    await fetching_msg.delete()
    await client.send_message(
        message.chat.id,
        message_text,
        disable_web_page_preview=True
    )

@check_banned
async def sgtop_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Top Shards Collectors Leaderboard")
    db = get_database()
    shard_users = []
    cursor = await db.users.find({})
    users = await cursor.to_list(length=None)
    for user in users:
        shards = user.get('shards', 0)
        if shards > 0:
            shard_users.append({
                'first_name': user['first_name'],
                'user_id': user['user_id'],
                'shards': shards
            })
    top_shards = sorted(shard_users, key=lambda x: x['shards'], reverse=True)[:10]
    if not top_shards:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ɴᴏ ᴜsᴇʀs ғᴏᴜɴᴅ!</b>"
        )
        return
    message_text = "<b>🎐 ɢʟᴏʙᴀʟ ᴛᴏᴘ 10 sʜᴀʀᴅ ᴄᴏʟʟᴇᴄᴛᴏʀs 🎐</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for idx, user in enumerate(top_shards, 1):
        user_id = user['user_id']
        fallback_name = user.get('first_name', 'Unknown')
        
        # Get current name from Telegram using our helper function
        current_name = await _get_user_display_name(client, user_id, fallback_name)
        
        user_link = f"tg://user?id={user_id}"
        escaped_name = escape_markdown(current_name, version=2)
        prefix = medals[idx-1] if idx <= 3 else f"{idx}"
        shards = f"{user['shards']:,}"
        message_text += (
            f"<b>{prefix}</b> <a href='{user_link}'>{escaped_name}</a> ➣ <b>{shards} Shards</b>\n"
        )
    await fetching_msg.delete()
    await client.send_message(
        message.chat.id,
        message_text,
        disable_web_page_preview=True
    )

@check_banned
async def wintop_command(client: Client, message: Message):
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Weekly Battle Winners Leaderboard")
    try:
        db = get_database()
        
        # Get weekly battle winners
        weekly_winners = await db.get_weekly_battle_winners(10)
        
        if not weekly_winners:
            await fetching_msg.delete()
            await client.send_message(
                message.chat.id,
                "<b>❌ ɴᴏ ʙᴀᴛᴛʟᴇ ᴡɪɴs ғᴏᴜɴᴅ ғᴏʀ ᴛʜɪs ᴡᴇᴇᴋ!</b>"
            )
            return
        
        # Calculate week info
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        days_since_monday = now.weekday()
        start_of_week = now - timedelta(days=days_since_monday)
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=7)
        
        # Calculate time remaining until next week
        time_remaining = end_of_week - now
        days = time_remaining.days
        hours = time_remaining.seconds // 3600
        minutes = (time_remaining.seconds % 3600) // 60
        
        message_text = (
            "⚔️ <b>Weekly Battle Winners</b> ⚔️\n\n"
            f"<b>📅 ᴡᴇᴇᴋ:</b> <code>{start_of_week.strftime('%B %d')} - {end_of_week.strftime('%B %d')}</code>\n"
            f"<b>⏰ ɴᴇxᴛ ʀᴇsᴇᴛ ɪɴ:</b> <code>{days}d {hours}h {minutes}m</code>\n\n"
        )
        
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, winner in enumerate(weekly_winners, 1):
            user_id = winner['user_id']
            fallback_name = winner.get('first_name', 'Unknown')
            
            # Get current name from Telegram using our smart helper function
            current_name = await _get_user_display_name_smart(client, user_id, fallback_name)
            
            user_link = f"tg://user?id={user_id}"
            escaped_name = escape_markdown(current_name, version=2)
            
            if idx <= 3:
                message_text += f"{medals[idx-1]} <a href='{user_link}'>{escaped_name}</a> ➣ <b>{winner['wins']} Wins</b>\n"
            else:
                message_text += f"{idx}. <a href='{user_link}'>{escaped_name}</a> ➣ <b>{winner['wins']} Wins</b>\n"
        
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            message_text,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ғᴇᴛᴄʜɪɴɢ ʙᴀᴛᴛʟᴇ ᴡɪɴɴᴇʀs!</b>"
        )

@check_banned
async def wtop_command(client: Client, message: Message):
    """Show weekly top collectors leaderboard"""
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "🔄 Fetching Weekly Top Collectors Leaderboard")
    
    try:
        db = get_database()
        
        # Get weekly top collectors
        weekly_collectors = await db.get_weekly_top_collectors(10)
        
        if not weekly_collectors:
            await fetching_msg.delete()
            await client.send_message(
                message.chat.id,
                "<b>❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛᴏʀs ғᴏᴜɴᴅ ғᴏʀ ᴛʜɪs ᴡᴇᴇᴋ!</b>"
            )
            return
        
        # Calculate week info
        from datetime import datetime, timedelta
        utc_now = datetime.utcnow()
        days_since_monday = utc_now.weekday()  # Monday is 0, Sunday is 6
        week_start = utc_now - timedelta(days=days_since_monday)
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
        next_monday = week_start + timedelta(days=7)
        
        # Calculate time remaining until next Monday (weekly reset)
        time_remaining = next_monday - utc_now
        days = time_remaining.days
        hours = time_remaining.seconds // 3600
        minutes = (time_remaining.seconds % 3600) // 60
        
        message_text = (
            "🏆 <b>Weekly Top Collectors</b> 🏆\n\n"
            f"<b>📅 Week:</b> <code>{week_start.strftime('%B %d')} - {week_end.strftime('%B %d')}</code>\n"
            f"<b>⏰ Next Reset:</b> <code>{days}d {hours}h {minutes}m</code>\n\n"
        )
        
        medals = ["🥇", "🥈", "🥉"]
        
        for idx, collector in enumerate(weekly_collectors, 1):
            user_id = collector['user_id']
            fallback_name = collector.get('first_name', 'Unknown')
            
            # Get current name from Telegram using smart helper function
            current_name = await _get_user_display_name_smart(client, user_id, fallback_name)
            
            user_link = f"tg://user?id={user_id}"
            escaped_name = escape_markdown(current_name, version=2)
            
            if idx <= 3:
                message_text += f"{medals[idx-1]} <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['count']} Collections</b>\n"
            else:
                message_text += f"{idx}. <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['count']} Collections</b>\n"
        
        await fetching_msg.delete()
        await client.send_message(
            message.chat.id,
            message_text,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await fetching_msg.delete()
        print(f"Error in wtop command: {e}")
        await client.send_message(
            message.chat.id,
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ғᴇᴛᴄʜɪɴɢ ᴡᴇᴇᴋʟʏ ᴄᴏʟʟᴇᴄᴛᴏʀs!</b>"
        )

@check_banned
async def test_leaderboard_command(client: Client, message: Message):
    user_id = message.from_user.id
    if isinstance(OWNER_ID, list):
        if user_id not in OWNER_ID:
            await message.reply_text(
                "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ!</b>"
            )
            return
    elif user_id != OWNER_ID:
        await message.reply_text(
            "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ!</b>"
        )
        return
    try:
        db = get_database()
        
        # Use the optimized database method
        top_collectors = await db.get_todays_top_collectors(10)
        
        if not top_collectors:
            await message.reply_text(
                "<b>❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛᴏʀs ғᴏᴜɴᴅ ғᴏʀ ᴛᴏᴅᴀʏ!</b>",
            )
            return
        
        # Distribute rewards
        for idx, collector in enumerate(top_collectors, 1):
            if idx in REWARDS:
                reward = REWARDS[idx]
                await db.users.update_one(
                    {'user_id': collector['user_id']},
                    {'$inc': {'wallet': reward}}
                )
        
        message_text = "🎉 <b>Daily Leaderboard Results</b> 🎉\n\n<b>Top Collectors of the Day:</b>\n\n"
        for idx, collector in enumerate(top_collectors, 1):
            if idx in REWARDS:
                reward = REWARDS[idx]
                user_id = collector['user_id']
                fallback_name = collector.get('first_name', 'Unknown')
                
                # Get current name from Telegram using our helper function
                current_name = await _get_user_display_name(client, user_id, fallback_name)
                
                user_link = f"tg://user?id={user_id}"
                escaped_name = escape_markdown(current_name, version=2)
                message_text += (
                    f"🏅 <b>{idx}</b> Place: <a href='{user_link}'>{escaped_name}</a> - <b>{reward:,} Tokens</b>\n"
                )
        message_text += "\n<b>Congratulations to the winners!</b> 🎊\nYour rewards have been added to your balances!"
        
        try:
            sent_message = await client.send_message(
                chat_id=DROPTIME_LOG_CHANNEL,
                text=message_text,
                disable_web_page_preview=True
            )
            await client.pin_chat_message(
                chat_id=DROPTIME_LOG_CHANNEL,
                message_id=sent_message.id,
                disable_notification=True
            )
            await message.reply_text(
                "<b>✅ ᴛᴇsᴛ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ ᴅɪsᴛʀɪʙᴜᴛɪᴏɴ ᴄᴏᴍᴘʟᴇᴛᴇᴅ!</b>"
            )
        except Exception as e:
            print(f"Error sending/pinning message: {e}")
            await message.reply_text(
                "<b>❌ ᴇʀʀᴏʀ sᴇɴᴅɪɴɢ/pɪɴɴɪɴɢ ᴍᴇssᴀɢᴇ!</b>"
            )
    except Exception as e:
        print(f"Error in test leaderboard: {e}")
        await message.reply_text(
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ᴛᴇsᴛɪɴɢ ʟᴇᴀᴅᴇʀʙᴏᴀʀᴅ!</b>"
        )

def setup_top_handlers(app: Client):
    app.add_handler(filters.command("tdtop")(tdtop_command))
    app.add_handler(filters.command("gtop")(gtop_command))
    app.add_handler(filters.command("top")(top_command))
    app.add_handler(filters.command("rgtop")(rgtop_command))
    app.add_handler(filters.command("btop")(btop_command))
    app.add_handler(filters.command("testleaderboard")(test_leaderboard_command))
    app.add_handler(filters.command("sgtop")(sgtop_command))
    app.add_handler(filters.command("wintop")(wintop_command))
    app.add_handler(filters.command("wtop")(wtop_command))
    app.add_handler(filters.command("testname")(test_name_fetch_command))

@check_banned
async def test_name_fetch_command(client: Client, message: Message):
    """Test command to verify user name fetching functionality."""
    user_id = message.from_user.id
    if isinstance(OWNER_ID, list):
        if user_id not in OWNER_ID:
            await message.reply_text(
                "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ!</b>"
            )
            return
    elif user_id != OWNER_ID:
        await message.reply_text(
            "<b>❌ ᴛʜɪs ᴄᴏᴍᴍᴀɴᴅ ɪs ʀᴇsᴛʀɪᴄᴛᴇᴅ ᴛᴏ ᴛʜᴇ ʙᴏᴛ ᴏᴡɴᴇʀ!</b>"
        )
        return
    
    try:
        db = get_database()
        user_data = await db.users.find_one({"user_id": user_id})
        if not user_data:
            await message.reply_text("<b>❌ User not found in database!</b>")
            return
        
        db_name = user_data.get('first_name', 'Unknown')
        
        # Test the smart name fetching
        current_name = await _get_user_display_name_smart(client, user_id, db_name)
        
        result = (
            f"<b>🧪 Name Fetch Test Results</b>\n\n"
            f"<b>User ID:</b> <code>{user_id}</code>\n"
            f"<b>Database Name:</b> <code>{db_name}</code>\n"
            f"<b>Current Name:</b> <code>{current_name}</code>\n"
            f"<b>Status:</b> {'✅ Updated' if current_name != db_name else '🔄 Same'}\n\n"
            f"<b>Note:</b> This tests the name fetching functionality."
        )
        
        await message.reply_text(result)
        
    except Exception as e:
        await message.reply_text(f"<b>❌ Error testing name fetch: {e}</b>")


async def post_tdtop_to_log_channel(client: Client):
    """Compute today's top collectors and pin the list in droptime log channel."""
    try:
        db = get_database()
        # Use UTC timezone for consistency, but show remaining time like tdtop
        now_utc = datetime.utcnow()
        today_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_utc = today_utc + timedelta(days=1)

        top_collectors = await db.get_todays_top_collectors(10)
        if not top_collectors:
            time_remaining = tomorrow_utc - now_utc
            hours = time_remaining.seconds // 3600
            minutes = (time_remaining.seconds % 3600) // 60
            text = (
                "🌟 <b>Today's Top 10 Collectors</b> 🌟\n\n"
                f"<b>⏰ ɴᴇxᴛ ʀᴇsᴇᴛ ɪɴ:</b> <code>{hours}h {minutes}m</code>\n\n"
                "<b>❌ ɴᴏ ᴄᴏʟʟᴇᴄᴛᴏʀs ғᴏᴜɴᴅ ғᴏʀ ᴛᴏᴅᴀʏ!</b>"
            )
            sent = await client.send_message(DROPTIME_LOG_CHANNEL, text, disable_web_page_preview=True)
            try:
                await client.pin_chat_message(DROPTIME_LOG_CHANNEL, sent.id, disable_notification=True)
            except Exception:
                pass
            return

        time_remaining = tomorrow_utc - now_utc
        hours = time_remaining.seconds // 3600
        minutes = (time_remaining.seconds % 3600) // 60
        message_text = (
            "🌟 <b>Today's Top 10 Collectors</b> 🌟\n\n"
            f"<b>⏰ ɴᴇxᴛ ʀᴇsᴇᴛ ɪɴ:</b> <code>{hours}h {minutes}m</code>\n\n"
        )
        medals = ["🥇", "🥈", "🥉"]
        for idx, collector in enumerate(top_collectors, 1):
            user_id = collector['user_id']
            fallback_name = collector.get('first_name', 'Unknown')
            
            # Get current name from Telegram using our helper function
            current_name = await _get_user_display_name(client, user_id, fallback_name)
            
            user_link = f"tg://user?id={user_id}"
            escaped_name = escape_markdown(current_name, version=2)
            if idx <= 3:
                message_text += f"{medals[idx-1]} <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['count']} Collected</b>\n"
            else:
                message_text += f"{idx}. <a href='{user_link}'>{escaped_name}</a> ➣ <b>{collector['count']} Collected</b>\n"

        sent_message = await client.send_message(
            chat_id=DROPTIME_LOG_CHANNEL,
            text=message_text,
            disable_web_page_preview=True
        )
        try:
            await client.pin_chat_message(
                chat_id=DROPTIME_LOG_CHANNEL,
                message_id=sent_message.id,
                disable_notification=True
            )
        except Exception:
            pass
    except Exception as e:
        print(f"Error posting tdtop to log channel: {e}")