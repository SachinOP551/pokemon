from pyrogram import Client, filters
from pyrogram.types import Message
from datetime import datetime
import random
import string
from .decorators import is_owner, is_og, is_sudo, check_banned
import os

# Import database based on configuration
from modules.postgres_database import get_database, get_rarity_emoji, RARITIES, RARITY_EMOJIS, get_rarity_display
from .logging_utils import send_redeem_log



def generate_redeem_code(length=8):
    """Generate a random redeem code"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


@check_banned
async def credeem_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    args = message.text.split()[1:]
    # Check if user is sudo, OG, or owner
    if not (await is_sudo(db, user_id) or await is_og(db, user_id) or is_owner(user_id)):
        return
    if not args:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ᴄʜᴀʀᴀᴄᴛᴇʀ ɪᴅ\nᴜsᴀɢᴇ: `/credeem <character_id> [max_claims]`</b>"
        )
        return
    try:
        character_id = int(args[0])
        max_claims = int(args[1]) if len(args) > 1 else 1
        if max_claims < 1:
            await message.reply_text(
                "<b>❌ ᴍᴀxɪᴍᴜᴍ ᴄʟᴀɪᴍs ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1!</b>"
            )
            return
        character = await db.get_character(character_id)
        if not character:
            await message.reply_text(
                "<b>❌ ᴄʜᴀʀᴀᴄᴛᴇʀ ɴᴏᴛ ғᴏᴜɴᴅ!</b>"
            )
            return
        while True:
            code = generate_redeem_code()
            existing_code = await db.redeem_codes.find_one({'code': code})
            if not existing_code:
                break
        redeem_data = {
            'code': code,
            'character_id': character_id,
            'created_by': user_id,
            'created_at': datetime.now().isoformat(),
            'max_claims': max_claims,
            'claims': 0,
            'claimed_by': []
        }
        # Before inserting redeem_data:
        if "created_at" in redeem_data and isinstance(redeem_data["created_at"], str):
            try:
                redeem_data["created_at"] = datetime.fromisoformat(redeem_data["created_at"])
            except Exception:
                redeem_data["created_at"] = datetime.utcnow()
        elif "created_at" not in redeem_data:
            redeem_data["created_at"] = datetime.utcnow()

        await db.insert_redeem_code(redeem_data)
        rarity_emoji = get_rarity_emoji(character['rarity'])
        msg = (
            "<b>✅ ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇ ᴄʀᴇᴀᴛᴇᴅ!</b>\n\n"
            f"🎨 ᴄʜᴀʀᴀᴄᴛᴇʀ: {rarity_emoji} "
            f"{character['name']}\n"
            f"🔑 ᴄᴏᴅᴇ: `{code}`\n"
            f"📊 ᴍᴀx ᴄʟᴀɪᴍs: `{max_claims}`"
        )
        await message.reply_text(msg)
        await send_redeem_log(
            client,
            message.from_user,
            'character',
            code,
            max_claims,
            {
                'name': character['name'],
                'rarity': character['rarity'],
                'character_id': character['character_id']
            }
        )
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀs!</b>"
        )

@check_banned
async def tredeem_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    args = message.text.split()[1:]
    if not (await is_sudo(db, user_id) or await is_og(db, user_id) or is_owner(user_id)):
        return
    if len(args) < 2:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴛᴏᴋᴇɴ ᴀᴍᴏᴜɴᴛ ᴀɴᴅ ᴍᴀx ᴄʟᴀɪᴍs\nᴜsᴀɢᴇ: `/tredeem <token_amount> <max_claims>`</b>"
        )
        return
    try:
        token_amount = int(args[0])
        max_claims = int(args[1])
        if token_amount < 1:
            await message.reply_text(
                "<b>❌ ᴛᴏᴋᴇɴ ᴀᴍᴏᴜɴᴛ ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1!</b>"
            )
            return
        if max_claims < 1:
            await message.reply_text(
                "<b>❌ ᴍᴀxɪᴍᴜᴍ ᴄʟᴀɪᴍs ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1!</b>"
            )
            return
        while True:
            code = generate_redeem_code()
            existing_code = await db.redeem_codes.find_one({'code': code})
            if not existing_code:
                break
        redeem_data = {
            'code': code,
            'type': 'token',
            'token_amount': token_amount,
            'created_by': user_id,
            'created_at': datetime.now().isoformat(),
            'max_claims': max_claims,
            'claims': 0,
            'claimed_by': []
        }
        # Before inserting redeem_data:
        if "created_at" in redeem_data and isinstance(redeem_data["created_at"], str):
            try:
                redeem_data["created_at"] = datetime.fromisoformat(redeem_data["created_at"])
            except Exception:
                redeem_data["created_at"] = datetime.utcnow()
        elif "created_at" not in redeem_data:
            redeem_data["created_at"] = datetime.utcnow()

        await db.insert_redeem_code(redeem_data)
        msg = (
            "<b>✅ ᴛᴏᴋᴇɴ ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇ ᴄʀᴇᴀᴛᴇᴅ!</b>\n\n"
            f"💰 ᴛᴏᴋᴇɴs: `{token_amount}`\n"
            f"🔑 ᴄᴏᴅᴇ: `{code}`\n"
            f"📊 ᴍᴀx ᴄʟᴀɪᴍs: `{max_claims}`"
        )
        await message.reply_text(msg)
        await send_redeem_log(
            client,
            message.from_user,
            'token',
            code,
            max_claims,
            {'token_amount': token_amount}
        )
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀs!</b>"
        )

@check_banned
async def sredeem_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    args = message.text.split()[1:]
    if not (await is_sudo(db, user_id) or await is_og(db, user_id) or is_owner(user_id)):
        return
    if len(args) < 2:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ sʜᴀʀᴅ ᴀᴍᴏᴜɴᴛ ᴀɴᴅ ᴍᴀx ᴄʟᴀɪᴍs\nᴜsᴀɢᴇ: `/sredeem <shard_amount> <max_claims>`</b>"
        )
        return
    try:
        shard_amount = int(args[0])
        max_claims = int(args[1])
        if shard_amount < 1:
            await message.reply_text(
                "<b>❌ sʜᴀʀᴅ ᴀᴍᴏᴜɴᴛ ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1!</b>"
            )
            return
        if max_claims < 1:
            await message.reply_text(
                "<b>❌ ᴍᴀxɪᴍᴜᴍ ᴄʟᴀɪᴍs ᴍᴜsᴛ ʙᴇ ᴀᴛ ʟᴇᴀsᴛ 1!</b>"
            )
            return
        while True:
            code = generate_redeem_code()
            existing_code = await db.redeem_codes.find_one({'code': code})
            if not existing_code:
                break
        redeem_data = {
            'code': code,
            'type': 'shard',
            'shard_amount': shard_amount,
            'created_by': user_id,
            'created_at': datetime.now().isoformat(),
            'max_claims': max_claims,
            'claims': 0,
            'claimed_by': []
        }
        # Before inserting redeem_data:
        if "created_at" in redeem_data and isinstance(redeem_data["created_at"], str):
            try:
                redeem_data["created_at"] = datetime.fromisoformat(redeem_data["created_at"])
            except Exception:
                redeem_data["created_at"] = datetime.utcnow()
        elif "created_at" not in redeem_data:
            redeem_data["created_at"] = datetime.utcnow()

        await db.insert_redeem_code(redeem_data)
        msg = (
            "<b>✅ sʜᴀʀᴅ ʀᴇᴅᴇᴇᴍ ᴄᴏᴅᴇ ᴄʀᴇᴀᴛᴇᴅ!</b>\n\n"
            f"🎐 sʜᴀʀᴅs: `{shard_amount}`\n"
            f"🔑 ᴄᴏᴅᴇ: `{code}`\n"
            f"📊 ᴍᴀx ᴄʟᴀɪᴍs: `{max_claims}`"
        )
        await message.reply_text(msg)
        await send_redeem_log(
            client,
            message.from_user,
            'shard',
            code,
            max_claims,
            {'shard_amount': shard_amount}
        )
    except ValueError:
        await message.reply_text(
            "<b>❌ ᴘʟᴇᴀsᴇ ᴇɴᴛᴇʀ ᴠᴀʟɪᴅ ɴᴜᴍʙᴇʀs!</b>"
        )


@check_banned
async def redeem_command(client: Client, message: Message):
    user_id = message.from_user.id
    db = get_database()
    args = message.text.split()[1:]
    user = await db.get_user(user_id)
    if not user:
        return
    if not args:
        await message.reply_text(
            "<b>ᴜsᴀɢᴇ: /redeem code</b>"
        )
        return
    code = args[0].upper()
    db = get_database()
    code = code.strip()  # Remove whitespace
    redeem_data = await db.get_redeem_code(code)
    if not redeem_data:
        await message.reply_text("❌ Invalid redeem code!")
        return
    if redeem_data['claims'] >= redeem_data['max_claims']:
        await message.reply_text(
            "<b>❌ ᴛʜɪs ᴄᴏᴅᴇ ʜᴀs ʙᴇᴇɴ ᴜsᴇᴅ ᴜᴘ!</b>"
        )
        return
    if user_id in redeem_data['claimed_by']:
        await message.reply_text(
            "<b>❌ ʏᴏᴜ ʜᴀᴠᴇ ᴀʟʀᴇᴀᴅʏ ᴄʟᴀɪᴍᴇᴅ ᴛʜɪs ᴄᴏᴅᴇ!</b>"
        )
        return
    try:     # --- TOKEN REDEEM ---
        if redeem_data.get('type') == 'token':
                    token_amount = redeem_data['token_amount']
                    await db.update_user(user_id, {'wallet': user.get('wallet', 0) + token_amount})
                    await db.update_redeem_code_claim(code, user_id)
                    msg = (
                        "<b>✅ ᴛᴏᴋᴇɴ ᴄᴏᴅᴇ ʀᴇᴅᴇᴇᴍᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                        f"💰 ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇᴅ: `{token_amount}` ᴛᴏᴋᴇɴs"
                    )
                    await send_redeem_log(
                        client,
                        message.from_user,
                        'token',
                        code,
                        1,
                        {'token_amount': token_amount}
                    )
                # --- SHARD REDEEM ---
        elif redeem_data.get('type') == 'shard':
                    shard_amount = redeem_data['shard_amount']
                    await db.update_user(user_id, {'shards': user.get('shards', 0) + shard_amount})
                    await db.update_redeem_code_claim(code, user_id)
                    msg = (
                        "<b>✅ sʜᴀʀᴅ ᴄᴏᴅᴇ ʀᴇᴅᴇᴇᴍᴇᴅ sᴜᴄᴄᴇssғᴜʟʟʏ!</b>\n\n"
                        f"🎐 ʏᴏᴜ ʀᴇᴄᴇɪᴠᴇᴅ: `{shard_amount}` sʜᴀʀᴅs"
                    )
                    await send_redeem_log(
                        client,
                        message.from_user,
                        'shard',
                        code,
                        1,
                        {'shard_amount': shard_amount}
                    )
                # --- CHARACTER REDEEM ---
        else:
                    character = await db.get_character(redeem_data['character_id'])
                    if not character:
                        raise Exception("Character not found")
                    await db.add_character_to_user(user_id, character['character_id'], source='redeem')
                    await db.update_redeem_code_claim(code, user_id)
                    rarity_emoji = get_rarity_emoji(character['rarity'])
                    msg = (
                        f"<b>🎯 Look You Redeemed A {character['rarity']} Character</b>\n\n"
                        f"<b>✨ Name:</b> {character['name']}\n"
                        f"<b>{rarity_emoji} Rarity:</b> {character['rarity']}\n"
                        f"<b>🎥 Anime:</b> {character.get('anime', '-') }\n\n"
                        f"<b>You can take a look at your collection using /mycollection.</b>"
                    )
                    await send_redeem_log(
                        client,
                        message.from_user,
                        'character',
                        code,
                        1,
                        {
                            'name': character['name'],
                            'rarity': character['rarity'],
                            'character_id': character['character_id']
                        }
                    )
        await message.reply_text(msg)
    except Exception as e:
        print(f"Error in redeem transaction: {e}")
        await message.reply_text(
            "<b>❌ ᴀɴ ᴇʀʀᴏʀ ᴏᴄᴄᴜʀʀᴇᴅ ᴡʜɪʟᴇ ʀᴇᴅᴇᴇᴍɪɴɢ ᴛʜᴇ ᴄᴏᴅᴇ!</b>"
        )

def setup_redeem_handlers(app: Client):
    app.add_handler(filters.command("credeem")(credeem_command))
    app.add_handler(filters.command("tredeem")(tredeem_command))
    app.add_handler(filters.command("sredeem")(sredeem_command))
    app.add_handler(filters.command("redeem")(redeem_command))
