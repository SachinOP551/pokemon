from datetime import datetime, timedelta
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram import Client
from modules.postgres_database import get_database
from .logging_utils import send_token_log
from .decorators import is_owner, is_og, is_sudo, check_banned
from pyrogram import filters
import random
import asyncio

from pyrogram.enums import ChatType

# BALANCE
@check_banned
async def balance_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    wallet = user.get('wallet', 0)
    bank = user.get('bank', 0)
    shards = user.get('shards', 0)
    loan_amount = user.get('loan_amount', 0)
    loan_active = user.get('loan_active', False)
    loan_defaulted = user.get('loan_defaulted', False)
    loan_due = user.get('loan_due')
    # Mark default if overdue
    if loan_active and loan_due:
        now = datetime.utcnow()
        try:
            due_dt = datetime.fromisoformat(loan_due) if isinstance(loan_due, str) else loan_due
        except Exception:
            due_dt = None
        if due_dt and now > due_dt and not loan_defaulted:
            await get_database().update_user(user_id, {'loan_defaulted': True})
            loan_defaulted = True
    due_text = ""
    if loan_due:
        if isinstance(loan_due, str):
            try:
                due_dt = datetime.fromisoformat(loan_due)
            except Exception:
                due_dt = None
        else:
            due_dt = loan_due
        if due_dt:
            due_text = f"\n• 📅 Loan Due: <code>{due_dt.strftime('%Y-%m-%d %H:%M')}</code>"
    await message.reply_text(
        f"💸 <b>Your current balance:</b>\n\n"
        f"• <b>Wallet:</b> <code>{wallet:,}</code>\n"
        f"• 🏦 <b>Bank Balance:</b> <code>{bank:,}</code>\n"
        f"• 🎐 <b>Shards:</b> <code>{shards:,}</code>\n"
        + (f"\n• 💳 <b>Active Loan:</b> <code>{loan_amount:,}</code>" if loan_active else "")
        + ("\n• 🚫 <b>Loan Status:</b> <code>Defaulted</code>" if loan_defaulted else "")
        + due_text
    )

# DEPOSIT
@check_banned
async def deposit_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in financial_locks:
        financial_locks[user_id] = asyncio.Lock()
    
    async with financial_locks[user_id]:
        db = get_database()
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("❌ <b>Please specify an amount to deposit!</b>")
            return
        try:
            amount = int(args[1])
            if amount <= 0:
                raise ValueError
            user = await db.get_user(user_id)
            wallet = user.get('wallet', 0)
            if wallet is None:
                wallet = 0
            if wallet < amount:
                await message.reply_text("❌ <b>You don't have enough tokens in your wallet!</b>")
                return
            bank = user.get('bank', 0)
            if bank is None:
                bank = 0
            await db.update_user(user_id, {'wallet': wallet - amount, 'bank': bank + amount})
            await message.reply_text(f"✅ <b>Successfully deposited</b> <code>{amount:,}</code> <b>tokens to your bank!</b>")
        except ValueError:
            await message.reply_text("❌ <b>Please provide a valid positive number!</b>")

# WITHDRAW
@check_banned
async def withdraw_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in financial_locks:
        financial_locks[user_id] = asyncio.Lock()
    
    async with financial_locks[user_id]:
        db = get_database()
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("❌ <b>Please specify an amount to withdraw!</b>")
            return
        try:
            amount = int(args[1])
            if amount <= 0:
                raise ValueError
            user = await db.get_user(user_id)
            wallet = user.get('wallet', 0)
            if wallet is None:
                wallet = 0
            bank = user.get('bank', 0)
            if bank is None:
                bank = 0
            if bank < amount:
                await message.reply_text("❌ <b>You don't have enough tokens in your bank!</b>")
                return
            await db.update_user(user_id, {'wallet': wallet + amount, 'bank': bank - amount})
            await message.reply_text(f"✅ <b>Successfully withdrew</b> <code>{amount:,}</code> <b>tokens from your bank!</b>")
            return
        except ValueError:
            await message.reply_text("❌ <b>Please provide a valid positive number!</b>")

# DAILY
@check_banned
async def daily_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    now = datetime.utcnow()
    last_daily = user.get('last_daily')
    if last_daily:
        if isinstance(last_daily, str):
            last_daily_dt = datetime.fromisoformat(last_daily)
        else:
            last_daily_dt = last_daily
        next_daily = last_daily_dt + timedelta(days=1)
        if now < next_daily:
            time_left = next_daily - now
            hours = time_left.seconds // 3600
            minutes = (time_left.seconds % 3600) // 60
            await message.reply_text(
                f"❌ <b>You've already claimed your daily reward!</b>\nPlease wait: <b>{hours}h {minutes}m</b>"
            )
            return
    reward = 5000
    wallet = user.get('wallet', 0)
    await db.update_user(user_id, {'wallet': wallet + reward, 'last_daily': now})
    await message.reply_text(f"✅ <b>Daily reward claimed!</b>\n\n💰 You received: <b>{reward:,}</b> tokens")

# WEEKLY
@check_banned
async def weekly_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    now = datetime.utcnow()
    last_weekly = user.get('last_weekly')
    if last_weekly:
        if isinstance(last_weekly, str):
            last_weekly_dt = datetime.fromisoformat(last_weekly)
        else:
            last_weekly_dt = last_weekly
        next_weekly = last_weekly_dt + timedelta(days=7)
        if now < next_weekly:
            time_left = next_weekly - now
            days = time_left.days
            hours = time_left.seconds // 3600
            await message.reply_text(
                f"❌ <b>You've already claimed your weekly reward!</b>\nPlease wait: <b>{days}d {hours}h</b>"
            )
            return
    reward = 15000
    wallet = user.get('wallet', 0)
    await db.update_user(user_id, {'wallet': wallet + reward, 'last_weekly': now})
    await message.reply_text(f"✅ <b>Weekly reward claimed!</b>\n\n💰 You received: <b>{reward:,}</b> tokens")

# MONTHLY
@check_banned
async def monthly_command(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    now = datetime.utcnow()
    last_monthly = user.get('last_monthly')
    if last_monthly:
        if isinstance(last_monthly, str):
            last_monthly_dt = datetime.fromisoformat(last_monthly)
        else:
            last_monthly_dt = last_monthly
        next_monthly = last_monthly_dt + timedelta(days=30)
        if now < next_monthly:
            time_left = next_monthly - now
            days = time_left.days
            hours = time_left.seconds // 3600
            await message.reply_text(
                f"❌ <b>You've already claimed your monthly reward!</b>\nPlease wait: <b>{days}d {hours}h</b>"
            )
            return
    reward = 35000
    wallet = user.get('wallet', 0)
    await db.update_user(user_id, {'wallet': wallet + reward, 'last_monthly': now})
    await message.reply_text(f"✅ <b>Monthly reward claimed!</b>\n\n💰 You received: <b>{reward:,}</b> tokens")

# GIVE TOKENS (ADMIN, REPLY)
@check_banned
async def give_tokens(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    # Check admin
    if not (is_owner(user_id) or user.get('og', False) or user.get('sudo', False)):
        await message.reply_text("❌ <b>This command is restricted to admins only!</b>")
        return
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Please reply to a user's message!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Please specify the amount of tokens!</b>")
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
        target_user = message.reply_to_message.from_user
        target_data = await db.get_user(target_user.id)
        if not target_data:
            await db.add_user({
                'user_id': target_user.id,
                'username': target_user.username,
                'first_name': target_user.first_name,
                'wallet': amount,
                'bank': 0,
                'characters': [],
                'last_daily': None,
                'last_weekly': None,
                'last_monthly': None,
                'sudo': False,
                'og': False,
                'collection_preferences': {'mode': 'default', 'filter': None}
            })
        else:
            new_balance = target_data.get('wallet', 0) + amount
            await db.update_user(target_user.id, {'wallet': new_balance})
        await message.reply_text(f"✅ <b>Successfully gave</b> <code>{amount:,}</code> <b>tokens to</b> {target_user.mention}")
        await send_token_log(client, message.from_user, target_user, amount, action="give_tokens (gbheek)")
    except ValueError:
        await message.reply_text("❌ <b>Please provide a valid positive number!</b>")

# TAKE TOKENS (ADMIN, REPLY)
@check_banned
async def take_tokens(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not (is_owner(user_id) or user.get('og', False) or user.get('sudo', False)):
        await message.reply_text("❌ <b>This command is restricted to admins only!</b>")
        return
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Please reply to a user's message!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Please specify the amount of tokens!</b>")
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
        target_user = message.reply_to_message.from_user
        target_data = await db.get_user(target_user.id)
        if not target_data:
            await message.reply_text("❌ <b>User not found!</b>")
            return
        wallet = target_data.get('wallet', 0)
        if wallet < amount:
            await message.reply_text("❌ <b>User doesn't have enough tokens!</b>")
            return
        new_balance = wallet - amount
        await db.update_user(target_user.id, {'wallet': new_balance})
        await message.reply_text(f"✅ <b>Successfully taken</b> <code>{amount:,}</code> <b>tokens from</b> {target_user.mention}")
        await send_token_log(client, message.from_user, target_user, amount, action="take_tokens (gbheek)")
    except ValueError:
        await message.reply_text("❌ <b>Please provide a valid positive number!</b>")

# PAY TOKENS (REPLY)
@check_banned
async def pay_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in financial_locks:
        financial_locks[user_id] = asyncio.Lock()
    
    async with financial_locks[user_id]:
        now = datetime.utcnow()
        last_used = pay_last_used.get(user_id)
        if last_used and (now - last_used).total_seconds() < PAY_COOLDOWN:
            seconds_left = PAY_COOLDOWN - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before making another payment.")
            return
        
        pay_last_used[user_id] = now
        
        db = get_database()
        if not message.reply_to_message:
            await message.reply_text("❌ <b>Please reply to a user's message!</b>")
            return
        args = message.text.split()
        if len(args) < 2:
            await message.reply_text("❌ <b>Please specify the amount of tokens!</b>")
            return
        sender = message.from_user
        receiver = message.reply_to_message.from_user
        if sender.id == receiver.id:
            await message.reply_text("❌ <b>You cannot pay tokens to yourself!</b>")
            return
        if receiver.is_bot:
            await message.reply_text("❌ <b>You cannot pay tokens to the bot!</b>")
            return
        try:
            amount = int(args[1])
            if amount <= 0:
                raise ValueError
        except ValueError:
            await message.reply_text("❌ <b>Please provide a valid positive number!</b>")
            return
        sender_data = await db.get_user(sender.id)
        if not sender_data:
            await message.reply_text("❌ <b>You don't have an account!</b>")
            return
        sender_wallet = sender_data.get('wallet', 0)
        if sender_wallet < amount:
            await message.reply_text("❌ <b>You don't have enough tokens!</b>")
            return
        receiver_data = await db.get_user(receiver.id)
        if not receiver_data:
            await db.add_user({
                'user_id': receiver.id,
                'username': receiver.username,
                'first_name': receiver.first_name,
                'wallet': amount,
                'bank': 0,
                'characters': [],
                'groups': []
            })
        else:
            receiver_wallet = receiver_data.get('wallet', 0)
            await db.update_user(receiver.id, {'wallet': receiver_wallet + amount})
        await db.update_user(sender.id, {'wallet': sender_wallet - amount})
        await message.reply_text(f"✅ <b>Payment successful!</b>\n\n💰 <b>{amount:,}</b> tokens paid to {receiver.mention}")

        # Log transaction for both sender and receiver
        now = datetime.utcnow().strftime('%Y-%m-%d %H:%M')
        await db.log_user_transaction(sender.id, "pay_sent", {
            "to_user_id": receiver.id,
            "to_user_name": receiver.first_name,
            "amount": amount,
            "date": now
        })
        await db.log_user_transaction(receiver.id, "pay_received", {
            "from_user_id": sender.id,
            "from_user_name": sender.first_name,
            "amount": amount,
            "date": now
        })

@check_banned
async def shards_pay(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    # Only allow /spay when replying to a user
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply_text("❌ <b>You must reply to a user's message to pay shards!</b>")
        return
    receiver = message.reply_to_message.from_user
    if receiver.is_bot or receiver.id == user_id:
        await message.reply_text("❌ <b>Invalid target user!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Please specify the amount of shards!</b>")
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.reply_text("❌ <b>Please provide a valid positive number!</b>")
        return
    sender_data = await db.get_user(user_id)
    if not sender_data or sender_data.get('shards', 0) < amount:
        await message.reply_text("❌ <b>You don't have enough 🎐 shards!</b>")
        return
    receiver_data = await db.get_user(receiver.id)
    if not receiver_data:
        await db.add_user({
            'user_id': receiver.id,
            'username': receiver.username,
            'first_name': receiver.first_name,
            'wallet': 0,
            'bank': 0,
            'shards': amount,
            'characters': [],
            'groups': []
        })
    else:
        receiver_shards = receiver_data.get('shards', 0)
        await db.update_user(receiver.id, {'shards': receiver_shards + amount})
    sender_shards = sender_data.get('shards', 0)
    await db.update_user(user_id, {'shards': sender_shards - amount})
    await message.reply_text(f"✅ <b>Shards payment successful!</b>\n\n🎐 <b>{amount:,}</b> shards paid to {receiver.mention}")

# GIVE SHARDS (ADMIN, REPLY)
@check_banned
async def give_shards(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    # Check admin
    if not (is_owner(user_id) or user.get('og', False) or user.get('sudo', False)):
        await message.reply_text("❌ <b>This command is restricted to admins only!</b>")
        return
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Please reply to a user's message!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Please specify the amount of shards!</b>")
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
        target_user = message.reply_to_message.from_user
        target_data = await db.get_user(target_user.id)
        if not target_data:
            await db.add_user({
                'user_id': target_user.id,
                'username': target_user.username,
                'first_name': target_user.first_name,
                'wallet': 0,
                'bank': 0,
                'shards': amount,
                'characters': [],
                'last_daily': None,
                'last_weekly': None,
                'last_monthly': None,
                'sudo': False,
                'og': False,
                'collection_preferences': {'mode': 'default', 'filter': None}
            })
        else:
            new_balance = target_data.get('shards', 0) + amount
            await db.update_user(target_user.id, {'shards': new_balance})
        await message.reply_text(f"✅ <b>Successfully gave</b> <code>{amount:,}</code> <b>🎐 shards to</b> {target_user.mention}")
    except ValueError:
        await message.reply_text("❌ <b>Please provide a valid positive number!</b>")

# TAKE SHARDS (ADMIN, REPLY)
@check_banned
async def take_shards(client: Client, message: Message):
    db = get_database()
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not (is_owner(user_id) or user.get('og', False) or user.get('sudo', False)):
        await message.reply_text("❌ <b>This command is restricted to admins only!</b>")
        return
    if not message.reply_to_message:
        await message.reply_text("❌ <b>Please reply to a user's message!</b>")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Please specify the amount of shards!</b>")
        return
    try:
        amount = int(args[1])
        if amount <= 0:
            raise ValueError
        target_user = message.reply_to_message.from_user
        target_data = await db.get_user(target_user.id)
        if not target_data:
            await message.reply_text("❌ <b>User not found!</b>")
            return
        shards = target_data.get('shards', 0)
        if shards < amount:
            await message.reply_text("❌ <b>User doesn't have enough 🎐 shards!</b>")
            return
        new_balance = shards - amount
        await db.update_user(target_user.id, {'shards': new_balance})
        await message.reply_text(f"✅ <b>Successfully taken</b> <code>{amount:,}</code> <b>🎐 shards from</b> {target_user.mention}")
    except ValueError:
        await message.reply_text("❌ <b>Please provide a valid positive number!</b>")



# Cooldown and lock dictionaries for each game command
football_locks = {}
football_last_used = {}
dart_locks = {}
dart_last_used = {}
basket_locks = {}
basket_last_used = {}
roll_locks = {}
roll_last_used = {}
slot_locks = {}
slot_last_used = {}
bowl_locks = {}
bowl_last_used = {}

# Payment locks to prevent farming
pay_locks = {}
pay_last_used = {}
sspay_locks = {}
sspay_last_used = {}

# Financial operation locks to prevent race conditions
financial_locks = {}

COOLDOWN_MIN = 120
COOLDOWN_MAX = 180
football_cooldowns = {}
dart_cooldowns = {}
basket_cooldowns = {}
roll_cooldowns = {}
slot_cooldowns = {}
bowl_cooldowns = {}

# Payment cooldown (30 seconds between payments)
PAY_COOLDOWN = 30

# Loan system constants
MAX_LOAN = 5_000_000  # 50 lakh tokens
LOAN_DAYS = 7
# Optional testing override. When >0, due date uses minutes instead of days.
LOAN_TEST_MINUTES = 0

def get_loan_due():
    now = datetime.utcnow()
    if LOAN_TEST_MINUTES and LOAN_TEST_MINUTES > 0:
        return now + timedelta(minutes=LOAN_TEST_MINUTES), f"{LOAN_TEST_MINUTES} minute(s)"
    return now + timedelta(days=LOAN_DAYS), f"{LOAN_DAYS} day(s)"

def get_loan_terms(amount: int):
    """Return weekly interest rate and daily late penalty based on tiers.

    Rates are returned as decimal fractions, e.g., 0.02 for 2%.
    """
    if amount <= 500_000:
        return 0.02, 0.01, "Starter / low risk"
    if amount <= 1_500_000:
        return 0.03, 0.01, "Medium-sized loans"
    if amount <= 3_000_000:
        return 0.04, 0.01, "Higher risk loans"
    # Up to MAX_LOAN
    return 0.05, 0.01, "Max loan, strong repayment required"

@check_banned
async def loan_request_command(client: Client, message: Message):
    # Check if command is used in bot DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "💡 <b>Please send this command in a private chat with the bot.</i>"
        )
        return
    
    db = get_database()
    try:
        await db.ensure_loan_columns()
    except Exception:
        pass
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    
    # Check character collection requirement using collection_history
    collection_history = user.get('collection_history', [])
    if not collection_history:
        collection_history = []
    
    # Count characters collected from legitimate sources (excluding admin commands)
    legitimate_collections = 0
    for entry in collection_history:
        if isinstance(entry, dict) and entry.get('source') == 'collected':
            legitimate_collections += 1
    
    if legitimate_collections < 150:
        await message.reply_text(
            "❌ <b>Loan requirement not met!</b>\n\n"
            f"• <b>Required:</b> At least 150 characters collected\n"
            f"• <b>Your legitimate collections:</b> {legitimate_collections} characters\n"
            f"• <b>Still needed:</b> {max(0, 150 - legitimate_collections)} characters\n\n"
            "🎯 <b>Keep collecting characters to unlock loan access!</b>\n"
            "💡 <i>Only characters collected from drops count towards this requirement.</i>"
        )
        return
    
    args = (message.text or "").split()
    if len(args) < 2:
        await message.reply_text(f"❌ <b>Usage:</b> <code>/loan amount</code> (max {MAX_LOAN:,})")
        return
    try:
        amount = int(args[1])
    except ValueError:
        await message.reply_text("❌ <b>Amount must be a number.</b>")
        return
    if amount <= 0 or amount > MAX_LOAN:
        await message.reply_text(f"❌ <b>Amount must be between 1 and {MAX_LOAN:,}.</b>")
        return
    # If overdue, mark default now
    try:
        loan_due = user.get('loan_due')
        if user.get('loan_active', False) and loan_due:
            due_dt = datetime.fromisoformat(loan_due) if isinstance(loan_due, str) else loan_due
            if due_dt and datetime.utcnow() > due_dt and not user.get('loan_defaulted', False):
                await db.update_user(user_id, {'loan_defaulted': True})
                user['loan_defaulted'] = True
    except Exception:
        pass
    
    # Get fresh user data to check current loan status
    current_user = await db.get_user(user_id)
    if current_user.get('loan_defaulted', False):
        await message.reply_text("🚫 <b>You are not eligible for new loans due to a previous default.</b>")
        return
    if user.get('loan_active', False):
        await message.reply_text("⚠️ <b>You already have an active loan. Repay it before requesting another.</b>")
        return
    # Show terms preview in user's chat
    weekly_interest_rate, daily_penalty_rate, notes = get_loan_terms(amount)
    base_interest = int(round(amount * weekly_interest_rate))
    preview_total = amount + base_interest
    _, duration_text = get_loan_due()
    pending = {
        'type': 'loan_request',
        'amount': amount,
        'requested_at': datetime.utcnow().isoformat()
    }
    await db.update_user(user_id, {'active_action': pending})
    await message.reply_text(
        "✅ <b>Your loan request has been submitted for owner approval.</b>\n\n"
        f"• <b>Weekly Interest:</b> <code>{int(weekly_interest_rate*100)}%</code>\n"
        f"• <b>Late Penalty:</b> <code>{int(daily_penalty_rate*100)}%/day</code> after due\n"
        f"• <b>Estimated Due in {duration_text}:</b> <code>{preview_total:,}</code> tokens\n"
        f"• <b>Tier:</b> {notes}"
    )

    # Notify owner via DM with Approve/Decline buttons
    try:
        from config import OWNER_ID
        requester = message.from_user
        approve_cb = f"loan_approve_{user_id}"
        decline_cb = f"loan_decline_{user_id}"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Approve", callback_data=approve_cb),
                InlineKeyboardButton("❌ Decline", callback_data=decline_cb),
            ]
        ])
        text = (
            "📝 <b>Loan Approval Request</b>\n\n"
            f"• <b>User:</b> <code>{requester.id}</code> ({requester.first_name or 'User'})\n"
            f"• <b>Amount:</b> <code>{amount:,}</code>\n"
            f"• <b>Weekly Interest:</b> <code>{int(weekly_interest_rate*100)}%</code>\n"
            f"• <b>Late Penalty:</b> <code>{int(daily_penalty_rate*100)}%/day</code>\n"
            f"• <b>Tier:</b> {notes}\n"
            f"• <b>Estimated Due in {duration_text}:</b> <code>{preview_total:,}</code>\n"
            f"• <b>Requested At (UTC):</b> <code>{pending['requested_at']}</code>\n\n"
            "Use the buttons below to approve or decline."
        )
        await client.send_message(OWNER_ID, text, reply_markup=keyboard)
    except Exception:
        # If DM fails (owner blocked bot), we silently ignore here
        pass

@check_banned
async def loan_approve_command(client: Client, message: Message):
    db = get_database()
    try:
        await db.ensure_loan_columns()
    except Exception:
        pass
    from config import OWNER_ID
    if message.from_user.id != OWNER_ID:
        await message.reply_text("❌ <b>Only owner can approve loans.</b>")
        return
    args = (message.text or "").split()
    if len(args) < 2:
        await message.reply_text("❌ <b>Usage:</b> <code>/loanapprove user_id</code>")
        return
    try:
        target_id = int(args[1])
    except ValueError:
        await message.reply_text("❌ <b>Invalid user_id.</b>")
        return
    user = await db.get_user(target_id)
    if not user:
        await message.reply_text("❌ <b>User not found.</b>")
        return
    action = user.get('active_action') or {}
    if not isinstance(action, dict) or action.get('type') != 'loan_request':
        await message.reply_text("❌ <b>No pending loan request for this user.</b>")
        return
    try:
        amount = int(action.get('amount') or 0)
    except Exception:
        amount = 0
    if amount <= 0 or amount > MAX_LOAN:
        await message.reply_text("❌ <b>Invalid loan amount in request.</b>")
        return
    # Check character collection requirement using collection_history
    collection_history = user.get('collection_history', [])
    if not collection_history:
        collection_history = []
    
    # Count characters collected from legitimate sources (excluding admin commands)
    legitimate_collections = 0
    for entry in collection_history:
        if isinstance(entry, dict) and entry.get('source') == 'collected':
            legitimate_collections += 1
    
    if legitimate_collections < 150:
        await message.reply_text(
            f"❌ <b>User {target_id} is not eligible for a loan!</b>\n\n"
            f"• <b>Required:</b> At least 150 characters collected\n"
            f"• <b>User's legitimate collections:</b> {legitimate_collections} characters\n"
            f"• <b>Still needed:</b> {max(0, 150 - legitimate_collections)} characters\n\n"
            "💡 <i>Only characters collected from drops count towards this requirement.</i>"
        )
        return
    
    if user.get('loan_defaulted', False) or user.get('loan_active', False):
        await message.reply_text("❌ <b>User not eligible for loan.</b>")
        return
    due, duration_text = get_loan_due()
    wallet = user.get('wallet', 0) or 0
    weekly_interest_rate, daily_penalty_rate, notes = get_loan_terms(amount)
    base_interest = int(round(amount * weekly_interest_rate))
    base_due = amount + base_interest
    await db.update_user(target_id, {
        'wallet': wallet + amount,
        'loan_amount': amount,
        'loan_due': due,
        'loan_active': True,
        'loan_defaulted': False,  # Reset defaulted status for new loan
        'loan_interest_rate': weekly_interest_rate,
        'loan_penalty_rate': daily_penalty_rate,
        'loan_base_due': base_due,
        'loan_tier': notes,
        'active_action': None
    })
    await message.reply_text(
        f"✅ <b>Approved loan of</b> <code>{amount:,}</code> <b>to</b> <code>{target_id}</code>.\n"
        f"• <b>Base Due in {duration_text}:</b> <code>{base_due:,}</code> (incl. interest)\n"
        f"• <b>Due Date (UTC):</b> <code>{due.strftime('%Y-%m-%d %H:%M')}</code>\n"
        f"• <b>Late Penalty:</b> <code>{int(daily_penalty_rate*100)}%/day</code>"
    )


async def handle_loan_callback(client: Client, callback_query: CallbackQuery):
    """Handle owner inline approvals/declines for loan requests."""
    from config import OWNER_ID
    if not callback_query.from_user or callback_query.from_user.id != OWNER_ID:
        await callback_query.answer("Unauthorized", show_alert=True)
        return
    data = callback_query.data or ""
    try:
        action, user_id_str = data.rsplit("_", 1)
        # action is like 'loan_approve' or 'loan_decline'
        user_id = int(user_id_str)
    except Exception:
        await callback_query.answer("Invalid data", show_alert=True)
        return
    db = get_database()
    try:
        await db.ensure_loan_columns()
    except Exception:
        pass
    user = await db.get_user(user_id)
    if not user:
        await callback_query.answer("User not found", show_alert=True)
        try:
            await callback_query.edit_message_reply_markup(None)
        except Exception:
            pass
        return
    pending = user.get('active_action') or {}
    if not isinstance(pending, dict) or pending.get('type') != 'loan_request':
        await callback_query.answer("No pending request", show_alert=True)
        try:
            await callback_query.edit_message_reply_markup(None)
        except Exception:
            pass
        return
    # Common: disable buttons after handling
    try:
        await callback_query.edit_message_reply_markup(None)
    except Exception:
        pass
    if action == 'loan_approve':
        try:
            amount = int(pending.get('amount') or 0)
        except Exception:
            amount = 0
        if amount <= 0 or amount > MAX_LOAN:
            await callback_query.answer("Invalid amount", show_alert=True)
            return
        
        # Check character collection requirement using collection_history
        collection_history = user.get('collection_history', [])
        if not collection_history:
            collection_history = []
        
        # Count characters collected from legitimate sources (excluding admin commands)
        legitimate_collections = 0
        for entry in collection_history:
            if isinstance(entry, dict) and entry.get('source') == 'collected':
                legitimate_collections += 1
        
        if legitimate_collections < 150:
            await callback_query.answer("User needs 150+ legitimate collections", show_alert=True)
            return
        
        # Eligibility re-check
        if user.get('loan_defaulted', False) or user.get('loan_active', False):
            await callback_query.answer("User not eligible", show_alert=True)
            return
        due, duration_text = get_loan_due()
        wallet = user.get('wallet', 0) or 0
        weekly_interest_rate, daily_penalty_rate, notes = get_loan_terms(amount)
        base_interest = int(round(amount * weekly_interest_rate))
        base_due = amount + base_interest
        await db.update_user(user_id, {
            'wallet': wallet + amount,
            'loan_amount': amount,
            'loan_due': due,
            'loan_active': True,
            'loan_defaulted': False,  # Reset defaulted status for new loan
            'loan_interest_rate': weekly_interest_rate,
            'loan_penalty_rate': daily_penalty_rate,
            'loan_base_due': base_due,
            'loan_tier': notes,
            'active_action': None
        })
        # Notify owner and user
        await callback_query.answer("Approved", show_alert=False)
        try:
            await client.send_message(
                user_id,
                (
                    f"✅ Your loan of <code>{amount:,}</code> was approved!\n"
                    f"• <b>Base Due in {duration_text}:</b> <code>{base_due:,}</code> (incl. interest)\n"
                    f"• <b>Due Date (UTC):</b> <code>{due.strftime('%Y-%m-%d %H:%M')}</code>\n"
                    f"• <b>Late Penalty:</b> <code>{int(daily_penalty_rate*100)}%/day</code>"
                )
            )
        except Exception:
            pass
        try:
            await callback_query.message.reply(f"✅ Approved loan for <code>{user_id}</code>: <code>{amount:,}</code>")
        except Exception:
            pass
    elif action == 'loan_decline':
        # Clear pending action
        await db.update_user(user_id, {'active_action': None})
        await callback_query.answer("Declined", show_alert=False)
        try:
            await client.send_message(user_id, "❌ Your loan request was declined by the owner.")
        except Exception:
            pass
        try:
            await callback_query.message.reply(f"❌ Declined loan request for <code>{user_id}</code>.")
        except Exception:
            pass
    else:
        await callback_query.answer("Unknown action", show_alert=True)

@check_banned
async def loan_repay_command(client: Client, message: Message):
    # Check if command is used in bot DM only
    if message.chat.type != ChatType.PRIVATE:
        await message.reply_text(
            "💡 <b>Please send this command in a private chat with the bot.</i>"
        )
        return
    
    db = get_database()
    try:
        await db.ensure_loan_columns()
    except Exception:
        pass
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    if not user.get('loan_active', False):
        await message.reply_text("ℹ️ <b>You have no active loan.</b>")
        return
    loan_amount = int(user.get('loan_amount', 0) or 0)
    if loan_amount <= 0:
        await db.update_user(user_id, {'loan_active': False, 'loan_amount': 0, 'loan_due': None})
        await message.reply_text("✅ <b>Loan cleared.</b>")
        return
    # If overdue, mark default flag (repayment still allowed but future loans blocked)
    try:
        loan_due = user.get('loan_due')
        due_dt = datetime.fromisoformat(loan_due) if isinstance(loan_due, str) else loan_due
        if due_dt and datetime.utcnow() > due_dt and not user.get('loan_defaulted', False):
            await db.update_user(user_id, {'loan_defaulted': True})
            user['loan_defaulted'] = True
    except Exception:
        pass
    # Compute total due: principal + weekly interest + daily late penalty (if overdue)
    try:
        weekly_interest_rate = float(user.get('loan_interest_rate') or 0)
    except Exception:
        weekly_interest_rate = 0.0
    try:
        daily_penalty_rate = float(user.get('loan_penalty_rate') or 0.01)
    except Exception:
        daily_penalty_rate = 0.01
    base_interest = int(round(loan_amount * weekly_interest_rate))
    base_due = loan_amount + base_interest
    # Late penalty per day on principal
    overdue_days = 0
    try:
        loan_due = user.get('loan_due')
        due_dt = datetime.fromisoformat(loan_due) if isinstance(loan_due, str) else loan_due
        if due_dt and datetime.utcnow() > due_dt:
            delta = datetime.utcnow() - due_dt
            overdue_days = max(1, (delta.days if delta.seconds == 0 else delta.days + 1))
    except Exception:
        overdue_days = 0
    penalty = int(round(loan_amount * daily_penalty_rate * overdue_days)) if overdue_days > 0 else 0
    total_due = base_due + penalty
    wallet = user.get('wallet', 0) or 0
    if wallet < total_due:
        await message.reply_text(
            "❌ <b>Insufficient wallet balance.</b>\n"
            f"• <b>Required:</b> <code>{total_due:,}</code> (Principal + Interest + Penalty)\n"
            f"• <b>Your Wallet:</b> <code>{wallet:,}</code>\n"
            f"• <b>Breakdown:</b> Principal <code>{loan_amount:,}</code> + Interest <code>{base_interest:,}</code>"
            + (f" + Penalty <code>{penalty:,}</code> ({overdue_days} day(s))" if penalty else "")
        )
        return
    await db.update_user(user_id, {
        'wallet': wallet - total_due,
        'loan_amount': 0,
        'loan_due': None,
        'loan_active': False,
        'loan_defaulted': False,  # Reset defaulted status when loan is repaid
        'loan_interest_rate': None,
        'loan_penalty_rate': None,
        'loan_base_due': None,
        'loan_tier': None
    })
    await message.reply_text(
        "✅ <b>Loan repaid. Thank you!</b>\n"
        f"• <b>Paid:</b> <code>{total_due:,}</code>\n"
        f"• <b>Breakdown:</b> Principal <code>{loan_amount:,}</code> + Interest <code>{base_interest:,}</code>"
        + (f" + Penalty <code>{penalty:,}</code> ({overdue_days} day(s))" if penalty else "")
    )

@check_banned
async def football_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in football_locks:
        football_locks[user_id] = asyncio.Lock()
    async with football_locks[user_id]:
        now = datetime.utcnow()
        last_used = football_last_used.get(user_id)
        cooldown = football_cooldowns.get(user_id, COOLDOWN_MIN)
        if last_used and (now - last_used).total_seconds() < cooldown:
            seconds_left = cooldown - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before using this command again.")
            return
        football_last_used[user_id] = now
        football_cooldowns[user_id] = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        try:
            if message.from_user is None or message.from_user.is_bot:
                await message.reply_text("❌ <b>Only real users can play this game!</b>")
                return
            dice = await client.send_dice(
                chat_id=message.chat.id,
                emoji="⚽"
            )
            if not hasattr(dice, 'dice') or dice.dice is None:
                await message.reply_text("❌ <b>Failed to send football. Please try again later.</b>")
                return
            await asyncio.sleep(3)
            # Score is a goal if value is 4 or 5
            if dice.dice.value in (4, 5):
                reward = random.randint(100, 600)
                db = get_database()
                user = await db.get_user(user_id)
                if not user:
                    await message.reply_text("❌ <b>You need an account to receive rewards. Use /start first!</b>")
                    return
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + reward})
                await db.log_user_transaction(user_id, "football_win", {
                    "reward": reward,
                    "chat_id": message.chat.id,
                    "date": datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                })
                await message.reply_text(f"⚽ <b>GOOOAL! You won {reward} 🎐 shards!</b>", reply_to_message_id=message.id)
            else:
                await message.reply_text("😢 <b>Missed the goal. Try again!</b>", reply_to_message_id=message.id)
        except Exception as e:
            await message.reply_text(f"❌ <b>Error:</b> {e}")

@check_banned
async def dart_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in dart_locks:
        dart_locks[user_id] = asyncio.Lock()
    async with dart_locks[user_id]:
        now = datetime.utcnow()
        last_used = dart_last_used.get(user_id)
        cooldown = dart_cooldowns.get(user_id, COOLDOWN_MIN)
        if last_used and (now - last_used).total_seconds() < cooldown:
            seconds_left = cooldown - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before using this command again.")
            return
        dart_last_used[user_id] = now
        dart_cooldowns[user_id] = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        try:
            if message.from_user is None or message.from_user.is_bot:
                await message.reply_text("❌ <b>Only real users can play this game!</b>")
                return
            dice = await client.send_dice(
                chat_id=message.chat.id,
                emoji="🎯"
            )
            if not hasattr(dice, 'dice') or dice.dice is None:
                await message.reply_text("❌ <b>Failed to send dart. Please try again later.</b>")
                return
            await asyncio.sleep(3)
            if dice.dice.value == 6:
                reward = random.randint(100, 600)
                db = get_database()
                user = await db.get_user(user_id)
                if not user:
                    await message.reply_text("❌ <b>You need an account to receive rewards. Use /start first!</b>")
                    return
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + reward})
                await db.log_user_transaction(user_id, "dart_win", {
                    "reward": reward,
                    "chat_id": message.chat.id,
                    "date": datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                })
                await message.reply_text(f"🎯 <b>Bullseye! You won {reward} 🎐 shards!</b>", reply_to_message_id=message.id)
            else:
                await message.reply_text("😢 <b>Missed the bullseye. Try again!</b>", reply_to_message_id=message.id)
        except Exception as e:
            await message.reply_text(f"❌ <b>Error:</b> {e}")

@check_banned
async def basket_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in basket_locks:
        basket_locks[user_id] = asyncio.Lock()
    async with basket_locks[user_id]:
        now = datetime.utcnow()
        last_used = basket_last_used.get(user_id)
        cooldown = basket_cooldowns.get(user_id, COOLDOWN_MIN)
        if last_used and (now - last_used).total_seconds() < cooldown:
            seconds_left = cooldown - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before using this command again.")
            return
        basket_last_used[user_id] = now
        basket_cooldowns[user_id] = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        try:
            if message.from_user is None or message.from_user.is_bot:
                await message.reply_text("❌ <b>Only real users can play this game!</b>")
                return
            dice = await client.send_dice(
                chat_id=message.chat.id,
                emoji="🏀"
            )
            if not hasattr(dice, 'dice') or dice.dice is None:
                await message.reply_text("❌ <b>Failed to send basketball. Please try again later.</b>")
                return
            await asyncio.sleep(3)
            if dice.dice.value in (4, 5):
                reward = random.randint(100, 600)
                db = get_database()
                user = await db.get_user(user_id)
                if not user:
                    await message.reply_text("❌ <b>You need an account to receive rewards. Use /start first!</b>")
                    return
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + reward})
                await db.log_user_transaction(user_id, "basket_win", {
                    "reward": reward,
                    "chat_id": message.chat.id,
                    "date": datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                })
                await message.reply_text(f"🏀 <b>Nice shot! You won {reward} 🎐 shards!</b>", reply_to_message_id=message.id)
            else:
                await message.reply_text("😢 <b>Missed the basket. Try again!</b>", reply_to_message_id=message.id)
        except Exception as e:
            await message.reply_text(f"❌ <b>Error:</b> {e}")

@check_banned
async def roll_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in roll_locks:
        roll_locks[user_id] = asyncio.Lock()
    async with roll_locks[user_id]:
        now = datetime.utcnow()
        last_used = roll_last_used.get(user_id)
        cooldown = roll_cooldowns.get(user_id, COOLDOWN_MIN)
        if last_used and (now - last_used).total_seconds() < cooldown:
            seconds_left = cooldown - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before using this command again.")
            return
        roll_last_used[user_id] = now
        roll_cooldowns[user_id] = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        try:
            args = message.text.split()
            if len(args) < 2:
                await message.reply_text("<b>ℹ️ Please specify a number between 1 and 6, like this: /roll 5</b>")
                return
            if message.from_user is None or message.from_user.is_bot:
                await message.reply_text("❌ <b>Only real users can play this game!</b>")
                return
            try:
                user_number = int(args[1])
            except ValueError:
                await message.reply_text("❌ <b>Please provide a valid number between 1 and 6.</b>")
                return
            if not (1 <= user_number <= 6):
                await message.reply_text("❌ <b>Please provide a number between 1 and 6.</b>")
                return
            dice = await client.send_dice(
                chat_id=message.chat.id,
                emoji="🎲"
            )
            if not hasattr(dice, 'dice') or dice.dice is None:
                await message.reply_text("❌ <b>Failed to roll the dice. Please try again later.</b>")
                return
            await asyncio.sleep(3)
            rolled = dice.dice.value
            if rolled == user_number:
                reward = random.randint(100, 600)
                db = get_database()
                user = await db.get_user(user_id)
                if not user:
                    await message.reply_text("❌ <b>You need an account to receive rewards. Use /start first!</b>")
                    return
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + reward})
                await message.reply_text(f"🎲 <b>Congrats! You guessed {user_number} and rolled {rolled}!</b>\nYou won <b>{reward} 🎐 shards!</b>", reply_to_message_id=message.id)
            else:
                await message.reply_text(f"🎲 <b>You guessed {user_number}, but rolled {rolled}. No reward this time!</b>", reply_to_message_id=message.id)
        except Exception as e:
            await message.reply_text(f"❌ <b>Error:</b> {e}")

@check_banned
async def slot_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in slot_locks:
        slot_locks[user_id] = asyncio.Lock()
    async with slot_locks[user_id]:
        now = datetime.utcnow()
        last_used = slot_last_used.get(user_id)
        cooldown = slot_cooldowns.get(user_id, COOLDOWN_MIN)
        if last_used and (now - last_used).total_seconds() < cooldown:
            seconds_left = cooldown - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before using this command again.")
            return
        slot_last_used[user_id] = now
        slot_cooldowns[user_id] = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        try:
            if message.from_user is None or message.from_user.is_bot:
                await message.reply_text("❌ <b>Only real users can play this game!</b>")
                return
            dice = await client.send_dice(
                chat_id=message.chat.id,
                emoji="🎰"
            )
            if not hasattr(dice, 'dice') or dice.dice.value is None:
                await message.reply_text("❌ <b>Failed to spin the slot machine. Please try again later.</b>")
                return
            await asyncio.sleep(3)
            # Slot machine rewards using the new logic
            slot_value = dice.dice.value
            if slot_value == 64:
                reward = random.randint(1000, 1500)  # Jackpot!
                win_message = f"🎰 ᴊᴀᴄᴋᴘᴏᴛ! ʏᴏᴜ ᴡᴏɴ {reward} 🎐 sʜᴀʀᴅs!"
            elif 40 <= slot_value < 64:
                reward = random.randint(500, 750)  # High tier win
                win_message = f"🎰 ᴄᴏɴɢʀᴀᴛs! ʏᴏᴜ ᴡᴏɴ {reward} 🎐 sʜᴀʀᴅs!"
            elif 20 <= slot_value < 40:
                reward = random.randint(250, 400)  # Medium tier win
                win_message = f"🎰 ɴɪᴄᴇ! ʏᴏᴜ ᴡᴏɴ {reward} 🎐 sʜᴀʀᴅs!"
            else:
                reward = 0
                win_message = "🎰 ɴᴏ ʟᴜᴄᴋ ᴛʜɪs ᴛɪᴍᴇ! ᴛʀʏ ᴀɢᴀɪɴ ʟᴀᴛᴇʀ."
            
            if reward > 0:
                db = get_database()
                user = await db.get_user(user_id)
                if not user:
                    await message.reply_text("❌ <b>You need an account to receive rewards. Use /start first!</b>")
                    return
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + reward})
                await db.log_user_transaction(user_id, "slot_win", {
                    "reward": reward,
                    "slot_value": slot_value,
                    "chat_id": message.chat.id,
                    "date": datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                })
                await message.reply_text(f"{win_message}", reply_to_message_id=message.id)
            else:
                await message.reply_text(win_message, reply_to_message_id=message.id)
        except Exception as e:
            await message.reply_text(f"❌ <b>Error:</b> {e}")

@check_banned
async def bowl_command(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in bowl_locks:
        bowl_locks[user_id] = asyncio.Lock()
    async with bowl_locks[user_id]:
        now = datetime.utcnow()
        last_used = bowl_last_used.get(user_id)
        cooldown = bowl_cooldowns.get(user_id, COOLDOWN_MIN)
        if last_used and (now - last_used).total_seconds() < cooldown:
            seconds_left = cooldown - int((now - last_used).total_seconds())
            await message.reply_text(f"⏳ Please wait {seconds_left} seconds before using this command again.")
            return
        bowl_last_used[user_id] = now
        bowl_cooldowns[user_id] = random.randint(COOLDOWN_MIN, COOLDOWN_MAX)
        try:
            if message.from_user is None or message.from_user.is_bot:
                await message.reply_text("❌ <b>Only real users can play this game!</b>")
                return
            dice = await client.send_dice(
                chat_id=message.chat.id,
                emoji="🎳"
            )
            if not hasattr(dice, 'dice') or dice.dice.value is None:
                await message.reply_text("❌ <b>Failed to bowl. Please try again later.</b>")
                return
            await asyncio.sleep(3)
            # Bowling rewards: 6 = strike, 5 = spare, 1-4 = partial
            bowl_value = dice.dice.value
            if bowl_value == 6:
                reward = random.randint(600, 900)  # Strike!
                win_message = "🎳 <b>STRIKE! 🎯 Perfect throw!</b>"
            elif bowl_value == 5:
                reward = random.randint(300, 500)  # Spare
                win_message = "🎳 <b>SPARE! Good throw!</b>"
            elif bowl_value in [1, 2, 3, 4]:
                reward = random.randint(50, 200)  # Partial pins
                win_message = "🎳 <b>Partial pins down. Not bad!</b>"
            else:
                reward = 0
                win_message = "😢 <b>Gutter ball! Better luck next time!</b>"
            
            if reward > 0:
                db = get_database()
                user = await db.get_user(user_id)
                if not user:
                    await message.reply_text("❌ <b>You need an account to receive rewards. Use /start first!</b>")
                    return
                shards = user.get('shards', 0)
                await db.update_user(user_id, {'shards': shards + reward})
                await db.log_user_transaction(user_id, "bowl_win", {
                    "reward": reward,
                    "bowl_value": bowl_value,
                    "chat_id": message.chat.id,
                    "date": datetime.utcnow().strftime('%Y-%m-%d %H:%M')
                })
                await message.reply_text(f"{win_message}\nYou won <b>{reward} 🎐 shards!</b>", reply_to_message_id=message.id)
            else:
                await message.reply_text(win_message, reply_to_message_id=message.id)
        except Exception as e:
            await message.reply_text(f"❌ <b>Error:</b> {e}")

            
          