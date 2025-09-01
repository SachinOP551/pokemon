from telethon import TelegramClient, events
import asyncio
import time

api_id = 20118977
api_hash = "c88e99dd46c405f7357acef8ccc92f85"

bot_username = "CCACRICKETTBot"
deposit_amount = 241500
group_chat_id = -1002660540399

client = TelegramClient("sync_sender_session", api_id, api_hash)

async def main():
    await client.start()
    bot = await client.get_entity(bot_username)
    start_time = time.time()
    success_event = asyncio.Event()

    # Function to click "Yes" button by row/column indices
    async def click_yes_button(message):
        if not getattr(message, "buttons", None):
            return False
        for i, row in enumerate(message.buttons):
            for j, btn in enumerate(row):
                if "no" in btn.text.lower():
                    try:
                        await asyncio.sleep(0.05)  # small delay for stability
                        await message.click(i, j)  # click using indices
                        print(f"⚡ Clicked 'Yes' on bot message id={message.id}")
                        print(f"Done in {(time.time() - start_time)*1000:.1f} ms")
                        success_event.set()
                        return True
                    except Exception as e:
                        print(f"❌ Failed to click button: {e}")
        return False

    # Continuously monitor bot DM messages
    async def monitor_bot_dm():
        # Check existing messages first
        async for msg in client.iter_messages(bot, limit=10):
            if await click_yes_button(msg):
                return
        # Listen for new messages
        event = asyncio.Event()

        async def handle_new_message(ev):
            if not ev.is_private:
                return
            await click_yes_button(ev.message)
            event.set()  # stop waiting once clicked

        client.add_event_handler(handle_new_message, events.NewMessage(from_users=bot))
        try:
            await asyncio.wait_for(event.wait(), timeout=30)
        except asyncio.TimeoutError:
            print("❌ Timed out waiting for 'Yes' button in bot DM.")
        finally:
            client.remove_event_handler(handle_new_message, events.NewMessage(from_users=bot))

    # Send deposit command
    async def send_deposit():
        await client.send_message(group_chat_id, f"/deposit {deposit_amount}")
        print(f"✅ Sent /deposit {deposit_amount} to group {group_chat_id}")

    # Run both tasks concurrently
    tasks = [
        asyncio.create_task(send_deposit()),
        asyncio.create_task(monitor_bot_dm())
    ]
    await asyncio.gather(*tasks)

    await client.disconnect()

asyncio.run(main())

