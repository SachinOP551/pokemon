from pyrogram import Client, filters
from pyrogram.types import Message
from .decorators import admin_only, is_owner, is_og, is_sudo, is_admin
import os

# Import database based on configuration
from modules.postgres_database import get_database as pg_get_database
from config import LOG_CHANNEL_ID

# Use the PostgreSQL get_database function
get_database = pg_get_database

# Debug function to check if get_database is working correctly
def debug_get_database():
    try:
        result = pg_get_database()
        print(f"[DEBUG] get_database() returned: {type(result)}")
        return result
    except Exception as e:
        print(f"[DEBUG] get_database() error: {e}")
        raise


@admin_only
async def bang_command(client: Client, message: Message):
    if not message.from_user:
        return
    print(f"[DEBUG] bang_command called by {message.from_user.id}")
    try:
        print(f"[DEBUG] Getting database in bang_command")
        db = debug_get_database()
        print(f"[DEBUG] Database object type in bang_command: {type(db)}")
        admin = message.from_user
        target_user = None

        # Support: /bang <user_id>
        args = message.text.split()
        if len(args) > 1:
            try:
                target_user_id = int(args[1])
                target_user_data = await db.get_user(target_user_id)
                if not target_user_data:
                    await message.reply_text("<b>❌ Target user not found in the database!</b>")
                    return
                target_user = type('User', (), target_user_data)()  # Fake a user object with .id and .first_name
                target_user.id = target_user_id
                target_user.first_name = target_user_data.get('first_name', str(target_user_id))
            except Exception:
                await message.reply_text("<b>❌ Invalid user ID!</b>")
                return
        elif message.reply_to_message:
            target_user = message.reply_to_message.from_user
            # Check if target user exists in DB
            user_data = await db.get_user(target_user.id)
            if not user_data:
                await message.reply_text("<b>❌ Target user not found in the database!</b>")
                return
        else:
            await message.reply_text("<b>❌ Please reply to a user's message or provide a user ID!</b>")
            return

        print(f"[DEBUG] Admin: {admin.id}, Target: {target_user.id}")

        # Don't allow banning admins
        if await is_admin(db, target_user.id):
            await message.reply_text("<b>❌ You cannot ban an admin!</b>")
            return

        # Ban user permanently using the new ban system
        from .ban_manager import ban_user
        success = await ban_user(target_user.id, db, permanent=True, reason="Admin ban")
        
        if not success:
            await message.reply_text("<b>❌ Failed to ban the user!</b>")
            return

        # Send success message
        await message.reply_text(f"<b>🔨 {target_user.first_name} has been banned from the bot!</b>")

        # Log the ban
        log_message = (
            f"<b>🔨 Ban Log</b>\n\n"
            f"<b>👤 Admin:</b> {admin.first_name} | <code>{admin.id}</code>\n"
            f"<b>👤 User:</b> {target_user.first_name} | <code>{target_user.id}</code>"
        )
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )

    except Exception as e:
        print(f"Error in bang command: {e}")
        await message.reply_text("<b>❌ An error occurred while banning the user!</b>")


@admin_only
async def unbang_command(client: Client, message: Message):
    """Unban a user from the bot (Sudo/OG only)"""
    print(f"[DEBUG] unbang_command called by {message.from_user.id}")
    try:
        db = debug_get_database()
        admin = message.from_user
        target_user = None

        # Support: /unbang <user_id>
        args = message.text.split()
        if len(args) > 1:
            try:
                target_user_id = int(args[1])
                target_user_data = await db.get_user(target_user_id)
                if not target_user_data:
                    await message.reply_text("<b>❌ Target user not found in the database!</b>")
                    return
                target_user = type('User', (), target_user_data)()
                target_user.id = target_user_id
                target_user.first_name = target_user_data.get('first_name', str(target_user_id))
            except Exception:
                await message.reply_text("<b>❌ Invalid user ID!</b>")
                return
        elif message.reply_to_message:
            target_user = message.reply_to_message.from_user
            # Check if target user exists in DB
            user_data = await db.get_user(target_user.id)
            if not user_data:
                await message.reply_text("<b>❌ Target user not found in the database!</b>")
                return
        else:
            await message.reply_text("<b>❌ Please reply to a user's message or provide a user ID!</b>")
            return

        print(f"[DEBUG] Admin: {admin.id}, Target: {target_user.id}")

        # Check if user is already unbanned
        from .ban_manager import check_user_ban_status
        is_banned, _ = await check_user_ban_status(target_user.id, db)
        
        if not is_banned:
            await message.reply_text(f"<b>✅ {target_user.first_name} Is Already Free To Use This Bot</b>")
            return

        # Unban user using the new ban system
        from .ban_manager import unban_user
        success = await unban_user(target_user.id, db)
        
        if not success:
            await message.reply_text("<b>❌ Failed to unban the user!</b>")
            return

        # Send success message
        await message.reply_text(f"<b>✅ {target_user.first_name} has been unbanned from the bot!</b>")

        # Log the unban
        log_message = (
            f"<b>🔓 Unban Log</b>\n\n"
            f"<b>👤 Admin:</b> {admin.first_name} | <code>{admin.id}</code>\n"
            f"<b>👤 User:</b> {target_user.first_name} | <code>{target_user.id}</code>"
        )
        await client.send_message(
            chat_id=LOG_CHANNEL_ID,
            text=log_message
        )

    except Exception as e:
        print(f"Error in unbang command: {e}")
        await message.reply_text("<b>❌ An error occurred while unbanning the user!</b>")

@admin_only
async def baninfo_command(client: Client, message: Message):
    """Get ban information for a user (Sudo/OG only)"""
    print(f"[DEBUG] baninfo_command called by {message.from_user.id}")
    try:
        db = debug_get_database()
        target_user = None

        # Support: /baninfo <user_id>
        args = message.text.split()
        if len(args) > 1:
            try:
                target_user_id = int(args[1])
                target_user_data = await db.get_user(target_user_id)
                if not target_user_data:
                    await message.reply_text("<b>❌ Target user not found in the database!</b>")
                    return
                target_user = type('User', (), target_user_data)()
                target_user.id = target_user_id
                target_user.first_name = target_user_data.get('first_name', str(target_user_id))
            except Exception:
                await message.reply_text("<b>❌ Invalid user ID!</b>")
                return
        elif message.reply_to_message:
            target_user = message.reply_to_message.from_user
            # Check if target user exists in DB
            user_data = await db.get_user(target_user.id)
            if not user_data:
                await message.reply_text("<b>❌ Target user not found in the database!</b>")
                return
        else:
            await message.reply_text("<b>❌ Please reply to a user's message or provide a user ID!</b>")
            return

        print(f"[DEBUG] Checking ban info for user: {target_user.id}")

        # Get ban information
        from .ban_manager import get_comprehensive_ban_info
        ban_info = await get_comprehensive_ban_info(target_user.id, db)

        if ban_info:
            ban_type = ban_info['type']
            reason = ban_info['reason']
            
            if ban_type == 'temporary':
                remaining = ban_info['remaining_minutes']
                end_time = ban_info['end_time'].strftime('%Y-%m-%d %H:%M:%S')
                info_text = (
                    f"<b>🔍 Ban Information for {target_user.first_name}</b>\n\n"
                    f"<b>Status:</b> 🔴 Temporarily Banned\n"
                    f"<b>Reason:</b> {reason}\n"
                    f"<b>End Time:</b> {end_time}\n"
                    f"<b>Remaining:</b> {remaining} minutes"
                )
            else:  # permanent
                info_text = (
                    f"<b>🔍 Ban Information for {target_user.first_name}</b>\n\n"
                    f"<b>Status:</b> 🔴 Permanently Banned\n"
                    f"<b>Reason:</b> {reason}\n"
                    f"<b>End Time:</b> Never (Permanent)"
                )
        else:
            info_text = (
                f"<b>🔍 Ban Information for {target_user.first_name}</b>\n\n"
                f"<b>Status:</b> ✅ Not Banned\n"
                f"<b>Reason:</b> N/A\n"
                f"<b>End Time:</b> N/A"
            )

        await message.reply_text(info_text)

    except Exception as e:
        print(f"Error in baninfo command: {e}")
        await message.reply_text("<b>❌ An error occurred while getting ban information!</b>")