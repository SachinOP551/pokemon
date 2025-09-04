#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Marvel Collector Bot - Main Entry Point
Enhanced with performance optimization to prevent slowdowns
"""
import asyncio
from datetime import datetime, timedelta, timezone
import gc
import logging
import os
import random
import signal
import sys
import sys
import time
import types

from aiohttp import web
import asyncpg
import psutil
from pyrogram import Client, filters, idle
from pyrogram.types import BotCommand, CallbackQuery, InlineQuery, Message

from config import (
    API_HASH,
    API_ID,
    DROPTIME_LOG_CHANNEL,
    LOG_CHANNEL_ID,
    NEON_URI,
    OWNER_ID,
    TOKEN,
)
from modules.achievement import achievement_callback, achievement_command
from modules.admin import (
    backup_cmd,
    backup_command,
    backup_shell_command,
    donate_command,
    info_callback,
    info_command,
    manual_reward_distribution_admin_command,
    og_command,
    postgres_backup_command,
    postgrescap_command,
    remove_og_command,
    remove_sudo_command,
    reset_drop_weights_command,
    reset_users_command,
    reset_users_confirm_callback,
    reset_all_users_data_command,
    reset_all_users_data_confirm_callback,
    sanime_command,
    sudo_command,
    track_command,
    view_admins_command,
)
from modules.auction import (
    auction_command,
    auction_view_callback,
    auctions_command,
    auctionview_back_callback,
    bid_command,
    cancel_auction_command,
)
from modules.auction import AUCTION_GROUP_ID
from modules.bang import bang_command, baninfo_command, unbang_command
from modules.broadcast import broadcast_command
from modules.check import (
    back_to_character_callback,
    check_command,
    collectors_here_callback,
    top_collectors_callback,
)
from modules.claim import claim_command
from modules.claim_settings import register_claim_settings_handlers
from modules.collection import (
    collection_command,
    handle_collection_callback,
    handle_inline_query,
    handle_smode_callback,
    smode_command,
)
from modules.collection import collection_command as open_collection
from modules.canime import canime_command, register_canime_handlers
from modules.decorators import auto_register_user
from modules.drop import (
    clear_banned_command,
    clear_cache_command,
    clear_proposes_command,
    collect_command,
    drop_command,
    droptime_command,
    free_command,
    handle_message,
    jackpot_command,
    set_all_droptime_command
)
from modules.drop_settings import register_drop_settings_handlers
from modules.drop_settings import (
    drop_settings_callback,
    drop_settings_command,
    lock_rarity_command,
    set_daily_limit_command,
    set_frequency_command,
    unlock_rarity_command,
)
from modules.suggest import register_suggest_handlers
from modules.vidcollection import register_vidcollection_handlers
from modules.vid import register_vid_handlers
from modules.upload import confirm_type_creation_handler, register_upload_handlers
from modules.drop_weights import setup_drop_weights_and_limits
from modules.favorite import favorite_command, handle_favorite_callback
from modules.fusion import fuse_command, fusion_info_command
from modules.give import (
    give_command,
    massgive_command,
    take_command,
)
from modules.admin_approval import handle_approval_callback
from modules.giveaway import (
    end_giveaway,
    enter_giveaway,
    giveaway_status,
    start_giveaway,
)
from modules.postgres_database import (
    clear_all_caches,
    close_database,
    ensure_database,
    get_database,
    get_performance_stats,
    init_database,
)
import modules.postgres_database as pg_db
from modules.propose import (
    pconfig_command,
    ping_command,
    prate_command,
    propose_callback,
    propose_command,
    proposelock_command,
    pweights_command,
    setacceptance_command,
    setcooldown_command,
    setcost_command,
)
from modules.redeem import (
    credeem_command,
    redeem_command,
    sredeem_command,
    tredeem_command,
)
from modules.search import inline_query_handler, search_command
from modules.sell import (
    handle_masssell_callback,
    handle_sell_callback,
    masssell_command,
    sell_command,
)
from modules.session_manager import cleanup_session
from modules.srarity import rarity_callback, srarity_command
from modules.start import back_callback, help_callback, new_chat_members, start_command
from modules.stats import stats_command
from modules.status import status_command
from modules.store import (
    buy_command,
    buy_from_store_callback,
    cancel_buy_callback,
    confirm_buy_callback,
    handle_id_input,
    mystore_command,
    refresh_all_stores_command,
    refresh_store_callback,
)
from modules.suggest import suggest_callback, suggest_command
from modules.suggest import suggest_callback, suggest_command
from modules.tdgoal import tdgoal_callback, tdgoal_command, track_collect_drop
from modules.tokens import (
    balance_command,
    basket_command,
    daily_command,
    dart_command,
    deposit_command,
    football_command,
    handle_loan_callback,
    give_shards,
    give_tokens,
    loan_approve_command,
    loan_repay_command,
    loan_request_command,
    monthly_command,
    pay_command,
    roll_command,
    shards_pay,
    take_shards,
    take_tokens,
    weekly_command,
    withdraw_command,
    bowl_command,
    slot_command,
    explore_command,
    explore_callback,
)
from modules.safari import safari_command, enter_command, exit_command, hunt_command, register_safari_handlers
from modules.team import setup_team_handlers, team_command, addteam_command, removeteam_command
from modules.battle import battle_command, battleinfo_command, mybattle_command, testteam_command, clearbattles_command, setup_battle_handlers
from modules.exchange import exchange_command, exchange_history_command, exchange_callback_handler, init_exchange_system
# Background loop: Loan reminders
async def loan_reminder_loop(client: Client):
    from modules.postgres_database import get_database
    from modules.tokens import LOAN_TEST_MINUTES
    while True:
        try:
            db = get_database()
            # Ensure loan columns exist
            try:
                await db.ensure_loan_columns()
            except Exception:
                pass
            # Frequency: daily; if testing minutes are enabled, check every minute
            sleep_seconds = 60 if (LOAN_TEST_MINUTES and LOAN_TEST_MINUTES > 0) else 3600
            # Determine min hours since last reminder
            min_hours = 1 if (LOAN_TEST_MINUTES and LOAN_TEST_MINUTES > 0) else 24
            users = await db.get_users_with_active_loans_for_reminder(min_hours_since_last=min_hours)
            now = datetime.now(timezone.utc)
            for u in users:
                try:
                    user_id = u.get('user_id')
                    loan_amount = int(u.get('loan_amount') or 0)
                    loan_due = u.get('loan_due')
                    if isinstance(loan_due, str):
                        from datetime import datetime as _dt
                        try:
                            loan_due_dt = _dt.fromisoformat(loan_due)
                        except Exception:
                            loan_due_dt = None
                    else:
                        loan_due_dt = loan_due
                    # Normalize to timezone-aware UTC
                    if loan_due_dt and loan_due_dt.tzinfo is None:
                        try:
                            loan_due_dt = loan_due_dt.replace(tzinfo=timezone.utc)
                        except Exception:
                            pass
                    # Time left / overdue
                    if loan_due_dt:
                        delta = loan_due_dt - now
                        if delta.total_seconds() > 0:
                            days = delta.days
                            hours = (delta.seconds // 3600)
                            status = f"⏳ <b>Time left:</b> {days}d {hours}h"
                        else:
                            overdue_days = abs(delta.days)
                            overdue_hours = abs((delta.seconds // 3600))
                            status = f"⚠️ <b>Overdue:</b> {overdue_days}d {overdue_hours}h"
                    else:
                        status = ""
                    text = (
                        "📢 <b>Loan Reminder</b>\n\n"
                        f"• <b>Principal:</b> <code>{loan_amount:,}</code>\n"
                        f"• <b>Due Date (UTC):</b> <code>{loan_due_dt.strftime('%Y-%m-%d %H:%M') if loan_due_dt else 'Unknown'}</code>\n"
                        f"{status}\n\n"
                        "Please repay using <code>/repay</code>. Late penalties apply after the due date."
                    )
                    await client.send_message(user_id, text)
                    await db.mark_loan_reminder_sent(user_id)
                except Exception:
                    pass
            await asyncio.sleep(sleep_seconds)
        except Exception:
            # Backoff on unexpected errors
            await asyncio.sleep(60)

from modules.top import (
    btop_command,
    gtop_command,
    rgtop_command,
    sgtop_command,
    tdtop_command,
    test_leaderboard_command,
    top_command,
    wintop_command,
    wtop_command
)
from modules.top import setup_top_handlers
from modules.trade import (
    gift_command,
    handle_cancel_callback,
    handle_gift_callback,
    handle_massgift_callback,
    handle_trade_callback,
    massgift_command,
    trade_command,
)
from modules.transfer import handle_transfer_callback, transfer_command
from modules.upload import (
    add_anime_handler,
    close_admin_panel,
    close_upload_handler,
    confirm_anime_creation_handler,
    confirm_delete_handler,
    confirm_edit_handler,
    confirm_rename_anime_handler,
    confirm_reset_handler,
    confirm_upload_handler,
    create_type_from_edit_handler,
    create_type_from_upload_handler,
    delete_character_handler,
    edit_character_handler,
    handle_admin_panel,
    handle_anime_input,
    handle_anime_name_input,
    handle_delete_character_id_input,
    handle_edit_anime_input,
    handle_edit_character_id_input,
    handle_edit_choice,
    handle_edit_image_upload,
    handle_edit_name_input,
    handle_edit_rarity_selection,
    handle_edit_type_input,
    handle_edit_type_name_input,
    handle_media_upload,
    handle_name_input,
    handle_new_anime_name_input,
    handle_rarity_selection,
    handle_rename_anime_input,
    handle_reset_character_id_input,
    handle_type_input,
    handle_type_name_input,
    rename_anime_handler,
    reset_character_handler,
    start_character_upload,
)
from modules.vid import vadd_command, vedit_command
from modules.vidcollection import (
    handle_vidcollection_pagination,
    handle_vidlist_pagination,
    vidcollection_command,
    vidlist_command,
)



# Set UTF-8 encoding for stdout and stderr
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


# Global flag to track database initialization
_database_initialized = False

# Global web app instance




print("=== MARVEL COLLECTOR BOT ===")
print("Starting Marvel Collector Bot...")

# Initialize the Pyrogram client
app = Client(
    "marvel_collector_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=TOKEN,
    workers=50,
    max_concurrent_transmissions=10
)

async def initialize_database():
    """Initialize the database at startup"""
    global _database_initialized
    try:
        # Import the function here to avoid circular import issues
        from modules.postgres_database import init_database as pg_init_database
        await pg_init_database(NEON_URI)
        print("✅ PostgreSQL database initialized at startup")
        _database_initialized = True
        return True
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        return False

async def ensure_database_initialized():
    """Ensure database is initialized before any command"""
    global _database_initialized
    if not _database_initialized:
        success = await initialize_database()
        if not success:
            raise RuntimeError("Failed to initialize database")
    return True 

# Database initialization function
async def startup_initialization():
    """Initialize database and other startup tasks"""
    print("🚀 Bot starting up...")
    
    # Initialize database
    success = await initialize_database()
    if not success:
        print("❌ Failed to initialize database. Bot may not work properly.")
        return False
    
    # Initialize drop weights and limits
    try:
        db = get_database()
        await setup_drop_weights_and_limits(db)
        print("✅ Drop weights and limits initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize drop weights: {e}")
    
    # Start periodic save task for active drops
    try:
        from modules.drop import start_periodic_save_task, initialize_drop_system, load_active_drops
        # Initialize the drop system first
        if await initialize_drop_system():
            print("✅ Drop system initialized successfully")
            # Then start the periodic save task
            start_periodic_save_task()
            print("✅ Periodic save task for active drops started")
        else:
            print("⚠️ Warning: Drop system initialization failed")
    except Exception as e:
        print(f"⚠️ Warning: Failed to start periodic save task: {e}")
        import traceback
        traceback.print_exc()
    

    
    # Start ban manager
    try:
        from modules.ban_manager import start_ban_manager
        start_ban_manager()
        print("✅ Ban manager started successfully")
    except Exception as e:
        print(f"⚠️ Warning: Failed to start ban manager: {e}")
        import traceback
        traceback.print_exc()
    
    # Start loan reminder loop
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(loan_reminder_loop(app))
        print("✅ Loan reminder loop started")
    except Exception as e:
        print(f"⚠️ Warning: Failed to start loan reminder loop: {e}")

    # Start backup scheduler
    try:
        from modules.backup_scheduler import start_backup_scheduler
        start_backup_scheduler(app)
        print("✅ PostgreSQL backup scheduler started (30-minute intervals)")
    except Exception as e:
        print(f"⚠️ Warning: Failed to start backup scheduler: {e}")
        import traceback
        traceback.print_exc()

    # Start daily reward scheduler
    try:
        from modules.daily_reward_scheduler import start_daily_reward_scheduler
        start_daily_reward_scheduler(app)
        print("✅ Daily reward scheduler started (daily at 5PM UTC)")
    except Exception as e:
        print(f"⚠️ Warning: Failed to start daily reward scheduler: {e}")
        import traceback
        traceback.print_exc()
    
    # Initialize exchange system
    try:
        await init_exchange_system()
        print("✅ Exchange system initialized successfully")
    except Exception as e:
        print(f"⚠️ Warning: Failed to initialize exchange system: {e}")
        import traceback
        traceback.print_exc()

    print("✅ Database initialized successfully")
    print("✅ Bot is ready to handle commands!")
    return True

# Database initialization decorator
def require_database(func):
    """Decorator to ensure database is initialized before executing any command"""
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        try:
            await ensure_database_initialized()
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            print(f"❌ Database error in {func.__name__}: {e}")
            await message.reply_text("❌ Database error. Please try again later.")
    return wrapper


@app.on_message(filters.command("start", prefixes=["/", ".", "!"]))
@require_database
async def start_handler(client: Client, message: Message):
    """Handle /start command using the start module"""
    print(f"START command from {message.from_user.id}")
    
    # Set bot commands at startup
    commands = [
        BotCommand("start", "Start the bot"),

        BotCommand("claim", "Claim a daily free Pokemon"),
        BotCommand("catch", "Catch a dropped Pokemon"),
        BotCommand("mycollection", "View your Pokemon collection"),
        BotCommand("sethandler", "Set a custom keyword to open your collection"),
        BotCommand("changehandler", "Change your collection handler (costs tokens)"),
        BotCommand("smode", "Switch collection view mode"),
        BotCommand("mystore", "View your store"),
        BotCommand("sell", "Sell a Pokemon from your collection"),
        BotCommand("gift", "Gift a Pokemon to another user"),
        BotCommand("trade", "Trade Pokemon with another user"),
        BotCommand("fuse", "Fuse two exclusive Pokemon"),
        BotCommand("fusioninfo", "View fusion rules and info"),
        BotCommand("dex", "Check Pokemon info"),
        BotCommand("status", "Show your collection stats"),
        BotCommand("search", "Search for a Pokemon"),
        BotCommand("propose", "Propose a new Pokemon"),
        BotCommand("bal", "Check your token balance"),
        BotCommand("daily", "Claim daily tokens"),
        BotCommand("achievement", "View and claim achievements"),
        BotCommand("tdgoal", "Complete tasks to earn tokens"),
        BotCommand("vidcollection", "View your video Pokemon collection"),
        BotCommand("vidlist", "View the list of video players"),
        BotCommand("srarity", "Search for a Pokemon by rarity"),
        BotCommand("droptime", "Change the drop time"),
        BotCommand("spay", "Send shards to another user"),
        BotCommand("dart", "Play dart game"),
        BotCommand("basket", "Play basket game"),
        BotCommand("roll", "Play roll game"),
        BotCommand("football", "Play football game"),
        BotCommand("sgtop", "View the top 10 shard collectors"),
        BotCommand("cregion", "Browse Pokemon by region"),
        BotCommand("tdtop", "View today's top collectors"),
        BotCommand("wintop", "View weekly battle winners"),
        BotCommand("safari", "View Safari Zone information"),
        BotCommand("enter", "Enter Safari Zone"),
        BotCommand("hunt", "Hunt a Pokemon in Safari Zone"),
        BotCommand("exit", "Exit Safari Zone"),
        BotCommand("team", "View and manage your Pokemon team"),
        BotCommand("addteam", "Add a Pokemon to your team"),
        BotCommand("removeteam", "Remove a Pokemon from your team"),
        BotCommand("poke", "View your owned Pokémon by ID"),
        BotCommand("explore", "Explore a pokemon region"),
        BotCommand("battle", "Challenge someone to a battle"),
        BotCommand("exchange", "Exchange tokens for shards"),
    ]
    
    try:
        await client.set_bot_commands(commands)
        print("Bot commands set")
    except Exception as e:
        print(f"Error setting bot commands: {e}")
    
    # Call the start command from the start module
    await start_command(client, message)



@app.on_message(filters.command("dex", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def check_handler(client: Client, message: Message):
    """Handle /check command using the check module"""
    print(f"CHECK command from {message.from_user.id}")

    # Initialize database on first command

    # Call the check command from the check module
    await check_command(client, message)

@app.on_message(filters.new_chat_members)
async def new_members_handler(client: Client, message: Message):
    """Handle new chat members using the start module"""
    await new_chat_members(client, message)

@app.on_callback_query(filters.regex("^help$"))
async def help_handler(client: Client, callback_query: CallbackQuery):
    """Handle help callback using the start module"""
    await help_callback(client, callback_query)

@app.on_callback_query(filters.regex("^back$"))
async def back_handler(client: Client, callback_query: CallbackQuery):
    """Handle back callback using the start module"""
    await back_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^collectors_here_\d+$"))
async def collectors_here_handler(client: Client, callback_query: CallbackQuery):
    """Handle collectors here callback using the check module"""
    await collectors_here_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^top_collectors_\d+$"))
async def top_collectors_handler(client: Client, callback_query: CallbackQuery):
    """Handle top collectors callback using the check module"""
    await top_collectors_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^back_to_character_\d+$"))
async def back_to_character_handler(client: Client, callback_query: CallbackQuery):
    """Handle back to character callback using the check module"""
    await back_to_character_callback(client, callback_query)

@app.on_message(filters.command("claim", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def claim_handler(client: Client, message: Message):
    """Handle /claim command using the claim module"""
    print(f"CLAIM command from {message.from_user.id}")
    await claim_command(client, message)


@app.on_message(filters.command("test"))
@auto_register_user
async def test_command(client: Client, message: Message):
    """Handle /test command"""
    print(f"TEST command from {message.from_user.id}")
    await message.reply_text("Test successful!")

@app.on_message(filters.command("sudo", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def sudo_handler(client: Client, message: Message):
    await sudo_command(client, message)

@app.on_message(filters.command("og", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def og_handler(client: Client, message: Message):
    await og_command(client, message)

@app.on_message(filters.command("rmsudo", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def remove_sudo_handler(client: Client, message: Message):
    await remove_sudo_command(client, message)


@app.on_message(filters.command("rmog", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def remove_og_handler(client: Client, message: Message):
    await remove_og_command(client, message)

@app.on_message(filters.command("vadmins", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def view_admins_handler(client: Client, message: Message):
    await view_admins_command(client, message)

@app.on_message(filters.command("sanime", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def sanime_handler(client: Client, message: Message):
    await sanime_command(client, message)

@app.on_message(filters.command("info", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def info_handler(client: Client, message: Message):
    await info_command(client, message)

@app.on_callback_query(filters.regex(r"^info_.*"))
@require_database
async def info_callback_handler(client: Client, callback_query: CallbackQuery):
    await info_callback(client, callback_query)





@app.on_message(filters.command("bang", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def bang_handler(client: Client, message: Message):
    await bang_command(client, message)

@app.on_message(filters.command("unbang", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def unbang_handler(client: Client, message: Message):
    await unbang_command(client, message)

@app.on_message(filters.command("baninfo", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def baninfo_handler(client: Client, message: Message):
    await baninfo_command(client, message)

@app.on_message(filters.command("srarity", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def srarity_handler(client: Client, message: Message):
    await srarity_command(client, message)

@app.on_callback_query(filters.regex(r"^(r_|p_|close$|r_back$)"))
async def srarity_callback_handler(client: Client, callback_query: CallbackQuery):
    await rarity_callback(client, callback_query)

@app.on_message(filters.command("stats", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def stats_handler(client: Client, message: Message):
    """Handle /stats command using the stats module"""
    await stats_command(client, message)

@app.on_message(filters.command("search", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def search_handler(client: Client, message: Message):
    """Handle /search command using the search module"""
    await search_command(client, message)

@app.on_message(filters.command("cregion", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def canime_handler(client: Client, message: Message):
    """Handle /cregion command using the cregion module"""
    await canime_command(client, message)

@app.on_message(filters.command("bal", prefixes=["/", ".", "!"]))
@auto_register_user
async def balance_handler(client: Client, message: Message):
    try:
        await ensure_database_initialized()
    except Exception as e:
        print(f"❌ Database error in balance_handler: {e}")
        await message.reply_text("❌ Database error. Please try again later.")
        return
    await balance_command(client, message)

@app.on_message(filters.command("loan", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def loan_request_handler(client: Client, message: Message):
    await loan_request_command(client, message)

@app.on_message(filters.command("loanapprove", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def loanapprove_handler(client: Client, message: Message):
    await loan_approve_command(client, message)

@app.on_message(filters.command("repay", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def loanrepay_handler(client: Client, message: Message):
    await loan_repay_command(client, message)

@app.on_callback_query(filters.regex(r"^(loan_approve_|loan_decline_)\d+$"))
async def loan_inline_decision_handler(client: Client, callback_query: CallbackQuery):
    await handle_loan_callback(client, callback_query)

@app.on_message(filters.command("deposit", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def deposit_handler(client: Client, message: Message):
    await deposit_command(client, message)

@app.on_message(filters.command("withdraw", prefixes=["/", ".", "!"]))
@auto_register_user
async def withdraw_handler(client: Client, message: Message):
    await withdraw_command(client, message)

@app.on_message(filters.command("daily", prefixes=["/", ".", "!"]))
@auto_register_user
async def daily_handler(client: Client, message: Message):
    await daily_command(client, message)
    # Track daily claim for tdgoal
    try:
        user_id = message.from_user.id
        await track_collect_drop(user_id)
    except Exception as e:
        print(f"tdgoal track_collect_drop error: {e}")

@app.on_message(filters.command("weekly", prefixes=["/", ".", "!"]))
@auto_register_user
async def weekly_handler(client: Client, message: Message):
    await weekly_command(client, message)

@app.on_message(filters.command("monthly", prefixes=["/", ".", "!"]))
@auto_register_user
async def monthly_handler(client: Client, message: Message):
    await monthly_command(client, message)

@app.on_message(filters.command("gbheek", prefixes=["/", ".", "!"]))
@auto_register_user
async def give_tokens_handler(client: Client, message: Message):
    await give_tokens(client, message)

@app.on_message(filters.command("tbheek", prefixes=["/", ".", "!"]))
@auto_register_user
async def take_tokens_handler(client: Client, message: Message):
    await take_tokens(client, message)

@app.on_message(filters.command("pay", prefixes=["/", ".", "!"]))
@auto_register_user
async def pay_handler(client: Client, message: Message):
    await pay_command(client, message)

@app.on_message(filters.command("spay", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def shards_pay_handler(client: Client, message: Message):
    await shards_pay(client, message)

@app.on_message(filters.command("gshards", prefixes=["/", ".", "!"]))
@auto_register_user
async def give_shards_handler(client: Client, message: Message):
    await give_shards(client, message)

@app.on_message(filters.command("tshards", prefixes=["/", ".", "!"]))
@auto_register_user
async def take_shards_handler(client: Client, message: Message):
    await take_shards(client, message)

@app.on_message(filters.command("status", prefixes=["/", ".", "!"]))
@auto_register_user
async def status_handler(client: Client, message: Message):
    await status_command(client, message)

@app.on_inline_query()
async def unified_inline_query_handler(client: Client, inline_query: InlineQuery):
    query = inline_query.query.strip()
    if query.startswith("collection:"):
        from modules.collection import handle_inline_query as handle_collection_inline_query
        await handle_collection_inline_query(client, inline_query)
    elif query.startswith(".anime"):
        from modules.upload import handle_anime_inline_query
        await handle_anime_inline_query(client, inline_query)
    elif query.startswith(".character"):
        from modules.upload import handle_character_inline_query
        await handle_character_inline_query(client, inline_query)
    elif query.startswith(".type"):
        from modules.upload import handle_type_inline_query
        await handle_type_inline_query(client, inline_query)
    else:
        from modules.search import inline_query_handler as handle_search_inline_query
        await handle_search_inline_query(client, inline_query)

@app.on_message(filters.command("give", prefixes=["/", ".", "!"]))
@auto_register_user
async def give_handler(client: Client, message: Message):
    await give_command(client, message)

@app.on_message(filters.command("take", prefixes=["/", ".", "!"]))
@auto_register_user
async def take_handler(client: Client, message: Message):
    await take_command(client, message)

@app.on_message(filters.command("massgive", prefixes=["/", ".", "!"]))
@auto_register_user
async def massgive_handler(client: Client, message: Message):
    await massgive_command(client, message)

@app.on_callback_query(filters.regex(r"^admin_(approve|decline)_"))
async def admin_approval_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_approval_callback(client, callback_query)

@app.on_message(filters.command("propose", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def propose_handler(client: Client, message: Message):
    await propose_command(client, message)

@app.on_message(filters.command("proposelock", prefixes=["/", ".", "!"]))
@auto_register_user
async def proposelock_handler(client: Client, message: Message):
    await proposelock_command(client, message)

@app.on_message(filters.command("pcooldown", prefixes=["/", ".", "!"]))
@auto_register_user
async def setcooldown_handler(client: Client, message: Message):
    await setcooldown_command(client, message)

@app.on_message(filters.command("pcost", prefixes=["/", ".", "!"]))
@auto_register_user
async def setcost_handler(client: Client, message: Message):
    await setcost_command(client, message)

@app.on_message(filters.command("pacceptance", prefixes=["/", ".", "!"]))
@auto_register_user
async def setacceptance_handler(client: Client, message: Message):
    await setacceptance_command(client, message)

@app.on_message(filters.command("pconfig", prefixes=["/", ".", "!"]))
@auto_register_user
async def pconfig_handler(client: Client, message: Message):
    await pconfig_command(client, message)

@app.on_message(filters.command("prate", prefixes=["/", ".", "!"]))
@auto_register_user
async def prate_handler(client: Client, message: Message):
    await prate_command(client, message)

@app.on_callback_query(filters.regex(r"^propose_"))
async def propose_callback_handler(client: Client, callback_query: CallbackQuery):
    await propose_callback(client, callback_query)

@app.on_message(filters.command("redeem", prefixes=["/", ".", "!"]))
@auto_register_user
async def redeem_handler(client: Client, message: Message):
    await redeem_command(client, message)

@app.on_message(filters.command("credeem", prefixes=["/", ".", "!"]))
@auto_register_user
async def credeem_handler(client: Client, message: Message):
    await credeem_command(client, message)

@app.on_message(filters.command("tredeem", prefixes=["/", ".", "!"]))
@auto_register_user
async def tredeem_handler(client: Client, message: Message):
    await tredeem_command(client, message)

@app.on_message(filters.command("tdtop", prefixes=["/", ".", "!"]))
@auto_register_user
async def tdtop_handler(client: Client, message: Message):
    await tdtop_command(client, message)

@app.on_message(filters.command("gtop", prefixes=["/", ".", "!"]))
@auto_register_user
async def gtop_handler(client: Client, message: Message):
    await gtop_command(client, message)

@app.on_message(filters.command("top", prefixes=["/", ".", "!"]))
@auto_register_user
async def top_handler(client: Client, message: Message):
    await top_command(client, message)

@app.on_message(filters.command("rgtop", prefixes=["/", ".", "!"]))
@auto_register_user
async def rgtop_handler(client: Client, message: Message):
    await rgtop_command(client, message)

@app.on_message(filters.command("btop", prefixes=["/", ".", "!"]))
@auto_register_user
async def btop_handler(client: Client, message: Message):
    await btop_command(client, message)

@app.on_message(filters.command("testleaderboard", prefixes=["/", ".", "!"]))
@auto_register_user
async def test_leaderboard_handler(client: Client, message: Message):
    await test_leaderboard_command(client, message)

@app.on_message(filters.command("fav", prefixes=["/", ".", "!"]))
@auto_register_user
async def fav_handler(client: Client, message: Message):
    await favorite_command(client, message)

@app.on_callback_query(filters.regex(r"^fav_"))
async def fav_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_favorite_callback(client, callback_query)

@app.on_message(filters.command("gift", prefixes=["/", ".", "!"]))
@auto_register_user
async def gift_handler(client: Client, message: Message):
    await gift_command(client, message)

@app.on_callback_query(filters.regex(r"^gift_"))
async def gift_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_gift_callback(client, callback_query)

@app.on_message(filters.command("trade", prefixes=["/", ".", "!"]))
@auto_register_user
async def trade_handler(client: Client, message: Message):
    await trade_command(client, message)

@app.on_callback_query(filters.regex(r"^trade_"))
async def trade_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_trade_callback(client, callback_query)

@app.on_message(filters.command("sell", prefixes=["/", ".", "!"]))
@auto_register_user
async def sell_handler(client: Client, message: Message):
    await sell_command(client, message)

@app.on_callback_query(filters.regex(r"^sell_"))
async def sell_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_sell_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^cancel_buy_"))
async def cancel_buy_callback_handler(client: Client, callback_query: CallbackQuery):
    await cancel_buy_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^cancel_.*_.*"))
async def cancel_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_cancel_callback(client, callback_query)

@app.on_message(filters.command("transfer", prefixes=["/", ".", "!"]))
@auto_register_user
async def transfer_handler(client: Client, message: Message):
    await transfer_command(client, message)

@app.on_callback_query(filters.regex(r"^transfer_confirm$|^transfer_cancel$"))
async def transfer_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_transfer_callback(client, callback_query)


# Old upload command handlers removed - now using admin panel instead

@app.on_message(filters.command("drop", prefixes=["/", ".", "!"]))
@auto_register_user
async def drop_handler(client: Client, message: Message):
    await drop_command(client, message)

@app.on_message(filters.command("catch", prefixes=["/", ".", "!"]))
@auto_register_user
async def collect_handler(client: Client, message: Message):
    await collect_command(client, message)

@app.on_message(filters.command("guess", prefixes=["/", ".", "!"]))
@auto_register_user
async def guess_handler(client: Client, message: Message):
    await collect_command(client, message)

@app.on_message(filters.command("droptime", prefixes=["/", ".", "!"]))
@auto_register_user
async def droptime_handler(client: Client, message: Message):
    await droptime_command(client, message)

@app.on_message(filters.command("free", prefixes=["/", ".", "!"]))
@auto_register_user
async def free_handler(client: Client, message: Message):
    await free_command(client, message)

@app.on_message(filters.command("mycollection", prefixes=["/", ".", "!"]))
@auto_register_user
async def mycollection_handler(client: Client, message: Message):
    await collection_command(client, message)

@app.on_message(filters.command("sethandler", prefixes=["/", ".", "!"]))
@auto_register_user
async def sethandler_handler(client: Client, message: Message):
    from modules.postgres_database import get_database
    db = get_database()
    user_id = message.from_user.id
    # Parse handler from arguments
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text("<b>ᴘʟᴇᴀsᴇ ᴘʀᴏᴠɪᴅᴇ ᴀ ʜᴀɴᴅʟᴇʀ ᴛᴇxᴛ.\nFor ᴇxᴀᴍᴘʟᴇ: <code>/sethandler Hello World</code></b>")
        return
    raw = parts[1].strip()
    # Normalize: allow letters, numbers, underscores, 3-32 chars
    import re
    handler = re.sub(r"[^a-zA-Z0-9_]+", "", raw)
    if not handler:
        await message.reply_text("<b>❌ Invalid handler. Use letters, numbers, or underscore.</b>")
        return
    if len(handler) < 1 or len(handler) > 32:
        await message.reply_text("<b>❌ Handler must be 1-32 characters.</b>")
        return
    # Check if reserved (avoid collision with commands)
    reserved = {
        "start","claim","collect","mycollection","smode","mystore","sell","gift","trade","fuse","fusioninfo","check","status","search","propose","bal","daily","achievement","tdgoal","vidcollection","vidlist","srarity","droptime","spay","dart","basket","roll","football","sgtop","canime","tdtop","sethandler","team","addteam","removeteam","hunt"
    }
    if handler.lower() in reserved:
        await message.reply_text("<b>❌ That keyword is reserved. Choose another.</b>")
        return
    # Ensure user has enough balance first
    user = await db.get_user(user_id)
    if not user or user.get('wallet', 0) < 500000:
        await message.reply_text("<b>You don't have enough tokens.\nYou need 500,000 tokens to set a custom handler.\nYour balance: <code>{user.get('wallet', 0)}</code> tokens</b>")
        return
    # Check availability before charging
    existing = await db.get_user_by_collection_handler(handler)
    if existing and existing.get('user_id') != user_id:
        await message.reply_text("<b>❌ That handler is already taken. Try a different one.</b>")
        return
    # Deduct cost
    try:
        await db.update_user(user_id, {"wallet": user.get('wallet', 0) - 500000})
    except Exception:
        await message.reply_text("<b>❌ Failed to deduct tokens. Try again later.</b>")
        return
    # Try to set; unique index enforces uniqueness (double-check race)
    success = await db.set_collection_handler(user_id, handler)
    if success:
        await message.reply_text(f"<b>✅ Your custom collection handler has been set to: <code>{handler}</code>\nNow just send <code>{handler}</code> to open your collection.</b>")
    else:
        # Refund on failure
        try:
            await db.update_user(user_id, {"wallet": (user.get('wallet', 0))})
        except Exception:
            pass
        # Check if taken by someone else (race)
        existing2 = await db.get_user_by_collection_handler(handler)
        if existing2 and existing2.get('user_id') != user_id:
            await message.reply_text("<b>❌ That handler is already taken. You were refunded.</b>")
        else:
            await message.reply_text("<b>❌ Failed to set handler. Tokens refunded. Try again later.</b>")

@app.on_message(filters.command("changehandler", prefixes=["/", ".", "!"]))
@auto_register_user
async def changehandler_handler(client: Client, message: Message):
    from modules.postgres_database import get_database
    db = get_database()
    user_id = message.from_user.id
    # Parse handler from arguments
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.reply_text("<b>Please provide a new handler text.\nFor example: <code>/changehandler Hello New World</code></b>")
        return
    raw = parts[1].strip()
    import re
    handler = re.sub(r"[^a-zA-Z0-9_]+", "", raw)
    if not handler:
        await message.reply_text("<b>❌ Invalid handler. Use letters, numbers, or underscore.</b>")
        return
    if len(handler) < 1 or len(handler) > 32:
        await message.reply_text("<b>❌ Handler must be 1-32 characters.</b>")
        return
    reserved = {
        "start","claim","collect","mycollection","smode","mystore","sell","gift","trade","fuse","fusioninfo","check","status","search","propose","bal","daily","achievement","tdgoal","vidcollection","vidlist","srarity","droptime","spay","dart","basket","roll","football","sgtop","canime","tdtop","sethandler","changehandler"
    }
    if handler.lower() in reserved:
        await message.reply_text("<b>❌ That keyword is reserved. Choose another.</b>")
        return
    # Ensure user has enough balance first
    user = await db.get_user(user_id)
    if not user or user.get('wallet', 0) < 200000:
        await message.reply_text("<b>❌ You need 200000 tokens to change your handler.</b>")
        return
    # Check availability before charging
    existing = await db.get_user_by_collection_handler(handler)
    if existing and existing.get('user_id') != user_id:
        await message.reply_text("<b>❌ That handler is already taken. Try a different one.</b>")
        return
    # Deduct cost
    try:
        await db.update_user(user_id, {"wallet": user.get('wallet', 0) - 200000})
    except Exception:
        await message.reply_text("❌ Failed to deduct tokens. Try again later.")
        return
    # Attempt to set
    success = await db.set_collection_handler(user_id, handler)
    if success:
        await message.reply_text(f"✅ Your custom collection handler has been changed to:<code>{handler}</code>\n\n<b>200,000 tokens have been deducted from your balance.</b>")
    else:
        # Refund on failure
        try:
            await db.update_user(user_id, {"wallet": (user.get('wallet', 0))})
        except Exception:
            pass
        # Check if taken by someone else (race)
        existing2 = await db.get_user_by_collection_handler(handler)
        if existing2 and existing2.get('user_id') != user_id:
            await message.reply_text("❌ That handler is already taken. You were refunded.")
        else:
            await message.reply_text("❌ Failed to change handler. Tokens refunded. Try again later.")



@app.on_message(filters.command("smode", prefixes=["/", ".", "!"]))
@auto_register_user
async def smode_handler(client: Client, message: Message):
    await smode_command(client, message)

@app.on_callback_query(filters.regex(r"^(sm_|f_|sm_back|sm_close)"))
async def smode_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_smode_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^(c_|s_)"))
async def collection_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_collection_callback(client, callback_query)

@app.on_message(filters.command("vadd", prefixes=["/", ".", "!"]))
@auto_register_user
async def vadd_handler(client: Client, message: Message):
    await vadd_command(client, message)

@app.on_message(filters.command("vidcollection", prefixes=["/", ".", "!"]))
@auto_register_user
async def vidcollection_handler(client: Client, message: Message):
    await vidcollection_command(client, message)

@app.on_callback_query(filters.regex(r"^vid_"))
async def vidcollection_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_vidcollection_pagination(client, callback_query)

@app.on_message(filters.command("dropsettings", prefixes=["/", ".", "!"]))
@auto_register_user
async def dropsettings_handler(client: Client, message: Message):
    await drop_settings_command(client, message)

@app.on_message(filters.command("lockrarity", prefixes=["/", ".", "!"]))
@auto_register_user
async def lockrarity_handler(client: Client, message: Message):
    await lock_rarity_command(client, message)

@app.on_message(filters.command("unlockrarity", prefixes=["/", ".", "!"]))
@auto_register_user
async def unlockrarity_handler(client: Client, message: Message):
    await unlock_rarity_command(client, message)

@app.on_message(filters.command("setfrequency", prefixes=["/", ".", "!"]))
@auto_register_user
async def setfrequency_handler(client: Client, message: Message):
    await set_frequency_command(client, message)

@app.on_message(filters.command("setdailylimit", prefixes=["/", ".", "!"]))
@auto_register_user
async def setdailylimit_handler(client: Client, message: Message):
    await set_daily_limit_command(client, message)

@app.on_callback_query(filters.regex(r"^(drop_|lock_|unlock_|freq_)") )
async def drop_settings_callback_handler(client: Client, callback_query: CallbackQuery):
    await drop_settings_callback(client, callback_query)

@app.on_message(filters.command("rdw", prefixes=["/", ".", "!"]))
@auto_register_user
async def reset_drop_weights_handler(client: Client, message: Message):
    await reset_drop_weights_command(client, message)

@app.on_message(filters.command("mystore", prefixes=["/", ".", "!"]))
@auto_register_user
async def mystore_handler(client: Client, message: Message):
    await mystore_command(client, message)

@app.on_message(filters.command("buy", prefixes=["/", ".", "!"]))
@auto_register_user
async def buy_handler(client: Client, message: Message):
    await buy_command(client, message)

@app.on_message(filters.regex(r"^\d+$") & filters.private)
async def handle_id_input_handler(client: Client, message: Message):
    await handle_id_input(client, message)

@app.on_callback_query(filters.regex(r"^buy_from_store$"))
async def buy_from_store_callback_handler(client: Client, callback_query: CallbackQuery):
    await buy_from_store_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^refresh_store$"))
async def refresh_store_callback_handler(client: Client, callback_query: CallbackQuery):
    await refresh_store_callback(client, callback_query)

@app.on_callback_query(filters.regex(r"^confirm_buy_"))
async def confirm_buy_callback_handler(client: Client, callback_query: CallbackQuery):
    await confirm_buy_callback(client, callback_query)

@app.on_message(filters.command("masssell", prefixes=["/", ".", "!"]))
@auto_register_user
async def masssell_handler(client: Client, message: Message):
    await masssell_command(client, message)

@app.on_callback_query(filters.regex(r"^masssell_"))
async def masssell_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_masssell_callback(client, callback_query)

@app.on_message(filters.command("donate", prefixes=["/", ".", "!"]))
@auto_register_user
async def donate_handler(client: Client, message: Message):
    await donate_command(client, message)

@app.on_message(filters.command("ping", prefixes=["/", ".", "!"]))
@auto_register_user
async def ping_handler(client: Client, message: Message):
    await ping_command(client, message)

@app.on_message(filters.command("resetusers", prefixes=["/", ".", "!"]))
@auto_register_user
async def reset_users_handler(client: Client, message: Message):
    await reset_users_command(client, message)

@app.on_callback_query(filters.regex(r"^resetusers_confirm$"))
async def reset_users_confirm_callback_handler(client: Client, callback_query: CallbackQuery):
    await reset_users_confirm_callback(client, callback_query)

@app.on_message(filters.command("resetalldata", prefixes=["/", ".", "!"]))
@auto_register_user
async def reset_all_users_data_handler(client: Client, message: Message):
    await reset_all_users_data_command(client, message)

@app.on_callback_query(filters.regex(r"^resetalldata_confirm$"))
async def reset_all_users_data_confirm_callback_handler(client: Client, callback_query: CallbackQuery):
    await reset_all_users_data_confirm_callback(client, callback_query)

@app.on_message(filters.command("suggest", prefixes=["/", ".", "!"]))
@auto_register_user
async def suggest_handler(client: Client, message: Message):
    await suggest_command(client, message)

@app.on_callback_query(filters.regex(r"^suggest_(accept|decline)_"))
async def suggest_callback_handler(client: Client, callback_query: CallbackQuery):
    await suggest_callback(client, callback_query)

@app.on_message(filters.command("achievement", prefixes=["/", ".", "!"]))
@auto_register_user
async def achievement_handler(client: Client, message: Message):
    await achievement_command(client, message)

@app.on_callback_query(filters.regex(r"^achievement_"))
async def achievement_callback_handler(client: Client, callback_query: CallbackQuery):
    await achievement_callback(client, callback_query)

@app.on_message(filters.command("tdgoal", prefixes=["/", ".", "!"]))
@auto_register_user
async def tdgoal_handler(client: Client, message: Message):
    await tdgoal_command(client, message)

@app.on_callback_query(filters.regex(r"^tdgoal_"))
async def tdgoal_callback_handler(client: Client, callback_query: CallbackQuery):
    await tdgoal_callback(client, callback_query)

@app.on_message(filters.command("massgift", prefixes=["/", ".", "!"]))
async def massgift_handler(client: Client, message: Message):
    await massgift_command(client, message)

@app.on_callback_query(filters.regex(r"^massgift_"))
async def massgift_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_massgift_callback(client, callback_query)

@app.on_message(filters.command("pweights", prefixes=["/", ".", "!"]))
@auto_register_user
async def pweights_handler(client: Client, message: Message):
    await pweights_command(client, message)



@app.on_message(filters.command("auctions", prefixes=["/", ".", "!"]))
@auto_register_user
async def auctions_handler(client: Client, message: Message):
    await auctions_command(client, message)

@app.on_callback_query(filters.regex(r"^auctionview_"))
async def auctionview_callback_handler(client: Client, callback_query: CallbackQuery):
    if callback_query.data == "auctionview_back":
        await auctionview_back_callback(client, callback_query)
    else:
        await auction_view_callback(client, callback_query)

@app.on_message(filters.command("auction", prefixes=["/", ".", "!"]))
@auto_register_user
async def auction_handler(client: Client, message: Message):
    await auction_command(client, message)

@app.on_message(filters.command("bid", prefixes=["/", ".", "!"]))
@auto_register_user
async def bid_handler(client: Client, message: Message):
    await bid_command(client, message)

@app.on_message(filters.command("cancelauction", prefixes=["/", ".", "!"]))
@auto_register_user
async def cancelauction_handler(client: Client, message: Message):
    await cancel_auction_command(client, message)

@app.on_message(filters.command("broadcast", prefixes=["/", ".", "!"]))
@auto_register_user
async def broadcast_handler(client: Client, message: Message):
    await broadcast_command(client, message)

@app.on_message(filters.command("giveaway", prefixes=["/", ".", "!"]))
@auto_register_user
async def giveaway_handler(client: Client, message: Message):
    await start_giveaway(client, message)



@app.on_message(filters.command("endgiveaway", prefixes=["/", ".", "!"]))
@auto_register_user
async def end_giveaway_handler(client: Client, message: Message):
    await end_giveaway(client, message)

@app.on_message(filters.command("givestatus", prefixes=["/", ".", "!"]))
@auto_register_user
async def giveaway_status_handler(client: Client, message: Message):
    
    await giveaway_status(client, message)

@app.on_message(filters.command("setalldroptime", prefixes=["/", ".", "!"]))
@auto_register_user
async def set_all_droptime_handler(client: Client, message: Message):
    await set_all_droptime_command(client, message)

@app.on_message(filters.command("clearbanned", prefixes=["/", ".", "!"]))
@auto_register_user
async def clear_banned_handler(client: Client, message: Message):
    await clear_banned_command(client, message)

@app.on_message(filters.command("clearproposes", prefixes=["/", ".", "!"]))
@auto_register_user
async def clear_proposes_handler(client: Client, message: Message):
    await clear_proposes_command(client, message)




@app.on_message(filters.command("backup", prefixes=["/", ".", "!"]))
@auto_register_user
async def backup_handler(client: Client, message: Message):
    await backup_command(client, message)

@app.on_message(filters.command("backup_shell", prefixes=["/", ".", "!"]))
@auto_register_user
async def backup_shell_handler(client: Client, message: Message):
    await backup_shell_command(client, message)

@app.on_message(filters.command("backup_cmd", prefixes=["/", ".", "!"]) & filters.user(OWNER_ID))
async def backup_cmd_handler(client: Client, message: Message):
    await backup_cmd(client, message)

@app.on_message(filters.command("track", prefixes=["/", ".", "!"]) & filters.user(OWNER_ID))
async def track_handler(client: Client, message: Message):
    await track_command(client, message)

@app.on_message(filters.command("postgrescap", prefixes=["/", ".", "!"]) & filters.user(OWNER_ID))
async def postgrescap_handler(client: Client, message: Message):
    await postgrescap_command(client, message)

@app.on_message(filters.command("pgbackup", prefixes=["/", ".", "!"]) & filters.user(OWNER_ID))
async def postgres_backup_handler(client: Client, message: Message):
    await postgres_backup_command(client, message)

@app.on_message(filters.command("manualreward", prefixes=["/", ".", "!"]) & filters.user(OWNER_ID))
async def manual_reward_distribution_handler(client: Client, message: Message):
    await manual_reward_distribution_admin_command(client, message)


@app.on_message(filters.command("fuse", prefixes=["/", ".", "!"]))
@auto_register_user
async def fuse_handler(client: Client, message: Message):
    await fuse_command(client, message)

@app.on_message(filters.command("fusioninfo", prefixes=["/", ".", "!"]))
@auto_register_user
async def fusioninfo_handler(client: Client, message: Message):
    await fusion_info_command(client, message)


@app.on_message(filters.command("vidlist", prefixes=["/", ".", "!"]))
@auto_register_user
async def vidlist_handler(client: Client, message: Message):
    await vidlist_command(client, message)


@app.on_callback_query(filters.regex(r"^vid_"))
async def vidcollection_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_vidcollection_pagination(client, callback_query)


@app.on_callback_query(filters.regex(r"^vidlist_"))
async def vidlist_callback_handler(client: Client, callback_query: CallbackQuery):
    await handle_vidlist_pagination(client, callback_query)

@app.on_message(filters.command("vedit", prefixes=["/", ".", "!"]))
@auto_register_user
async def vedit_handler(client: Client, message: Message):
    await vedit_command(client, message)

@app.on_message(filters.command("refreshallstores", prefixes=["/", ".", "!"]))
@auto_register_user
async def refreshallstores_handler(client: Client, message: Message):
    await refresh_all_stores_command(client, message)

@app.on_message(filters.command("jackpot", prefixes=["/", ".", "!"]))
@auto_register_user
async def jackpot_handler(client: Client, message: Message):
    await jackpot_command(client, message)


@app.on_message(filters.command("dart", prefixes=["/", ".", "!"]))
@auto_register_user
async def dart_handler(client: Client, message: Message):
    await dart_command(client, message)

@app.on_message(filters.command("basket", prefixes=["/", ".", "!"]))
@auto_register_user
async def basket_handler(client: Client, message: Message):
    await basket_command(client, message)


@app.on_message(filters.command("roll", prefixes=["/", ".", "!"]))
@auto_register_user
async def roll_handler(client: Client, message: Message):
    await roll_command(client, message)

@app.on_message(filters.command("football", prefixes=["/", ".", "!"]))
@auto_register_user
async def football_handler(client: Client, message: Message):
    await football_command(client, message)

@app.on_message(filters.command("sgtop", prefixes=["/", ".", "!"]))
@auto_register_user
async def sgtop_handler(client: Client, message: Message):
    await sgtop_command(client, message)

@app.on_message(filters.command("wintop", prefixes=["/", ".", "!"]))
@auto_register_user
async def wintop_handler(client: Client, message: Message):
    await wintop_command(client, message)

@app.on_message(filters.command("wtop", prefixes=["/", ".", "!"]))
@auto_register_user
async def wtop_handler(client: Client, message: Message):
    await wtop_command(client, message)

@app.on_message(filters.command("sredeem", prefixes=["/", ".", "!"]))
@auto_register_user
async def sredeem_handler(client: Client, message: Message):
    await sredeem_command(client, message)

@app.on_message(filters.command("safari", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def safari_handler(client: Client, message: Message):
    await safari_command(client, message)

@app.on_message(filters.command("enter", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def enter_handler(client: Client, message: Message):
    await enter_command(client, message)

@app.on_message(filters.command("exit", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def exit_handler(client: Client, message: Message):
    await exit_command(client, message)

@app.on_message(filters.command("hunt", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def hunt_handler(client: Client, message: Message):
    await hunt_command(client, message)

@app.on_message(filters.command("team", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def team_handler(client: Client, message: Message):
    from modules.team import team_command
    await team_command(client, message)

@app.on_message(filters.command("addteam", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def addteam_handler(client: Client, message: Message):
    from modules.team import addteam_command
    await addteam_command(client, message)

@app.on_message(filters.command("removeteam", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def removeteam_handler(client: Client, message: Message):
    from modules.team import removeteam_command
    await removeteam_command(client, message)

@app.on_message(filters.command("editteam", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def editteam_handler(client: Client, message: Message):
    from modules.team import editteam_command
    await editteam_command(client, message)

@app.on_message(filters.command("swapteam", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def swapteam_handler(client: Client, message: Message):
    from modules.team import swapteam_command
    await swapteam_command(client, message)

@app.on_message(filters.command("moveteam", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def moveteam_handler(client: Client, message: Message):
    from modules.team import moveteam_command
    await moveteam_command(client, message)

@app.on_message(filters.command("battle", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def battle_handler(client: Client, message: Message):
    from modules.battle import battle_command
    await battle_command(client, message)

@app.on_message(filters.command("battleinfo", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def battleinfo_handler(client: Client, message: Message):
    from modules.battle import battleinfo_command
    await battleinfo_command(client, message)

@app.on_message(filters.command("mybattle", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def mybattle_handler(client: Client, message: Message):
    from modules.battle import mybattle_command
    await mybattle_command(client, message)

@app.on_message(filters.command("testteam", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def testteam_handler(client: Client, message: Message):
    from modules.battle import testteam_command
    await testteam_command(client, message)

@app.on_message(filters.command("clearbattles", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def clearbattles_handler(client: Client, message: Message):
    from modules.battle import clearbattles_command
    await clearbattles_command(client, message)
 

@app.on_message(filters.command("poke", prefixes=["/", ".", "!"]))
@auto_register_user
@require_database
async def poke_handler(client: Client, message: Message):
    from modules.poke import poke_command
    await poke_command(client, message)

@app.on_callback_query(filters.regex(r"^(poke_stats_|poke_moves_|poke_info_)\d+_\d+$"))
async def poke_callback_router(client: Client, callback_query: CallbackQuery):
    from modules.poke import poke_callback_handler
    await poke_callback_handler(client, callback_query)

@app.on_message(filters.command("clearcache", prefixes=["/", ".", "!"]))
@auto_register_user
async def clearcache_handler(client: Client, message: Message):
    await clear_cache_command(client, message)

@app.on_message(filters.command("bowl", prefixes=["/", ".", "!"]))
@auto_register_user
async def bowl_handler(client: Client, message: Message):
    await bowl_command(client, message)


@app.on_message(filters.command("slot", prefixes=["/", ".", "!"]))
@auto_register_user
async def slot_handler(client: Client, message: Message):
    await slot_command(client, message)


@app.on_message(filters.command("explore", prefixes=["/", ".", "!"]))
@auto_register_user
async def explore_handler(client: Client, message: Message):
    await explore_command(client, message)


@app.on_callback_query(filters.regex(r"^explore_"))
async def explore_callback_handler(client: Client, callback_query: CallbackQuery):
    await explore_callback(client, callback_query)

@app.on_message(filters.command("exchange", prefixes=["/", ".", "!"]) & filters.private)
@auto_register_user
@require_database
async def exchange_handler(client: Client, message: Message):
    await exchange_command(client, message)

@app.on_message(filters.command("exchangehistory", prefixes=["/", ".", "!"]) & filters.private)
@auto_register_user
@require_database
async def exchange_history_handler(client: Client, message: Message):
    await exchange_history_command(client, message)

@app.on_callback_query(filters.regex(r"^(exchange_|exchange_history$)"))
async def exchange_callback_handler_router(client: Client, callback_query: CallbackQuery):
    await exchange_callback_handler(client, callback_query)

# Group handlers for exchange commands - show helpful message
@app.on_message(filters.command(["exchange", "exchangehistory"], prefixes=["/", ".", "!"]) & filters.group)
async def exchange_group_handler(client: Client, message: Message):
    await message.reply_text(
        "💫 <b>Exchange Commands</b> 💫\n\n"
        "For security and privacy, exchange commands only work in private messages.\n\n"
        "Please send me a private message and use:\n"
        "• <code>/exchange</code> - View exchange interface\n"
        "• <code>/exchange [amount]</code> - Exchange tokens for shards\n"
        "• <code>/exchangehistory</code> - View your exchange history"
    )

@app.on_message(filters.reply & filters.text)
@auto_register_user
async def reply_giveaway_handler(client: Client, message: Message):
    await enter_giveaway(client, message)


@app.on_message(filters.text & filters.group, group=10)
@auto_register_user
@require_database
async def handler_trigger_group(client: Client, message: Message):
    # Allow users to open their collection in groups using their handler
    if not message.from_user:
        return
    text = (message.text or "").strip()
    if not text or len(text) > 64:
        return
    from modules.postgres_database import get_database
    db = get_database()
    user = await db.get_user_by_collection_handler(text)
    # Only trigger for the sender's own handler
    if not user or user.get('user_id') != message.from_user.id:
        return
    await collection_command(client, message)


@app.on_message(filters.group, group=-1)
@auto_register_user
@require_database
async def group_message_counter(client: Client, message: Message):
    # Ensure this handler never blocks others
    db = get_database()
    user_id = message.from_user.id if message.from_user else None
    if user_id:
        try:
            from modules.ban_manager import check_user_ban_status
            is_banned, _ = await check_user_ban_status(user_id, db)
            if is_banned:
                return  # Do not count messages from banned users
        except Exception as e:
            # On any error, assume not banned and continue counting
            try:
                print(f"group_message_counter ban check error (continuing): {e}")
            except:
                pass

    try:
        await handle_message(client, message)
    except Exception as e:
        try:
            print(f"group_message_counter error: {e}")
        except:
            pass


# Upload handlers
@app.on_message(filters.regex("⚙ Admin Panel ⚙") & filters.private)
async def admin_panel_handler(client: Client, message: Message):
    await handle_admin_panel(client, message)

@app.on_message(filters.command("admin", prefixes=["/", ".", "!"]) & filters.private, group=2)
async def admin_command_handler(client: Client, message: Message):
    await handle_admin_panel(client, message)

# Media handlers for upload process
@app.on_message(filters.photo & filters.private)
async def handle_photo_upload(client: Client, message: Message):
    # Check if user is in edit image state
    if await handle_edit_image_upload(client, message):
        return
    # Otherwise handle as regular upload
    await handle_media_upload(client, message)

@app.on_message(filters.video & filters.private)
async def handle_video_upload(client: Client, message: Message):
    # Check if user is in edit image state
    if await handle_edit_image_upload(client, message):
        return
    # Otherwise handle as regular upload
    await handle_media_upload(client, message)


# Text message handlers for conversation flow
@app.on_message(filters.text & filters.private, group=5)
async def handle_text_input(client: Client, message: Message):
    # Handle name input first
    if await handle_name_input(client, message):
        return
    # Handle anime input if name input didn't handle it
    if await handle_anime_input(client, message):
        return
    # Handle type input if anime input didn't handle it
    if await handle_type_input(client, message):
        return
    # Handle anime name input for creation
    if await handle_anime_name_input(client, message):
        return
    # Handle type name input for creation
    if await handle_type_name_input(client, message):
        return
    # Handle edit character ID input
    if await handle_edit_character_id_input(client, message):
        return
    # Handle edit name input
    if await handle_edit_name_input(client, message):
        return
    # Handle edit anime input
    if await handle_edit_anime_input(client, message):
        return
    # Handle edit type input
    if await handle_edit_type_input(client, message):
        return
    # Handle edit type name input for creation
    if await handle_edit_type_name_input(client, message):
        return
    # Handle delete character ID input
    if await handle_delete_character_id_input(client, message):
        return
    # Handle reset character ID input
    if await handle_reset_character_id_input(client, message):
        return
    # Handle rename anime input
    if await handle_rename_anime_input(client, message):
        return
    # Handle new anime name input for rename
    if await handle_new_anime_name_input(client, message):
        return

# Callback query handlers for upload process
@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "add_waifu"))
async def add_waifu_callback(client: Client, callback_query: CallbackQuery):
    await start_character_upload(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "glob_confirm"))
async def glob_confirm_callback(client: Client, callback_query: CallbackQuery):
    await confirm_upload_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "close_upload"))
async def close_upload_callback(client: Client, callback_query: CallbackQuery):
    await close_upload_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "xxx"))
async def close_admin_panel_callback(client: Client, callback_query: CallbackQuery):
    await close_admin_panel(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "add_anime"))
async def add_anime_callback(client: Client, callback_query: CallbackQuery):
    await add_anime_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "rename_anime"))
async def rename_anime_callback(client: Client, callback_query: CallbackQuery):
    await rename_anime_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "edit_character"))
async def edit_character_callback(client: Client, callback_query: CallbackQuery):
    await edit_character_handler(client, callback_query)

# Edit character choice handlers
@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data in ["edit_name", "edit_anime", "edit_type", "edit_rarity", "edit_image"]))
async def edit_choice_callback(client: Client, callback_query: CallbackQuery):
    await handle_edit_choice(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data.startswith("edit_rarity_")))
async def edit_rarity_selection_callback(client: Client, callback_query: CallbackQuery):
    await handle_edit_rarity_selection(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "edit_type"))
async def edit_type_callback(client: Client, callback_query: CallbackQuery):
    await handle_edit_choice(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_edit"))
async def confirm_edit_callback(client: Client, callback_query: CallbackQuery):
    await confirm_edit_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_delete"))
async def confirm_delete_callback(client: Client, callback_query: CallbackQuery):
    await confirm_delete_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_reset"))
async def confirm_reset_callback(client: Client, callback_query: CallbackQuery):
    await confirm_reset_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_rename_anime"))
async def confirm_rename_anime_callback(client: Client, callback_query: CallbackQuery):
    await confirm_rename_anime_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "delete_character"))
async def delete_character_callback(client: Client, callback_query: CallbackQuery):
    await delete_character_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "reset_character"))
async def reset_character_callback(client: Client, callback_query: CallbackQuery):
    await reset_character_handler(client, callback_query)

# Type creation confirmation handler
@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_type_creation"))
async def confirm_type_creation_callback(client: Client, callback_query: CallbackQuery):
    await confirm_type_creation_handler(client, callback_query)

# Type creation from edit flow handler
@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "create_type"))
async def create_type_callback(client: Client, callback_query: CallbackQuery):
    await create_type_from_upload_handler(client, callback_query)

@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "create_type_from_edit"))
async def create_type_from_edit_callback(client: Client, callback_query: CallbackQuery):
    await create_type_from_edit_handler(client, callback_query)

# Anime creation confirmation handler
@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data == "confirm_anime_creation"))
async def confirm_anime_creation_callback(client: Client, callback_query: CallbackQuery):
    await confirm_anime_creation_handler(client, callback_query)

# Rarity selection handler
@app.on_callback_query(filters.create(lambda _, __, callback_query: callback_query.data.startswith("glob_") and callback_query.data != "glob_confirm"))
async def handle_rarity_selection_callback(client: Client, callback_query: CallbackQuery):
    await handle_rarity_selection(client, callback_query)



# Periodic cleanup task
async def periodic_cleanup():
    """Periodic cleanup task to prevent memory leaks"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            cleanup_session()
            print("Session cleanup completed")
        except Exception as e:
            print(f"Error in periodic cleanup: {e}")



# Global error handler using try-catch in handlers
async def safe_handler(func):
    """Decorator to safely handle errors in message handlers"""
    async def wrapper(client: Client, message: Message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except Exception as e:
            # Log the error
            print(f"Error in handler {func.__name__}: {type(e).__name__}: {e}")
            
            # Log to file for debugging
            import traceback
            with open("error_log.txt", "a", encoding="utf-8") as f:
                f.write(f"\n{datetime.now()}: {type(e).__name__}: {e}\n")
                f.write(traceback.format_exc())
                f.write("\n" + "="*50 + "\n")
            
            # Try to send a user-friendly error message
            try:
                await message.reply_text("An error occurred while processing your request. Please try again later.")
            except:
                print(f"Failed to send error message for {func.__name__}")
    
    return wrapper






if __name__ == "__main__":
    register_claim_settings_handlers(app)
    register_canime_handlers(app)
    register_safari_handlers(app)
    setup_team_handlers(app)
    setup_battle_handlers(app)
    # Clear session data on startup
    cleanup_session()
    print("Session data cleared on startup")
    # Initialize database before running the bot
    # Synchronously initialize the database before running the bot
    loop = asyncio.get_event_loop()
    loop.run_until_complete(startup_initialization())
    print("🔄 Starting bot...")
    
    app.run()
