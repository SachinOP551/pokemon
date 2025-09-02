from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultPhoto, InlineQueryResultVideo, InlineQueryResultArticle, InputTextMessageContent, InputMediaPhoto, InputMediaVideo
from pyrogram.errors import MessageNotModified
import os

# Import database based on configuration
from modules.postgres_database import get_database
import random
import re
from collections import Counter
import asyncio
from datetime import datetime

ITEMS_PER_PAGE = 10
DEFAULT_ITEMS_PER_PAGE = 5

# Type emojis mapping
TYPE_EMOJIS = {
    "Normal": "🔘",
    "Fire": "🔥",
    "Water": "💧",
    "Electric": "⚡",
    "Grass": "🌱",
    "Ice": "❄️",
    "Fighting": "🥊",
    "Poison": "☣️",
    "Ground": "⛰",
    "Flying": "🌪",
    "Psychic": "🔮",
    "Bug": "🪲",
    "Rock": "🪨",
    "Ghost": "👁‍🗨",
    "Dragon": "🐉",
    "Dark": "🌑",
    "Steel": "🔩",
    "Fairy": "🧚",
    "Goat": "🐐",
    "Trio": "💮",
    "Duo": "💠",
    "Regional Champion": "🥇",
    "World Champion": "🏆",
    "Team Leader": "⭐️",
    "Team": "🌟",
    "Rivals": "⚔️"
}

def format_pokemon_type(pokemon_type):
    """Format Pokémon type with emoji, handling dual types like 'Grass/Poison'"""
    if not pokemon_type:
        return "❓ Unknown"
    
    # Handle dual types (e.g., "Grass/Poison")
    if "/" in pokemon_type:
        types = pokemon_type.split("/")
        formatted_types = []
        for type_name in types:
            type_name = type_name.strip()
            emoji = TYPE_EMOJIS.get(type_name, "❓")
            formatted_types.append(f"{emoji} <b>{type_name.upper()}</b>")
        return " & ".join(formatted_types)
    else:
        # Single type
        emoji = TYPE_EMOJIS.get(pokemon_type.strip(), "❓")
        return f"{emoji} <b>{pokemon_type.strip().upper()}</b>"

# Separate rarity definitions
RARITY_DATA = {
    "Common": {
        "emoji": "⚪️",
        "level": 1
    },
    "Medium": {
        "emoji": "🟢",
        "level": 2
    },
    "Rare": {
        "emoji": "🟠",
        "level": 3
    },
    "Legendary": {
        "emoji": "🟡",
        "level": 4
    },
    "Exclusive": {
        "emoji": "🫧",
        "level": 5
    },
    "Elite": {
        "emoji": "💎",
        "level": 6
    },
    "Limited Edition": {
        "emoji": "🔮",
        "level": 7
    },
    "Ultimate": {
        "emoji": "🔱",
        "level": 8
    },
    "Supreme": {
        "emoji": "👑",
        "level": 9
    },
    "Mythic": {
        "emoji": "🔴",
        "level": 10
    },
    "Zenith": {
        "emoji": "💫",
        "level": 11
    },
    "Ethereal": {
        "emoji": "❄️",
        "level": 12
    },
    "Premium": {
        "emoji": "🧿",
        "level": 13
    },
    "Mega Evolution": {
        "emoji": "🧬",
        "level": 14
    }
}

# Helper functions for rarity handling
def get_rarity_parts(rarity_full: str) -> tuple:
    """Split full rarity string into emoji and name"""
    for rarity_name, data in RARITY_DATA.items():
        if rarity_name in rarity_full:
            return data["emoji"], rarity_name
    return "⭐", rarity_full  # Default fallback

def get_rarity_level(rarity_full: str) -> int:
    """Get rarity level for sorting"""
    for rarity_name, data in RARITY_DATA.items():
        if rarity_name in rarity_full:
            return data["level"]
    return 0  # Default fallback

async def collection_command(client, message: Message):
    """Handle /mycollection command (Pyrogram version)"""
    try:
        user_id = message.from_user.id
        db = get_database()

        # Get user data using PostgreSQL-compatible method
        if hasattr(db, 'pool'):  # PostgreSQL
            user_data = await db.get_user(user_id)
        else:  # MongoDB
            user_data = await db.users.find_one({"user_id": user_id}, {"user_id": 1, "first_name": 1, "favorite_character": 1})
        
        if not user_data:
            # Try to create user if they don't exist
            try:
                user_data = {
                    'user_id': user_id,
                    'username': message.from_user.username,
                    'first_name': message.from_user.first_name,
                    'last_name': message.from_user.last_name,
                    'wallet': 0,
                    'shards': 0,
                    'characters': [],
                    'coins': 100,
                    'last_daily': None,
                    'last_weekly': None,
                    'last_monthly': None,
                    'sudo': False,
                    'og': False,
                    'collection_preferences': {
                        'mode': 'default',
                        'filter': None
                    },
                    'joined_at': datetime.now()
                }
                await db.add_user(user_data)
            except Exception as e:
                print(f"Error creating user: {e}")
                await message.reply_text(
                    "<b>❌ ᴘʟᴇᴀsᴇ sᴛᴀʀᴛ ᴛʜᴇ ʙᴏᴛ ғɪʀsᴛ ʙʏ ᴜsɪɴɢ /start ᴄᴏᴍᴍᴀɴᴅ!</b>"
                )
                return

        # Ensure user_data is a dictionary
        if not isinstance(user_data, dict):
            await message.reply_text(
                "<b>❌ ᴇʀʀᴏʀ ʀᴇᴀᴅɪɴɢ ᴜsᴇʀ ᴅᴀᴛᴀ!</b>"
            )
            return

        # Get preferences directly from database
        preferences = await db.get_user_preferences(user_id)
        mode = preferences.get('mode', 'default')
        rarity_filter = preferences.get('filter', None)
        sort_by = preferences.get('sort_by', None)

        # Get unique character count using optimized method
        collection = await db.get_user_collection(user_id)
        unique_count = len(collection)

        # Create keyboard with inline query button
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🔍 View Collection ({unique_count} unique)", switch_inline_query_current_chat=f"collection:{user_id}:0")]
        ])

        # Show collection page with current preferences
        await show_collection_page(
            client,
            message,
            user_id,
            page=1,
            mode=mode,
            rarity_filter=rarity_filter,
            sort_by=sort_by,
            reply_markup=keyboard,
            from_user=message.from_user
        )
    except Exception as e:
        print(f"Error in collection_command: {e}")
        await message.reply_text(
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!</b>"
        )

async def batch_fetch_characters(db, char_ids, batch_size=500):
    """Fetch characters in batches to avoid memory issues"""
    if not char_ids:
        return []
    
    projection = {
        'character_id': 1,
        'name': 1,
        'rarity': 1,
        'anime': 1,
        'img_url': 1,
        'file_id': 1,
        'is_video': 1
    }
    
    if hasattr(db, 'pool'):  # PostgreSQL
        async with db.pool.acquire() as conn:
            # Convert list to tuple for SQL IN clause
            char_ids_tuple = tuple(char_ids)
            if len(char_ids_tuple) == 1:
                # Handle single item case
                char_ids_tuple = (char_ids_tuple[0],)
            
            characters = await conn.fetch(
                "SELECT character_id, name, rarity, anime, img_url, file_id, is_video, type FROM characters WHERE character_id = ANY($1)",
                char_ids_tuple
            )
            return [dict(char) for char in characters]
    else:  # MongoDB
        batches = [char_ids[i:i+batch_size] for i in range(0, len(char_ids), batch_size)]
        async def fetch_batch(batch):
            return await db.characters.find({'character_id': {'$in': batch}}, projection).to_list(length=None)
        results = await asyncio.gather(*(fetch_batch(batch) for batch in batches))
        char_docs = [doc for batch in results for doc in batch]
        return char_docs

async def get_anime_statistics(db, collection):
    """Get statistics for each anime in the collection"""
    anime_stats = {}
    
    # Group characters by anime to calculate owned counts
    for char in collection:
        anime_name = char.get('anime', 'Unknown Anime')
        if anime_name not in anime_stats:
            anime_stats[anime_name] = {
                'owned': 0,
                'total_available': 0
            }
        anime_stats[anime_name]['owned'] += char['count']
    
    # Get total available characters for each anime
    try:
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                for anime_name in anime_stats.keys():
                    result = await conn.fetchval(
                        "SELECT COUNT(*) FROM characters WHERE anime = $1",
                        anime_name
                    )
                    anime_stats[anime_name]['total_available'] = result or 0
        else:  # MongoDB
            for anime_name in anime_stats.keys():
                count = await db.characters.count_documents({'anime': anime_name})
                anime_stats[anime_name]['total_available'] = count
    except Exception as e:
        print(f"Error getting anime statistics: {e}")
        # If we can't get the stats, just use owned counts
        for anime_name in anime_stats.keys():
            anime_stats[anime_name]['total_available'] = anime_stats[anime_name]['owned']
    
    return anime_stats

async def show_collection_page(client, message, user_id: int, page: int, mode='default', rarity_filter=None, sort_by=None, reply_markup=None, from_user=None, callback_query=None):
    """Show a page of the user's collection (Pyrogram version)"""
    try:
        db = get_database()
        # Get user data using PostgreSQL-compatible method
        if hasattr(db, 'pool'):  # PostgreSQL
            user_data = await db.get_user(user_id)
        else:  # MongoDB
            user_data = await db.users.find_one({"user_id": user_id}, {"user_id": 1, "first_name": 1, "favorite_character": 1})
        
        collection = await db.get_user_collection(user_id)
        total_items = len(collection)
        if rarity_filter:
            collection = [c for c in collection if c['rarity'] == rarity_filter]

        # Apply sorting by anime if requested
        if sort_by in ("anime_count", "anime_alpha"):
            # Build counts per anime based on the (possibly filtered) collection
            anime_counts = {}
            for item in collection:
                anime_name = item.get('anime', 'Unknown Anime')
                anime_counts[anime_name] = anime_counts.get(anime_name, 0) + max(1, item.get('count', 1))
            if sort_by == "anime_count":
                # Sort by total owned per anime (desc), then anime name, then character name
                collection.sort(key=lambda x: (
                    -anime_counts.get(x.get('anime', 'Unknown Anime'), 0),
                    (x.get('anime') or 'Unknown Anime').lower(),
                    (x.get('name') or '').lower()
                ))
            elif sort_by == "anime_alpha":
                # Sort by anime name alphabetically, then character name
                collection.sort(key=lambda x: (
                    (x.get('anime') or 'Unknown Anime').lower(),
                    (x.get('name') or '').lower()
                ))
        
        # Use different pagination limits based on mode
        items_per_page = DEFAULT_ITEMS_PER_PAGE if mode == 'default' else ITEMS_PER_PAGE
        total_pages = max(1, (len(collection) + items_per_page - 1) // items_per_page)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, len(collection))
        current_page_items = collection[start_idx:end_idx]
        
        # Get anime statistics for the current page items
        anime_stats = await get_anime_statistics(db, current_page_items)
        
        display_name = from_user.first_name if from_user else user_data.get('first_name', 'User')
        text = _create_collection_message(
            display_name,
            total_items,
            page,
            total_pages,
            current_page_items,
            mode=mode,
            rarity_filter=rarity_filter,
            anime_stats=anime_stats,
            sort_by=sort_by
        )
        keyboard = _create_keyboard(page, total_pages, user_id, total_items)
        reply_markup = keyboard
        # Only fetch favorite_character if needed
        favorite_id = None
        if user_data and 'favorite_character' in user_data:
            favorite_id = user_data.get('favorite_character')
        favorite_char = None
        if favorite_id:
            # Use batch fetch for favorite character
            if hasattr(db, 'pool'):  # PostgreSQL
                async with db.pool.acquire() as conn:
                    char_docs = await conn.fetch(
                        "SELECT character_id, name, rarity, anime, file_id, img_url, is_video, type FROM characters WHERE character_id = $1",
                        favorite_id
                    )
                    char_docs = [dict(char) for char in char_docs]
            else:  # MongoDB
                char_docs = await db.characters.find({"character_id": favorite_id}, {"character_id": 1, "name": 1, "rarity": 1, "file_id": 1, "img_url": 1, "is_video": 1}).to_list(length=1)
            
            if char_docs:
                # Check if user actually owns this character (use full collection, not filtered)
                full_collection = await db.get_user_collection(user_id)
                if favorite_id in [char['character_id'] for char in full_collection]:
                    favorite_char = char_docs[0]
                else:
                    # User doesn't own this character anymore, clear favorite
                    await db.update_user(user_id, {'favorite_character': None})
                    favorite_id = None
                    favorite_char = None
            else:
                # Character doesn't exist in database, clear favorite
                await db.update_user(user_id, {'favorite_character': None})
                favorite_id = None
                favorite_char = None
        if not favorite_id and collection:
            # If no favorite is set, set a random character as favorite and save it
            # Use the full collection (before rarity filter) for random selection
            full_collection = await db.get_user_collection(user_id)
            if full_collection:
                random_char = random.choice(full_collection)
                await db.update_user(user_id, {'favorite_character': random_char['character_id']})
                # Get the full character data for display
                if hasattr(db, 'pool'):  # PostgreSQL
                    async with db.pool.acquire() as conn:
                        char_docs = await conn.fetch(
                            "SELECT character_id, name, rarity, anime, file_id, img_url, is_video, type FROM characters WHERE character_id = $1",
                            random_char['character_id']
                        )
                        char_docs = [dict(char) for char in char_docs]
                else:  # MongoDB
                    char_docs = await db.characters.find({"character_id": random_char['character_id']}, {"character_id": 1, "name": 1, "rarity": 1, "file_id": 1, "img_url": 1, "is_video": 1}).to_list(length=1)
                
                if char_docs:
                    favorite_char = char_docs[0]
        elif not favorite_id:
            favorite_char = None
        if favorite_char:
            is_video = favorite_char.get('is_video', False)
            if is_video:
                # For video characters, prefer img_url (Cloudinary URL) over file_id
                video_source = favorite_char.get('img_url') or favorite_char.get('file_id')
                if callback_query:
                    try:
                        if reply_markup:
                            await callback_query.edit_message_media(
                                media=InputMediaVideo(
                                    media=video_source,
                                    caption=text
                                ),
                                reply_markup=reply_markup
                            )
                        else:
                            await callback_query.edit_message_media(
                                media=InputMediaVideo(
                                    media=video_source,
                                    caption=text
                                )
                            )
                    except MessageNotModified:
                        pass
                    except Exception as e:
                        print(f"Error editing video message: {e}")
                        # Fallback to text message
                        await callback_query.edit_message_text(
                            text,
                            reply_markup=reply_markup
                        )
                else:
                    try:
                        await message.reply_video(
                            video=video_source,
                            caption=text,
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        print(f"Error sending video message: {e}")
                        # Fallback to text message
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup
                        )
            else:
                photo = favorite_char.get('img_url', favorite_char['file_id'])
                if callback_query:
                    try:
                        if reply_markup:
                            await callback_query.edit_message_media(
                                media=InputMediaPhoto(
                                    media=photo,
                                    caption=text
                                ),
                                reply_markup=reply_markup
                            )
                        else:
                            await callback_query.edit_message_media(
                                media=InputMediaPhoto(
                                    media=photo,
                                    caption=text
                                )
                            )
                    except MessageNotModified:
                        pass
                    except Exception as e:
                        print(f"Error editing photo message: {e}")
                        # Fallback to text message
                        await callback_query.edit_message_text(
                            text,
                            reply_markup=reply_markup
                        )
                else:
                    try:
                        await message.reply_photo(
                            photo=photo,
                            caption=text,
                            reply_markup=reply_markup
                        )
                    except Exception as e:
                        print(f"Error sending photo message: {e}")
                        # Fallback to text message
                        await message.reply_text(
                            text,
                            reply_markup=reply_markup
                        )
        else:
            if callback_query:
                try:
                    if reply_markup:
                        await callback_query.edit_message_text(
                            text,
                            reply_markup=reply_markup
                        )
                    else:
                        await callback_query.edit_message_text(
                            text
                        )
                except MessageNotModified:
                    pass
            else:
                await message.reply_text(
                    text,
                    reply_markup=reply_markup
                )
    except Exception as e:
        print(f"Error in show_collection_page: {e}")
        error_message = "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ sʜᴏᴡɪɴɢ ʏᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ!</b>"
        if callback_query:
            await callback_query.edit_message_text(
                error_message
            )
        else:
            await message.reply_text(
                error_message
            )

async def smode_command(client, message):
    owner_id = message.from_user.id
    keyboard = [
        [InlineKeyboardButton("Sort by Region 🧩", callback_data=f"sm_anime:{owner_id}"), InlineKeyboardButton("Sort by Rarity 📊", callback_data=f"sm_rarity:{owner_id}")],
        [InlineKeyboardButton("Default Mode 📱", callback_data=f"sm_default:{owner_id}")],
        [InlineKeyboardButton("Detailed Mode 📋", callback_data=f"sm_detailed:{owner_id}")],
        [InlineKeyboardButton("Close ❌", callback_data=f"sm_close:{owner_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "<b>🔧 Customize your hunts interface using the buttons below:</b>",
        reply_markup=reply_markup
    )

async def handle_smode_callback(client, callback_query: CallbackQuery):
    query = callback_query
    await query.answer()

    user_id = query.from_user.id
    db = get_database()
    current_preferences = await db.get_user_preferences(user_id)

    # Parse command and owner restriction from callback data
    raw = query.data
    if ":" in raw:
        cmd, owner_part = raw.split(":", 1)
        try:
            owner_id = int(owner_part)
        except ValueError:
            owner_id = None
    else:
        cmd = raw
        owner_id = None

    # Only the initiating user can interact with this menu
    if owner_id is not None and owner_id != user_id:
        await query.answer("🚫 This action is not for you!", show_alert=True)
        return
    owner_suffix = f":{owner_id}" if owner_id is not None else f":{user_id}"

    if cmd == "sm_close":
        await query.message.delete()
        return

    elif cmd == "sm_rarity":
        # Show rarity selection buttons
        keyboard = []
        for rarity_name, data in RARITY_DATA.items():
            keyboard.append([InlineKeyboardButton(
                f"{data['emoji']} {rarity_name}",
                callback_data=f"f_{rarity_name}{owner_suffix}"
            )])
        keyboard.append([InlineKeyboardButton("Back 🔙", callback_data=f"sm_back{owner_suffix}")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        current_filter = current_preferences.get('filter', None)
        header_text = "<b>Select Rarity Filter:</b>"
        if current_filter:
            header_text += f"\n\nYour Collection Sort is set to: <b>{current_filter}</b>"
        await query.edit_message_text(
            header_text,
            reply_markup=reply_markup
        )
        return

    elif cmd == "sm_anime":
        # Show anime sorting options
        keyboard = [
            [InlineKeyboardButton("🔢 By Counting", callback_data=f"sm_anime_count{owner_suffix}")],
            [InlineKeyboardButton("🔤 By Alphabetically", callback_data=f"sm_anime_alpha{owner_suffix}")],
            [InlineKeyboardButton("❌ Close", callback_data=f"sm_close{owner_suffix}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "<b>Select Anime Sort:</b>",
            reply_markup=reply_markup
        )
        return

    elif cmd in ("sm_anime_count", "sm_anime_alpha"):
        # Update sort preference while preserving current mode/filter
        sort_by = "anime_count" if cmd == "sm_anime_count" else "anime_alpha"
        preferences = {
            "mode": current_preferences.get('mode', 'default'),
            "filter": current_preferences.get('filter', None),
            "sort_by": sort_by
        }
        await db.update_user_preferences(user_id, preferences)
        selection_text = "By Counting" if sort_by == "anime_count" else "By Alphabetically"
        await query.edit_message_text(
            f"<b>🔄 Yᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ ᴀɴɪᴍᴇ sᴏʀᴛ ʜᴀs ʙᴇᴇɴ sᴇᴛ ᴛᴏ:</b> <b>{selection_text.upper()}</b>"
        )
        return

    elif cmd.startswith("f_"):
        rarity = cmd.split("_", 1)[1]
        # Keep the current mode when changing rarity filter
        preferences = {
            "mode": current_preferences.get('mode', 'default'),
            "filter": rarity,
            "sort_by": current_preferences.get('sort_by', None)
        }
        await db.update_user_preferences(user_id, preferences)

        await query.edit_message_text(
            f"<b>🔄 Yᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ sᴏʀᴛ sʏsᴛᴇᴍ ʜᴀs ʙᴇᴇɴ sᴜᴄᴄᴇssғᴜʟʟʏ sᴇᴛ:</b> <b>{rarity.upper()}</b>"
        )
        return

    elif cmd == "sm_back":
        keyboard = [
            [InlineKeyboardButton("Sort by Region 🧩", callback_data=f"sm_anime{owner_suffix}"), InlineKeyboardButton("Sort by Rarity 📊", callback_data=f"sm_rarity{owner_suffix}")],
            [InlineKeyboardButton("Default Mode 📱", callback_data=f"sm_default{owner_suffix}")],
            [InlineKeyboardButton("Detailed Mode 📋", callback_data=f"sm_detailed{owner_suffix}")],
            [InlineKeyboardButton("Close ❌", callback_data=f"sm_close{owner_suffix}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "🔧 Customize your hunts interface using the buttons below:",
            reply_markup=reply_markup
        )
        return

    elif cmd.startswith("sm_"):
        mode = cmd.split("_")[1]
        if mode == "detailed":
            preferences = {
                "mode": mode,
                "filter": current_preferences.get('filter', None),
                "sort_by": current_preferences.get('sort_by', None)
            }
        elif mode == "default":
            preferences = {
                "mode": "default",
                "filter": None,
                "sort_by": current_preferences.get('sort_by', None)
            }
        await db.update_user_preferences(user_id, preferences)
        mode_name = "Detailed Mode" if mode == "detailed" else "Default Mode"
        await query.edit_message_text(
            f"<b>🔄 Yᴏᴜʀ ᴄᴏʟʟᴇᴄᴛɪᴏɴ ɪɴᴛᴇʀғᴀᴄᴇ ʜᴀs ʙᴇᴇɴ sᴇᴛ ᴛᴏ:</b> <b>{mode_name}</b>"
        )

async def handle_collection_callback(client, callback_query: CallbackQuery):
    query = callback_query
    await query.answer()
    
    if query.data == "current_page":
        return
    
    if query.data.startswith("c_"):
        # Parse callback data: c_<page>_<owner_user_id>
        parts = query.data.split("_")
        if len(parts) >= 3:
            page = int(parts[1])
            owner_user_id = int(parts[2])
            
            # Check if the user clicking is the collection owner
            if query.from_user.id != owner_user_id:
                await query.answer("❌ You can only navigate your own collection!", show_alert=True)
                return
            
            # Get current preferences to preserve mode and filter
            db = get_database()
            preferences = await db.get_user_preferences(query.from_user.id)
            mode = preferences.get('mode', 'default')
            rarity_filter = preferences.get('filter', None)
            sort_by = preferences.get('sort_by', None)
            await show_collection_page(
                client,
                query.message,
                query.from_user.id,
                page,
                mode=mode,
                rarity_filter=rarity_filter,
                sort_by=sort_by,
                from_user=query.from_user,
                callback_query=query
            )
        else:
            # Handle old format for backward compatibility
            page = int(query.data.split("_")[1])
            db = get_database()
            preferences = await db.get_user_preferences(query.from_user.id)
            mode = preferences.get('mode', 'default')
            rarity_filter = preferences.get('filter', None)
            sort_by = preferences.get('sort_by', None)
            await show_collection_page(
                client,
                query.message,
                query.from_user.id,
                page,
                mode=mode,
                rarity_filter=rarity_filter,
                sort_by=sort_by,
                from_user=query.from_user,
                callback_query=query
            )
    
    elif query.data.startswith("s_"):
        sort_type = query.data.split("_")[1]
        await sort_collection(client, query.message, query.from_user.id, sort_type, callback_query=query)

async def sort_collection(client, message, user_id: int, sort_type: str, callback_query=None):
    db = get_database()
    user_data = await db.get_user(user_id)

    if not user_data or not user_data.get('characters', []):
        return

    char_ids = user_data['characters']
    characters = []

    for char_id in char_ids:
        char = await db.get_character(char_id)
        if char:
            characters.append(char)

    if sort_type == "name":
        characters.sort(key=lambda x: x['name'].lower())
    elif sort_type == "rarity":
        characters.sort(key=lambda x: get_rarity_level(x['rarity']), reverse=True)

    # Update user's character order
    new_char_ids = [char['character_id'] for char in characters]
    await db.update_user(user_id, {'characters': new_char_ids})

    # Get user preferences for mode and filter
    preferences = await db.get_user_preferences(user_id)
    mode = preferences.get('mode', 'default')
    rarity_filter = preferences.get('filter', None)
    sort_by = preferences.get('sort_by', None)

    # Show first page of sorted collection
    await show_collection_page(
        client,
        message,
        user_id,
        page=1,
        mode=mode,
        rarity_filter=rarity_filter,
        sort_by=sort_by,
        from_user=message.from_user,
        callback_query=callback_query
    )

def _create_collection_message(first_name, total_chars, page, total_pages, characters, mode='default', rarity_filter=None, anime_stats=None, sort_by=None):
    """Create the collection display message (HTML version for Pyrogram)"""
    try:
        # Base message with user info and pagination
        message = (
            f"<b>{first_name}'s {rarity_filter if rarity_filter else 'Collection'} Page {page} of {total_pages}</b>\n\n"
        )

        if not characters:
            return message  # Return just the header with total count if no characters

        if mode == "detailed":
            # Group by anime first, then by rarity within each anime
            anime_groups = {}
            for char in characters:
                anime_name = char.get('anime', 'Unknown Anime')
                if anime_name not in anime_groups:
                    anime_groups[anime_name] = {}
                
                rarity = char['rarity']
                if rarity not in anime_groups[anime_name]:
                    anime_groups[anime_name][rarity] = []
                anime_groups[anime_name][rarity].append(char)

            # Display by anime groups
            # Determine anime ordering based on sort preference
            if sort_by == 'anime_count' and anime_stats:
                ordered_animes = sorted(
                    anime_groups.items(),
                    key=lambda kv: (-anime_stats.get(kv[0], {}).get('owned', 0), kv[0].lower())
                )
            elif sort_by == 'anime_alpha':
                ordered_animes = sorted(anime_groups.items(), key=lambda kv: kv[0].lower())
            else:
                ordered_animes = sorted(anime_groups.items())

            for anime_name, rarity_groups in ordered_animes:
                message += f"<b>⛩️ {anime_name}</b>\n"
                
                # Sort rarities within each anime
                for rarity, chars in sorted(rarity_groups.items(), key=lambda x: get_rarity_level(x[0]), reverse=True):
                    rarity_emoji = RARITY_DATA.get(rarity, {}).get('emoji', '🟢')
                    for char in chars:
                        count_display = f" [x{char['count']}]" if char['count'] > 1 else ""
                        message += (
                            f"{rarity_emoji} ({char['character_id']}) {char['name']}{count_display}\n"
                        )
                message += "\n"
        else:
            # Default mode - show each character individually with anime stats
            for char in characters:
                rarity_emoji = RARITY_DATA.get(char['rarity'], {}).get('emoji', '⭐')
                anime_name = char.get('anime', 'Unknown Anime')
                
                # Get statistics for this anime
                if anime_stats and anime_name in anime_stats:
                    total_owned = anime_stats[anime_name]['owned']
                    total_available = anime_stats[anime_name]['total_available']
                    message += (
                        f"<b>{rarity_emoji} {char['name']}\n"
                        f"➥ {anime_name}</b>\n\n"
                    )
                else:
                    # Fallback if no stats available
                    message += (
                        f"<b>{rarity_emoji} {char['name']}\n"
                        f"➥ {anime_name} (?)</b>\n\n"
                    )

        return message
    except Exception as e:
        print(f"Error creating collection message: {e}")
        return "<b>❌ Error displaying collection!</b>"

def _create_keyboard(page, total_pages, user_id, total_items):
    keyboard = []
    if total_pages > 1:
        nav_row = []
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"c_{page-1}_{user_id}"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"c_{page+1}_{user_id}"))
        keyboard.append(nav_row)
    # Always add the View Collection button (no :0)
    keyboard.append([InlineKeyboardButton(f"📜 Total ({total_items})", switch_inline_query_current_chat=f"collection:{user_id}")])
    return InlineKeyboardMarkup(keyboard) if keyboard else None

# Helper for inline results (adapted from search.py)
def create_inline_result(character, user_name):
    rarity_emoji = RARITY_DATA.get(character['rarity'], {}).get('emoji', '⭐')
    
    # Format the type with emojis
    pokemon_type = character.get('type', 'Unknown')
    formatted_type = format_pokemon_type(pokemon_type)
    
    caption = (
        f"<b>{user_name}'s {character['rarity']} Collect</b>\n\n"
        f"👤<b>Name: {character['name']}</b>"
    )
    if character['count'] > 1:
        caption += f" [x{character['count']}]"
    caption += f"\n{rarity_emoji}<b>Rarity: {character['rarity']}</b>\n"
    caption += f"<b>⛩ Region: {character['anime']}</b>\n"
    caption += f"<b>{formatted_type}</b>\n"
    caption += f"🔖<b>ID: {character['character_id']}</b>"
    title = f"{rarity_emoji} {character['name']}"
    description = f"🆔 {character['character_id']} | {character['rarity']}"
    if character.get('img_url'):
        if character.get('is_video', False):
            return InlineQueryResultVideo(
                id=str(character['character_id']),
                video_url=character['img_url'],
                thumb_url=character['img_url'],
                mime_type='video/mp4',
                title=title,
                description=description,
                caption=caption
            )
        else:
            return InlineQueryResultPhoto(
                id=str(character['character_id']),
                photo_url=character['img_url'],
                thumb_url=character['img_url'],
                title=title,
                description=description,
                caption=caption
            )
    else:
        return InlineQueryResultArticle(
            id=str(character['character_id']),
            title=title,
            description=description,
            input_message_content=InputTextMessageContent(
                message_text=caption
            )
        )

async def handle_inline_query(client, inline_query: InlineQuery):
    import re
    query = inline_query.query.strip()
    m = re.match(r'^collection:(\d+)[ :]*(.*)$', query)
    if not m:
        await inline_query.answer([], cache_time=1)
        return

    user_id = int(m.group(1))
    search_str = m.group(2).strip() if m.group(2) else ''
    try:
        offset = int(inline_query.offset) if inline_query.offset else 0
    except ValueError:
        offset = 0

    db = get_database()
    user_data = await db.get_user(user_id)
    if not user_data or not user_data.get('characters'):
        await inline_query.answer([
            InlineQueryResultArticle(
                id="no_results",
                title="No results found",
                description="You have no characters.",
                input_message_content=InputTextMessageContent(
                    message_text="No results found."
                )
            )
        ], cache_time=1)
        return

    # Deduplicate and count characters
    char_ids = user_data['characters']
    char_counts = Counter(char_ids)
    # Batch fetch all character details
    char_docs = await batch_fetch_characters(db, list(char_counts.keys()), batch_size=500)
    id_to_char = {c['character_id']: c for c in char_docs}
    collection = []
    for char_id, count in char_counts.items():
        char = id_to_char.get(char_id)
        if char:
            char = dict(char)  # copy
            char['count'] = count
            collection.append(char)

    user_name = user_data.get('first_name', 'User')
    # Filter by search string
    if search_str:
        s = search_str.lower()
        filtered = [c for c in collection if s in c['name'].lower() or s in c['rarity'].lower()]
    else:
        filtered = collection

    # Pagination
    items_per_page = 50
    start_idx = offset
    end_idx = min(start_idx + items_per_page, len(filtered))
    results = []
    for char in filtered[start_idx:end_idx]:
        rarity_emoji = RARITY_DATA.get(char['rarity'], {}).get('emoji', '⭐')
        count_display = f" [x{char['count']}]" if char.get('count', 1) > 1 else ""
        # Format the type with emojis
        pokemon_type = char.get('type', 'Unknown')
        formatted_type = format_pokemon_type(pokemon_type)
        
        caption = (
            f"<b>{user_name}'s {char['rarity']} Collect</b>\n\n"
            f"👤<b>Name</b>: {char['name']}{count_display}\n"
            f"{rarity_emoji}<b>Rarity</b>:  {char['rarity']} \n"
            f"<b>⛩ Region</b>: {char['anime']}\n\n"
            f"<b>{formatted_type}</b>\n"
            f"🔖<b>ID</b>: {char['character_id']}"
        )
        title = f"{char['name']} ({char['rarity']})"
        description = f"ID: {char['character_id']}"
        if char.get('img_url'):
            if char.get('is_video', False):
                results.append(
                    InlineQueryResultVideo(
                        id=str(char['character_id']),
                        video_url=char['img_url'],
                        thumb_url=char['img_url'],
                        mime_type='video/mp4',
                        title=title,
                        description=description,
                        caption=caption
                    )
                )
            else:
                results.append(
                    InlineQueryResultPhoto(
                        id=str(char['character_id']),
                        photo_url=char['img_url'],
                        thumb_url=char['img_url'],
                        title=title,
                        description=description,
                        caption=caption
                    )
                )
        else:
            results.append(
                InlineQueryResultArticle(
                    id=str(char['character_id']),
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=caption
                    )
                )
            )

    next_offset = str(end_idx) if end_idx < len(filtered) else ""
    if not results:
        results.append(InlineQueryResultArticle(
            id="no_results",
            title="No results found",
            description="Try searching by name or rarity.",
            input_message_content=InputTextMessageContent(
                message_text="No results found."
            )
        ))
    await inline_query.answer(results, cache_time=1, next_offset=next_offset)
