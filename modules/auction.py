from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, InputMediaPhoto, InputMediaVideo
from pyrogram.enums import ChatType
from pyrogram import Client, filters
from modules.postgres_database import get_database, get_rarity_emoji
from modules.decorators import is_owner, is_og
from datetime import datetime, timedelta, timezone
import asyncio
import os

AUCTION_GROUP_ID = -1002621009797
ACTIVE_AUCTIONS = {}

RARITY_EMOJIS = {
    "Common": "⚪️", "Medium": "🟢", "Rare": "🟠", "Legendary": "🟡", "Exclusive": "🫧", "Elite": "💎",
    "Limited Edition": "🔮", "Ultimate": "🔱", "Supreme": "👑", "Mythic": "🔴", "Zenith": "💫", "Ethereal": "❄️", "Premium": "🧿"
}

BOT_USERNAME = os.environ.get("BOT_USERNAME", "CollectHeroesBot")

def parse_time(time_str):
    time_str = time_str.lower().strip()
    if time_str.endswith("h"):
        try:
            hours = float(time_str[:-1])
            return timedelta(hours=hours)
        except Exception:
            return None
    elif time_str.endswith("m"):
        try:
            minutes = float(time_str[:-1])
            return timedelta(minutes=minutes)
        except Exception:
            return None
    else:
        # Try to parse as minutes by default
        try:
            minutes = float(time_str)
            return timedelta(minutes=minutes)
        except Exception:
            return None

async def auction_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text("❌ <b>This command is restricted to owners and OGs only!</b>")
        return
    args = message.text.split()
    if len(args) < 4:
        await message.reply_text("❌ <b>Usage: /auction &lt;character_id&gt; &lt;base_price&gt; &lt;time&gt; (e.g. /auction 123 50000 30m or /auction 123 50000 2h)</b>")
        return
    try:
        char_id = int(args[1])
        base_price = int(args[2])
        if base_price < 1:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ <b>Invalid character ID or base price!</b>")
        return
    time_delta = parse_time(args[3])
    if not time_delta or time_delta.total_seconds() < 60 or time_delta.total_seconds() > 86400:
        await message.reply_text("❌ <b>Invalid time! Use e.g. 30m, 2h, or minutes/hours (min 1m, max 24h)</b>")
        return
    character = await db.get_character(char_id)
    if not character:
        await message.reply_text("❌ <b>Character not found!</b>")
        return
    # Check if already in auction
    if char_id in ACTIVE_AUCTIONS:
        await message.reply_text("❌ <b>This character is already in an active auction!</b>")
        return
    end_time = datetime.utcnow() + time_delta
    auction_id = f"AUC{char_id}_{int(end_time.timestamp())}"
    ACTIVE_AUCTIONS[char_id] = {
        "auction_id": auction_id,
        "character": character,
        "base_price": base_price,
        "end_time": end_time,
        "creator_id": user_id,
        "highest_bid": None,
        "highest_bidder": None,
        "bids": [],
        "active": True
    }
    rarity_emoji = RARITY_EMOJIS.get(character['rarity'], '❓')
    ist_offset = timedelta(hours=5, minutes=30)
    ist_time = end_time + ist_offset
    time_str = ist_time.strftime('%Y-%m-%d %I:%M:%S %p IST')
    min_next_bid = base_price + 10000
    caption = (
        f"<b>🏆 New Auction Created!</b>\n\n"
        f"<b>🆔 Auction ID:</b> <code>{auction_id}</code>\n"
        f"<b>👤 Character:</b> {character['name']}\n"
        f"{rarity_emoji} <b>Rarity:</b> {character['rarity']}\n"
        f"<b>💰 Base Price:</b> <code>{base_price}</code> tokens\n"
        f"<b>⏰ Ends At:</b> <code>{time_str}</code>\n"
        f"<b>To bid:</b> <code>/bid {auction_id} amount</code>\n"
        f"<b>Minimum Next Bid:</b> <code>{min_next_bid}</code> tokens\n"
        f"<b>Highest Bid:</b> None yet!\n"
    )
    bid_url = f"https://t.me/{BOT_USERNAME}?start=bid_{auction_id}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"auctionview_{auction_id}")]
    ])
    if character.get('is_video', False):
        sent_msg = await client.send_video(
            chat_id=AUCTION_GROUP_ID,
            video=character.get('img_url', character.get('file_id')),
            caption=caption,
            reply_markup=keyboard
        )
    else:
        sent_msg = await client.send_photo(
            chat_id=AUCTION_GROUP_ID,
            photo=character.get('img_url', character.get('file_id')),
            caption=caption,
            reply_markup=keyboard
        )
    try:
        await client.pin_chat_message(AUCTION_GROUP_ID, sent_msg.id, disable_notification=True)
    except Exception as e:
        print(f"Failed to pin auction message: {e}")
    await message.reply_text(f"✅ Auction created and announced in group!\nAuction ID: <code>{auction_id}</code>")
    asyncio.create_task(end_auction_after(client, char_id, auction_id, end_time))

async def end_auction_after(client, char_id, auction_id, end_time):
    now = datetime.utcnow()
    wait_time = (end_time - now).total_seconds()
    if wait_time > 0:
        await asyncio.sleep(wait_time)
    auction = ACTIVE_AUCTIONS.get(char_id)
    if not auction or not auction['active']:
        return
    auction['active'] = False
    char = auction['character']
    rarity_emoji = RARITY_EMOJIS.get(char['rarity'], '❓')
    winner_id = auction['highest_bidder']
    amount = auction['highest_bid']
    caption = (
        f"<b>🏁 Auction Ended!</b>\n\n"
        f"<b>🆔 Auction ID:</b> <code>{auction_id}</code>\n"
        f"<b>👤 Character:</b> {char['name']}\n"
        f"{rarity_emoji} <b>Rarity:</b> {char['rarity']}\n"
        f"<b>💰 Base Price:</b> <code>{auction['base_price']}</code> tokens\n"
    )
    if winner_id and amount:
        caption += (
            f"<b>🏆 Winner:</b> <a href='tg://user?id={winner_id}'>User {winner_id}</a>\n"
            f"<b>Bid:</b> <code>{amount}</code> tokens\n"
        )
    else:
        caption += "<b>No valid bids were placed. Character remains unclaimed.</b>\n"
    # Send image or video with result
    if char.get('is_video', False):
        sent_msg = await client.send_video(
            chat_id=AUCTION_GROUP_ID,
            video=char.get('img_url', char.get('file_id')),
            caption=caption
        )
    else:
        sent_msg = await client.send_photo(
            chat_id=AUCTION_GROUP_ID,
            photo=char.get('img_url', char.get('file_id')),
            caption=caption
        )
    # Pin the result message
    try:
        await client.pin_chat_message(AUCTION_GROUP_ID, sent_msg.id, disable_notification=True)
    except Exception as e:
        print(f"Failed to pin auction result: {e}")
    # Transfer character to winner if any
    if winner_id and amount:
        db = get_database()
        await db.add_character_to_user(winner_id, char_id, source='auction')
    del ACTIVE_AUCTIONS[char_id]

async def bid_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    args = message.text.split()
    if len(args) < 3:
        await message.reply_text("❌ <b>Usage: /bid &lt;auction_id&gt; &lt;amount&gt;</b>")
        return
    auction_id = args[1]
    try:
        amount = int(args[2])
        if amount < 1:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ <b>Invalid bid amount!</b>")
        return
    # Find auction by auction_id
    auction = None
    for auc in ACTIVE_AUCTIONS.values():
        if auc['auction_id'] == auction_id and auc['active']:
            auction = auc
            break
    if not auction:
        await message.reply_text("❌ <b>Auction not found or already ended!</b>")
        return
    # Prevent current highest bidder from bidding again
    if auction['highest_bidder'] == user_id:
        await message.reply_text("❌ <b>You are already the highest bidder. Wait for someone else to outbid you!</b>")
        return
    if datetime.utcnow() >= auction['end_time']:
        await message.reply_text("❌ <b>This auction has already ended!</b>")
        auction['active'] = False
        return
    user = await db.get_user(user_id)
    if not user or user.get('wallet', 0) < amount:
        await message.reply_text("❌ <b>Not enough tokens in your wallet!</b>")
        return
    # Minimum bid increment system (now 10,000)
    min_bid = auction['base_price'] if not auction['highest_bid'] else auction['highest_bid'] + 10000
    if amount < min_bid:
        await message.reply_text(f"❌ <b>Bid must be at least {min_bid} tokens!</b>")
        return
    # Refund previous highest bidder
    if auction['highest_bidder']:
        await db.update_user_wallet(auction['highest_bidder'], auction['highest_bid'])
    # Deduct tokens from new bidder
    await db.update_user_wallet(user_id, -amount)
    auction['highest_bid'] = amount
    auction['highest_bidder'] = user_id
    auction['bids'].append({'user_id': user_id, 'amount': amount, 'time': datetime.now()})
    await message.reply_text(f"✅ <b>Your bid of {amount} tokens has been placed! Minimum next bid: {amount + 10000} tokens.</b>")
    # Announce new highest bid in group
    await client.send_message(
        chat_id=AUCTION_GROUP_ID,
        text=(f"<b>🔔 New Highest Bid!</b>\n"
              f"<b>🆔 Auction ID:</b> <code>{auction_id}</code>\n"
              f"<b>Bidder:</b> <a href='tg://user?id={user_id}'>User {user_id}</a>\n"
              f"<b>Bid:</b> <code>{amount}</code> tokens\n"
              f"<b>Minimum Next Bid:</b> <code>{amount + 10000}</code> tokens"),
        disable_web_page_preview=True
    )

async def auctions_command(client: Client, message: Message):
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text("<b>Please use the /auctions command in the bot's DM (private chat).</b>")
        return
    if not ACTIVE_AUCTIONS:
        await message.reply_text("<b>❌ No active auctions at the moment.</b>")
        return
    buttons = []
    for auc in ACTIVE_AUCTIONS.values():
        char = auc['character']
        auction_id = auc['auction_id']
        label = f"{char['name']} ({char['rarity']})"
        buttons.append([InlineKeyboardButton(label, callback_data=f"auctionview_{auction_id}")])
    markup = InlineKeyboardMarkup(buttons)
    await message.reply_text("<b>🏆 Active Auctions:</b>", reply_markup=markup)

async def auction_view_callback(client: Client, callback_query: CallbackQuery):
    auction_id = callback_query.data.split('_', 1)[-1]
    auction = None
    for auc in ACTIVE_AUCTIONS.values():
        if auc['auction_id'] == auction_id and auc['active']:
            auction = auc
            break
    if not auction:
        await callback_query.answer("Auction not found or ended!", show_alert=True)
        return
    char = auction['character']
    rarity_emoji = RARITY_EMOJIS.get(char['rarity'], '❓')
    now = datetime.utcnow()
    time_left = auction['end_time'] - now
    if time_left.total_seconds() < 0:
        time_left_str = "Ended"
    else:
        mins, secs = divmod(int(time_left.total_seconds()), 60)
        hours, mins = divmod(mins, 60)
        if hours:
            time_left_str = f"{hours}h {mins}m {secs}s"
        else:
            time_left_str = f"{mins}m {secs}s"
    highest = auction['highest_bid']
    highest_bidder = auction['highest_bidder']
    min_next_bid = auction['base_price'] if not highest else highest + 10000
    if highest:
        highest_str = f"<b>💰 Highest Bid:</b> <code>{highest}</code> by <a href='tg://user?id={highest_bidder}'>User {highest_bidder}</a>"
    else:
        highest_str = "<b>💰 Highest Bid:</b> None yet!"
    caption = (
        f"<b>🏆 Auction Details</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👤 Character:</b> <code>{char['name']}</code>\n"
        f"{rarity_emoji} <b>Rarity:</b> <code>{char['rarity']}</code>\n"
        f"<b>🆔 Auction ID:</b> <code>{auction_id}</code>\n"
        f"<b>💰 Base Price:</b> <code>{auction['base_price']}</code> tokens\n"
        f"{highest_str}\n"
        f"<b>⏰ Time Left:</b> <code>{time_left_str}</code>\n"
        f"<b>Minimum Next Bid:</b> <code>{min_next_bid}</code> tokens\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>To bid:</b> <code>/bid {auction_id} amount</code>\n"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"auctionview_{auction_id}")]
    ])
    try:
        if char.get('is_video', False):
            media = InputMediaVideo(media=char.get('img_url', char.get('file_id')), caption=caption, parse_mode="html")
        else:
            media = InputMediaPhoto(media=char.get('img_url', char.get('file_id')), caption=caption, parse_mode="html")
        await callback_query.message.edit_media(
            media=media,
            reply_markup=markup
        )
    except Exception:
        # If can't edit media, just edit the caption as fallback
        await callback_query.message.edit_caption(
            caption=caption,
            reply_markup=markup
        )
    await callback_query.answer()

async def auctionview_back_callback(client: Client, callback_query: CallbackQuery):
    # Just call auctions_command for the user
    await auctions_command(client, callback_query.message)
    await callback_query.answer()

@Client.on_message(filters.command("cancelauction"))
async def cancel_auction_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    if not (is_owner(user_id) or await is_og(db, user_id)):
        await message.reply_text("❌ <b>This command is restricted to owners and OGs only!</b>")
        return
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.reply_text("❌ <b>Usage: /cancelauction &lt;character_id&gt;</b>")
        return
    char_id = int(args[1])
    print("DEBUG: ACTIVE_AUCTIONS keys:", list(ACTIVE_AUCTIONS.keys()))
    print("DEBUG: char_id type/value:", type(char_id), char_id)
    auction = ACTIVE_AUCTIONS.get(char_id)
    if not auction or not auction['active']:
        active_ids = [str(k) for k, v in ACTIVE_AUCTIONS.items() if v['active']]
        await message.reply_text(
            f"❌ <b>No active auction found for this character.</b>\n"
            f"Active auction character IDs: {', '.join(active_ids)}"
        )
        return
    # Refund the current highest bidder if there is one
    if auction['highest_bidder'] and auction['highest_bid']:
        await db.update_user_wallet(auction['highest_bidder'], auction['highest_bid'])
    auction['active'] = False
    del ACTIVE_AUCTIONS[char_id]
    await message.reply_text(f"✅ Auction for character {char_id} has been cancelled and bidders refunded.")
