from pyrogram.types import Message
from pyrogram import Client
from pyrogram.enums import ChatType
# from .decorators import check_banned  # Remove check_banned for status
import os

# Import database based on configuration
from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
from datetime import datetime
import random
import asyncio
from modules.collection import batch_fetch_characters
import time

# Remove @check_banned so banned users can use status
async def status_command(client: Client, message: Message):
    # Determine if in group (same logic as top command)
    chat = message.chat
    is_group = chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]
    reply_args = {"reply_to_message_id": message.id} if is_group else {}
    # Show fetching message
    fetching_msg = await client.send_message(message.chat.id, "<b>⏳ Please wait fetching your Info..</b>", **reply_args)
    try:
        db = get_database()
        user = message.from_user
        user_data = await db.get_user(user.id)
        if not user_data:
            await fetching_msg.delete()
            if is_group:
                await client.send_message(message.chat.id, "❌ <b>You don't have an account!</b>", **reply_args)
            else:
                await client.send_message(message.chat.id, "❌ <b>You don't have an account!</b>", **reply_args)
            return
        # Ban status using new ban system
        from .ban_manager import check_user_ban_status
        is_banned, ban_reason = await check_user_ban_status(user.id, db)
        
        # Collection
        char_ids = user_data.get('characters', [])
        total_collected = len(char_ids)
        unique_ids = set(char_ids)
        unique_collected = len(unique_ids)
        
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                all_characters_result = await conn.fetchrow("SELECT COUNT(*) FROM characters")
                all_characters = all_characters_result[0] if all_characters_result else 0
        else:  # MongoDB
            all_characters = await db.characters.count_documents({})
        
        collection_percentage = (unique_collected / all_characters * 100) if all_characters > 0 else 0
        level = unique_collected // 100 + 1
        ranks = {
            1: "Bronze", 5: "Silver", 10: "Gold", 15: "Platinum", 20: "Diamond", 25: "Master", 30: "Grandmaster", 35: "Elite", 40: "Legend"
        }
        rank = "Bronze"
        for level_threshold, rank_name in sorted(ranks.items(), reverse=True):
            if level >= level_threshold:
                rank = rank_name
                break
        # Batch fetch all unique character details
        collection = []
        rarity_counts = {}
        id_to_char = {}  # Always define this, even if empty
        if unique_ids:
            char_docs = await batch_fetch_characters(db, list(unique_ids), batch_size=500)
            id_to_char = {c['character_id']: c for c in char_docs}
            for cid in unique_ids:
                char = id_to_char.get(cid)
                if char:
                    rarity = char.get('rarity', 'Unknown')
                    # Count only unique characters per rarity
                    rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
                    collection.append(char)
        progress_percentage = (unique_collected / all_characters) * 100 if all_characters else 0
        progress = int((progress_percentage / 100) * 10)
        progress_bar = "▰" * progress + "▱" * (10 - progress)
        # Simple in-memory cache for global position (PostgreSQL version)
        _global_position_cache = {'users': [], 'time': 0}
        _CACHE_TTL = 60  # seconds
        now = time.time()
        users = []
        if hasattr(db, 'pool'):
            if _global_position_cache['users'] and now - _global_position_cache['time'] < _CACHE_TTL:
                users = _global_position_cache['users']
            else:
                try:
                    async with db.pool.acquire() as conn:
                        rows = await conn.fetch("SELECT user_id, array_length(characters, 1) AS total_count FROM users ORDER BY total_count DESC NULLS LAST")
                        users = [row['user_id'] for row in rows]
                        _global_position_cache['users'] = users
                        _global_position_cache['time'] = now
                except Exception as e:
                    pass
                    users = []
                    _global_position_cache['users'] = users
                    _global_position_cache['time'] = now
        else:
            # Fallback for MongoDB (should not be used)
            users = []
        global_position = users.index(user.id) + 1 if users and user.id in users else "N/A"
        
        # Calculate chat position (group-specific position) using exact same logic as top command
        chat_position = "N/A"
        if is_group:
            try:
                # First, ensure the current user is added to this group (same as top command)
                await db.add_user_to_group(user.id, message.chat.id)
                
                # Get all users who are members of this specific group (same query as top command)
                cursor = await db.users.find({"groups": message.chat.id})
                group_users = await cursor.to_list(length=None)
                
                pass
                

                # Always include the current user in the group collectors list
                collectors = []
                user_in_group = False
                for group_user in group_users:
                    if group_user['user_id'] == user.id:
                        user_in_group = True
                    characters = group_user.get('characters', [])
                    total_chars = len(characters) if characters else 0
                    collectors.append({
                        'user_id': group_user['user_id'],
                        'total_count': total_chars
                    })
                if not user_in_group:
                    # Add current user if not present
                    collectors.append({
                        'user_id': user.id,
                        'total_count': len(user_data.get('characters', []))
                    })
                pass
                pass
                pass
                # Sort by total characters collected (same as top command)
                collectors_sorted = sorted(collectors, key=lambda x: x['total_count'], reverse=True)
                # Find user's position in this group
                chat_position = "N/A"
                for i, collector in enumerate(collectors_sorted):
                    if collector['user_id'] == user.id:
                        chat_position = str(i + 1).zfill(2)
                        pass
                        break
                if chat_position == "N/A":
                    # If for some reason not found, set to 1
                    chat_position = "01"
                        
            except Exception as e:
                pass
                chat_position = "N/A"
        
        # Build status message with new UI format
        status_text = f"━━\\ 🤖User's Stats🤖 /━━\n\n"
        status_text += f"━|👤| User → {user.first_name}\n"
        status_text += f"━|🐙| User ID → {user.id}\n"
        status_text += f"━|🎖️| Level → {level}\n"
        status_text += f"━|🥈| Rank → {rank}\n"
        
        # Add ban status if user is banned
        if is_banned:
            from .ban_manager import get_ban_info
            ban_info = get_ban_info(user.id)
            if ban_info:
                ban_type = ban_info.get('type', 'Unknown')
                remaining_minutes = ban_info.get('remaining_minutes')
                if ban_type == 'temporary' and remaining_minutes is not None and remaining_minutes > 0:
                    minutes = int(remaining_minutes)
                    seconds = int((remaining_minutes - minutes) * 60)
                    if seconds < 0:
                        seconds = 0
                    status_text += f"━|⛔️| Banned → {minutes}m {seconds}s remaining\n"
                else:
                    status_text += f"━|⛔️| Banned → Permanent\n"
            else:
                # If no ban_info but user is banned, check if it's a permanent ban
                try:
                    is_permanent_banned = await db.is_banned(user.id)
                    if is_permanent_banned:
                        status_text += f"━|⛔️| Banned → Permanent\n"
                    else:
                        # This shouldn't happen, but just in case
                        status_text += f"━|⛔️| Banned → Unknown\n"
                except Exception as e:
                    status_text += f"━|⛔️| Banned → Unknown\n"
        
        status_text += f"━|✨| Total Collected → {total_collected:,} ({unique_collected:,})\n"
        status_text += f"━|🌪| Collection → {unique_collected:,}/{all_characters:,} ({collection_percentage:.2f}%)\n"
        status_text += f"━|💰| Balance → {user_data.get('wallet', 0):,} Grab-Tokens\n"
        status_text += f"━|📈| Progress Bar →\n{progress_bar}\n"
        status_text += f"━|🎐| Shards → {user_data.get('shards', 0):,}\n\n"
        
        # Add all rarities with their exact emojis
        status_text += f"━|👑| Supreme → {rarity_counts.get('Supreme', 0)}\n"
        status_text += f"━|🔱| Ultimate → {rarity_counts.get('Ultimate', 0)}\n"
        status_text += f"━|🔮| Limited Edition → {rarity_counts.get('Limited Edition', 0)}\n"
        status_text += f"━|💎| Elite → {rarity_counts.get('Elite', 0)}\n"
        status_text += f"━|🫧| Exclusive → {rarity_counts.get('Exclusive', 0)}\n"
        status_text += f"━|🟡| Legendary → {rarity_counts.get('Legendary', 0)}\n"
        status_text += f"━|🟠| Rare → {rarity_counts.get('Rare', 0)}\n"
        status_text += f"━|🟢| Medium → {rarity_counts.get('Medium', 0)}\n"
        status_text += f"━|⚪️| Common → {rarity_counts.get('Common', 0)}\n"
        # Calculate chat position using only users currently present in the group
        chat_position = "N/A"
        if is_group:
            try:
                await db.add_user_to_group(user.id, message.chat.id)
                chat_members = []
                try:
                    async for member in client.get_chat_members(message.chat.id):
                        if not member.user.is_bot:
                            chat_members.append(member.user.id)
                except Exception as e:
                    pass
                pass
                collectors = []
                for member_id in chat_members:
                    db_user = await db.get_user(member_id)
                    if db_user:
                        characters = db_user.get('characters', [])
                        total_chars = len(characters) if characters else 0
                        collectors.append({
                            'user_id': member_id,
                            'total_count': total_chars
                        })
                if user.id not in chat_members:
                    collectors.append({
                        'user_id': user.id,
                        'total_count': len(user_data.get('characters', []))
                    })
                pass
                collectors_sorted = sorted(collectors, key=lambda x: x['total_count'], reverse=True)
                for i, collector in enumerate(collectors_sorted):
                    if collector['user_id'] == user.id:
                        chat_position = str(i + 1).zfill(2)
                        pass
                        break
                if chat_position == "N/A":
                    chat_position = "01"
            except Exception as e:
                pass
                chat_position = "N/A"
        status_text += f"━|🔴| Mythic → {rarity_counts.get('Mythic', 0)}\n"
        status_text += f"━|💫| Zenith → {rarity_counts.get('Zenith', 0)}\n"
        status_text += f"━|❄️| Ethereal → {rarity_counts.get('Ethereal', 0)}\n"
        status_text += f"━|🧿| Premium → {rarity_counts.get('Premium', 0)}\n\n"
        
        status_text += f"━━━━━━━━━━━━━━━\n"
        status_text += f"━|🌍| Position Globally → {global_position}\n"
        status_text += f"━|💬| Chat Position → {chat_position}"
        # Try to get user's first profile photo
        profile_photo = None
        try:
            async for photo in client.get_chat_photos(user.id, limit=1):
                profile_photo = photo
                break
        except Exception as e:
            pass
        # If user has a profile photo, send it with the status text
        if profile_photo:
            try:
                await fetching_msg.delete()
                if is_group:
                    await client.send_photo(
                        message.chat.id,
                        photo=profile_photo.file_id,
                        caption=status_text,
                        **reply_args
                    )
                else:
                    await client.send_photo(
                        message.chat.id,
                        photo=profile_photo.file_id,
                        caption=status_text,
                        **reply_args
                    )
                return
            except Exception as e:
                pass
        # If no profile photo, show favorite character if available
        favorite_id = user_data.get('favorite_character')
        favorite = None
        if favorite_id:
            favorite = id_to_char.get(favorite_id)
            if not favorite or favorite_id not in char_ids:
                await db.update_user(user.id, {'favorite_character': None})
                favorite_id = None
                favorite = None
        if not favorite_id and collection:
            random_char = random.choice(collection)
            favorite_id = random_char['character_id']
            await db.update_user(user.id, {'favorite_character': favorite_id})
            favorite = random_char
        if favorite:
            img_url = favorite.get('img_url')
            is_video = favorite.get('is_video', False)
            if img_url:
                await fetching_msg.delete()
                if is_video:
                    await client.send_video(
                        message.chat.id,
                        video=img_url,
                        caption=status_text,
                        **reply_args
                    )
                else:
                    await client.send_photo(
                        message.chat.id,
                        photo=img_url,
                        caption=status_text,
                        **reply_args
                    )
                return
        await fetching_msg.delete()
        if is_group:
            await client.send_message(message.chat.id, status_text, **reply_args)
        else:
            await client.send_message(message.chat.id, status_text, **reply_args)
    except Exception as e:
        pass
        await fetching_msg.delete()
        if is_group:
            await client.send_message(message.chat.id, "❌ <b>An error occurred!</b>", **reply_args)
        else:
            await client.send_message(message.chat.id, "❌ <b>An error occurred!</b>", **reply_args)