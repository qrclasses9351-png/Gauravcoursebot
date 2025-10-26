import os
import re
import aiohttp
import aiofiles
import asyncio
import threading
from flask import Flask, request
from telebot.async_telebot import AsyncTeleBot
from telebot import types, apihelper
from urllib.parse import unquote

# --- Config / Globals ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8099375497:AAEs0UZ7gMlA1j25xDZN6Gawg0HKzKOXRJY")
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# set a slightly larger timeout for outgoing Telegram API requests
apihelper.RETRY_TIMEOUT = 20

bot = AsyncTeleBot(BOT_TOKEN)
app = Flask(__name__)

# download stop flags per user_id
download_flags = {}  # user_id -> bool (True means stop)

# ------------------ Helpers ------------------
def sanitize_filename(name: str) -> str:
    # keep basic chars, replace others with underscore
    return re.sub(r'[^a-zA-Z0-9._-]', '_', name)

async def download_from_url(user_id: int, chat_id: int, url: str, count: int = 1):
    url = unquote(url.strip())
    filename = url.split('/')[-1] or f'file_{count}'
    if not any(filename.lower().endswith(ext) for ext in ('.mp4', '.pdf', '.ws', '.bin')):
        # try to add .bin if no extension
        filename = filename + '.bin'
    safe = sanitize_filename(filename)
    save_path = os.path.join(DOWNLOAD_DIR, f"{count:03d}_{safe}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as resp:
                if resp.status != 200:
                    await bot.send_message(chat_id, f"⚠️ Download failed ({resp.status}): {url}")
                    return
                # stream and write in chunks
                async with aiofiles.open(save_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(1024 * 64)
                        if not chunk:
                            break
                        # check stop flag
                        if download_flags.get(user_id):
                            await bot.send_message(chat_id, "🛑 Download stopped by user.")
                            # try to remove partial file
                            try:
                                await f.close()
                            except Exception:
                                pass
                            try:
                                os.remove(save_path)
                            except Exception:
                                pass
                            return
                        await f.write(chunk)

        # send file to user
        if save_path.lower().endswith('.pdf'):
            await bot.send_document(chat_id, open(save_path, 'rb'), caption=f"📘 PDF {count}")
        elif save_path.lower().endswith('.mp4'):
            await bot.send_video(chat_id, open(save_path, 'rb'), caption=f"🎥 Video {count}")
        else:
            await bot.send_document(chat_id, open(save_path, 'rb'), caption=f"📁 File {count}")

    except Exception as e:
        await bot.send_message(chat_id, f"❌ Downloading Interrupted\nError: {e}")

# ------------------ Handlers ------------------
@bot.message_handler(commands=["start"]) 
async def start_cmd(message):
    await bot.send_message(message.chat.id, "👋 नमस्ते! .txt भेजो या कोई Utkarsh लिंक भेजो — मैं डाउनलोड कर दूँगा।\nUse /download to test or upload a .txt file.")

@bot.message_handler(commands=["download"])
async def cmd_download(message):
    # simple test download (user will still be able to stop)
    user_id = message.from_user.id
    chat_id = message.chat.id
    download_flags[user_id] = False
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await bot.send_message(chat_id, "⬇️ Test download starting...", reply_markup=markup)
    # Example test file (replace or let user provide real link)
    test_url = os.getenv('TEST_URL', "https://d1q5ugnejk3zoi.cloudfront.net/ut-production-jw/admin_v1/file_library/videos/enc_plain_mp4/2340465/plain/720x1280.mp4")
    await download_from_url(user_id, chat_id, test_url, count=1)

@bot.message_handler(content_types=['document'])
async def handle_text_file(message):
    # When user uploads a .txt file, extract links and download them
    user_id = message.from_user.id
    chat_id = message.chat.id
    download_flags[user_id] = False  # reset stop flag

    file_info = await bot.get_file(message.document.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                text_data = await resp.text()
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Could not download the uploaded file. Error: {e}")
        return

    # find all URLs in the text file
    links = re.findall(r'https?://[^\s\)\]\}]+', text_data)
    if not links:
        await bot.send_message(chat_id, "⚠️ No valid links found in the uploaded file.")
        return

    await bot.send_message(chat_id, f"🔗 Found {len(links)} links. Starting downloads...")

    # show stop button
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await bot.send_message(chat_id, "Press the button to stop downloads at any time.", reply_markup=markup)

    # download links sequentially
    for i, url in enumerate(links, start=1):
        await download_from_url(user_id, chat_id, url, count=i)
        # small pause to avoid hitting rate limits
        await asyncio.sleep(0.8)

@bot.message_handler(func=lambda m: 'https://' in m.text)
async def handle_single_link(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    download_flags[user_id] = False
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await bot.send_message(chat_id, "⬇️ Starting download...", reply_markup=markup)
    await download_from_url(user_id, chat_id, message.text.strip(), count=1)

@bot.callback_query_handler(func=lambda call: call.data == 'stop_download')
async def stop_download(call):
    user_id = call.from_user.id
    download_flags[user_id] = True
    await bot.send_message(call.message.chat.id, "🛑 Download stopped!")

@bot.message_handler(commands=['stop'])
async def stop_command(message):
    user_id = message.from_user.id
    download_flags[user_id] = True
    await bot.send_message(message.chat.id, "🛑 Download stopped by command.")

# ------------------ Webhook & Flask ------------------
@app.route("/")
def home():
    return "🤖 GAURAV Bot running via Webhook"

@app.route("/webhook", methods=["POST"])
def webhook():
    update = request.get_json(force=True)
    if update:
        telegram_update = types.Update.de_json(update)
        threading.Thread(target=lambda: asyncio.run(bot.process_new_updates([telegram_update]))).start()
    return "ok"

async def set_webhook():
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        try:
            await bot.remove_webhook()
            await bot.set_webhook(webhook_url)
            print(f"🚀 Webhook set to: {webhook_url}")
        except Exception as e:
            print("Failed to set webhook:", e)
    else:
        print("RENDER_EXTERNAL_URL not set - webhook not configured")

# start webhook setup in background so gunicorn import won't block
threading.Thread(target=lambda: asyncio.run(set_webhook())).start()

# expose app for gunicorn
