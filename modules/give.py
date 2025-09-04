from pyrogram.types import Message
from pyrogram import Client
from modules.postgres_database import get_database
from .decorators import is_owner, is_og
from datetime import datetime
from modules.logging_utils import send_character_log
from .admin_approval import AdminAction, create_approval_request

RARITY_EMOJIS = {
    "Common": "⚪️", "Medium": "🟢", "Rare": "🟠", "Legendary": "🟡", "Exclusive": "🫧", "Elite": "💎",
    "Limited Edition": "🔮", "Ultimate": "🔱", "Supreme": "👑", "Mythic": "🔴", "Zenith": "💫", "Ethereal": "❄️", "Premium": "🧿", "Mega Evolution": "🧬"
}

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
    
    # Check if user is owner - if so, execute directly
    if is_owner(user_id):
        # Execute the action directly for owner
        await db.add_character_to_user(target_user.id, char_id, source='give')
        await message.reply_text(f"✅ <b>Character {character['name']} given to {target_user.first_name}!</b>")
        
        # Log the action
        from modules.logging_utils import send_character_log
        admin_user = await client.get_users(user_id)
        target_user_obj = await client.get_users(target_user.id)
        await send_character_log(client, admin_user, target_user_obj, character, 'give')
        
        # Send log to both channels
        from config import LOG_CHANNEL_ID, DROPTIME_LOG_CHANNEL
        log_text = (
            f"✅ <b>ADMIN ACTION APPROVED</b>\n\n"
            f"<b>Type:</b> Give Character\n"
            f"<b>Approved by:</b> {message.from_user.first_name}\n"
            f"<b>Requested by:</b> {message.from_user.first_name}\n"
            f"<b>Target:</b> {target_user.first_name}\n"
            f"<b>Result:</b> ✅ Success: Pokemon {character['name']} given to {target_user.first_name}."
        )
        await client.send_message(LOG_CHANNEL_ID, log_text)
        await client.send_message(DROPTIME_LOG_CHANNEL, log_text)
        return
    
    # For non-owners, create approval request
    action = AdminAction(
        action_type='give',
        admin_id=user_id,
        target_id=target_user.id,
        admin_name=message.from_user.first_name or "Admin",
        target_name=target_user.first_name or "User",
        details={
            'char_id': char_id,
            'char_name': character['name']
        }
    )
    
    # Send approval request to owner
    success = await create_approval_request(client, action)
    if success:
        await message.reply_text("⏳ Your request has been sent to the owner for approval.")
    else:
        await message.reply_text("❌ <b>Failed to send approval request. Please try again.</b>")

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
    
    # Check if user is owner - if so, execute directly
    if is_owner(user_id):
        # Execute the action directly for owner
        await db.remove_single_character_from_user(target_user.id, char_id)
        await message.reply_text(f"✅ <b>Character {character['name']} taken from {target_user.first_name}!</b>")
        
        # Log the action
        from modules.logging_utils import send_character_log
        admin_user = await client.get_users(user_id)
        target_user_obj = await client.get_users(target_user.id)
        await send_character_log(client, admin_user, target_user_obj, character, 'take')
        
        # Send log to both channels
        from config import LOG_CHANNEL_ID, DROPTIME_LOG_CHANNEL
        log_text = (
            f"✅ <b>ADMIN ACTION APPROVED</b>\n\n"
            f"<b>Type:</b> Take Character\n"
            f"<b>Approved by:</b> {message.from_user.first_name}\n"
            f"<b>Requested by:</b> {message.from_user.first_name}\n"
            f"<b>Target:</b> {target_user.first_name}\n"
            f"<b>Result:</b> ✅ Success: Pokemon {character['name']} taken from {target_user.first_name}."
        )
        await client.send_message(LOG_CHANNEL_ID, log_text)
        await client.send_message(DROPTIME_LOG_CHANNEL, log_text)
        return
    
    # Create approval request
    action = AdminAction(
        action_type='take',
        admin_id=user_id,
        target_id=target_user.id,
        admin_name=message.from_user.first_name or "Admin",
        target_name=target_user.first_name or "User",
        details={
            'char_id': char_id,
            'char_name': character['name']
        }
    )
    
    # Send approval request to owner
    success = await create_approval_request(client, action)
    if success:
        await message.reply_text("⏳ Your request has been sent to the owner for approval.")
    else:
        await message.reply_text("❌ <b>Failed to send approval request. Please try again.</b>")

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
    
    # Check if user is owner - if so, execute directly
    if is_owner(user_id):
        # Execute the action directly for owner
        now = datetime.utcnow()
        collection_history = [{
            'character_id': cid,
            'collected_at': now.isoformat(),
            'source': 'give'
        } for cid in char_ids_int]
        await db.users.update_one(
            {'user_id': target_user.id},
            {
                '$push': {
                    'characters': {'$each': char_ids_int},
                    'collection_history': {'$each': collection_history}
                }
            }
        )
        await message.reply_text(f"✅ <b>Characters given to {target_user.first_name}!</b>")
        
        # Send log to both channels
        from config import LOG_CHANNEL_ID, DROPTIME_LOG_CHANNEL
        log_text = (
            f"✅ <b>ADMIN ACTION APPROVED</b>\n\n"
            f"<b>Type:</b> Mass Give Characters\n"
            f"<b>Approved by:</b> {message.from_user.first_name}\n"
            f"<b>Requested by:</b> {message.from_user.first_name}\n"
            f"<b>Target:</b> {target_user.first_name}\n"
            f"<b>Result:</b> ✅ Success: Players with IDs {', '.join(map(str, char_ids_int))} given to {target_user.first_name}."
        )
        await client.send_message(LOG_CHANNEL_ID, log_text)
        await client.send_message(DROPTIME_LOG_CHANNEL, log_text)
        return
    
    # Create approval request
    action = AdminAction(
        action_type='massgive',
        admin_id=user_id,
        target_id=target_user.id,
        admin_name=message.from_user.first_name or "Admin",
        target_name=target_user.first_name or "User",
        details={
            'char_ids': char_ids_int,
            'char_names': [char['name'] for char in characters]
        }
    )
    
    # Send approval request to owner
    success = await create_approval_request(client, action)
    if success:
        await message.reply_text("⏳ Your request has been sent to the owner for approval.")
    else:
        await message.reply_text("❌ <b>Failed to send approval request. Please try again.</b>")
