from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import os

from .postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
from .decorators import check_banned, auto_register_user, is_owner, is_og
from modules.upload import upload_to_imgbb
import uuid

# In-memory storage for pending suggestions
PENDING_SUGGESTIONS = {}

SUGGESTION_GROUP_ID = -1002832255565  # The group to send suggestions to

@check_banned
@auto_register_user
async def suggest_command(client: Client, message: Message):
    user = message.from_user
    db = get_database()
    # Must be a reply to a photo
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply_text("<b>❌ Please reply to an image with /suggest &lt;name&gt; &lt;rarity&gt;.</b>")
        return
    parts = message.text.split()[1:]  # remove command itself
    if len(parts) < 2:
        await message.reply_text("<b>❌ Usage: /suggest &lt;name&gt; &lt;rarity&gt; (as a reply to an image)</b>")
        return
    # Try to match the longest possible rarity from the end
    matched_rarity = None
    name = None
    for i in range(1, min(3, len(parts)) + 1):  # check last 1, 2, or 3 words
        candidate = " ".join(parts[-i:]).strip()
        for r in RARITIES:
            if candidate.lower() == r.lower():
                matched_rarity = r
                name = " ".join(parts[:-i]).strip()
                break
        if matched_rarity:
            break
    if not matched_rarity or not name:
        await message.reply_text(f"<b>❌ Invalid rarity! Choose one of:</b> {' | '.join(RARITIES.keys())}")
        return
    if len(name) < 2 or len(name) > 50:
        await message.reply_text("<b>❌ Name must be between 2 and 50 characters.</b>")
        return
    file_id = message.reply_to_message.photo.file_id
    processing_msg = await message.reply_text("<i>Processing your suggestion, please wait...</i>")
    img_url = await upload_to_imgbb(file_id, client)
    if not img_url:
        await processing_msg.edit_text("<b>❌ Failed to upload image. Please try again.</b>")
        return
    # Generate unique suggestion ID
    suggestion_id = str(uuid.uuid4())
    # Store pending suggestion
    PENDING_SUGGESTIONS[suggestion_id] = {
        "name": name,
        "rarity": matched_rarity,
        "file_id": file_id,
        "img_url": img_url,
        "suggested_by": user.id,
        "suggested_by_name": user.first_name,
        "suggested_by_username": user.username,
    }
    rarity_emoji = RARITY_EMOJIS.get(matched_rarity, "❓")
    # Prepare message for group
    caption = (
        f"<b>📝 New Character Suggestion</b>\n\n"
        f"<b>👤 Suggested by:</b> <a href='tg://user?id={user.id}'>{user.first_name}</a>"
    )
    if user.username:
        caption += f" (@{user.username})"
    caption += (f"\n<b>🆕 Name:</b> {name}\n"
                f"<b>✨ Rarity:</b> {rarity_emoji} {matched_rarity}\n\n"
                f"Do you want to add this character to the database?")
    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"suggest_accept_{suggestion_id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"suggest_decline_{suggestion_id}")
        ]
    ]
    # Send to group
    await client.send_photo(
        chat_id=SUGGESTION_GROUP_ID,
        photo=img_url,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await processing_msg.edit_text("<b>✅ Your suggestion has been sent for review!</b>")

async def suggest_callback(client: Client, callback_query: CallbackQuery):
    db = get_database()
    user = callback_query.from_user
    data = callback_query.data
    if data.startswith("suggest_accept_") or data.startswith("suggest_decline_"):
        action, _, suggestion_id = data.partition("_accept_") if "_accept_" in data else data.partition("_decline_")
        is_accept = "_accept_" in data
        suggestion = PENDING_SUGGESTIONS.get(suggestion_id)
        if not suggestion:
            await callback_query.answer("Suggestion expired or not found.", show_alert=True)
            return
        # Only OGs or Owner can accept/decline
        if not (is_owner(user.id) or await is_og(db, user.id)):
            await callback_query.answer("Only OGs or Owner can accept/decline.", show_alert=True)
            return
        if is_accept:
            # Add to database
            inserted_id = await db.add_character({
                "name": suggestion["name"],
                "rarity": suggestion["rarity"],
                "file_id": suggestion["file_id"],
                "img_url": suggestion["img_url"],
                "is_video": False
            })
            char = await db.characters.find_one({"_id": inserted_id})
            char_id = char.get("character_id", inserted_id)
            await callback_query.message.edit_caption(
                f"<b>✅ Character accepted and added to the database!</b>\n\n"
                f"<b>🆔 ID:</b> <code>{char_id}</code>\n"
                f"<b>🆕 Name:</b> {suggestion['name']}\n"
                f"<b>✨ Rarity:</b> {RARITY_EMOJIS.get(suggestion['rarity'], '❓')} {suggestion['rarity']}\n\n"
                f"<b>👤 Suggested by:</b> <a href='tg://user?id={suggestion['suggested_by']}'>{suggestion['suggested_by_name']}</a>"
                + (f" (@{suggestion['suggested_by_username']})" if suggestion['suggested_by_username'] else "")
            )
            # Announce in main group
            DROPTIME_LOG_CHANNEL = -1002558794123
            suggester_mention = f"<a href='tg://user?id={suggestion['suggested_by']}'>{suggestion['suggested_by_name']}</a>"
            log_caption = (
                f"<b>🆕 New character added</b>\n"
                f"<b>👤 Name:</b> {char.get('name', '-') }\n"
                f"<b>🆔 ID:</b> <code>{char.get('character_id', char.get('_id', '-'))}</code>\n"
                f"<b>✨ Rarity:</b> {char.get('rarity', '-') }\n"
                f"<b>🙋‍♂️ Suggested by:</b> {suggester_mention}"
            )
            try:
                await client.send_photo(
                    chat_id=DROPTIME_LOG_CHANNEL,
                    photo=char.get('img_url', suggestion['file_id']),
                    caption=log_caption,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"Failed to send character suggestion log to droptime channel: {e}")
                # Don't crash the bot, just log the error
        else:
            await callback_query.message.edit_caption(
                f"<b>❌ Character suggestion was declined.</b>\n\n"
                f"<b>🆕 Name:</b> {suggestion['name']}\n"
                f"<b>✨ Rarity:</b> {RARITY_EMOJIS.get(suggestion['rarity'], '❓')} {suggestion['rarity']}\n\n"
                f"<b>👤 Suggested by:</b> <a href='tg://user?id={suggestion['suggested_by']}'>{suggestion['suggested_by_name']}</a>"
                + (f" (@{suggestion['suggested_by_username']})" if suggestion['suggested_by_username'] else "")
            )
        # Remove from pending
        PENDING_SUGGESTIONS.pop(suggestion_id, None)
        await callback_query.answer("Done!", show_alert=True)

# Handler registration helper
def register_suggest_handlers(app: Client):
    app.add_handler(filters.command("suggest"), suggest_command)
    app.add_handler(filters.callback_query & filters.create(lambda _, cq: cq.data.startswith("suggest_accept_") or cq.data.startswith("suggest_decline_")), suggest_callback)
