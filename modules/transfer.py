import logging
import os

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from modules.postgres_database import get_database

from .decorators import check_banned, is_owner
from .logging_utils import send_character_log, send_token_log

# Temp storage for pending transfers
_pending_transfers = {}

@check_banned
async def transfer_command(client: Client, message: Message):
    """Transfer one account's data to another account (with confirmation)"""
    user_id = message.from_user.id
    db = get_database()
    if not is_owner(user_id):
        await message.reply_text(
            "❌ This command is restricted to owner only!"
        )
        return
    args = message.text.split()
    if len(args) != 3:
        await message.reply_text(
            "❌ Please provide both source and target user IDs!\nUsage: /transfer <source_user_id> <target_user_id>"
        )
        return
    try:
        source_user_id = int(args[1])
        target_user_id = int(args[2])
        source_user = await db.get_user(source_user_id)
        if not source_user:
            await message.reply_text(
                "❌ Source user not found!"
            )
            return
        target_user = await db.get_user(target_user_id)
        if not target_user:
            await message.reply_text(
                "❌ Target user is not registered!"
            )
            return
        source_characters = source_user.get('characters', [])
        source_wallet = source_user.get('wallet', 0)
        source_bank = source_user.get('bank', 0)
        if not source_characters and source_wallet == 0 and source_bank == 0:
            await message.reply_text(
                "❌ Source user has no data to transfer!"
            )
            return
        # Store pending transfer
        _pending_transfers[user_id] = {
            'source_user_id': source_user_id,
            'target_user_id': target_user_id
        }
        # Show confirmation buttons
        summary = (
            f"<b>🔄 Confirm Account Transfer</b>\n\n"
            f"<b>👤 Admin:</b> {message.from_user.first_name} (ID: <code>{message.from_user.id}</code>)\n"
            f"<b>📤 Source User:</b> {source_user.get('first_name', 'Unknown')} (ID: <code>{source_user_id}</code>)\n"
            f"<b>📥 Target User:</b> {target_user.get('first_name', 'Unknown')} (ID: <code>{target_user_id}</code>)\n"
            f"<b>📦 Characters to Transfer:</b> <code>{len(source_characters)}</code>\n"
            f"<b>💰 Wallet to Transfer:</b> <code>{source_wallet}</code>\n"
            f"<b>🏦 Bank to Transfer:</b> <code>{source_bank}</code>\n\n"
            f"Are you sure you want to transfer all data from <b>{source_user_id}</b> to <b>{target_user_id}</b>?"
        )
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm Transfer", callback_data="transfer_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="transfer_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text(summary, reply_markup=reply_markup)
    except ValueError:
        await message.reply_text(
            "❌ Please enter valid user IDs!"
        )
    except Exception as e:
        print(f"Error in transfer command: {e}")
        await message.reply_text(
            "❌ An error occurred during transfer!"
        )

@check_banned
async def handle_transfer_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    db = get_database()
    await callback_query.answer()
    if user_id not in _pending_transfers:
        await callback_query.edit_message_text("❌ Session expired! Please try again.")
        return
    if callback_query.data == "transfer_cancel":
        del _pending_transfers[user_id]
        await callback_query.edit_message_text("❌ Transfer cancelled.")
        return
    if callback_query.data == "transfer_confirm":
        transfer = _pending_transfers[user_id]
        source_user_id = transfer['source_user_id']
        target_user_id = transfer['target_user_id']
        try:
            source_user = await db.get_user(source_user_id)
            target_user = await db.get_user(target_user_id)
            source_characters = source_user.get('characters', [])
            source_wallet = source_user.get('wallet', 0)
            source_bank = source_user.get('bank', 0)
            
            # Store original values for potential rollback
            original_source_characters = source_characters.copy()
            original_source_wallet = source_wallet
            original_source_bank = source_bank
            
            # Perform transfer operations without transactions
            try:
                # Transfer characters
                if source_characters:
                    await db.users.update_one(
                        {'user_id': target_user_id},
                        {'$push': {'characters': {'$each': source_characters}}}
                    )
                    await db.users.update_one(
                        {'user_id': source_user_id},
                        {'$set': {'characters': []}}
                    )
                
                # Transfer wallet
                if source_wallet > 0:
                    await db.users.update_one(
                        {'user_id': target_user_id},
                        {'$inc': {'wallet': source_wallet}}
                    )
                    await db.users.update_one(
                        {'user_id': source_user_id},
                        {'$inc': {'wallet': -source_wallet}}
                    )
                
                # Transfer bank
                if source_bank > 0:
                    await db.users.update_one(
                        {'user_id': target_user_id},
                        {'$inc': {'bank': source_bank}}
                    )
                    await db.users.update_one(
                        {'user_id': source_user_id},
                        {'$inc': {'bank': -source_bank}}
                    )
                
                # Invalidate cache for both users' collections
                if hasattr(db, 'cache'):
                    db.cache.pop(f'collection:{source_user_id}', None)
                    db.cache.pop(f'collection:{target_user_id}', None)
                
            except Exception as transfer_error:
                # Rollback in case of partial failure
                print(f"Transfer error occurred, attempting rollback: {transfer_error}")
                try:
                    # Rollback characters
                    if original_source_characters:
                        await db.users.update_one(
                            {'user_id': source_user_id},
                            {'$set': {'characters': original_source_characters}}
                        )
                        # Remove characters from target if they were added
                        await db.users.update_one(
                            {'user_id': target_user_id},
                            {'$pullAll': {'characters': original_source_characters}}
                        )
                    
                    # Rollback wallet
                    if original_source_wallet > 0:
                        await db.users.update_one(
                            {'user_id': source_user_id},
                            {'$inc': {'wallet': original_source_wallet}}
                        )
                        await db.users.update_one(
                            {'user_id': target_user_id},
                            {'$inc': {'wallet': -original_source_wallet}}
                        )
                    
                    # Rollback bank
                    if original_source_bank > 0:
                        await db.users.update_one(
                            {'user_id': source_user_id},
                            {'$inc': {'bank': original_source_bank}}
                        )
                        await db.users.update_one(
                            {'user_id': target_user_id},
                            {'$inc': {'bank': -original_source_bank}}
                        )
                except Exception as rollback_error:
                    print(f"Rollback failed: {rollback_error}")
                
                raise transfer_error
            
            log_message = (
                f"<b>🔄 Account Transfer Log</b>\n\n"
                f"<b>👤 Admin:</b> {callback_query.from_user.first_name} (ID: <code>{callback_query.from_user.id}</code>)\n"
                f"<b>📤 Source User:</b> {source_user.get('first_name', 'Unknown')} (ID: <code>{source_user_id}</code>)\n"
                f"<b>📥 Target User:</b> {target_user.get('first_name', 'Unknown')} (ID: <code>{target_user_id}</code>)\n"
                f"<b>📦 Characters Transferred:</b> <code>{len(source_characters)}</code>\n"
                f"<b>💰 Wallet Transferred:</b> <code>{source_wallet}</code>\n"
                f"<b>🏦 Bank Transferred:</b> <code>{source_bank}</code>"
            )
            try:
                await client.send_message(
                    chat_id=-1002585831452,  # LOG_CHANNEL_ID
                    text=log_message
                )
            except Exception as e:
                print(f"Failed to send transfer log: {e}")
            message_text = (
                f"<b>✅ Transfer completed successfully!</b>\n\n"
                f"<b>👤 Source User:</b> {source_user.get('first_name', 'Unknown')} (ID: <code>{source_user_id}</code>)\n"
                f"<b>👥 Target User:</b> {target_user.get('first_name', 'Unknown')} (ID: <code>{target_user_id}</code>)\n"
                f"<b>📦 Characters Transferred:</b> <code>{len(source_characters)}</code>\n"
                f"<b>💰 Wallet Transferred:</b> <code>{source_wallet}</code>\n"
                f"<b>🏦 Bank Transferred:</b> <code>{source_bank}</code>"
            )
            await callback_query.edit_message_text(message_text)
            del _pending_transfers[user_id]
        except Exception as e:
            print(f"Error in transfer confirmation: {e}")
            await callback_query.edit_message_text("❌ An error occurred during transfer!")
            del _pending_transfers[user_id]

def setup_transfer_handlers(app: Client):
    app.add_handler(filters.command("transfer")(transfer_command))
    app.add_handler(filters.callback_query(lambda client, cq: cq.data in ["transfer_confirm", "transfer_cancel"])(handle_transfer_callback))
