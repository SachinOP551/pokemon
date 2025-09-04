#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Daily Reward Scheduler Module
Automatically distributes rewards to top 10 collectors daily at 5PM UTC
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pyrogram import Client
from config import DROPTIME_LOG_CHANNEL, LOG_CHANNEL_ID
from .top import distribute_daily_rewards

# Setup logging
reward_logger = logging.getLogger('daily_reward_scheduler')
reward_logger.setLevel(logging.INFO)

# Create file handler for reward logs
if not reward_logger.handlers:
    handler = logging.FileHandler('daily_reward_scheduler.log')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    reward_logger.addHandler(handler)

class DailyRewardScheduler:
    def __init__(self, client: Client):
        self.client = client
        self.is_running = False
        self.reward_task = None
        
    async def wait_until_next_reward_time(self):
        """Wait until the next 5PM UTC"""
        now = datetime.now(timezone.utc)
        target_time = now.replace(hour=17, minute=0, second=0, microsecond=0)
        
        # If it's already past 5PM today, schedule for tomorrow
        if now >= target_time:
            target_time += timedelta(days=1)
        
        # Calculate seconds to wait
        wait_seconds = (target_time - now).total_seconds()
        reward_logger.info(f"Next reward distribution scheduled for: {target_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        reward_logger.info(f"Waiting {wait_seconds:.0f} seconds ({wait_seconds/3600:.1f} hours)")
        
        return wait_seconds
    
    async def perform_daily_reward_distribution(self):
        """Perform the daily reward distribution"""
        try:
            reward_logger.info("Starting daily reward distribution...")
            
            # Distribute rewards using the existing function
            await distribute_daily_rewards(self.client)
            
            reward_logger.info("Daily reward distribution completed successfully")
            
            # Send success notification to log channel
            try:
                success_message = (
                    f"✅ **Daily Reward Distribution Completed**\n\n"
                    f"🎉 Rewards have been distributed to top 10 collectors\n"
                    f"📅 **Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"🔄 **Next Distribution:** Tomorrow at 5PM UTC"
                )
                
                await self.client.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=success_message
                )
            except Exception as notify_error:
                reward_logger.error(f"Failed to send success notification: {notify_error}")
                
        except Exception as e:
            reward_logger.error(f"Daily reward distribution failed: {e}")
            
            # Send error notification to log channel
            try:
                error_message = (
                    f"🚨 **Daily Reward Distribution Error**\n\n"
                    f"❌ **Error:** {str(e)}\n"
                    f"📅 **Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"🔄 **Type:** Daily Reward Distribution"
                )
                
                await self.client.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=error_message
                )
            except Exception as notify_error:
                reward_logger.error(f"Failed to send error notification: {notify_error}")
    
    async def reward_loop(self):
        """Main reward loop that runs daily at 5PM UTC"""
        reward_logger.info("Daily reward scheduler started - running daily at 5PM UTC")
        
        while self.is_running:
            try:
                # Wait until next reward time
                wait_seconds = await self.wait_until_next_reward_time()
                await asyncio.sleep(wait_seconds)
                
                # Perform reward distribution
                await self.perform_daily_reward_distribution()
                
            except asyncio.CancelledError:
                reward_logger.info("Daily reward scheduler cancelled")
                break
            except Exception as e:
                reward_logger.error(f"Error in reward loop: {e}")
                # Wait 1 hour before retrying on error
                await asyncio.sleep(3600)
    
    def start(self):
        """Start the daily reward scheduler"""
        if self.is_running:
            reward_logger.warning("Daily reward scheduler is already running")
            return
        
        self.is_running = True
        self.reward_task = asyncio.create_task(self.reward_loop())
        reward_logger.info("Daily reward scheduler started")
    
    def stop(self):
        """Stop the daily reward scheduler"""
        if not self.is_running:
            reward_logger.warning("Daily reward scheduler is not running")
            return
        
        self.is_running = False
        if self.reward_task:
            self.reward_task.cancel()
        reward_logger.info("Daily reward scheduler stopped")
    
    async def manual_reward_distribution(self):
        """Perform a manual reward distribution (for testing or on-demand use)"""
        try:
            reward_logger.info("Starting manual reward distribution...")
            await self.perform_daily_reward_distribution()
            return True
        except Exception as e:
            reward_logger.error(f"Manual reward distribution failed: {e}")
            return False

# Global reward scheduler instance
reward_scheduler = None

def get_reward_scheduler(client: Client = None) -> DailyRewardScheduler:
    """Get or create the global reward scheduler instance"""
    global reward_scheduler
    if reward_scheduler is None and client:
        reward_scheduler = DailyRewardScheduler(client)
    return reward_scheduler

def start_daily_reward_scheduler(client: Client):
    """Start the daily reward scheduler"""
    scheduler = get_reward_scheduler(client)
    if scheduler:
        scheduler.start()

def stop_daily_reward_scheduler():
    """Stop the daily reward scheduler"""
    global reward_scheduler
    if reward_scheduler:
        reward_scheduler.stop()

async def manual_reward_distribution_command(client: Client):
    """Command to perform a manual reward distribution"""
    scheduler = get_reward_scheduler(client)
    if scheduler:
        success = await scheduler.manual_reward_distribution()
        return success
    return False
