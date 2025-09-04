import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from pyrogram import Client
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from modules.postgres_database import get_database
from .decorators import is_owner
from config import OWNER_ID

# Store pending actions
PENDING_ADMIN_ACTIONS = {}

class AdminAction:
    def __init__(self, action_type: str, admin_id: int, target_id: int, 
                 admin_name: str, target_name: str, details: Dict[str, Any]):
        self.action_type = action_type
        self.admin_id = admin_id
        self.target_id = target_id
        self.admin_name = admin_name
        self.target_name = target_name
        self.details = details
        self.requested_at = datetime.utcnow()
        self.unique_id = f"{action_type}_{admin_id}_{target_id}_{int(self.requested_at.timestamp())}"

async def create_approval_request(client: Client, action: AdminAction) -> bool:
    """Create an approval request and send it to the owner"""
    try:
        # Store the action
        PENDING_ADMIN_ACTIONS[action.unique_id] = action
        
        # Create approval message
        action_display_names = {
            'give': 'Give Character',
            'take': 'Take Character', 
            'massgive': 'Mass Give Characters',
            'gbheek': 'Give Tokens',
            'tbheek': 'Take Tokens'
        }
        
        display_name = action_display_names.get(action.action_type, action.action_type.title())
        
        # Build details text based on action type
        details_text = ""
        if action.action_type == 'give':
            char_id = action.details.get('char_id')
            char_name = action.details.get('char_name', 'Unknown')
            details_text = f"Character: {char_name} (ID: {char_id})"
        elif action.action_type == 'take':
            char_id = action.details.get('char_id')
            char_name = action.details.get('char_name', 'Unknown')
            details_text = f"Character: {char_name} (ID: {char_id})"
        elif action.action_type == 'massgive':
            char_ids = action.details.get('char_ids', [])
            char_names = action.details.get('char_names', [])
            details_text = f"Characters: {len(char_ids)} items"
            if char_names:
                details_text += f" ({', '.join(char_names[:3])}{'...' if len(char_names) > 3 else ''})"
        elif action.action_type in ['gbheek', 'tbheek']:
            amount = action.details.get('amount', 0)
            details_text = f"Amount: {amount:,} tokens"
        
        # Create keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"admin_approve_{action.unique_id}"),
                InlineKeyboardButton("❌ Decline", callback_data=f"admin_decline_{action.unique_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send approval request to owner
        approval_text = (
            f"🔐 <b>ADMIN ACTION APPROVAL REQUEST</b>\n\n"
            f"<b>Type:</b> {display_name}\n"
            f"<b>Requested by:</b> {action.admin_name}\n"
            f"<b>Target:</b> {action.target_name}\n"
            f"<b>Details:</b> {details_text}\n"
            f"<b>Requested at:</b> {action.requested_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Use the buttons below to approve or decline this action."
        )
        
        await client.send_message(OWNER_ID, approval_text, reply_markup=reply_markup)
        
        return True
        
    except Exception as e:
        print(f"Error creating approval request: {e}")
        return False

async def handle_approval_callback(client: Client, callback_query: CallbackQuery) -> bool:
    """Handle owner approval/decline callbacks"""
    try:
        # Check if user is owner
        if isinstance(OWNER_ID, list):
            if callback_query.from_user.id not in OWNER_ID:
                await callback_query.answer("❌ Only the owner can approve/decline actions!", show_alert=True)
                return False
        elif callback_query.from_user.id != OWNER_ID:
            await callback_query.answer("❌ Only the owner can approve/decline actions!", show_alert=True)
            return False
        
        data = callback_query.data
        if not data.startswith(("admin_approve_", "admin_decline_")):
            return False
        
        action_type, unique_id = data.split("_", 2)[1:]
        action = PENDING_ADMIN_ACTIONS.get(unique_id)
        
        if not action:
            await callback_query.answer("❌ Action not found or expired!", show_alert=True)
            return False
        
        # Remove from pending actions
        PENDING_ADMIN_ACTIONS.pop(unique_id, None)
        
        if action_type == "approve":
            # Execute the approved action
            success = await execute_approved_action(client, action)
            if success:
                await callback_query.answer("✅ Action approved and executed!", show_alert=False)
                await log_approved_action(client, action, success=True)
            else:
                await callback_query.answer("❌ Action failed to execute!", show_alert=True)
                await log_approved_action(client, action, success=False)
        else:
            # Decline the action
            await callback_query.answer("❌ Action declined!", show_alert=False)
            await log_declined_action(client, action)
        
        # Update the approval message
        try:
            status = "✅ APPROVED" if action_type == "approve" else "❌ DECLINED"
            await callback_query.edit_message_text(
                f"🔐 <b>ADMIN ACTION {status}</b>\n\n"
                f"<b>Type:</b> {action.action_type.title()}\n"
                f"<b>Approved by:</b> {callback_query.from_user.first_name}\n"
                f"<b>Requested by:</b> {action.admin_name}\n"
                f"<b>Target:</b> {action.target_name}\n"
                f"<b>Status:</b> {status}"
            )
        except Exception:
            pass
        
        return True
        
    except Exception as e:
        print(f"Error handling approval callback: {e}")
        return False

async def execute_approved_action(client: Client, action: AdminAction) -> bool:
    """Execute the approved admin action"""
    try:
        db = get_database()
        
        if action.action_type == 'give':
            char_id = action.details.get('char_id')
            await db.add_character_to_user(action.target_id, char_id, source='give')
            
        elif action.action_type == 'take':
            char_id = action.details.get('char_id')
            await db.remove_single_character_from_user(action.target_id, char_id)
            
        elif action.action_type == 'massgive':
            char_ids = action.details.get('char_ids', [])
            now = datetime.utcnow()
            collection_history = [{
                'character_id': cid,
                'collected_at': now.isoformat(),
                'source': 'give'
            } for cid in char_ids]
            await db.users.update_one(
                {'user_id': action.target_id},
                {
                    '$push': {
                        'characters': {'$each': char_ids},
                        'collection_history': {'$each': collection_history}
                    }
                }
            )
            
        elif action.action_type == 'gbheek':
            amount = action.details.get('amount', 0)
            target_data = await db.get_user(action.target_id)
            if not target_data:
                await db.add_user({
                    'user_id': action.target_id,
                    'username': action.details.get('target_username'),
                    'first_name': action.target_name,
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
                await db.update_user(action.target_id, {'wallet': new_balance})
                
        elif action.action_type == 'tbheek':
            amount = action.details.get('amount', 0)
            target_data = await db.get_user(action.target_id)
            if target_data:
                wallet = target_data.get('wallet', 0)
                if wallet >= amount:
                    new_balance = wallet - amount
                    await db.update_user(action.target_id, {'wallet': new_balance})
                else:
                    return False  # Insufficient balance
            else:
                return False  # User not found
        
        return True
        
    except Exception as e:
        print(f"Error executing approved action: {e}")
        return False

async def log_approved_action(client: Client, action: AdminAction, success: bool = True):
    """Log the approved action"""
    try:
        from modules.logging_utils import send_character_log, send_token_log
        
        # Get owner name
        owner_id = OWNER_ID[0] if isinstance(OWNER_ID, list) else OWNER_ID
        owner_user = await client.get_users(owner_id)
        owner_name = owner_user.first_name if owner_user else "Owner"
        
        # Build log message
        action_display_names = {
            'give': 'Give Character',
            'take': 'Take Character', 
            'massgive': 'Mass Give Characters',
            'gbheek': 'Give Tokens',
            'tbheek': 'Take Tokens'
        }
        
        display_name = action_display_names.get(action.action_type, action.action_type.title())
        
        # Build result text
        if success:
            if action.action_type == 'give':
                char_name = action.details.get('char_name', 'Unknown')
                result_text = f"✅ Success: Pokemon {char_name} given to {action.target_name}."
            elif action.action_type == 'take':
                char_name = action.details.get('char_name', 'Unknown')
                result_text = f"✅ Success: Pokemon {char_name} taken from {action.target_name}."
            elif action.action_type == 'massgive':
                char_ids = action.details.get('char_ids', [])
                result_text = f"✅ Success: Pokemons with IDs {', '.join(map(str, char_ids))} given to {action.target_name}."
            elif action.action_type == 'gbheek':
                amount = action.details.get('amount', 0)
                result_text = f"✅ Success: {amount:,} tokens given to {action.target_name}."
            elif action.action_type == 'tbheek':
                amount = action.details.get('amount', 0)
                result_text = f"✅ Success: {amount:,} tokens taken from {action.target_name}."
        else:
            result_text = "❌ Failed: Action execution failed."
        
        log_text = (
            f"✅ <b>ADMIN ACTION APPROVED</b>\n\n"
            f"<b>Type:</b> {display_name}\n"
            f"<b>Approved by:</b> {owner_name}\n"
            f"<b>Requested by:</b> {action.admin_name}\n"
            f"<b>Target:</b> {action.target_name}\n"
            f"<b>Result:</b> {result_text}"
        )
        
        # Send to both log channels
        from config import LOG_CHANNEL_ID, DROPTIME_LOG_CHANNEL
        await client.send_message(LOG_CHANNEL_ID, log_text)
        await client.send_message(DROPTIME_LOG_CHANNEL, log_text)
        
        # Send specific logs for character actions
        if action.action_type in ['give', 'take']:
            admin_user = await client.get_users(action.admin_id)
            target_user = await client.get_users(action.target_id)
            char_id = action.details.get('char_id')
            character = await get_database().get_character(char_id)
            if character:
                await send_character_log(client, admin_user, target_user, character, action.action_type)
        
        # Send specific logs for token actions
        elif action.action_type in ['gbheek', 'tbheek']:
            admin_user = await client.get_users(action.admin_id)
            target_user = await client.get_users(action.target_id)
            amount = action.details.get('amount', 0)
            action_name = f"{action.action_type} (approved)"
            await send_token_log(client, admin_user, target_user, amount, action=action_name)
            
    except Exception as e:
        print(f"Error logging approved action: {e}")

async def log_declined_action(client: Client, action: AdminAction):
    """Log the declined action"""
    try:
        # Get owner name
        owner_id = OWNER_ID[0] if isinstance(OWNER_ID, list) else OWNER_ID
        owner_user = await client.get_users(owner_id)
        owner_name = owner_user.first_name if owner_user else "Owner"
        
        action_display_names = {
            'give': 'Give Character',
            'take': 'Take Character', 
            'massgive': 'Mass Give Characters',
            'gbheek': 'Give Tokens',
            'tbheek': 'Take Tokens'
        }
        
        display_name = action_display_names.get(action.action_type, action.action_type.title())
        
        log_text = (
            f"❌ <b>ADMIN ACTION DECLINED</b>\n\n"
            f"<b>Type:</b> {display_name}\n"
            f"<b>Declined by:</b> {owner_name}\n"
            f"<b>Requested by:</b> {action.admin_name}\n"
            f"<b>Target:</b> {action.target_name}\n"
            f"<b>Result:</b> ❌ Action was declined by owner."
        )
        
        # No longer sending to log channels for declined actions
        
    except Exception as e:
        print(f"Error logging declined action: {e}")

def cleanup_expired_actions():
    """Clean up expired actions (older than 1 hour)"""
    now = datetime.utcnow()
    expired_actions = []
    
    for unique_id, action in PENDING_ADMIN_ACTIONS.items():
        if (now - action.requested_at).total_seconds() > 3600:  # 1 hour
            expired_actions.append(unique_id)
    
    for unique_id in expired_actions:
        PENDING_ADMIN_ACTIONS.pop(unique_id, None)
