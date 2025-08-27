from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineQueryResultPhoto, InlineQueryResultVideo
import os

# Import database based on configuration
from modules.postgres_database import get_database, RARITIES, RARITY_EMOJIS, get_rarity_display
import re
from bson import ObjectId

RESULTS_LIMIT = 50  # Telegram's maximum per page

def create_inline_result(character):
    rarity = character.get('rarity', 'Unknown')
    rarity_emoji = RARITY_EMOJIS.get(rarity, "❓")
    name = character.get('name', 'Unknown')
    char_id = character.get('character_id', 'N/A')
    anime = character.get('anime', 'Unknown')
    caption = (
        f"<b>👤 Name: {name}</b>\n"
        f"{rarity_emoji}<b>Rarity: {rarity}</b>\n"
        f"🎥<b>Anime: {anime}</b>\n\n"
        f"🆔<b>ID: {char_id}</b>"
    )
    title = f"{rarity_emoji} {name}"
    description = f"🆔 {char_id} | {rarity}"
    char_id_str = str(character.get('character_id', 'no_id'))
    if character.get('img_url'):
        if character.get('is_video', False):
            return InlineQueryResultVideo(
                id=char_id_str,
                video_url=character['img_url'],
                thumb_url=character['img_url'],
                mime_type='video/mp4',
                title=title,
                description=description,
                caption=caption
            )
        else:
            return InlineQueryResultPhoto(
                id=char_id_str,
                photo_url=character['img_url'],
                thumb_url=character['img_url'],
                title=title,
                description=description,
                caption=caption
            )
    else:
        return InlineQueryResultArticle(
            id=char_id_str,
            title=title,
            description=description,
            input_message_content=InputTextMessageContent(
                message_text=caption
            )
        )

async def search_command(client: Client, message: Message):
    """Show search button for inline character search"""
    keyboard = [
        [InlineKeyboardButton("🔍 Search Characters", switch_inline_query_current_chat="")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    rarity_list = "\n".join([f"• {RARITY_EMOJIS[rarity]} {rarity}" for rarity in RARITIES.keys()])
    await message.reply_text(
        "🔍 <b>Character Search</b>\n\nClick the button below to start searching!",
        reply_markup=reply_markup
    )

async def inline_query_handler(client: Client, inline_query: InlineQuery):
    db = get_database()
    query = inline_query.query.lower().strip()
    offset = inline_query.offset
    results = []
    # Parse offset
    try:
        offset = int(offset) if offset else 0
    except ValueError:
        offset = 0
    
    # If no query, show all characters sorted by ID
    if not query:
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                # Get total count
                count_result = await conn.fetchrow("SELECT COUNT(*) FROM characters")
                total_count = count_result[0] if count_result else 0
                
                # Get characters for current page
                characters = await conn.fetch(
                    "SELECT * FROM characters ORDER BY character_id LIMIT $1 OFFSET $2",
                    RESULTS_LIMIT, offset
                )
                for character in characters:
                    results.append(create_inline_result(character))
        else:  # MongoDB
            cursor = db.characters.find().sort("character_id", 1)
            if offset > 0:
                cursor = cursor.skip(offset)
            cursor = cursor.limit(RESULTS_LIMIT)
            async for character in cursor:
                results.append(create_inline_result(character))
            total_count = await db.characters.count_documents({})
        
        next_offset = str(offset + RESULTS_LIMIT) if offset + RESULTS_LIMIT < total_count else ""
        if not results:
            results.append(InlineQueryResultArticle(
                id="no_results",
                title="No results found",
                description="Try searching by name, ID, rarity, or anime.",
                input_message_content=InputTextMessageContent(
                    message_text="<b>No results found.</b>"
                )
            ))
        await inline_query.answer(results, cache_time=1, next_offset=next_offset)
        return
    
    # Try to parse as ID
    try:
        char_id = int(query)
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                character = await conn.fetchrow("SELECT * FROM characters WHERE character_id = $1", char_id)
        else:  # MongoDB
            character = await db.characters.find_one({"character_id": char_id})
        
        if character:
            results.append(create_inline_result(character))
            await inline_query.answer(results, cache_time=1)
            return
    except ValueError:
        pass

    # If query exactly matches an anime title, prioritize returning that anime's full character list
    anime_exact_match = False
    if hasattr(db, 'pool'):  # PostgreSQL
        async with db.pool.acquire() as conn:
            count_row = await conn.fetchrow(
                "SELECT COUNT(*) FROM characters WHERE LOWER(anime) = $1",
                query
            )
            total_count = count_row[0] if count_row else 0
            anime_exact_match = total_count > 0
            if anime_exact_match:
                characters = await conn.fetch(
                    "SELECT * FROM characters WHERE LOWER(anime) = $1 ORDER BY character_id LIMIT $2 OFFSET $3",
                    query, RESULTS_LIMIT, offset
                )
                for character in characters:
                    results.append(create_inline_result(character))
                next_offset = str(offset + RESULTS_LIMIT) if offset + RESULTS_LIMIT < total_count else ""
                if not results:
                    results.append(InlineQueryResultArticle(
                        id="no_results",
                        title="No results found",
                        description="Try searching by name, ID, rarity, or anime.",
                        input_message_content=InputTextMessageContent(
                            message_text="<b>No results found.</b>"
                        )
                    ))
                await inline_query.answer(results, cache_time=1, next_offset=next_offset)
                return
    else:  # MongoDB
        # Exact case-insensitive match for anime
        anime_exact_query = {"anime": {"$regex": f"^{re.escape(query)}$", "$options": "i"}}
        total_count = await db.characters.count_documents(anime_exact_query)
        anime_exact_match = total_count > 0
        if anime_exact_match:
            cursor = db.characters.find(anime_exact_query).sort("character_id", 1)
            if offset > 0:
                cursor = cursor.skip(offset)
            cursor = cursor.limit(RESULTS_LIMIT)
            async for character in cursor:
                results.append(create_inline_result(character))
            next_offset = str(offset + RESULTS_LIMIT) if offset + RESULTS_LIMIT < total_count else ""
            if not results:
                results.append(InlineQueryResultArticle(
                    id="no_results",
                    title="No results found",
                    description="Try searching by name, ID, rarity, or anime.",
                    input_message_content=InputTextMessageContent(
                        message_text="<b>No results found.</b>"
                    )
                ))
            await inline_query.answer(results, cache_time=1, next_offset=next_offset)
            return
    
    # Search by name
    if hasattr(db, 'pool'):  # PostgreSQL
        async with db.pool.acquire() as conn:
            # Search by name
            characters = await conn.fetch(
                "SELECT * FROM characters WHERE LOWER(name) LIKE $1 ORDER BY rarity DESC LIMIT $2 OFFSET $3",
                f"%{query}%", RESULTS_LIMIT, offset
            )
            for character in characters:
                results.append(create_inline_result(character))
            
            # Get total count for name search
            count_result = await conn.fetchrow(
                "SELECT COUNT(*) FROM characters WHERE LOWER(name) LIKE $1",
                f"%{query}%"
            )
            total_count = count_result[0] if count_result else 0
            
            # If no results, try by rarity
            if not results:
                for rarity in RARITIES.keys():
                    if rarity.lower().startswith(query):
                        characters = await conn.fetch(
                            "SELECT * FROM characters WHERE rarity = $1 ORDER BY character_id LIMIT $2 OFFSET $3",
                            rarity, RESULTS_LIMIT, offset
                        )
                        for character in characters:
                            results.append(create_inline_result(character))
                        
                        count_result = await conn.fetchrow(
                            "SELECT COUNT(*) FROM characters WHERE rarity = $1",
                            rarity
                        )
                        total_count = count_result[0] if count_result else 0
                        break
            
            # If still no results, try by anime
            if not results:
                characters = await conn.fetch(
                    "SELECT * FROM characters WHERE LOWER(anime) LIKE $1 ORDER BY character_id LIMIT $2 OFFSET $3",
                    f"%{query}%", RESULTS_LIMIT, offset
                )
                for character in characters:
                    results.append(create_inline_result(character))
                
                count_result = await conn.fetchrow(
                    "SELECT COUNT(*) FROM characters WHERE LOWER(anime) LIKE $1",
                    f"%{query}%"
                )
                total_count = count_result[0] if count_result else 0
    else:  # MongoDB
        name_query = {"name": {"$regex": query, "$options": "i"}}
        cursor = db.characters.find(name_query).sort("rarity", -1)
        if offset > 0:
            cursor = cursor.skip(offset)
        cursor = cursor.limit(RESULTS_LIMIT)
        async for character in cursor:
            results.append(create_inline_result(character))
        total_count = await db.characters.count_documents(name_query)
        
        # If no results, try by rarity
        if not results:
            for rarity in RARITIES.keys():
                if rarity.lower().startswith(query):
                    rarity_query = {"rarity": rarity}
                    cursor = db.characters.find(rarity_query).sort("character_id", 1)
                    if offset > 0:
                        cursor = cursor.skip(offset)
                    cursor = cursor.limit(RESULTS_LIMIT)
                    async for character in cursor:
                        results.append(create_inline_result(character))
                    total_count = await db.characters.count_documents(rarity_query)
                    break
        
        # If still no results, try by anime
        if not results:
            anime_query = {"anime": {"$regex": query, "$options": "i"}}
            cursor = db.characters.find(anime_query).sort("character_id", 1)
            if offset > 0:
                cursor = cursor.skip(offset)
            cursor = cursor.limit(RESULTS_LIMIT)
            async for character in cursor:
                results.append(create_inline_result(character))
            total_count = await db.characters.count_documents(anime_query)
    
    # Ensure we don't exceed Telegram's limit
    results = results[:RESULTS_LIMIT]
    next_offset = str(offset + RESULTS_LIMIT) if offset + RESULTS_LIMIT < total_count else ""
    
    if not results:
        results.append(InlineQueryResultArticle(
            id="no_results",
            title="No results found",
            description="Try searching by name, ID, rarity, or anime.",
            input_message_content=InputTextMessageContent(
                message_text="<b>No results found.</b>"
            )
        ))
    await inline_query.answer(results, cache_time=1, next_offset=next_offset)
