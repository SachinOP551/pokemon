import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaVideo,
    Message,
)

from modules.postgres_database import (
    RARITIES,
    RARITY_EMOJIS,
    get_database,
    get_rarity_display,
    get_rarity_emoji,
)

from .decorators import check_banned


# Constants
ITEMS_PER_PAGE = 5

temp_data = {}

@check_banned
async def vidcollection_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    try:
        # Get user data
        user_data = await db.users.find_one({"user_id": user_id}, {"user_id": 1})
        if not user_data:
            await message.reply_text("❌ You are not registered!")
            return
        # Get user's collection
        collection = await db.get_user_collection(user_id)
        # Filter for video characters only
        video_collection = [char for char in collection if char.get('is_video', False)]
        if not video_collection:
            await message.reply_text("❌ You don't have any video characters in your collection!")
            return
        # Store collection data for pagination
        temp_data[user_id] = {
            'collection': video_collection,
            'current_index': 0
        }
        # Send first video
        await send_video_message(client, message, user_id, 0)
    except Exception as e:
        print(f"Error in vidcollection command: {e}")
        await message.reply_text("❌ An error occurred!")

async def send_video_message(client: Client, message: Message, user_id: int, index: int):
    try:
        collection = temp_data[user_id]['collection']
        character = collection[index]
        total_chars = len(collection)
        current_page = index + 1
        # Create caption
        caption = (
            f"<b>{message.from_user.first_name}'s Video Character Collection</b>\n"
            f"<b>Page {current_page} of {total_chars}</b>\n\n"
            f"<b>👤 Name:</b> {character['name']}\n"
            f"{get_rarity_emoji(character['rarity'])} <b>Rarity:</b> {character['rarity']}\n"
            f"<b>🆔 ID:</b> <code>{character['character_id']}</code>\n"
            f"<b>📥 Count:</b> x{character['count']}"
        )
        # Create navigation keyboard
        keyboard = []
        nav_buttons = []
        # Previous button
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data="vid_prev"))
        # Next button
        if index < total_chars - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="vid_next"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        # Close button
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="vid_close")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send video with caption and buttons
        await message.reply_video(
            video=character['img_url'],
            caption=caption,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error sending video message: {e}")
        await message.reply_text("❌ An error occurred!")

async def handle_vidcollection_pagination(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in temp_data:
        await callback_query.edit_message_text("❌ Collection view expired! Please use /vidcollection again!")
        return
    action = callback_query.data.split('_')[1]
    current_index = temp_data[user_id]['current_index']
    total_chars = len(temp_data[user_id]['collection'])
    if action == 'close':
        await callback_query.answer()
        await callback_query.message.delete()
        del temp_data[user_id]
        return
    # Update index based on action
    if action == 'prev' and current_index > 0:
        current_index -= 1
    elif action == 'next' and current_index < total_chars - 1:
        current_index += 1
    # Update stored index
    temp_data[user_id]['current_index'] = current_index
    # Edit the current message instead of deleting and sending a new one
    collection = temp_data[user_id]['collection']
    character = collection[current_index]
    caption = (
        f"<b>{callback_query.from_user.first_name}'s Video Character Collection</b>\n"
        f"<b>Page {current_index + 1} of {total_chars}</b>\n\n"
        f"<b>👤 Name:</b> {character['name']}\n"
        f"{get_rarity_emoji(character['rarity'])} <b>Rarity:</b> {character['rarity']}\n"
        f"<b>🆔 ID:</b> <code>{character['character_id']}</code>\n"
        f"<b>📥 Count:</b> x{character['count']}"
    )
    # Create navigation keyboard
    keyboard = []
    nav_buttons = []
    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data="vid_prev"))
    if current_index < total_chars - 1:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="vid_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="vid_close")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    # Edit the video and caption
    try:
        await callback_query.edit_message_media(
            media=InputMediaVideo(
                media=character['img_url'],
                caption=caption
            ),
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error editing video message: {e}")
        await callback_query.edit_message_caption("❌ An error occurred!")

global_vidlist_data = {}

async def vidlist_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    try:
        # Get all video characters from the database
        if hasattr(db, 'pool'):  # PostgreSQL
            async with db.pool.acquire() as conn:
                video_chars_result = await conn.fetch("SELECT * FROM characters WHERE is_video = TRUE")
                video_chars = [dict(char) for char in video_chars_result]
        else:  # MongoDB
            video_chars = await db.characters.find({'is_video': True}).to_list(length=None)
        
        if not video_chars:
            await message.reply_text("❌ No video characters found in the database!")
            return
        # Sort by name for consistency
        video_chars = sorted(video_chars, key=lambda c: c.get('name', ''))
        global_vidlist_data[user_id] = {
            'video_chars': video_chars,
            'current_index': 0
        }
        await send_vidlist_video(client, message, user_id, 0)
    except Exception as e:
        print(f"Error in vidlist_command: {e}")
        await message.reply_text("❌ An error occurred!")

async def send_vidlist_video(client: Client, message: Message, user_id: int, index: int):
    try:
        video_chars = global_vidlist_data[user_id]['video_chars']
        character = video_chars[index]
        total_chars = len(video_chars)
        current_page = index + 1
        # Get stats
        db = client.db if hasattr(client, 'db') else None
        if db is None:
            db = get_database()
        # Count total occurrences of this character in all users' collections
        pipeline = [
            {"$match": {"characters": character['character_id']}},
            {"$project": {"count": {"$size": {"$filter": {"input": "$characters", "as": "c", "cond": {"$eq": ["$$c", character['character_id']]}}}}}},
        ]
        user_counts = await db.users.aggregate(pipeline).to_list(length=None)
        global_count = sum(u['count'] for u in user_counts)
        unique_owners = await db.users.count_documents({'characters': character['character_id']})
        # Caption
        caption = (
            f"<b>Video Character List (Page {current_page}/{total_chars})</b>\n\n"
            f"<b>👤 Name:</b> {character.get('name', 'Unknown')}\n"
            f"<b>🆔 ID:</b> {character.get('character_id', 'N/A')}\n"
            f"{get_rarity_emoji(character['rarity'])} <b>Rarity:</b> {character.get('rarity', 'Unknown')}\n"
            f"<b>📊 Stats:</b>\n"
            f"- Global Count: {global_count}\n"
            f"- Unique Owners: {unique_owners}\n"
            f"📽️ Type: Video Character"
        )
        # Navigation buttons
        keyboard = []
        nav_buttons = []
        if index > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data="vidlist_prev"))
        if index < total_chars - 1:
            nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="vidlist_next"))
        if nav_buttons:
            keyboard.append(nav_buttons)
        keyboard.append([InlineKeyboardButton("❌ Close", callback_data="vidlist_close")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_video(
            video=character.get('img_url'),
            caption=caption,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error sending vidlist video: {e}")
        await message.reply_text("❌ An error occurred!")

async def handle_vidlist_pagination(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id not in global_vidlist_data:
        await callback_query.edit_message_text("❌ List view expired! Please use /vidlist again!")
        return
    action = callback_query.data.split('_')[1]
    current_index = global_vidlist_data[user_id]['current_index']
    total_chars = len(global_vidlist_data[user_id]['video_chars'])
    if action == 'close':
        await callback_query.answer()
        await callback_query.message.delete()
        del global_vidlist_data[user_id]
        return
    # Update index based on action
    if action == 'prev' and current_index > 0:
        current_index -= 1
    elif action == 'next' and current_index < total_chars - 1:
        current_index += 1
    # Update stored index
    global_vidlist_data[user_id]['current_index'] = current_index
    video_chars = global_vidlist_data[user_id]['video_chars']
    character = video_chars[current_index]
    db = client.db if hasattr(client, 'db') else None
    if db is None:
        db = get_database()
    # Count total occurrences of this character in all users' collections
    pipeline = [
        {"$match": {"characters": character['character_id']}},
        {"$project": {"count": {"$size": {"$filter": {"input": "$characters", "as": "c", "cond": {"$eq": ["$$c", character['character_id']]}}}}}},
    ]
    user_counts = await db.users.aggregate(pipeline).to_list(length=None)
    global_count = sum(u['count'] for u in user_counts)
    unique_owners = await db.users.count_documents({'characters': character['character_id']})
    caption = (
        f"<b>Video Character List (Page {current_index + 1}/{total_chars})</b>\n\n"
        f"<b>👤 Name:</b> {character.get('name', 'Unknown')}\n"
        f"<b>🆔 ID:</b> {character.get('character_id', 'N/A')}\n"
        f"{get_rarity_emoji(character['rarity'])} <b>Rarity:</b> {character.get('rarity', 'Unknown')}\n"
        f"📊 Stats:\n"
        f"- Global Count: {global_count}\n"
        f"- Unique Owners: {unique_owners}\n"
        f"📽️ Type: Video Character"
    )
    keyboard = []
    nav_buttons = []
    if current_index > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Previous", callback_data="vidlist_prev"))
    if current_index < total_chars - 1:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data="vidlist_next"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("❌ Close", callback_data="vidlist_close")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await callback_query.edit_message_media(
            media=InputMediaVideo(
                media=character.get('img_url'),
                caption=caption
            ),
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Error editing vidlist video: {e}")
        await callback_query.edit_message_caption("❌ An error occurred!")

def register_vidcollection_handlers(app: Client):
    app.add_handler(filters.command("vidcollection"), vidcollection_command)
    app.add_handler(filters.callback_query(lambda _, q: q.data.startswith("vid_")), handle_vidcollection_pagination)
    app.add_handler(filters.command("vidlist"), vidlist_command)
    app.add_handler(filters.callback_query(lambda _, q: q.data.startswith("vidlist_")), handle_vidlist_pagination) 