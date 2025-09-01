from pyrogram import Client, filters
from pyrogram.types import Message
import os

# Import database based on configuration
from modules.postgres_database import get_database
from config import OWNER_ID
import random
from datetime import datetime

# Store active giveaways
active_giveaways = {}

async def start_giveaway(client: Client, message: Message):
    """Start a giveaway - only owner can use this command"""
    user = message.from_user
    
    # Check if user is owner
    if user.id != OWNER_ID:
        await message.reply_text("❌ Only the owner can start giveaways!")
        return
    
    # Check if there's already an active giveaway in this chat
    chat_id = message.chat.id
    if chat_id in active_giveaways:
        await message.reply_text("❌ There's already an active giveaway in this group!")
        return
    
    # Generate random number between 1 and 200
    target_number = random.randint(1, 200)
    
    # Store giveaway data
    active_giveaways[chat_id] = {
        'target_number': target_number,
        'participants': set(),
        'start_time': datetime.now(),
        'start_message_id': None,
        'winner_message_id': None
    }
    
    # Debug: Print the winning number (for testing)
    print(f"[GIVEAWAY] Started in chat {chat_id}, winning number: {target_number}")
    
    # Create giveaway message
    giveaway_text = (
        "🎉 **Giveaway started in this group!** 🎉\n\n"
        f"🎯 I've selected a winning number between **1** and **200**!\n"
        f"**Reply to this message with your number to participate!**\n\n"
        f"**Example:** Reply with `50`\n\n"
        f"💡 **Hint:** The closer you get, the better the feedback!"
    )
    
    # Send giveaway message and pin it
    giveaway_msg = await message.reply_text(giveaway_text)
    
    # Store the message ID for pinning
    active_giveaways[chat_id]['start_message_id'] = giveaway_msg.id
    
    # Pin the giveaway message
    try:
        await client.pin_chat_message(chat_id, giveaway_msg.id, disable_notification=True)
    except Exception as e:
        print(f"Could not pin message: {e}")

async def enter_giveaway(client: Client, message: Message):
    """Handle user entering the giveaway via reply"""
    chat_id = message.chat.id
    user = message.from_user
    
    # Check if there's an active giveaway
    if chat_id not in active_giveaways:
        return  # Don't reply if no active giveaway
    
    # Check if this is a reply to the giveaway message
    if not message.reply_to_message:
        return  # Only process replies
    
    # Check if the reply is to the giveaway start message
    giveaway_data = active_giveaways[chat_id]
    if message.reply_to_message.id != giveaway_data['start_message_id']:
        return  # Only process replies to the giveaway message
    
    # Parse the number from the reply
    try:
        # Extract number from the reply text
        guess_text = message.text.strip()
        guess = int(guess_text)
        
        # Validate guess range
        if guess < 1 or guess > 200:
            await message.reply_text("❌ Please guess a number between 1 and 200!")
            return
            
    except ValueError:
        await message.reply_text("❌ Please reply with a valid number between 1-200!")
        return
    
    # Add user to participants (no limit on participation)
    active_giveaways[chat_id]['participants'].add(user.id)
    
    # Get target number
    target_number = active_giveaways[chat_id]['target_number']
    
    # Calculate difference
    difference = abs(guess - target_number)
    
    # Provide feedback based on how close the guess is
    if guess == target_number:
        # WINNER!
        # Create user mention with hyperlink
        user_mention = f"[{user.first_name}](tg://user?id={user.id})"
        winner_text = (
            f"🎉🎉 <b>Congratulations {user_mention}!</b> 🎉🎉\n\n"
            f"You guessed the correct number: <b>{target_number}!</b>\n\n"
            f"🏆 <b>You are the winner!</b> 🏆"
        )
        
        winner_msg = await message.reply_text(winner_text)
        
        # Store winner message ID for pinning
        active_giveaways[chat_id]['winner_message_id'] = winner_msg.id
        
        # Pin the winner message
        try:
            await client.pin_chat_message(chat_id, winner_msg.id, disable_notification=True)
        except Exception as e:
            print(f"Could not pin winner message: {e}")
        
        # End the giveaway
        del active_giveaways[chat_id]
        
    elif difference >= 50:
        await message.reply_text("❄️ **Very far!** ❄️")
    elif difference >= 20:
        await message.reply_text("😐 **Far.**")
    elif difference >= 10:
        await message.reply_text("🙂 **Close!**")
    else:
        await message.reply_text("🔥 **Very close!** 🔥")

async def end_giveaway(client: Client, message: Message):
    """End a giveaway - only owner can use this command"""
    user = message.from_user
    
    # Check if user is owner
    if user.id != OWNER_ID:
        await message.reply_text("❌ Only the owner can end giveaways!")
        return
    
    chat_id = message.chat.id
    
    # Check if there's an active giveaway
    if chat_id not in active_giveaways:
        await message.reply_text("❌ No active giveaway in this group!")
        return
    
    # Get giveaway data
    giveaway_data = active_giveaways[chat_id]
    target_number = giveaway_data['target_number']
    participants = len(giveaway_data['participants'])
    
    # End the giveaway
    end_text = (
        "🏁 **Giveaway ended!** 🏁\n\n"
        f"The correct number was: **{target_number}**\n"
        f"Total participants: **{participants}**\n\n"
        "No one guessed correctly this time!"
    )
    
    await message.reply_text(end_text)
    
    # Remove from active giveaways
    del active_giveaways[chat_id]

async def giveaway_status(client: Client, message: Message):
    """Check giveaway status"""
    chat_id = message.chat.id
    
    if chat_id not in active_giveaways:
        await message.reply_text("❌ No active giveaway in this group!")
        return
    
    giveaway_data = active_giveaways[chat_id]
    participants = len(giveaway_data['participants'])
    
    status_text = (
        "📊 **Giveaway Status** 📊\n\n"
        f"🎯 Winning number: **???** (1-200)\n"
        f"👥 Participants: **{participants}**\n"
        f"⏰ Started: **{giveaway_data['start_time'].strftime('%Y-%m-%d %H:%M:%S')}**\n\n"
        "Reply to the giveaway message with your number to participate!"
    )
    
    await message.reply_text(status_text)

def setup_giveaway_handlers(app: Client):
    """Setup handlers for giveaway module"""
    print("Registering giveaway handlers...")
    app.on_message(filters.command("giveaway"))(start_giveaway)
    app.on_message(filters.command("enter"))(enter_giveaway)
    app.on_message(filters.command("endgiveaway"))(end_giveaway)
    app.on_message(filters.command("givestatus"))(giveaway_status)
    print("All giveaway handlers registered successfully!") 