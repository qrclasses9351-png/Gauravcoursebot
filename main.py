from urllib.parse import unquote
import os
import asyncio
import threading
import aiohttp
from flask import Flask, request
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from telebot import apihelper

BOT_TOKEN = os.getenv("BOT_TOKEN", "8099375497:AAEs0UZ7gMlA1j25xDZN6Gawg0HKzKOXRJY")
apihelper.RETRY_TIMEOUT = 20

bot = AsyncTeleBot(BOT_TOKEN)
app = Flask(__name__)

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@bot.message_handler(commands=["start"])
async def start(message):
    await bot.send_message(
        message.chat.id,
        "👋 नमस्ते!\nमुझे Utkarsh App का कोई PDF या Video लिंक भेजें "
        "या .txt फाइल अपलोड करें — मैं सब डाउनलोड कर दूँ 📥"
    )

@bot.message_handler(content_types=["document"])

@bot.message_handler(commands=['stop'])
async def stop_download(message):
    download_flags[message.from_user.id] = True
    await bot.send_message(message.chat.id, "🛑 Download stopped!")
    
async def handle_textfile(message):
    file_info = await bot.get_file(message.document.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

    async with aiohttp.ClientSession() as s:
        async with s.get(file_url) as r:
            text = await r.text()

    links = [l.strip() for l in text.splitlines() if "https://" in l]
    await bot.send_message(message.chat.id, f"📑 {len(links)} लिंक मिले, डाउनलोड शुरू...")

    for i, url in enumerate(links, 1):
        await download_and_send(bot, message.chat.id, url, i)
        await asyncio.sleep(1)

@bot.message_handler(func=lambda m: "https://" in m.text)
async def single(message):
    await download_and_send(bot, message.chat.id, message.text.strip(), 1)

async def download_and_send(bot, chat_id, url, count):
    try:
        url = unquote(url.strip())
        filename = url.split("/")[-1]
        if not any(ext in filename for ext in [".mp4", ".pdf", ".ws"]):
            filename += ".bin"
        safe = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        path = os.path.join(DOWNLOAD_DIR, f"{count:03d}_{safe}")

        async with aiohttp.ClientSession() as s:
            async with s.get(url) as r:
                if r.status != 200:
                    await bot.send_message(chat_id, f"⚠️ Download failed ({r.status}): {url}")
                    return
                async with aiofiles.open(path, "wb") as f:
                    await f.write(await r.read())

        if path.endswith(".pdf"):
            await bot.send_document(chat_id, open(path, "rb"), caption=f"📘 PDF {count}")
        elif path.endswith(".mp4"):
            await bot.send_video(chat_id, open(path, "rb"), caption=f"🎥 Video {count}")
        else:
            await bot.send_document(chat_id, open(path, "rb"), caption=f"📁 File {count}")

    except Exception as e:
        await bot.send_message(chat_id, f"❌ Downloading Interrupted\nError: {e}")

@app.route("/")
def index():
    return "🤖 GAURAV Utkarsh Downloader Bot running via Webhook!"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    if update:
        telegram_update = types.Update.de_json(update)
        # ✅ Use background thread to avoid blocking Flask
        threading.Thread(
            target=lambda: asyncio.run(bot.process_new_updates([telegram_update]))
        ).start()
    return "ok"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

async def main():
    print("🚀 Setting Webhook & starting bot...")
    threading.Thread(target=run_flask).start()
    await bot.remove_webhook()
    render_url = os.getenv("RENDER_EXTERNAL_URL", "https://your-app-name.onrender.com")
    await bot.set_webhook(f"{render_url}/webhook")
    while True:
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
