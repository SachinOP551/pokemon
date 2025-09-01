from pyrogram import Client, filters
from pyrogram.types import Message
from modules.decorators import owner_only
from modules.postgres_database import get_database
import asyncio

REMOVED_GROUPS_FILE = "removed_groups.txt"

async def _broadcast_to_targets(client, targets, send_func, content_args, summary, is_group=False, db=None):
    success, failed = 0, 0
    removed_groups = []
    for target_id in targets:
        try:
            if is_group:
                try:
                    chat = await client.get_chat(target_id)
                    if chat.type not in ["group", "supergroup"]:
                        continue
                except Exception:
                    # Only log the invalid group, do NOT remove from DB
                    removed_groups.append(str(target_id))
                    failed += 1
                    continue
            await send_func(target_id, **content_args)
            success += 1
        except Exception as e:
            failed += 1
        await asyncio.sleep(0.05)  # avoid hitting flood limits
    summary['success'] += success
    summary['failed'] += failed
    # Export removed group IDs if any
    if removed_groups:
        async with asyncio.Lock():
            with open(REMOVED_GROUPS_FILE, "a") as f:
                for gid in removed_groups:
                    f.write(gid + "\n")

@Client.on_message(filters.command("broadcast", prefixes=["/", ".", "!"]) & filters.private)
@owner_only
async def broadcast_command(client: Client, message: Message):
    db = get_database()
    if not message.reply_to_message and not (message.text and len(message.command) > 1):
        await message.reply("Reply to a message or use /broadcast <text> to broadcast.")
        return

    # Determine content to send
    content_args = {}
    send_func = client.send_message
    if message.reply_to_message:
        if message.reply_to_message.text:
            content_args['text'] = message.reply_to_message.text
        elif message.reply_to_message.photo:
            send_func = client.send_photo
            content_args['photo'] = message.reply_to_message.photo.file_id
            if message.reply_to_message.caption:
                content_args['caption'] = message.reply_to_message.caption
        elif message.reply_to_message.video:
            send_func = client.send_video
            content_args['video'] = message.reply_to_message.video.file_id
            if message.reply_to_message.caption:
                content_args['caption'] = message.reply_to_message.caption
        elif message.reply_to_message.document:
            send_func = client.send_document
            content_args['document'] = message.reply_to_message.document.file_id
            if message.reply_to_message.caption:
                content_args['caption'] = message.reply_to_message.caption
        else:
            await message.reply("Unsupported media type. Only text, photo, video, and document are supported.")
            return
    else:
        # /broadcast <text>
        content_args['text'] = message.text.split(None, 1)[1]

    await message.reply("Broadcast started. This may take a while...")

    # Get all user IDs and group IDs
    user_ids = await db.get_all_user_ids()
    group_ids = await db.get_all_group_ids()
    summary = {'success': 0, 'failed': 0}

    # Broadcast to users and groups
    await _broadcast_to_targets(client, user_ids, send_func, content_args, summary)
    await _broadcast_to_targets(client, group_ids, send_func, content_args, summary, is_group=True, db=db)

    await message.reply(f"Broadcast finished!\nSuccess: {summary['success']}\nFailed: {summary['failed']}")

def register_broadcast_handler(app: Client):
    app.add_handler(broadcast_command) 