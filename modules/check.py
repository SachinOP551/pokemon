from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from .decorators import check_banned
from .logging_utils import LOG_CHANNEL_ID
import os

# Import database based on configuration
from modules.postgres_database import get_database

# Rarity emoji mapping
RARITY_EMOJIS = {
    "Common": "⚪️",
    "Medium": "🟢",
    "Rare": "🟠",
    "Legendary": "🟡",
    "Exclusive": "🫧",
    "Elite": "💎",
    "Limited Edition": "🔮",
    "Erotic": "🔞",
    "Ultimate": "🔱",
    "Supreme": "👑",
    "Zenith": "💫",
    "Ethereal": "❄️",
    "Mythic": "🔴",
    "Premium": "🧿"
}

async def check_command(client: Client, message: Message):
    """Check character details and collectors"""
    try:
        # Check if character ID is provided
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text(
                "<b>❌ Please provide a character ID!\n"
                "Usage: /check <character_id></b>"
            )
            return

        try:
            character_id = int(args[1])
        except ValueError:
            await message.reply_text(
                "<b>❌ Invalid character ID! Please provide a number!</b>"
            )
            return

        db = get_database()
        user_id = message.from_user.id
        # Always add user to group if in a group
        if message.chat.type != "private":
            chat_id = message.chat.id
            await db.add_user_to_group(user_id, chat_id)

        # Try to find character in main collection
        character = await db.get_character(character_id)
        if not character:
            await message.reply_text(
                "<b>❌ Character not found!</b>"
            )
            return
        # Get global collector count
        global_collectors = await db.get_character_collectors(character_id)
        unique_count = len(global_collectors)
        # Create message text
        name = character.get('name', 'Unknown')
        rarity = character.get('rarity', 'Unknown')
        rarity_emoji = RARITY_EMOJIS.get(rarity, "❓")
        char_id = character.get('character_id', character_id)
        message_text = (
            f"<b>👤 Name:</b> {name}\n"
            f"<b>{rarity_emoji} Rarity:</b> {rarity}\n"
            f"<b>🎥 Anime:</b> {character.get('anime', '-') }\n"
            f"<b>🆔 ID:</b> `{char_id}`\n\n"
            f"<b>☘️ Globally Collected:</b> {unique_count} <b>Times</b>"
        )
        # Create buttons in vertical layout
        keyboard = [
            [InlineKeyboardButton("👥 Show Collectors Here", callback_data=f"collectors_here_{char_id}")],
            [InlineKeyboardButton("🏆 Show Top Collectors", callback_data=f"top_collectors_{char_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Send character media with details
        if character.get('is_video', False):
            await message.reply_video(
                video=character['img_url'],
                caption=message_text,
                reply_markup=reply_markup
            )
        else:
            # Use img_url if available, fallback to file_id
            photo = character.get('img_url', character['file_id'])
            await message.reply_photo(
                photo=photo,
                caption=message_text,
                reply_markup=reply_markup
            )
    except Exception as e:
        print(f"Error in check command: {e}")
        await message.reply_text(
            "❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ!"
        )

async def collectors_here_callback(client: Client, callback_query: CallbackQuery):
    """Show collectors in current group"""
    try:
        await callback_query.answer()
        character_id = int(callback_query.data.split('_')[-1])
        chat_id = callback_query.message.chat.id
        db = get_database()
        # Get collectors in current group
        collectors = await db.get_group_collectors(chat_id, character_id)
        # Patch: Ensure all these users have this group in their groups field
        for collector in collectors:
            await db.add_user_to_group(collector['user_id'], chat_id)
        if not collectors:
            await callback_query.message.edit_caption(
                caption="<b>👥 No Collectors Here!</b>"
            )
            return
        # Calculate group stats
        unique_count = len(collectors)
        total_count = sum(collector['count'] for collector in collectors)
        # Format collectors list
        collectors_text = (
            f"<b>👥 Collectors Here:</b>\n"
        )
        for i, collector in enumerate(collectors, 1):
            name = collector['name']
            username = collector.get('username', '')
            count = collector['count']
            if username:
                collectors_text += f"{i}. [{name}](https://t.me/{username}) (x{count})\n"
            else:
                collectors_text += f"{i}. {name} (x{count})\n"
        await callback_query.message.edit_caption(
            caption=collectors_text
        )
    except Exception as e:
        print(f"Error in collectors_here_callback: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def top_collectors_callback(client: Client, callback_query: CallbackQuery):
    """Handle top collectors callback"""
    await callback_query.answer()
    
    try:
        # Extract character ID from callback data
        char_id = int(callback_query.data.split('_')[2])
        db = get_database()
        
        # Get character details
        character = await db.get_character(char_id)
        if not character:
            await callback_query.message.edit_caption(
                caption="<b>❌ Character Not Found!</b>"
            )
            return
        
        # Get top collectors
        top_collectors = await db.get_top_collectors(str(char_id), limit=10)
        
        if not top_collectors:
            await callback_query.message.edit_caption(
                caption="<b>❌ No Collectors Found!</b>"
            )
            return
        
        # Create message text
        name = character.get('name', 'Unknown')
        rarity = character.get('rarity', 'Unknown')
        rarity_emoji = RARITY_EMOJIS.get(rarity, "❓")
        
        message_text = (
            f"<b>🏆 Top Collectors For:</b>\n"
            f"<b>👤 Name:</b> {name}\n"
            f"<b>{rarity_emoji} Rarity:</b> {rarity}\n\n"
        )
        
        for i, collector in enumerate(top_collectors, 1):
            name = collector['name']
            username = collector.get('username', '')
            count = collector['count']
            if username:
                message_text += f"{i}. [{name}](https://t.me/{username}) (x{count})\n"
            else:
                message_text += f"{i}. {name} (x{count})\n"
        
        await callback_query.message.edit_caption(
            caption=message_text
        )

    except Exception as e:
        print(f"Error in top_collectors_callback: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def back_to_character_callback(client: Client, callback_query: CallbackQuery):
    """Handle back to character callback"""
    await callback_query.answer()
    
    try:
        # Extract character ID from callback data
        char_id = int(callback_query.data.split('_')[-1])
        db = get_database()
        
        # Get character details
        character = await db.get_character(char_id)
        if not character:
            await callback_query.message.edit_caption(
                caption="<b>❌ Character Not Found!</b>"
            )
            return
        
        # Get global collector count
        global_collectors = await db.get_character_collectors(char_id)
        unique_count = len(global_collectors)

        # Create message text
        name = character.get('name', 'Unknown')
        rarity = character.get('rarity', 'Unknown')
        rarity_emoji = RARITY_EMOJIS.get(rarity, "❓")
        
        message_text = (
            f"<b>👤 Name:</b> {name}\n"
            f"<b>{rarity_emoji} Rarity:</b> {rarity}\n"
            f"<b>🎥 Anime:</b> {character.get('anime', '-') }\n"
            f"<b>🆔 ID:</b> `{char_id}`\n"
            f"<b>☘️ Globally Collected:</b> {unique_count} <b>Times</b>"
        )

        # Create buttons
        keyboard = [
            [InlineKeyboardButton("👥 Show Collectors Here", callback_data=f"collectors_here_{char_id}")],
            [InlineKeyboardButton("🏆 Show Top Collectors", callback_data=f"top_collectors_{char_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await callback_query.message.edit_caption(
            caption=message_text,
            reply_markup=reply_markup
        )

    except Exception as e:
        print(f"Error in back_to_character_callback: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

def setup_check_handlers(app: Client):
    """Setup handlers for check module"""
    print("Registering check command handler...")
    app.on_message(filters.command("check"))(check_command)
    print("Registering check callback handlers...")
    app.on_callback_query(filters.regex(r"^collectors_here_\d+$"))(collectors_here_callback)
    app.on_callback_query(filters.regex(r"^top_collectors_\d+$"))(top_collectors_callback)
    app.on_callback_query(filters.regex(r"^back_to_character_\d+$"))(back_to_character_callback)
    print("All check handlers registered successfully!")
