from pyrogram.types import Message
from pyrogram import Client
from modules.decorators import is_owner, is_og, is_sudo
import os

# Import database based on configuration

from modules.postgres_database import get_database, RARITY_EMOJIS, RARITIES

from datetime import datetime, timedelta
from config import BOT_VERSION
import time

# You must set this in your main.py at startup:
# BOT_START_TIME = time.time()
try:
    from main import BOT_START_TIME
except ImportError:
    BOT_START_TIME = time.time()

# Simple in-memory cache for stats result
_stats_cache = {'data': None, 'time': 0}
_CACHE_TTL = 60  # seconds

def get_uptime():
    seconds = int(time.time() - BOT_START_TIME)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    if seconds or not parts: parts.append(f"{seconds}s")
    return ' '.join(parts)

async def stats_command(client: Client, message: Message):
    """Show bot statistics (admins only)"""
    user_id = message.from_user.id
    db = get_database()

    # Check if user is sudo, OG, or owner
    if not (await is_sudo(db, user_id) or await is_og(db, user_id) or is_owner(user_id)):
        await message.reply_text(
            "<b>❌ This command is restricted to sudo, OGs, and owners only!</b>"
        )
        return

    # Check cache
    now = time.time()
    if _stats_cache['data'] and now - _stats_cache['time'] < _CACHE_TTL:
        await message.reply_text(_stats_cache['data'])
        return

    # DB status check
    db_status = "🟢 Connected"
    try:
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                await conn.fetchrow("SELECT 1")
        else:  # MongoDB
            await db.users.estimated_document_count()
    except Exception:
        db_status = "🔴 Error"

    try:
        # Uptime
        uptime = get_uptime()
        
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Get total groups using union of chat_settings and users.groups
                try:
                    groups_result = await conn.fetchrow(
                        """
                        SELECT COUNT(*) FROM (
                            SELECT chat_id FROM chat_settings
                            UNION
                            SELECT DISTINCT unnest(groups) AS chat_id FROM users WHERE groups IS NOT NULL
                        ) t
                        """
                    )
                    total_groups = groups_result[0] if groups_result else 0
                except Exception:
                    # Fallback to chat_settings only if users.groups not available
                    groups_result = await conn.fetchrow("SELECT COUNT(*) FROM chat_settings")
                    total_groups = groups_result[0] if groups_result else 0
                
                # Get total users
                users_result = await conn.fetchrow("SELECT COUNT(*) FROM users")
                total_users = users_result[0] if users_result else 0
                
                # Get total characters
                chars_result = await conn.fetchrow("SELECT COUNT(*) FROM characters")
                total_characters = chars_result[0] if chars_result else 0
                
                # Get total harem count (sum of all characters in users' collections)
                harem_result = await conn.fetchrow("""
                    SELECT COALESCE(SUM(
                        CASE 
                            WHEN characters IS NOT NULL AND array_length(characters, 1) IS NOT NULL
                            THEN array_length(characters, 1)
                            ELSE 0
                        END
                    ), 0) FROM users
                """)
                total_harem = harem_result[0] if harem_result else 0
                
                # Get character count by rarity
                rarity_counts_result = await conn.fetch("""
                    SELECT rarity, COUNT(*) as count 
                    FROM characters 
                    GROUP BY rarity 
                    ORDER BY rarity
                """)
                rarity_counts = [{'count': row['count'], '_id': row['rarity']} for row in rarity_counts_result]
                
                # Get latest characters
                latest_chars_result = await conn.fetch("""
                    SELECT name FROM characters 
                    ORDER BY character_id DESC 
                    LIMIT 5
                """)
                latest_chars = [{'name': row['name']} for row in latest_chars_result]
                
        else:  # MongoDB
            # Get total groups using union of chat_settings and users.groups
            try:
                settings_ids = []
                try:
                    settings_ids = await db.chat_settings.distinct('chat_id')
                except Exception:
                    settings_ids = []
                user_group_ids = []
                try:
                    user_group_ids = await db.users.distinct('groups')
                except Exception:
                    user_group_ids = []
                # Filter out None values and compute union
                total_groups = len(set([g for g in settings_ids if g is not None]) |
                                   set([g for g in user_group_ids if g is not None]))
            except Exception:
                # Fallback to chat_settings count
                total_groups = await db.chat_settings.count_documents({})
            
            # Get total users
            total_users = await db.users.count_documents({})
            
            # Get total characters
            total_characters = await db.characters.count_documents({})
            
            # Get total harem count (sum of all characters in users' collections)
            # Use a more robust aggregation that handles missing fields
            try:
                total_harem_result = await db.users.aggregate([
                    {
                        "$project": {
                            "characters_count": {
                                "$cond": {
                                    "if": {"$isArray": "$characters"},
                                    "then": {"$size": "$characters"},
                                    "else": 0
                                }
                            }
                        }
                    },
                    {"$group": {"_id": None, "total": {"$sum": "$characters_count"}}}
                ]).to_list(length=1)
                total_harem = total_harem_result[0]['total'] if total_harem_result else 0
            except Exception as e:
                print(f"Error calculating total harem: {e}")
                total_harem = 0
            
            # Get character count by rarity
            try:
                rarity_counts = await db.characters.aggregate([
                    {"$group": {"_id": "$rarity", "count": {"$sum": 1}}},
                    {"$sort": {"_id": 1}}
                ]).to_list(length=None)
            except Exception as e:
                print(f"Error getting rarity counts: {e}")
                rarity_counts = []
            
            # Get latest characters
            try:
                latest_chars = await db.characters.find({}, {"name": 1}).sort("character_id", -1).limit(5).to_list(length=5)
            except Exception as e:
                print(f"Error getting latest characters: {e}")
                latest_chars = []
        
        # Sort rarity_counts by canonical rarity order
        rarity_order = [
            "Common", "Medium", "Rare", "Legendary", "Exclusive", "Elite",
            "Limited Edition", "Ultimate", "Premium", "Supreme", "Zenith", "Mythic", "Ethereal"
        ]
        rarity_counts_sorted = sorted(
            rarity_counts,
            key=lambda r: rarity_order.index(r['_id']) if r['_id'] in rarity_order else 999
        )
        
        # Timestamp
        last_updated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        # Compose message in a beautiful box style
        message_text = (
            "╭━━━━━━━━━━━━━━━━━━━╮\n"
            "  Collect Heroes  Database Info\n"
            "╰━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"👥 Total Registered Users: <code>{total_users}</code>\n"
            f"🎮 Total Characters Available: <code>{total_characters}</code>\n"
            f"🏘️ Total Groups: <code>{total_groups}</code>\n"
            f"💎 Total Characters Collected: <code>{total_harem}</code>\n\n"
            f"📊 Rarity Distribution:\n"
        )
        
        for rarity in rarity_counts_sorted:
            emoji = RARITY_EMOJIS.get(rarity['_id'], "❓")
            message_text += f"{emoji} <b>{rarity['_id'].upper()}</b>: <code>{rarity['count']}</code>\n"
        
        # Latest added characters (last 5)
        if latest_chars:
            message_text += "\n🔥 Latest Added Characters:\n"
            for char in latest_chars:
                message_text += f"🔹 {char.get('name', '-') }\n"
        
        message_text += f"\n<i>Last updated: {last_updated}</i>"
        _stats_cache['data'] = message_text
        _stats_cache['time'] = time.time()
        await message.reply_text(message_text)
        
    except Exception as e:
        print(f"Error in stats command: {e}")
        await message.reply_text(
            "<b>❌ An error occurred while getting stats!</b>"
        )

def setup_stats_handlers(application):
    """Setup stats command handler"""
    application.add_handler(stats_command)
