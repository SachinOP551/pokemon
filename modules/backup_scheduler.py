#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PostgreSQL Backup Scheduler Module
Creates automated backups using pg_dump every 30 minutes and sends to Telegram channel
"""

import asyncio
import os
import subprocess
import tempfile
import shutil
from datetime import datetime, timezone
from pathlib import Path
import logging
import urllib.parse
from pyrogram import Client
from pyrogram.types import InputMediaDocument
from config import NEON_URI, LOG_CHANNEL_ID

# Setup logging
backup_logger = logging.getLogger('backup_scheduler')
backup_logger.setLevel(logging.INFO)

# Create file handler for backup logs
if not backup_logger.handlers:
    handler = logging.FileHandler('backup_scheduler.log')
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    backup_logger.addHandler(handler)

# Target channel for backup files
BACKUP_CHANNEL_ID = -1002936399284

class PostgreSQLBackupScheduler:
    def __init__(self, client: Client):
        self.client = client
        self.is_running = False
        self.backup_task = None
        
    def parse_database_uri(self, uri: str) -> dict:
        """Parse PostgreSQL connection URI to extract connection parameters"""
        try:
            # Use urllib.parse to properly handle URL encoding
            parsed = urllib.parse.urlparse(uri)
            
            # Extract components
            username = urllib.parse.unquote(parsed.username or '')
            password = urllib.parse.unquote(parsed.password or '')
            host = parsed.hostname or ''
            port = str(parsed.port or 5432)
            database = urllib.parse.unquote(parsed.path.lstrip('/') or '')
            
            return {
                'host': host,
                'port': port,
                'database': database,
                'username': username,
                'password': password
            }
        except Exception as e:
            backup_logger.error(f"Error parsing database URI: {e}")
            return {}
    
    async def create_backup(self) -> str:
        """Create a PostgreSQL backup using pg_dump"""
        try:
            # Parse database connection parameters
            db_params = self.parse_database_uri(NEON_URI)
            if not db_params:
                raise Exception("Failed to parse database URI")
            
            # Log connection parameters (without password for security)
            backup_logger.info(f"Connecting to: {db_params['host']}:{db_params['port']}/{db_params['database']} as {db_params['username']}")
            
            # Create timestamp for backup filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_filename = f"pokemon_backup_{timestamp}.dump"
            
            # Create temporary directory for backup
            with tempfile.TemporaryDirectory() as temp_dir:
                backup_path = os.path.join(temp_dir, backup_filename)
                
                # Set environment variables for pg_dump
                env = os.environ.copy()
                env['PGPASSWORD'] = db_params['password']
                
                # Build pg_dump command for custom format (.dump)
                pg_dump_cmd = [
                    'pg_dump',
                    '-h', db_params['host'],
                    '-p', db_params['port'],
                    '-U', db_params['username'],
                    '-d', db_params['database'],
                    '--no-password',
                    '--verbose',
                    '--clean',
                    '--if-exists',
                    '--create',
                    '--format=custom',
                    '--compress=9',
                    '--file', backup_path
                ]
                
                backup_logger.info(f"Starting backup with command: {' '.join(pg_dump_cmd[:-2])}")  # Don't log password
                
                # Execute pg_dump
                process = await asyncio.create_subprocess_exec(
                    *pg_dump_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                    raise Exception(f"pg_dump failed with return code {process.returncode}: {error_msg}")
                
                # Check if backup file was created and has content
                if not os.path.exists(backup_path):
                    raise Exception("Backup file was not created")
                
                file_size = os.path.getsize(backup_path)
                if file_size == 0:
                    raise Exception("Backup file is empty")
                
                backup_logger.info(f"Backup created successfully: {backup_filename} ({file_size} bytes)")
                
                # Create a permanent backup file in the project directory
                permanent_backup_path = os.path.join(os.getcwd(), backup_filename)
                shutil.copy2(backup_path, permanent_backup_path)
                
                return permanent_backup_path
                
        except Exception as e:
            backup_logger.error(f"Error creating backup: {e}")
            raise
    
    async def send_backup_to_channel(self, backup_path: str):
        """Send backup file to the specified Telegram channel"""
        try:
            if not os.path.exists(backup_path):
                raise Exception(f"Backup file not found: {backup_path}")
            
            file_size = os.path.getsize(backup_path)
            filename = os.path.basename(backup_path)
            
            # Create caption with backup information
            caption = (
                f"🗄️ **Pokemon Database Backup**\n\n"
            )
            
            # Send the backup file to the channel
            await self.client.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=backup_path,
                caption=caption,
                file_name=filename
            )
            
            backup_logger.info(f"Backup sent to channel successfully: {filename}")
            
            # Clean up the backup file after sending
            try:
                os.remove(backup_path)
                backup_logger.info(f"Cleaned up backup file: {filename}")
            except Exception as e:
                backup_logger.warning(f"Failed to clean up backup file {filename}: {e}")
                
        except Exception as e:
            backup_logger.error(f"Error sending backup to channel: {e}")
            # Try to clean up the backup file even if sending failed
            try:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
            except:
                pass
            raise
    
    def format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    async def perform_backup(self):
        """Perform a complete backup operation"""
        try:
            backup_logger.info("Starting automated backup process...")
            
            # Create backup
            backup_path = await self.create_backup()
            
            # Send to channel
            await self.send_backup_to_channel(backup_path)
            
            backup_logger.info("Automated backup completed successfully")
            
        except Exception as e:
            backup_logger.error(f"Automated backup failed: {e}")
            
            # Send error notification to log channel
            try:
                error_message = (
                    f"🚨 **Backup Error**\n\n"
                    f"❌ **Error:** {str(e)}\n"
                    f"📅 **Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
                    f"🔄 **Type:** Automated Backup (30min interval)"
                )
                
                await self.client.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=error_message
                )
            except Exception as notify_error:
                backup_logger.error(f"Failed to send error notification: {notify_error}")
    
    async def backup_loop(self):
        """Main backup loop that runs every 30 minutes"""
        backup_logger.info("Backup scheduler started - running every 30 minutes")
        
        while self.is_running:
            try:
                # Perform backup
                await self.perform_backup()
                
                # Wait 30 minutes (1800 seconds)
                await asyncio.sleep(1800)
                
            except asyncio.CancelledError:
                backup_logger.info("Backup scheduler cancelled")
                break
            except Exception as e:
                backup_logger.error(f"Error in backup loop: {e}")
                # Wait 5 minutes before retrying on error
                await asyncio.sleep(300)
    
    def start(self):
        """Start the backup scheduler"""
        if self.is_running:
            backup_logger.warning("Backup scheduler is already running")
            return
        
        self.is_running = True
        self.backup_task = asyncio.create_task(self.backup_loop())
        backup_logger.info("Backup scheduler started")
    
    def stop(self):
        """Stop the backup scheduler"""
        if not self.is_running:
            backup_logger.warning("Backup scheduler is not running")
            return
        
        self.is_running = False
        if self.backup_task:
            self.backup_task.cancel()
        backup_logger.info("Backup scheduler stopped")
    
    async def manual_backup(self):
        """Perform a manual backup (for testing or on-demand use)"""
        try:
            backup_logger.info("Starting manual backup...")
            await self.perform_backup()
            return True
        except Exception as e:
            backup_logger.error(f"Manual backup failed: {e}")
            return False

# Global backup scheduler instance
backup_scheduler = None

def get_backup_scheduler(client: Client = None) -> PostgreSQLBackupScheduler:
    """Get or create the global backup scheduler instance"""
    global backup_scheduler
    if backup_scheduler is None and client:
        backup_scheduler = PostgreSQLBackupScheduler(client)
    return backup_scheduler

def start_backup_scheduler(client: Client):
    """Start the backup scheduler"""
    scheduler = get_backup_scheduler(client)
    if scheduler:
        scheduler.start()

def stop_backup_scheduler():
    """Stop the backup scheduler"""
    global backup_scheduler
    if backup_scheduler:
        backup_scheduler.stop()

async def manual_backup_command(client: Client):
    """Command to perform a manual backup"""
    scheduler = get_backup_scheduler(client)
    if scheduler:
        success = await scheduler.manual_backup()
        return success
    return False
