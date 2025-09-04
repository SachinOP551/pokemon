from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from modules.postgres_database import get_database, get_postgres_pool
from modules.decorators import auto_register_user
import re

# Exchange constants
TOKENS_PER_SHARD = 35  # 1 shard = 35 tokens
DAILY_EXCHANGE_LIMIT = 3000000  # 30 lakh tokens = 3,000,000 tokens
MAX_SHARDS_PER_DAY = DAILY_EXCHANGE_LIMIT // TOKENS_PER_SHARD  # 85,714 shards max per day

class ExchangeManager:
    """Manages token to shard exchanges"""
    
    # Class-level locks dictionary for per-user concurrency control
    _user_locks = {}
    _locks_lock = asyncio.Lock()  # Protects the _user_locks dictionary itself
    
    @classmethod
    async def get_user_lock(cls, user_id: int) -> asyncio.Lock:
        """Get or create a lock for a specific user"""
        async with cls._locks_lock:
            if user_id not in cls._user_locks:
                cls._user_locks[user_id] = asyncio.Lock()
            return cls._user_locks[user_id]
    
    @classmethod
    async def cleanup_old_locks(cls, max_locks: int = 1000):
        """Clean up old locks to prevent memory leaks"""
        async with cls._locks_lock:
            if len(cls._user_locks) > max_locks:
                # Remove locks that are not currently acquired
                to_remove = []
                for user_id, lock in cls._user_locks.items():
                    if not lock.locked():
                        to_remove.append(user_id)
                        if len(to_remove) >= len(cls._user_locks) - max_locks:
                            break
                
                for user_id in to_remove:
                    del cls._user_locks[user_id]
                
                print(f"Cleaned up {len(to_remove)} unused exchange locks")
    
    @staticmethod
    async def ensure_exchange_table():
        """Create the exchange_history table if it doesn't exist"""
        try:
            pool = get_postgres_pool()
            if not pool:
                print("No database pool available for exchange table creation")
                return False
                
            async with pool.acquire() as conn:
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS exchange_history (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT NOT NULL,
                        tokens_spent INTEGER NOT NULL,
                        shards_received INTEGER NOT NULL,
                        exchange_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_exchange_user_date 
                    ON exchange_history(user_id, exchange_date);
                ''')
                print("Exchange history table ensured")
                return True
        except Exception as e:
            print(f"Error creating exchange history table: {e}")
            return False
    
    @classmethod
    async def get_user_daily_exchange(cls, user_id: int) -> int:
        """Get the total tokens exchanged by user today with optional locking"""
        try:
            pool = get_postgres_pool()
            if not pool:
                return 0
                
            async with pool.acquire() as conn:
                # Get tokens exchanged in the last 24 hours
                row = await conn.fetchrow('''
                    SELECT COALESCE(SUM(tokens_spent), 0) as total_tokens
                    FROM exchange_history 
                    WHERE user_id = $1 
                    AND exchange_date >= NOW() - INTERVAL '24 hours'
                ''', user_id)
                
                return int(row['total_tokens']) if row else 0
        except Exception as e:
            print(f"Error getting user daily exchange: {e}")
            return 0
    
    @classmethod
    async def get_user_balances(cls, user_id: int, use_lock: bool = False) -> Dict[str, int]:
        """Get user's current token and shard balances with optional locking"""
        if use_lock:
            user_lock = await cls.get_user_lock(user_id)
            async with user_lock:
                return await cls._get_user_balances_unlocked(user_id)
        else:
            return await cls._get_user_balances_unlocked(user_id)
    
    @staticmethod
    async def _get_user_balances_unlocked(user_id: int) -> Dict[str, int]:
        """Internal method to get user balances without locking"""
        try:
            pool = get_postgres_pool()
            if not pool:
                return {"tokens": 0, "shards": 0}
                
            async with pool.acquire() as conn:
                row = await conn.fetchrow('''
                    SELECT wallet, shards 
                    FROM users 
                    WHERE user_id = $1
                ''', user_id)
                
                if row:
                    return {
                        "tokens": int(row['wallet']) if row['wallet'] else 0,
                        "shards": int(row['shards']) if row['shards'] else 0
                    }
                return {"tokens": 0, "shards": 0}
        except Exception as e:
            print(f"Error getting user balances: {e}")
            return {"tokens": 0, "shards": 0}
    
    @classmethod
    async def execute_exchange(cls, user_id: int, tokens_to_exchange: int) -> Dict[str, Any]:
        """Execute a token to shard exchange with user-specific locking and retry mechanism"""
        # Get user-specific lock to prevent concurrent exchanges for the same user
        user_lock = await cls.get_user_lock(user_id)
        
        # Implement retry mechanism for transient failures
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use timeout to prevent indefinite blocking
                async with asyncio.wait_for(user_lock.acquire(), timeout=30.0):
                    try:
                        return await cls._execute_exchange_locked(user_id, tokens_to_exchange)
                    finally:
                        user_lock.release()
            except asyncio.TimeoutError:
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": "timeout_error",
                        "message": "Exchange operation timed out. Please try again later."
                    }
                # Wait before retry with exponential backoff
                await asyncio.sleep(0.5 * (2 ** attempt))
            except Exception as e:
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": "retry_exhausted",
                        "message": f"Exchange failed after {max_retries} attempts. Please try again later."
                    }
                # Wait before retry
                await asyncio.sleep(0.5 * (2 ** attempt))
        
        return {
            "success": False,
            "error": "unexpected_failure",
            "message": "Unexpected failure in exchange operation."
        }
    
    @staticmethod
    async def _execute_exchange_locked(user_id: int, tokens_to_exchange: int) -> Dict[str, Any]:
        """Internal method that executes exchange while already holding user lock"""
        try:
            # Validate exchange amount
            if tokens_to_exchange < TOKENS_PER_SHARD:
                return {
                    "success": False,
                    "error": "minimum_amount",
                    "message": f"Minimum exchange amount is {TOKENS_PER_SHARD:,} tokens (1 shard)"
                }
            
            # Must be a multiple of TOKENS_PER_SHARD
            if tokens_to_exchange % TOKENS_PER_SHARD != 0:
                return {
                    "success": False,
                    "error": "invalid_amount",
                    "message": f"Exchange amount must be a multiple of {TOKENS_PER_SHARD} tokens"
                }
            
            shards_to_receive = tokens_to_exchange // TOKENS_PER_SHARD
            
            pool = get_postgres_pool()
            if not pool:
                return {
                    "success": False,
                    "error": "database_error",
                    "message": "Database connection unavailable"
                }
            
            async with pool.acquire() as conn:
                # Start transaction with isolation level for consistency
                async with conn.transaction(isolation='serializable'):
                    # Check user balances with row-level locking
                    user_row = await conn.fetchrow('''
                        SELECT wallet, shards 
                        FROM users 
                        WHERE user_id = $1
                        FOR UPDATE
                    ''', user_id)
                    
                    if not user_row:
                        return {
                            "success": False,
                            "error": "user_not_found",
                            "message": "User not found in database"
                        }
                    
                    current_tokens = int(user_row['wallet']) if user_row['wallet'] else 0
                    current_shards = int(user_row['shards']) if user_row['shards'] else 0
                    
                    # Check if user has enough tokens
                    if current_tokens < tokens_to_exchange:
                        return {
                            "success": False,
                            "error": "insufficient_tokens",
                            "message": f"You need {tokens_to_exchange:,} tokens but only have {current_tokens:,}"
                        }
                    
                    # Check daily limit
                    daily_exchanged = await ExchangeManager.get_user_daily_exchange(user_id)
                    if daily_exchanged + tokens_to_exchange > DAILY_EXCHANGE_LIMIT:
                        remaining_limit = DAILY_EXCHANGE_LIMIT - daily_exchanged
                        return {
                            "success": False,
                            "error": "daily_limit_exceeded",
                            "message": f"Daily exchange limit exceeded. You can exchange {remaining_limit:,} more tokens today"
                        }
                    
                    # Update user balances
                    await conn.execute('''
                        UPDATE users 
                        SET wallet = wallet - $1, shards = shards + $2
                        WHERE user_id = $3
                    ''', tokens_to_exchange, shards_to_receive, user_id)
                    
                    # Record the exchange
                    await conn.execute('''
                        INSERT INTO exchange_history (user_id, tokens_spent, shards_received)
                        VALUES ($1, $2, $3)
                    ''', user_id, tokens_to_exchange, shards_to_receive)
                    
                    return {
                        "success": True,
                        "tokens_spent": tokens_to_exchange,
                        "shards_received": shards_to_receive,
                        "new_token_balance": current_tokens - tokens_to_exchange,
                        "new_shard_balance": current_shards + shards_to_receive,
                        "daily_exchanged": daily_exchanged + tokens_to_exchange,
                        "daily_remaining": DAILY_EXCHANGE_LIMIT - (daily_exchanged + tokens_to_exchange)
                    }
                    
        except Exception as e:
            print(f"Error executing exchange: {e}")
            return {
                "success": False,
                "error": "execution_error",
                "message": f"An error occurred during the exchange: {str(e)}"
            }

# Global exchange manager instance
exchange_manager = ExchangeManager()

@auto_register_user
async def exchange_command(client: Client, message: Message):
    """Handle /exchange command - show exchange information and interface"""
    user_id = message.from_user.id
    args = message.text.split()
    
    # Ensure exchange table exists
    await exchange_manager.ensure_exchange_table()
    
    # Get user balances and daily exchange info with locking for consistency
    balances = await exchange_manager.get_user_balances(user_id, use_lock=True)
    daily_exchanged = await exchange_manager.get_user_daily_exchange(user_id)
    daily_remaining = DAILY_EXCHANGE_LIMIT - daily_exchanged
    
    # If user provided an amount, try to exchange
    if len(args) > 1:
        try:
            # Parse the amount (support formats like 1k, 1m, etc.)
            amount_str = args[1].lower()
            if amount_str.endswith('k'):
                tokens_to_exchange = int(float(amount_str[:-1]) * 1000)
            elif amount_str.endswith('m'):
                tokens_to_exchange = int(float(amount_str[:-1]) * 1000000)
            elif amount_str.endswith('l'):
                tokens_to_exchange = int(float(amount_str[:-1]) * 100000)
            else:
                tokens_to_exchange = int(amount_str)
            
            if tokens_to_exchange <= 0:
                await message.reply_text("❌ Please provide a valid positive amount!")
                return
            
            # Execute the exchange
            result = await exchange_manager.execute_exchange(user_id, tokens_to_exchange)
            
            if result["success"]:
                success_text = (
                    "✅ <b>Exchange Successful!</b>\n\n"
                    f"🪙 <b>Tokens Spent:</b> {result['tokens_spent']:,}\n"
                    f"💎 <b>Shards Received:</b> {result['shards_received']:,}\n\n"
                    f"💰 <b>New Token Balance:</b> {result['new_token_balance']:,}\n"
                    f"💎 <b>New Shard Balance:</b> {result['new_shard_balance']:,}\n\n"
                    f"📊 <b>Daily Usage:</b> {result['daily_exchanged']:,} / {DAILY_EXCHANGE_LIMIT:,} tokens\n"
                    f"🔄 <b>Remaining Today:</b> {result['daily_remaining']:,} tokens"
                )
                await message.reply_text(success_text)
            else:
                error_messages = {
                    "minimum_amount": f"❌ <b>Minimum Exchange</b>\n\nYou need at least {TOKENS_PER_SHARD:,} tokens to exchange for 1 shard.",
                    "invalid_amount": f"❌ <b>Invalid Amount</b>\n\nExchange amount must be a multiple of {TOKENS_PER_SHARD} tokens.",
                    "insufficient_tokens": f"❌ <b>Insufficient Tokens</b>\n\n{result['message']}",
                    "daily_limit_exceeded": f"⛔ <b>Daily Limit Exceeded</b>\n\n{result['message']}",
                    "user_not_found": "❌ <b>User Error</b>\n\nUser not found in database.",
                    "database_error": "❌ <b>Database Error</b>\n\nUnable to connect to database. Please try again later.",
                    "execution_error": f"❌ <b>Exchange Error</b>\n\n{result['message']}",
                    "timeout_error": "⏰ <b>Operation Timeout</b>\n\nThe exchange operation timed out. Please try again in a few moments.",
                    "retry_exhausted": "🔄 <b>System Busy</b>\n\nThe system is currently busy. Please wait a moment and try again.",
                    "unexpected_failure": "❌ <b>System Error</b>\n\nAn unexpected error occurred. Please try again later."
                }
                
                error_text = error_messages.get(result["error"], f"❌ <b>Unknown Error</b>\n\n{result['message']}")
                await message.reply_text(error_text)
            return
            
        except ValueError:
            await message.reply_text(
                "❌ <b>Invalid Format</b>\n\n"
                "Please use a valid number format:\n"
                "• <code>/exchange 35000</code> (exact amount)\n"
                "• <code>/exchange 35k</code> (thousands)\n"
                "• <code>/exchange 3.5l</code> (lakhs)\n"
                "• <code>/exchange 1m</code> (millions)"
            )
            return
    
    # Show exchange interface
    max_possible_shards = min(balances["tokens"] // TOKENS_PER_SHARD, daily_remaining // TOKENS_PER_SHARD)
    max_possible_tokens = max_possible_shards * TOKENS_PER_SHARD
    
    exchange_text = (
        "💱 <b>Token to Shard Exchange</b>\n\n"
        f"🪙 <b>Your Tokens:</b> {balances['tokens']:,}\n"
        f"💎 <b>Your Shards:</b> {balances['shards']:,}\n\n"
        f"📋 <b>Exchange Rate:</b> {TOKENS_PER_SHARD:,} tokens = 1 shard\n"
        f"📊 <b>Daily Limit:</b> {DAILY_EXCHANGE_LIMIT:,} tokens ({MAX_SHARDS_PER_DAY:,} shards)\n"
        f"🔄 <b>Used Today:</b> {daily_exchanged:,} tokens\n"
        f"⚡ <b>Remaining Today:</b> {daily_remaining:,} tokens\n\n"
        f"🎯 <b>Max Exchange Now:</b> {max_possible_tokens:,} tokens → {max_possible_shards:,} shards\n\n"
        "<b>How to Exchange:</b>\n"
        "• <code>/exchange [amount]</code>\n"
        "• <code>/exchange 35k</code> (35,000 tokens → 1,000 shards)\n"
        "• <code>/exchange 1l</code> (1,00,000 tokens → 2,857 shards)\n"
        "• <code>/exchange 1m</code> (10,00,000 tokens → 28,571 shards)"
    )
    
    # Create quick exchange buttons
    keyboard = []
    
    if max_possible_tokens >= TOKENS_PER_SHARD:
        # Quick exchange options
        quick_amounts = []
        
        # 1 shard option
        if max_possible_tokens >= TOKENS_PER_SHARD:
            quick_amounts.append((TOKENS_PER_SHARD, 1))
        
        # 1000 shards option
        if max_possible_tokens >= TOKENS_PER_SHARD * 1000:
            quick_amounts.append((TOKENS_PER_SHARD * 1000, 1000))
        
        # 5000 shards option
        if max_possible_tokens >= TOKENS_PER_SHARD * 5000:
            quick_amounts.append((TOKENS_PER_SHARD * 5000, 5000))
        
        # Max possible option
        if max_possible_shards > 0 and max_possible_shards not in [1, 1000, 5000]:
            quick_amounts.append((max_possible_tokens, max_possible_shards))
        
        # Create buttons (2 per row)
        for i in range(0, len(quick_amounts), 2):
            row = []
            for j in range(i, min(i + 2, len(quick_amounts))):
                tokens, shards = quick_amounts[j]
                if shards >= 1000000:
                    shard_text = f"{shards/1000000:.1f}M"
                elif shards >= 1000:
                    shard_text = f"{shards/1000:.0f}k"
                else:
                    shard_text = f"{shards:,}"
                
                row.append(InlineKeyboardButton(
                    f"💎 {shard_text} shards",
                    callback_data=f"exchange_{tokens}"
                ))
            keyboard.append(row)
    
    # Add exchange history button
    keyboard.append([InlineKeyboardButton("📊 Exchange History", callback_data="exchange_history")])
    
    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    await message.reply_text(exchange_text, reply_markup=reply_markup)

@auto_register_user
async def exchange_history_command(client: Client, message: Message):
    """Handle /exchangehistory command - show user's exchange history"""
    user_id = message.from_user.id
    
    try:
        pool = get_postgres_pool()
        if not pool:
            await message.reply_text("❌ Database connection unavailable!")
            return
            
        async with pool.acquire() as conn:
            # Get recent exchange history (last 10 exchanges)
            rows = await conn.fetch('''
                SELECT tokens_spent, shards_received, exchange_date
                FROM exchange_history 
                WHERE user_id = $1 
                ORDER BY exchange_date DESC 
                LIMIT 10
            ''', user_id)
            
            if not rows:
                await message.reply_text(
                    "📊 <b>Exchange History</b>\n\n"
                    "You haven't made any exchanges yet!\n"
                    "Use <code>/exchange</code> to start exchanging tokens for shards."
                )
                return
            
            # Get total stats
            stats_row = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_exchanges,
                    SUM(tokens_spent) as total_tokens_spent,
                    SUM(shards_received) as total_shards_received
                FROM exchange_history 
                WHERE user_id = $1
            ''', user_id)
            
            history_text = "📊 <b>Exchange History</b>\n\n"
            
            # Add total stats
            if stats_row:
                history_text += (
                    f"📈 <b>Total Exchanges:</b> {stats_row['total_exchanges']:,}\n"
                    f"🪙 <b>Total Tokens Spent:</b> {stats_row['total_tokens_spent']:,}\n"
                    f"💎 <b>Total Shards Received:</b> {stats_row['total_shards_received']:,}\n\n"
                )
            
            history_text += "<b>Recent Exchanges:</b>\n"
            
            for i, row in enumerate(rows, 1):
                exchange_date = row['exchange_date']
                date_str = exchange_date.strftime("%d/%m/%Y %H:%M")
                history_text += (
                    f"{i}. <code>{date_str}</code>\n"
                    f"   🪙 {row['tokens_spent']:,} tokens → 💎 {row['shards_received']:,} shards\n"
                )
            
            await message.reply_text(history_text)
            
    except Exception as e:
        print(f"Error getting exchange history: {e}")
        await message.reply_text("❌ Error retrieving exchange history!")

# Callback handler for exchange buttons
async def exchange_callback_handler(client: Client, callback_query: CallbackQuery):
    """Handle exchange-related callback queries"""
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data.startswith("exchange_") and data != "exchange_history":
        # Parse token amount from callback data like "exchange_35000"
        try:
            tokens_to_exchange = int(data.split("_")[1])
        except (ValueError, IndexError):
            await callback_query.answer("❌ Invalid exchange data!", show_alert=True)
            return
        
        # Execute the exchange
        result = await exchange_manager.execute_exchange(user_id, tokens_to_exchange)
        
        if result["success"]:
            success_text = (
                "✅ <b>Exchange Complete!</b>\n\n"
                f"🪙 Spent: {result['tokens_spent']:,} tokens\n"
                f"💎 Received: {result['shards_received']:,} shards\n\n"
                f"💰 Token Balance: {result['new_token_balance']:,}\n"
                f"💎 Shard Balance: {result['new_shard_balance']:,}"
            )
            await callback_query.answer("✅ Exchange successful!", show_alert=True)
            
            # Update the message to show the result
            await callback_query.message.edit_text(success_text)
        else:
            error_text = f"❌ {result['message']}"
            await callback_query.answer(error_text, show_alert=True)
    
    elif data == "exchange_history":
        try:
            pool = get_postgres_pool()
            if not pool:
                await callback_query.answer("❌ Database unavailable!", show_alert=True)
                return
                
            async with pool.acquire() as conn:
                # Get recent exchange history (last 5 for callback)
                rows = await conn.fetch('''
                    SELECT tokens_spent, shards_received, exchange_date
                    FROM exchange_history 
                    WHERE user_id = $1 
                    ORDER BY exchange_date DESC 
                    LIMIT 5
                ''', user_id)
                
                if not rows:
                    await callback_query.answer("No exchange history found!", show_alert=True)
                    return
                
                history_text = "📊 Recent Exchanges:\n\n"
                
                for i, row in enumerate(rows, 1):
                    exchange_date = row['exchange_date']
                    date_str = exchange_date.strftime("%d/%m %H:%M")
                    history_text += f"{i}. {date_str}: {row['tokens_spent']:,}🪙 → {row['shards_received']:,}💎\n"
                
                history_text += f"\nUse /exchangehistory for full history"
                
                await callback_query.answer(history_text, show_alert=True)
                
        except Exception as e:
            print(f"Error getting exchange history callback: {e}")
            await callback_query.answer("❌ Error retrieving history!", show_alert=True)

# Initialize exchange manager
async def init_exchange_system():
    """Initialize the exchange system"""
    await exchange_manager.ensure_exchange_table()
    
    # Start periodic lock cleanup task
    asyncio.create_task(periodic_lock_cleanup())
    
    print("Exchange system initialized")

async def periodic_lock_cleanup():
    """Periodic task to clean up unused locks"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            await ExchangeManager.cleanup_old_locks()
        except Exception as e:
            print(f"Error in periodic lock cleanup: {e}")
