from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from modules.postgres_database import get_database
import logging

logger = logging.getLogger(__name__)

# Constants for pagination
ITEMS_PER_PAGE = 10  # Reduced for better column display

def _get_initiator_user_id(callback_query: CallbackQuery):
    """Return the user id of the original initiator if available, else None."""
    try:
        if callback_query and callback_query.message and callback_query.message.reply_to_message and callback_query.message.reply_to_message.from_user:
            return callback_query.message.reply_to_message.from_user.id
    except Exception:
        pass
    return None

def _is_authorized(callback_query: CallbackQuery) -> bool:
    """Authorize if initiator unknown, or the clicker matches the initiator."""
    initiator_id = _get_initiator_user_id(callback_query)
    return initiator_id is None or callback_query.from_user.id == initiator_id

def create_letters_keyboard() -> InlineKeyboardMarkup:
    """Build the letters/numbers/specials keyboard grid."""
    # First row: Numbers 0-4
    row1 = [InlineKeyboardButton(str(i), callback_data=f"canime_letter_{i}") for i in range(5)]
    # Second row: Numbers 5-9
    row2 = [InlineKeyboardButton(str(i), callback_data=f"canime_letter_{i}") for i in range(5, 10)]
    # Third row: Letters A-E
    row3 = [InlineKeyboardButton(chr(65 + i), callback_data=f"canime_letter_{chr(65 + i)}") for i in range(5)]
    # Fourth row: Letters F-J
    row4 = [InlineKeyboardButton(chr(70 + i), callback_data=f"canime_letter_{chr(70 + i)}") for i in range(5)]
    # Fifth row: Letters K-O
    row5 = [InlineKeyboardButton(chr(75 + i), callback_data=f"canime_letter_{chr(75 + i)}") for i in range(5)]
    # Sixth row: Letters P-T
    row6 = [InlineKeyboardButton(chr(80 + i), callback_data=f"canime_letter_{chr(80 + i)}") for i in range(5)]
    # Seventh row: Letters U-Z
    row7 = [InlineKeyboardButton(chr(85 + i), callback_data=f"canime_letter_{chr(85 + i)}") for i in range(6)]
    # Eighth row: Special characters
    row8 = [
        InlineKeyboardButton("-", callback_data="canime_letter_dash"),
        InlineKeyboardButton(".", callback_data="canime_letter_dot"),
        InlineKeyboardButton("'", callback_data="canime_letter_apostrophe"),
        InlineKeyboardButton(" ", callback_data="canime_letter_space"),
    ]
    keyboard = [row1, row2, row3, row4, row5, row6, row7, row8]
    return InlineKeyboardMarkup(keyboard)

async def canime_command(client: Client, message: Message):
    """Show a grid of letters/numbers to choose from for anime search"""
    reply_markup = create_letters_keyboard()
    
    await message.reply_text(
        "🔤 <b>Choose a letter to browse region:</b>\n\n",
        reply_markup=reply_markup
    )

async def handle_canime_letter_callback(client: Client, callback_query: CallbackQuery):
    """Handle letter selection and show anime names"""
    try:
        # Authorize user; allow if initiator unknown
        if not _is_authorized(callback_query):
            await callback_query.answer("❌ Access denied! Only the user who initiated this command can use it.", show_alert=True)
            return
        
        letter = callback_query.data.split("_")[-1]
        
        # Handle special characters
        if letter == "space":
            letter = " "
        elif letter == "dash":
            letter = "-"
        elif letter == "dot":
            letter = "."
        elif letter == "apostrophe":
            letter = "'"
        elif letter == "0":
            # For 0, show anime names that start with numbers
            letter = "0-9"
        
        # Get anime names starting with the selected letter
        db = get_database()
        anime_names = await get_anime_names_by_letter(db, letter)
        
        if not anime_names:
            await callback_query.answer("No anime found starting with this character!")
            return
        
        # Create anime buttons (paginated) - start with page 0
        keyboard = create_anime_keyboard(anime_names, 0, letter)
        
        # Update the message
        await callback_query.message.edit_text(
            f"ℹ️ <b>CHOOSE A REGION TO SEE ITS ALL POKEMON:</b>\n\n",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in canime letter callback: {e}")
        await callback_query.answer("An error occurred!")

async def handle_canime_anime_callback(client: Client, callback_query: CallbackQuery):
    """Handle anime selection and show inline query button"""
    try:
        # Authorize user; allow if initiator unknown
        if not _is_authorized(callback_query):
            await callback_query.answer("❌ Access denied! Only the user who initiated this command can use it.", show_alert=True)
            return
        
        # Extract anime name from callback data
        # Format: canime_anime_AnimeName
        parts = callback_query.data.split("_", 2)
        if len(parts) < 3:
            await callback_query.answer("Invalid callback data!")
            return
        
        anime_name = parts[2]
        
        # Get bot username for the search query
        bot_username = (await client.get_me()).username
        
        # Create inline query button for character search
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"{anime_name} list",
                switch_inline_query_current_chat=f"{anime_name}"
            )],
            [InlineKeyboardButton("🔙 Back to Letters", callback_data="canime_back_to_letters")]
        ])
        
        # Update the message
        await callback_query.message.edit_text(
            f"❄️ <b>GO INLINE AND SEE ALL POKEMON OF {anime_name}</b>\n\n",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in canime anime callback: {e}")
        await callback_query.answer("An error occurred!")

async def handle_canime_navigation_callback(client: Client, callback_query: CallbackQuery):
    """Handle navigation (previous/next) for anime lists"""
    try:
        # Authorize user; allow if initiator unknown
        if not _is_authorized(callback_query):
            await callback_query.answer("❌ Access denied! Only the user who initiated this command can use it.", show_alert=True)
            return
        
        data = callback_query.data
        if data == "canime_back_to_letters":
            # Go back to the letter selection grid in-place
            keyboard = create_letters_keyboard()
            await callback_query.message.edit_text(
                "🔤 <b>Choose a letter to browse region:</b>\n\n",
                reply_markup=keyboard
            )
            
    except Exception as e:
        logger.error(f"Error in canime navigation callback: {e}")
        await callback_query.answer("An error occurred!")

async def get_anime_names_by_letter(db, letter):
    """Get anime names starting with a specific letter"""
    try:
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                if letter == "0-9":
                    # For numbers, get anime names starting with digits
                    result = await conn.fetch(
                        "SELECT DISTINCT anime FROM characters WHERE anime ~ '^[0-9]' ORDER BY anime"
                    )
                else:
                    # For letters and special characters
                    result = await conn.fetch(
                        "SELECT DISTINCT anime FROM characters WHERE anime ILIKE $1 ORDER BY anime",
                        f"{letter}%"
                    )
                return [row['anime'] for row in result]
        else:  # MongoDB
            if letter == "0-9":
                # For numbers, get anime names starting with digits
                pipeline = [
                    {"$match": {"anime": {"$regex": "^[0-9]", "$options": "i"}}},
                    {"$group": {"_id": "$anime"}},
                    {"$sort": {"_id": 1}}
                ]
            else:
                # For letters and special characters
                pipeline = [
                    {"$match": {"anime": {"$regex": f"^{letter}", "$options": "i"}}},
                    {"$group": {"_id": "$anime"}},
                    {"$sort": {"_id": 1}}
                ]
            
            cursor = db.characters.aggregate(pipeline)
            return [doc['_id'] async for doc in cursor]
            
    except Exception as e:
        logger.error(f"Error getting anime names by letter: {e}")
        return []

def create_anime_keyboard(anime_names, page, letter):
    """Create keyboard for anime selection with pagination - one anime per row"""
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_anime = anime_names[start_idx:end_idx]
    
    keyboard = []
    
    # Create anime buttons (one per row for column display)
    for anime_name in page_anime:
        # Truncate long anime names for button text
        button_text = anime_name[:30] + "..." if len(anime_name) > 30 else anime_name
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"canime_anime_{anime_name}"
        )])
    
    # Navigation buttons
    nav_row = []
    if page > 0:
        # Handle special characters in callback data
        safe_letter = letter.replace(" ", "space").replace("-", "dash").replace(".", "dot").replace("'", "apostrophe")
        if letter == "0-9":
            safe_letter = "0"
        nav_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"canime_page_{page-1}_{safe_letter}"))
    
    if end_idx < len(anime_names):
        # Handle special characters in callback data
        safe_letter = letter.replace(" ", "space").replace("-", "dash").replace(".", "dot").replace("'", "apostrophe")
        if letter == "0-9":
            safe_letter = "0"
        nav_row.append(InlineKeyboardButton("➡️ Next", callback_data=f"canime_page_{page+1}_{safe_letter}"))
    
    if nav_row:
        keyboard.append(nav_row)
    
    # Back button
    keyboard.append([InlineKeyboardButton("🔙 Back to Letters", callback_data="canime_back_to_letters")])
    
    return InlineKeyboardMarkup(keyboard)

async def handle_canime_page_callback(client: Client, callback_query: CallbackQuery):
    """Handle page navigation for anime lists"""
    try:
        # Authorize user; allow if initiator unknown
        if not _is_authorized(callback_query):
            await callback_query.answer("❌ Access denied! Only the user who initiated this command can use it.", show_alert=True)
            return
        
        # Format: canime_page_pageNumber_letter
        data = callback_query.data.split("_")
        if len(data) < 4:
            await callback_query.answer("Invalid callback data!")
            return
        
        page = int(data[2])
        letter = data[3]
        
        # Handle special characters
        if letter == "space":
            letter = " "
        elif letter == "dash":
            letter = "-"
        elif letter == "dot":
            letter = "."
        elif letter == "apostrophe":
            letter = "'"
        elif letter == "0":
            letter = "0-9"
        
        # Get anime names for the selected letter
        db = get_database()
        anime_names = await get_anime_names_by_letter(db, letter)
        
        if not anime_names:
            await callback_query.answer("No anime found!")
            return
        
        # Create keyboard for the selected page
        keyboard = create_anime_keyboard(anime_names, page, letter)
        
        # Calculate total pages
        total_pages = (len(anime_names) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        # Update the message
        await callback_query.message.edit_text(
            f"ℹ️ <b>CHOOSE A REGION TO SEE ITS ALL POKEMON:</b>\n\n",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Error in canime page callback: {e}")
        await callback_query.answer("An error occurred!")

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler

def register_canime_handlers(app):
    """Register all canime-related callback handlers"""

    app.add_handler(CallbackQueryHandler(
        handle_canime_letter_callback,
        filters.create(lambda _, __, cq: cq.data and cq.data.startswith("canime_letter_"))
    ))

    app.add_handler(CallbackQueryHandler(
        handle_canime_anime_callback,
        filters.create(lambda _, __, cq: cq.data and cq.data.startswith("canime_anime_"))
    ))

    app.add_handler(CallbackQueryHandler(
        handle_canime_page_callback,
        filters.create(lambda _, __, cq: cq.data and cq.data.startswith("canime_page_"))
    ))

    app.add_handler(CallbackQueryHandler(
        handle_canime_navigation_callback,
        filters.create(lambda _, __, cq: cq.data in ["canime_prev", "canime_next", "canime_back_to_letters"])
    ))

