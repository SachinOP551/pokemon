from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import os

# Import database based on configuration
if os.environ.get('USE_POSTGRESQL', 'false').lower() == 'true':
    from .postgres_database import get_database
else:
    from .database import get_database
from .decorators import auto_register_user
from datetime import datetime
import re

# Referral reward amounts
REFERRAL_REWARDS = {
    'referrer': 50000,  # 50k tokens for referrer
    'referred': 25000   # 25k tokens for referred user
}

async def referral_command(client, message: Message):
    """Handle /referral command - show user's referral stats"""
    try:
        user_id = message.from_user.id
        db = get_database()
        
        # Get user's referral stats
        stats = await db.get_referral_stats(user_id)
        
        if not stats['referral_code']:
            # Generate referral code if user doesn't have one
            stats['referral_code'] = await db.generate_referral_code(user_id)
        
        # Create referral link
        bot_username = (await client.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start=ref{stats['referral_code']}"
        
        # Get referrals list
        referrals = await db.get_referrals(user_id)
        
        # Create message
        text = f"<b>🎯 Your Referral Stats</b>\n\n"
        text += f"<b>Your Referral Code:</b> <code>{stats['referral_code']}</code>\n"
        text += f"<b>Total Referrals:</b> {stats['total_referrals']}\n"
        text += f"<b>Total Rewards Earned:</b> {stats['referral_rewards']:,} tokens\n\n"
        
        text += f"<b>💰 Rewards:</b>\n"
        text += f"• You get {REFERRAL_REWARDS['referrer']:,} tokens per referral\n"
        text += f"• Your friend gets {REFERRAL_REWARDS['referred']:,} tokens\n\n"
        
        text += f"<b>🔗 Your Referral Link:</b>\n"
        text += f"<code>{referral_link}</code>\n\n"
        
        if referrals:
            text += f"<b>👥 Your Referrals ({len(referrals)}):</b>\n"
            for i, referral in enumerate(referrals[:5], 1):  # Show first 5
                username = f"@{referral['username']}" if referral['username'] else referral['first_name']
                text += f"{i}. {username}\n"
            if len(referrals) > 5:
                text += f"... and {len(referrals) - 5} more\n"
        else:
            text += f"<b>👥 Your Referrals:</b> None yet\n"
        
        # Create keyboard
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 Top Referrers", callback_data="ref_top")],
            [InlineKeyboardButton("📋 My Referrals", callback_data="ref_list")],
            [InlineKeyboardButton("💰 Referral Rewards", callback_data="ref_rewards")]
        ])
        
        await message.reply_text(text, reply_markup=keyboard)
        
    except Exception as e:
        print(f"Error in referral_command: {e}")
        await message.reply_text("❌ An error occurred while fetching your referral stats!")

async def referral_callback(client, callback_query: CallbackQuery):
    """Handle referral callback queries"""
    try:
        query = callback_query
        await query.answer()
        
        if query.data == "ref_top":
            await show_top_referrers(client, query)
        elif query.data == "ref_list":
            await show_referrals_list(client, query)
        elif query.data == "ref_rewards":
            await show_referral_rewards(client, query)
        elif query.data == "ref_back":
            await referral_command(client, query.message)
            
    except Exception as e:
        print(f"Error in referral_callback: {e}")
        await query.answer("❌ An error occurred!", show_alert=True)

async def show_top_referrers(client, callback_query: CallbackQuery):
    """Show top referrers leaderboard"""
    try:
        db = get_database()
        top_referrers = await db.get_top_referrers(10)
        
        text = "<b>🏆 Top Referrers</b>\n\n"
        
        if top_referrers:
            for i, referrer in enumerate(top_referrers, 1):
                username = f"@{referrer['username']}" if referrer['username'] else referrer['first_name']
                text += f"<b>{i}.</b> {username}\n"
                text += f"   📊 {referrer['referral_count']} referrals\n"
                text += f"   💰 {referrer['referral_rewards']:,} tokens earned\n\n"
        else:
            text += "No referrals yet!\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="ref_back")]
        ])
        
        await callback_query.edit_message_text(text, reply_markup=keyboard)
        
    except Exception as e:
        print(f"Error in show_top_referrers: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def show_referrals_list(client, callback_query: CallbackQuery):
    """Show detailed referrals list"""
    try:
        user_id = callback_query.from_user.id
        db = get_database()
        referrals = await db.get_referrals(user_id)
        
        text = f"<b>👥 Your Referrals ({len(referrals)})</b>\n\n"
        
        if referrals:
            for i, referral in enumerate(referrals, 1):
                username = f"@{referral['username']}" if referral['username'] else referral['first_name']
                joined_date = referral['joined_at'].strftime("%Y-%m-%d") if referral['joined_at'] else "Unknown"
                text += f"<b>{i}.</b> {username}\n"
                text += f"   📅 Joined: {joined_date}\n\n"
        else:
            text += "You haven't referred anyone yet!\n"
            text += "Share your referral link to start earning rewards!\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="ref_back")]
        ])
        
        await callback_query.edit_message_text(text, reply_markup=keyboard)
        
    except Exception as e:
        print(f"Error in show_referrals_list: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def show_referral_rewards(client, callback_query: CallbackQuery):
    """Show referral rewards information"""
    try:
        text = "<b>💰 Referral Rewards</b>\n\n"
        text += f"<b>For You (Referrer):</b>\n"
        text += f"• {REFERRAL_REWARDS['referrer']:,} tokens per successful referral\n"
        text += f"• Rewards are added to your token balance\n"
        text += f"• Track your earnings in referral stats\n\n"
        
        text += f"<b>For Your Friend (Referred):</b>\n"
        text += f"• {REFERRAL_REWARDS['referred']:,} tokens bonus\n"
        text += f"• Instant reward upon joining\n"
        text += f"• Perfect start for new collectors!\n\n"
        
        text += f"<b>📋 How it works:</b>\n"
        text += f"1. Share your referral link\n"
        text += f"2. Friend clicks and starts the bot\n"
        text += f"3. Both of you get rewarded!\n"
        text += f"4. Track your referrals anytime\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="ref_back")]
        ])
        
        await callback_query.edit_message_text(text, reply_markup=keyboard)
        
    except Exception as e:
        print(f"Error in show_referral_rewards: {e}")
        await callback_query.answer("❌ An error occurred!", show_alert=True)

async def handle_referral_start(client, message: Message):
    """Handle referral start parameter"""
    try:
        # Extract referral code from start parameter
        start_param = message.text.split()[1] if len(message.text.split()) > 1 else ""
        
        if not start_param.startswith("ref"):
            return False  # Not a referral start
        
        referral_code = start_param[3:]  # Remove "ref" prefix
        if not referral_code:
            return False
        
        user_id = message.from_user.id
        db = get_database()
        
        # Check if user already exists
        existing_user = await db.get_user(user_id)
        if existing_user:
            # User already exists, can't use referral
            return False
        
        # Get referrer by code
        referrer = await db.get_user_by_referral_code(referral_code)
        if not referrer:
            # Invalid referral code
            return False
        
        referrer_id = referrer['user_id']
        
        # Check if user is trying to refer themselves
        if referrer_id == user_id:
            return False
        
        # Check if referrer already referred this user
        if existing_user and existing_user.get('referred_by') == referrer_id:
            return False
        
        # Add referral relationship
        await db.add_referral(referrer_id, user_id)
        
        # Give rewards
        await db.add_referral_reward(referrer_id, REFERRAL_REWARDS['referrer'])
        await db.add_referral_reward(user_id, REFERRAL_REWARDS['referred'])
        
        # Send success messages
        referrer_name = referrer.get('first_name', 'Unknown')
        await message.reply_text(
            f"🎉 <b>Welcome to Marvel Collector Bot!</b>\n\n"
            f"You were referred by <b>{referrer_name}</b>!\n"
            f"💰 You received <b>{REFERRAL_REWARDS['referred']:,} tokens</b> as a welcome bonus!\n\n"
            f"Start collecting Marvel characters now! 🦸‍♂️"
        )
        
        # Notify referrer
        try:
            await client.send_message(
                referrer_id,
                f"🎉 <b>New Referral!</b>\n\n"
                f"<b>{message.from_user.first_name}</b> joined using your referral link!\n"
                f"💰 You earned <b>{REFERRAL_REWARDS['referrer']:,} tokens</b>!\n\n"
                f"Total referrals: {(await db.get_referral_stats(referrer_id))['total_referrals']}"
            )
        except Exception as e:
            print(f"Could not notify referrer: {e}")
        
        return True
        
    except Exception as e:
        print(f"Error in handle_referral_start: {e}")
        return False

async def refcode_command(client, message: Message):
    """Handle /refcode command - generate new referral code"""
    try:
        user_id = message.from_user.id
        db = get_database()
        
        # Generate new referral code
        new_code = await db.generate_referral_code(user_id)
        
        # Create referral link
        bot_username = (await client.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start=ref{new_code}"
        
        text = f"<b>🔄 New Referral Code Generated!</b>\n\n"
        text += f"<b>Your New Code:</b> <code>{new_code}</code>\n"
        text += f"<b>Your Referral Link:</b>\n"
        text += f"<code>{referral_link}</code>\n\n"
        text += f"Share this link with friends to earn rewards! 🎉"
        
        await message.reply_text(text)
        
    except Exception as e:
        print(f"Error in refcode_command: {e}")
        await message.reply_text("❌ An error occurred while generating your referral code!")

async def refstats_command(client, message: Message):
    """Handle /refstats command - show detailed referral statistics"""
    try:
        user_id = message.from_user.id
        db = get_database()
        
        # Get referral stats
        stats = await db.get_referral_stats(user_id)
        referrals = await db.get_referrals(user_id)
        
        text = f"<b>📊 Detailed Referral Statistics</b>\n\n"
        text += f"<b>Total Referrals:</b> {stats['total_referrals']}\n"
        text += f"<b>Total Rewards Earned:</b> {stats['referral_rewards']:,} tokens\n"
        text += f"<b>Average per Referral:</b> {stats['referral_rewards'] // max(1, stats['total_referrals']):,} tokens\n\n"
        
        if referrals:
            # Calculate recent referrals (last 30 days)
            recent_count = 0
            for referral in referrals:
                if referral['joined_at']:
                    days_ago = (datetime.now() - referral['joined_at']).days
                    if days_ago <= 30:
                        recent_count += 1
            
            text += f"<b>📈 Recent Activity:</b>\n"
            text += f"• Last 30 days: {recent_count} referrals\n"
            text += f"• This month's earnings: {recent_count * REFERRAL_REWARDS['referrer']:,} tokens\n\n"
        
        text += f"<b>🎯 Next Milestones:</b>\n"
        next_milestone = ((stats['total_referrals'] // 5) + 1) * 5
        text += f"• {next_milestone} referrals: {next_milestone * REFERRAL_REWARDS['referrer']:,} tokens\n"
        
        await message.reply_text(text)
        
    except Exception as e:
        print(f"Error in refstats_command: {e}")
        await message.reply_text("❌ An error occurred while fetching referral statistics!") 