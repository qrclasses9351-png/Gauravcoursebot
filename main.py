import asyncio
import aiohttp
import aiofiles
from telebot.async_telebot import AsyncTeleBot
from flask import Flask
import os
import threading

BOT_TOKEN = "8099375497:AAEs0UZ7gMlA1j25xDZN6Gawg0HKzKOXRJY"
bot = AsyncTeleBot(BOT_TOKEN)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- Flask server for Render ---
app = Flask(__name__)

@app.route("/")
def home():
    return "🤖 GAURAV Utkarsh Downloader Bot is running successfully on Render!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# --- Telegram Bot Handlers ---
@bot.message_handler(commands=["start"])
async def start(message):
    await bot.send_message(
        message.chat.id,
        "👋 नमस्ते!\nमुझे Utkarsh App का कोई PDF या Video लिंक भेजें "
        "या .txt फाइल अपलोड करें — मैं सब डाउनलोड कर दूँ 📥",
    )

@bot.message_handler(content_types=["document"])
async def handle_textfile(message):
    file_info = await bot.get_file(message.document.file_id)
    file_path = file_info.file_path
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            text = await resp.text()

    lines = [l.strip() for l in text.splitlines() if "https://" in l]
    await bot.send_message(message.chat.id, f"📑 कुल {len(lines)} लिंक मिले। डाउनलोड शुरू कर रहा हूँ...")

    for i, url in enumerate(lines, 1):
        await download_and_send(bot, message.chat.id, url, i)
        await asyncio.sleep(1)

@bot.message_handler(func=lambda m: "https://" in m.text)
async def handle_single_link(message):
    await download_and_send(bot, message.chat.id, message.text.strip(), 1)

import re

async def download_and_send(bot, chat_id, url, count):
    try:
        filename = url.split("/")[-1]
        if not any(ext in filename for ext in [".mp4", ".pdf", ".ws"]):
            filename += ".bin"

        # ✅ Unsafe characters हटाओ
        safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
        save_path = os.path.join(DOWNLOAD_DIR, f"{count:03d}_{safe_name}")

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    await bot.send_message(chat_id, f"⚠️ Download failed ({resp.status}): {url}")
                    return
                async with aiofiles.open(save_path, "wb") as f:
                    await f.write(await resp.read())

        # ✅ अब भेजो
        if save_path.endswith(".pdf"):
            await bot.send_document(chat_id, open(save_path, "rb"), caption=f"📘 PDF {count}")
        elif save_path.endswith(".mp4"):
            await bot.send_video(chat_id, open(save_path, "rb"), caption=f"🎥 Video {count}")
        else:
            await bot.send_document(chat_id, open(save_path, "rb"), caption=f"📁 File {count}")

    except Exception as e:
        await bot.send_message(chat_id, f"❌ Downloading Interrupted\\nError: {e}")


async def main():
    print("🤖 Bot is running...")
    threading.Thread(target=run_flask).start()
    await bot.polling(non_stop=True)

if __name__ == "__main__":
    asyncio.run(main())
