from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo
from pyrogram import Client
from modules.postgres_database import get_database
from .decorators import is_owner, is_og, is_sudo
import uuid
from datetime import datetime
from modules.logging_utils import send_character_log
from collections import Counter

RARITY_EMOJIS = {
    "Common": "⚪️", "Medium": "🟢", "Rare": "🟠", "Legendary": "🟡", "Exclusive": "🫧", "Elite": "💎",
    "Limited Edition": "🔮", "Ultimate": "🔱", "Supreme": "👑", "Mythic": "🔴", "Zenith": "💫", "Ethereal": "❄️", "Premium": "🧿"
}

PENDING_ACTIONS = {}

# --- /give ---
async def give_command(client: Client, message: Message):
    if not message.from_user or not message.reply_to_message or not message.reply_to_message.from_user:
        return
    db = get_database()
    user_id = message.from_user.id
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text("❌ <b>This command is restricted to owners and OGs only!</b>")
        return
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Please reply to a user's message!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Usage: /give &lt;character_id&gt; (reply to user)</b>")
        return
    try:
        char_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ <b>Invalid character ID!</b>")
        return
    character = await db.get_character(char_id)
    if not character:
        await message.reply_text("❌ <b>Character not found!</b>")
        return
    target_user = message.reply_to_message.from_user
    unique_id = f"give_{user_id}_{target_user.id}_{char_id}"
    PENDING_ACTIONS[unique_id] = {'type': 'give', 'admin_id': user_id, 'target_id': target_user.id, 'char_id': char_id}
    keyboard = [[
        InlineKeyboardButton("✅ Confirm", callback_data=f"give_ok_{unique_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"give_no_{unique_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    emoji = RARITY_EMOJIS.get(character['rarity'], '❓')
    caption = (
        f"❓ <b>Are you sure you want to give:</b>\n\n"
        f"👤 <b>Character:</b> {character['name']}\n"
        f"{emoji} <b>Rarity:</b> {character['rarity']}\n"
        f"🆔: <code>{char_id}</code>\n\n"
        f"📨 <b>To:</b> {target_user.mention}"
    )
    if character.get('img_url'):
        if character.get('is_video', False):
            await message.reply_video(
                video=character['img_url'],
                caption=caption,
                reply_markup=reply_markup
            )
        else:
            await message.reply_photo(
                photo=character['img_url'],
                caption=caption,
                reply_markup=reply_markup
            )
    else:
        await message.reply_text(caption, reply_markup=reply_markup)

# --- /take ---
async def take_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text("❌ <b>This command is restricted to owners and OGs only!</b>")
        return
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Please reply to a user's message!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Usage: /take &lt;character_id&gt; (reply to user)</b>")
        return
    try:
        char_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ <b>Invalid character ID!</b>")
        return
    character = await db.get_character(char_id)
    if not character:
        await message.reply_text("❌ <b>Character not found!</b>")
        return
    target_user = message.reply_to_message.from_user
    target_data = await db.get_user(target_user.id)
    if not target_data or char_id not in target_data.get('characters', []):
        await message.reply_text("❌ <b>This user doesn't have this character!</b>")
        return
    unique_id = f"take_{user_id}_{target_user.id}_{char_id}"
    PENDING_ACTIONS[unique_id] = {'type': 'take', 'admin_id': user_id, 'target_id': target_user.id, 'char_id': char_id}
    keyboard = [[
        InlineKeyboardButton("✅ Confirm", callback_data=f"take_ok_{unique_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"take_no_{unique_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    emoji = RARITY_EMOJIS.get(character['rarity'], '❓')
    caption = (
        f"❓ <b>Are you sure you want to take:</b>\n\n"
        f"👤 <b>Character:</b> {character['name']}\n"
        f"{emoji} <b>Rarity:</b> {character['rarity']}\n"
        f"🆔: <code>{char_id}</code>\n\n"
        f"📨 <b>From:</b> {target_user.mention}"
    )
    if character.get('img_url'):
        if character.get('is_video', False):
            await message.reply_video(
                video=character['img_url'],
                caption=caption,
                reply_markup=reply_markup
            )
        else:
            await message.reply_photo(
                photo=character['img_url'],
                caption=caption,
                reply_markup=reply_markup
            )
    else:
        await message.reply_text(caption, reply_markup=reply_markup)

# --- /massgive ---
async def massgive_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text("❌ <b>This command is restricted to owners and OGs only!</b>")
        return
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ <b>Usage: /massgive &lt;user_id or reply&gt; &lt;char_id1&gt; [char_id2] ...</b>")
        return
    # Get target user
    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        char_ids = args[1:]
    else:
        try:
            target_user_id = int(args[1])
            target_user = await client.get_users(target_user_id)
        except Exception:
            await message.reply_text("❌ <b>Invalid user ID!</b>")
            return
        char_ids = args[2:]
    # Validate char_ids
    char_ids_int = []
    for cid in char_ids:
        try:
            char_ids_int.append(int(cid))
        except ValueError:
            await message.reply_text(f"❌ <b>Invalid character ID: {cid}</b>")
            return
    # Get character objects
    user_data = await db.get_user(user_id)
    owned_characters = user_data.get('characters', []) if user_data else []
    owned_counts = {cid: owned_characters.count(cid) for cid in set(owned_characters)}
    # Build the list of char_ids to gift, up to the number owned for each
    requested_counts = {cid: char_ids_int.count(cid) for cid in set(char_ids_int)}
    # Remove the check for insufficient copies
    # If we reach here, all requests are valid
    characters = []
    for cid in char_ids_int:
        char = await db.get_character(cid)
        if not char:
            await message.reply_text(f"❌ <b>Character not found: {cid}</b>")
            return
        characters.append(char)
    # Build summary for confirmation message
    rarity_counter = Counter()
    for cid in char_ids_int:
        char = await db.get_character(cid)
        if not char:
            continue
        rarity = char.get('rarity', '?')
        rarity_counter[rarity] += 1
    summary_lines = []
    for rarity, count in rarity_counter.items():
        emoji = RARITY_EMOJIS.get(rarity, '?')
        summary_lines.append(f"{emoji} {rarity} x{count}")
    # Use a short unique_id for callback data
    short_id = str(uuid.uuid4())[:8]
    unique_id = f"massgive_{user_id}_{target_user.id}_{short_id}"
    PENDING_ACTIONS[unique_id] = {'type': 'massgive', 'admin_id': user_id, 'target_id': target_user.id, 'char_ids': char_ids_int}
    keyboard = [[
        InlineKeyboardButton("✅ Confirm", callback_data=f"massgive_ok_{unique_id}"),
        InlineKeyboardButton("❌ Cancel", callback_data=f"massgive_no_{unique_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    caption = (
        f"❓ <b>Are you sure you want to give</b> <b>{len(char_ids_int)}</b> <b>characters to {target_user.mention}?</b>\n\n"
        + '\n'.join(summary_lines) +
        "\n\nThis action cannot be undone."
    )
    await message.reply_text(caption, reply_markup=reply_markup)

# --- Callback handler ---
async def give_take_massgive_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    try:
        parts = data.split('_', 2)
        if len(parts) < 3:
            await callback_query.answer("Invalid action.", show_alert=True)
            return
        action, confirm, unique_id = parts
        pending = PENDING_ACTIONS.get(unique_id)
        if not pending:
            await callback_query.answer("This action has expired or is invalid.", show_alert=True)
            return
        
        # Security check: Only the admin who initiated the action can use the buttons
        if user_id != pending['admin_id']:
            await callback_query.answer("You are not authorized to use this button!", show_alert=True)
            return
        
        # Additional admin check for non-admin users
        # Check if user is owner, OG, or sudo
        is_admin = is_owner(user_id) or await is_og(db, user_id) or await is_sudo(db, user_id)
        
        if not is_admin:
            await callback_query.answer("You are not authorized to use this button!", show_alert=True)
            return
        
        # Get character(s)
        if pending['type'] == 'massgive':
            characters = [await db.get_character(cid) for cid in pending['char_ids']]
        else:
            character = await db.get_character(pending['char_id'])
        # Handle confirm/cancel
        if confirm == "ok":
            if pending['type'] == "give":
                await db.add_character_to_user(pending['target_id'], pending['char_id'], source='give')
                # Log the give action
                admin_user = await client.get_users(pending['admin_id'])
                target_user = await client.get_users(pending['target_id'])
                await send_character_log(client, admin_user, target_user, character, 'give')
                # Show image if available
                if character.get('img_url'):
                    if character.get('is_video', False):
                        await callback_query.edit_message_media(
                            InputMediaVideo(
                                media=character['img_url'],
                                caption="✅ <b>Character given successfully!</b>"
                            )
                        )
                    else:
                        await callback_query.edit_message_media(
                            InputMediaPhoto(
                                media=character['img_url'],
                                caption="✅ <b>Character given successfully!</b>"
                            )
                        )
                else:
                    await callback_query.edit_message_text("✅ <b>Character given successfully!</b>")
            elif pending['type'] == "take":
                await db.remove_single_character_from_user(pending['target_id'], pending['char_id'])
                # Log the take action
                admin_user = await client.get_users(pending['admin_id'])
                target_user = await client.get_users(pending['target_id'])
                await send_character_log(client, admin_user, target_user, character, 'take')
                if character.get('img_url'):
                    if character.get('is_video', False):
                        await callback_query.edit_message_media(
                            InputMediaVideo(
                                media=character['img_url'],
                                caption="✅ <b>Character taken successfully!</b>"
                            )
                        )
                    else:
                        await callback_query.edit_message_media(
                            InputMediaPhoto(
                                media=character['img_url'],
                                caption="✅ <b>Character taken successfully!</b>"
                            )
                        )
                else:
                    await callback_query.edit_message_text("✅ <b>Character taken successfully!</b>")
            elif pending['type'] == "massgive":
                # Batch update: add all characters and collection_history in one call
                char_ids = pending['char_ids']
                now = datetime.now()
                collection_history = [{
                    'character_id': cid,
                    'collected_at': now.isoformat(),  # Convert datetime to ISO string
                    'source': 'give'
                } for cid in char_ids]
                await db.users.update_one(
                    {'user_id': pending['target_id']},
                    {
                        '$push': {
                            'characters': {'$each': char_ids},
                            'collection_history': {'$each': collection_history}
                        }
                    }
                )
                # Invalidate cache if needed
                cache_key = f"collection:{pending['target_id']}"
                if hasattr(db, 'cache') and cache_key in db.cache:
                    del db.cache[cache_key]
                await callback_query.edit_message_text(f"✅ <b>Successfully gave {len(char_ids)} characters!</b>")
        else:
            # Cancel: show original image if available, else just text
            if pending['type'] in ("give", "take") and character.get('img_url'):
                if character.get('is_video', False):
                    await callback_query.edit_message_media(
                        InputMediaVideo(
                            media=character['img_url'],
                            caption="❌ <b>Action cancelled.</b>"
                        )
                    )
                else:
                    await callback_query.edit_message_media(
                        InputMediaPhoto(
                            media=character['img_url'],
                            caption="❌ <b>Action cancelled.</b>"
                        )
                    )
            else:
                await callback_query.edit_message_text("❌ <b>Action cancelled.</b>")
    except Exception as e:
        print(f"Error in give/take/massgive callback: {e}")
        await callback_query.edit_message_text("❌ <b>An error occurred!</b>")
    finally:
        if 'unique_id' in locals():
            PENDING_ACTIONS.pop(unique_id, None)