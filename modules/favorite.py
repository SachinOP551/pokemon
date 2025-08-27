from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from .decorators import check_banned
import os

from modules.postgres_database import get_database
from urllib.parse import urlparse

# Session storage for favorite confirmation
_temp_data = {}

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

@check_banned
async def favorite_command(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴛʜᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ ᴛᴏ sᴇᴛ ᴀs ғᴀᴠᴏʀɪᴛᴇ!</b>"
        )
        return
    
    # Check if the argument is a valid integer
    try:
        character_id = int(args[1])
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀ ғᴏʀ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ!</b>"
        )
        return
    
    try:
        db = get_database()
        user_id = message.from_user.id
        character = await db.get_character(character_id)
        user_data = await db.get_user(user_id)
        
        if not character:
            await message.reply_text(
                "<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!</b>"
            )
            return
        
        if character_id not in user_data.get('characters', []):
            await message.reply_text(
                "<b>❌ ʏᴏᴜ ᴅᴏɴ'ᴛ ᴏᴡɴ ᴛʜɪs ᴄʜᴀʀᴀᴄᴛᴇʀ!</b>"
            )
            return
        
        _temp_data[user_id] = character_id
        keyboard = [
            [
                InlineKeyboardButton("✅ ᴄᴏɴғɪʀᴍ", callback_data="fav_confirm"),
                InlineKeyboardButton("❌ ᴄᴀɴᴄᴇʟ", callback_data="fav_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        caption = (
            f"<b>ᴅᴏ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ sᴇᴛ {character['name']} "
            "ᴀs ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ?</b>"
        )
        
        if character.get('is_video', False):
            # For video characters, prefer img_url (Cloudinary URL) over file_id
            video_source = character.get('img_url') or character.get('file_id')
            try:
                await message.reply_video(
                    video=video_source,
                    caption=caption,
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"Error sending video in favorite command: {e}")
                # Fallback to text message
                await message.reply_text(
                    caption,
                    reply_markup=reply_markup
                )
        else:
            photo = character.get('img_url', character['file_id'])
            try:
                await message.reply_photo(
                    photo=photo,
                    caption=caption,
                    reply_markup=reply_markup
                )
            except Exception as e:
                print(f"Error sending photo in favorite command: {e}")
                # Fallback to text message
                await message.reply_text(
                    caption,
                    reply_markup=reply_markup
                )
    except Exception as e:
        print(f"Error in favorite_command: {e}")
        await message.reply_text(
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ sᴇᴛᴛɪɴɢ ғᴀᴠᴏʀɪᴛᴇ!</b>"
        )

async def handle_favorite_callback(client: Client, callback_query: CallbackQuery):
    await callback_query.answer()
    user_id = callback_query.from_user.id
    if user_id not in _temp_data:
        await callback_query.edit_message_caption(
            "<b>❌ sᴇssɪᴏɴ ᴇxᴘɪʀᴇᴅ! ᴘʟᴇᴀsᴇ ᴛʀʏ ᴀɢᴀɪɴ!</b>"
        )
        return
    if callback_query.data == "fav_cancel":
        await callback_query.edit_message_caption(
            "<b>❌ ᴏᴘᴇʀᴀᴛɪᴏɴ ᴄᴀɴᴄᴇʟʟᴇᴅ!</b>"
        )
        del _temp_data[user_id]
        return
    if callback_query.data == "fav_confirm":
        character_id = _temp_data[user_id]
        db = get_database()
        await db.set_favorite_character(user_id, character_id)
        character = await db.get_character(character_id)
        await callback_query.edit_message_caption(
            f"<b>✨ {character['name']} "
            "ʜᴀs ʙᴇᴇɴ sᴇᴛ ᴀs ʏᴏᴜʀ ғᴀᴠᴏʀɪᴛᴇ ᴄʜᴀʀᴀᴄᴛᴇʀ! 🎉</b>"
        )
        del _temp_data[user_id]

def setup_favorite_handlers(app: Client):
    app.add_handler(filters.command("fav")(favorite_command))
    app.add_handler(filters.callback_query(lambda _, __, query: query.data and query.data.startswith("fav_"))(handle_favorite_callback))