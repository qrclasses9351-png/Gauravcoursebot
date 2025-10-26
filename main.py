import asyncio
import aiohttp, aiofiles
from telebot.async_telebot import AsyncTeleBot
from telebot import types
from flask import Flask, request
from urllib.parse import urlparse, quote, unquote
import re, os, threading

# ===========================
# 🔧 BOT CONFIG
# ===========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8099375497:AAEs0UZ7gMlA1j25xDZN6Gawg0HKzKOXRJY")
bot = AsyncTeleBot(BOT_TOKEN)

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ===========================
# 🔹 Helper: Extract clean URL
# ===========================
def extract_url(text):
    """Extract only the valid https:// link from any mixed text line"""
    match = re.search(r"https://[^\s]+", text)
    return match.group(0) if match else None


# ===========================
# 🔹 Telegram Handlers
# ===========================
@bot.message_handler(commands=["start"])
async def start(message):
    await bot.send_message(
        message.chat.id,
        "👋 नमस्ते! मुझे Utkarsh App का कोई PDF या Video लिंक भेजें "
        "या .txt फाइल अपलोड करें — मैं सब डाउनलोड कर दूँ 📥"
    )


@bot.message_handler(content_types=["document"])
async def handle_textfile(message):
    file_info = await bot.get_file(message.document.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as s:
        async with s.get(file_url) as r:
            text = await r.text()

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    await bot.send_message(message.chat.id, f"📑 {len(lines)} लिंक मिले, डाउनलोड शुरू...")

    for i, line in enumerate(lines, 1):
        await download_and_send(bot, message.chat.id, line, i)
        await asyncio.sleep(1)


@bot.message_handler(func=lambda m: "https://" in m.text)
async def single(message):
    await download_and_send(bot, message.chat.id, message.text.strip(), 1)


# ===========================
# 🔹 Downloader Function
# ===========================
async def download_and_send(bot, chat_id, raw_text, count):
    try:
        url = extract_url(raw_text)
        if not url:
            await bot.send_message(chat_id, f"⚠️ कोई वैध लिंक नहीं मिला:\n{raw_text}")
            return

        # Skip private Utkarsh links
        if "apps-s3-prod.utkarshapp.com" in url:
            await bot.send_message(chat_id, f"🔒 Locked file (private Utkarsh link):\n{url}")
            return

        # Decode + re-encode URL safely
        url = unquote(url.strip())
        parsed = urlparse(url)
        clean_path = quote(parsed.path)
        safe_url = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
        if parsed.query:
            safe_url += f"?{parsed.query}"

        filename = os.path.basename(parsed.path)
        if not any(ext in filename for ext in [".pdf", ".mp4", ".ws"]):
            filename += ".bin"

        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
        path = os.path.join(DOWNLOAD_DIR, f"{count:03d}_{safe_name}")

        async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as s:
            async with s.get(safe_url) as r:
                if r.status != 200:
                    await bot.send_message(chat_id, f"⚠️ Download failed ({r.status}): {safe_url}")
                    return
                async with aiofiles.open(path, "wb") as f:
                    await f.write(await r.read())

        # Upload file to Telegram
        if path.endswith(".pdf"):
            await bot.send_document(chat_id, open(path, "rb"), caption=f"📘 PDF {count}")
        elif path.endswith(".mp4"):
            await bot.send_video(chat_id, open(path, "rb"), caption=f"🎥 Video {count}")
        else:
            await bot.send_document(chat_id, open(path, "rb"), caption=f"📁 File {count}")

    except Exception as e:
        await bot.send_message(chat_id, f"❌ Downloading Interrupted\nError: {e}")


# ===========================
# 🔹 Flask Webhook Routes
# ===========================
@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    if update:
        telegram_update = types.Update.de_json(update)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # अगर loop नहीं है, नया बनाओ
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            asyncio.ensure_future(bot.process_new_updates([telegram_update]))
        else:
            loop.run_until_complete(bot.process_new_updates([telegram_update]))

    return "ok"

# ===========================
# 🔹 Start Flask + Webhook
# ===========================
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
