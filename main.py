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

# ---------- Config ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "8099375497:AAEs0UZ7gMlA1j25xDZN6Gawg0HKzKOXRJY")
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# make Telegram API waits longer to reduce timeouts
apihelper.SESSION_TIMEOUT = 90
apihelper.RETRY_TIMEOUT = 60

bot = AsyncTeleBot(BOT_TOKEN)
app = Flask(__name__)

# per-user stop flags
download_flags = {}

# ---------- Helpers ----------
def sanitize_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9._-]', '_', name)

async def safe_send(chat_id: int, text: str, **kwargs):
    """Send a message but swallow timeouts/connection errors so the bot doesn't crash."""
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        # log but do not raise
        print("⚠️ safe_send ignored error:", e)

async def download_from_url(user_id: int, chat_id: int, url: str, count: int = 1, auto_delete_partial: bool = True):
    url = unquote(url.strip())
    filename = url.split('/')[-1] or f'file_{count}'
    if not any(filename.lower().endswith(ext) for ext in ('.mp4', '.pdf', '.ws', '.bin')):
        filename += '.bin'
    safe = sanitize_filename(filename)
    save_path = os.path.join(DOWNLOAD_DIR, f"{count:03d}_{safe}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=90) as resp:
                if resp.status != 200:
                    await safe_send(chat_id, f"⚠️ Download failed ({resp.status}): {url}")
                    return
                async with aiofiles.open(save_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(1024 * 64)
                        if not chunk:
                            break
                        if download_flags.get(user_id):
                            await safe_send(chat_id, "🛑 Download stopped by user.")
                            try:
                                await f.close()
                            except Exception:
                                pass
                            if auto_delete_partial:
                                try:
                                    os.remove(save_path)
                                except Exception:
                                    pass
                            return
                        await f.write(chunk)

        # send file
        if save_path.lower().endswith('.pdf'):
            try:
                await bot.send_document(chat_id, open(save_path, 'rb'), caption=f"📘 PDF {count}")
            except Exception as e:
                print("⚠️ send_document error:", e)
                await safe_send(chat_id, f"✅ Downloaded: {safe} (but failed to send file)")
        elif save_path.lower().endswith('.mp4'):
            try:
                await bot.send_video(chat_id, open(save_path, 'rb'), caption=f"🎥 Video {count}")
            except Exception as e:
                print("⚠️ send_video error:", e)
                await safe_send(chat_id, f"✅ Downloaded: {safe} (but failed to send file)")
        else:
            try:
                await bot.send_document(chat_id, open(save_path, 'rb'), caption=f"📁 File {count}")
            except Exception as e:
                print("⚠️ send_document error:", e)
                await safe_send(chat_id, f"✅ Downloaded: {safe} (but failed to send file)")
    except Exception as e:
        await safe_send(chat_id, f"❌ Downloading Interrupted\nError: {e}")

# ---------- Handlers ----------
@bot.message_handler(commands=["start"])
async def start_cmd(message):
    await safe_send(message.chat.id, "👋 नमस्ते! .txt भेजो या कोई Utkarsh लिंक भेजो — मैं डाउनलोड कर दूँगा।\nUse /download to test or upload a .txt file.")

@bot.message_handler(commands=["download"])
async def cmd_download(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    download_flags[user_id] = False
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await safe_send(chat_id, "⬇️ Test download starting...", reply_markup=markup)
    test_url = os.getenv('TEST_URL', "https://d1q5ugnejk3zoi.cloudfront.net/ut-production-jw/admin_v1/file_library/videos/enc_plain_mp4/2340465/plain/720x1280.mp4")
    await download_from_url(user_id, chat_id, test_url, count=1)

@bot.message_handler(content_types=['document'])
async def handle_text_file(message):
    user_id, chat_id = message.from_user.id, message.chat.id
    download_flags[user_id] = False

    file_info = await bot.get_file(message.document.file_id)
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_info.file_path}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                text_data = await resp.text()
    except Exception as e:
        await safe_send(chat_id, f"❌ Could not read uploaded file. Error: {e}")
        return

    links = re.findall(r'https?://[^\s\)\]\}]+', text_data)
    if not links:
        await safe_send(chat_id, "⚠️ No valid links found in the file.")
        return

    await safe_send(chat_id, f"🔗 Found {len(links)} links. Starting downloads...")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await safe_send(chat_id, "Press Stop anytime to cancel.", reply_markup=markup)

    for i, url in enumerate(links, start=1):
        await download_from_url(user_id, chat_id, url, count=i)
        await asyncio.sleep(4)

@bot.message_handler(func=lambda m: m.text and 'https://' in m.text)
async def handle_link(message):
    user_id, chat_id = message.from_user.id, message.chat.id
    download_flags[user_id] = False
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await safe_send(chat_id, "⬇️ Starting download...", reply_markup=markup)
    await download_from_url(user_id, chat_id, message.text.strip(), count=1)

@bot.callback_query_handler(func=lambda call: call.data == 'stop_download')
async def stop_download(call):
    user_id = call.from_user.id
    download_flags[user_id] = True
    await safe_send(call.message.chat.id, "🛑 Download stopped!")

@bot.message_handler(commands=['stop'])
async def stop_command(message):
    user_id = message.from_user.id
    download_flags[user_id] = True
    await safe_send(message.chat.id, "🛑 Download stopped by command.")

# ---------- Flask + Webhook ----------
@app.route("/")
def home():
    return "🤖 GAURAV SafeSend Bot running with Webhook"

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
        print("⚠️ RENDER_EXTERNAL_URL not set")

# start webhook setup in background
threading.Thread(target=lambda: asyncio.run(set_webhook())).start()
