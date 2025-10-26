import os, re, aiohttp, aiofiles, asyncio, threading
from flask import Flask, request
from telebot.async_telebot import AsyncTeleBot
from telebot import types, apihelper
from urllib.parse import unquote

# --- Configuration ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

apihelper.SESSION_TIMEOUT = 90
apihelper.RETRY_TIMEOUT = 60

bot = AsyncTeleBot(BOT_TOKEN)
app = Flask(__name__)

# Track download flags per user
download_flags = {}

# ------------------ Helpers ------------------
def sanitize_filename(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9._-]', '_', name)

async def download_from_url(user_id: int, chat_id: int, url: str, count: int = 1):
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
                    await bot.send_message(chat_id, f"⚠️ Download failed ({resp.status}): {url}")
                    return
                async with aiofiles.open(save_path, 'wb') as f:
                    while True:
                        chunk = await resp.content.read(1024 * 64)
                        if not chunk:
                            break
                        if download_flags.get(user_id):
                            await bot.send_message(chat_id, "🛑 Download stopped by user.")
                            try: await f.close()
                            except: pass
                            try: os.remove(save_path)
                            except: pass
                            return
                        await f.write(chunk)

        # Send file
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
    await bot.send_message(message.chat.id, "👋 नमस्ते! .txt या कोई Utkarsh लिंक भेजो — मैं डाउनलोड कर दूँगा।")

@bot.message_handler(commands=["stop"])
async def stop_command(message):
    user_id = message.from_user.id
    download_flags[user_id] = True
    await bot.send_message(message.chat.id, "🛑 Download stopped by command.")

@bot.callback_query_handler(func=lambda call: call.data == 'stop_download')
async def stop_download(call):
    user_id = call.from_user.id
    download_flags[user_id] = True
    await bot.send_message(call.message.chat.id, "🛑 Download stopped!")

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
        await bot.send_message(chat_id, f"❌ Could not read uploaded file. Error: {e}")
        return

    links = re.findall(r'https?://[^\s\)\]\}]+', text_data)
    if not links:
        await bot.send_message(chat_id, "⚠️ No valid links found in the file.")
        return

    await bot.send_message(chat_id, f"🔗 Found {len(links)} links. Starting downloads...")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await bot.send_message(chat_id, "Press Stop anytime to cancel.", reply_markup=markup)

    for i, url in enumerate(links, start=1):
        await download_from_url(user_id, chat_id, url, count=i)
        await asyncio.sleep(2)  # avoid timeout

@bot.message_handler(func=lambda m: m.text and 'https://' in m.text)
async def handle_link(message):
    user_id, chat_id = message.from_user.id, message.chat.id
    download_flags[user_id] = False
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Stop Download", callback_data="stop_download"))
    await bot.send_message(chat_id, "⬇️ Starting download...", reply_markup=markup)
    await download_from_url(user_id, chat_id, message.text.strip(), count=1)

# ------------------ Flask + Webhook ------------------
@app.route("/")
def home():
    return "🤖 GAURAV Bot running with Webhook"

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

threading.Thread(target=lambda: asyncio.run(set_webhook())).start()
