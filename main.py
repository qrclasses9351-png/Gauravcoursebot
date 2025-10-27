import os
import re
import requests
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from urllib.parse import urlparse
import asyncio

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class FileDownloaderBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.setup_handlers()
        
    def setup_handlers(self):
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued."""
        welcome_text = """
🤖 **File Downloader Bot**

मैं आपकी टेक्स्ट फ़ाइल से PDF और वीडियो लिंक्स को डाउनलोड कर सकता हूँ।

**उपयोग करने का तरीका:**
1. मुझे एक टेक्स्ट फ़ाइल भेजें जिसमें PDF और वीडियो लिंक्स हों
2. मैं सभी लिंक्स को एक्सट्रैक्ट करके डाउनलोड कर दूंगा

**कमांड्स:**
/start - बॉट शुरू करें
/help - मदद प्राप्त करें

सपोर्ट: @your_support_channel
        """
        await update.message.reply_text(welcome_text)
        
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /help is issued."""
        help_text = """
📖 **मदद**

यह बॉट टेक्स्ट फ़ाइल से PDF और वीडियो लिंक्स को डाउनलोड करता है।

**समर्थित फ़ाइल फॉर्मेट:**
- .txt फ़ाइलें
- PDF लिंक्स (https://apps-s3-prod.utkarshapp.com/...)
- वीडियो लिंक्स (https://d1q5ugnejk3zoi.cloudfront.net/...)

**उदाहरण फ़ाइल फॉर्मेट:**
(विषय) Part-1 || टॉपिक || Date: https://example.com/file.pdf

**नोट:**
- बड़ी फ़ाइलें डाउनलोड करने में समय लग सकता है
- सभी डाउनलोडेड फ़ाइलें 'downloads' फोल्डर में सेव होंगी
        """
        await update.message.reply_text(help_text)
    
    def extract_links_from_text(self, text):
        """Extract PDF and video links from text with their titles"""
        links = []
        
        # Pattern to match the file format: (title) ... https://link
        pattern = r'\(([^)]+)\)\s*(.*?)\s*https://([^\s]+)'
        
        matches = re.findall(pattern, text)
        for match in matches:
            subject = match[0].strip()
            description = match[1].strip()
            url = f"https://{match[2].strip()}"
            
            # Determine file type
            if '.pdf' in url.lower():
                file_type = 'PDF'
            elif any(ext in url.lower() for ext in ['.mp4', '.avi', '.mov', '.wmv']):
                file_type = 'VIDEO'
            else:
                file_type = 'UNKNOWN'
            
            links.append({
                'subject': subject,
                'description': description,
                'url': url,
                'type': file_type
            })
        
        return links
    
    def download_file(self, url, filename):
        """Download file from URL"""
        try:
            # Create downloads directory if it doesn't exist
            os.makedirs('downloads', exist_ok=True)
            
            # Clean filename
            filename = re.sub(r'[^\w\-_.]', '_', filename)
            filepath = os.path.join('downloads', filename)
            
            # Download file
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            return filepath
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages containing file content"""
        user_message = update.message.text
        
        # Check if message contains file content (has URLs)
        if 'https://' not in user_message:
            await update.message.reply_text("❌ कृपया टेक्स्ट फ़ाइल कंटेंट भेजें जिसमें PDF/वीडियो लिंक्स हों।")
            return
        
        # Send processing message
        processing_msg = await update.message.reply_text("🔄 फ़ाइल प्रोसेसिंग... लिंक्स एक्सट्रैक्ट किए जा रहे हैं।")
        
        try:
            # Extract links
            links = self.extract_links_from_text(user_message)
            
            if not links:
                await processing_msg.edit_text("❌ कोई वैलिड लिंक्स नहीं मिले। कृपया सही फॉर्मेट में डेटा भेजें।")
                return
            
            # Send links found message
            await processing_msg.edit_text(f"✅ {len(links)} लिंक्स मिले हैं। डाउनलोड शुरू कर रहा हूँ...")
            
            # Download files
            successful_downloads = []
            failed_downloads = []
            
            for i, link in enumerate(links, 1):
                # Create filename
                filename = f"{link['subject']}_{link['description']}_{os.path.basename(urlparse(link['url']).path)}"
                if not filename.endswith(('.pdf', '.mp4', '.avi', '.mov', '.wmv')):
                    filename += '.pdf' if link['type'] == 'PDF' else '.mp4'
                
                # Update progress
                progress_msg = f"📥 डाउनलोड हो रहा है ({i}/{len(links)}): {link['subject']}"
                await processing_msg.edit_text(progress_msg)
                
                # Download file
                filepath = self.download_file(link['url'], filename)
                
                if filepath and os.path.exists(filepath):
                    successful_downloads.append({
                        'filepath': filepath,
                        'subject': link['subject'],
                        'description': link['description'],
                        'type': link['type']
                    })
                else:
                    failed_downloads.append({
                        'subject': link['subject'],
                        'description': link['description'],
                        'url': link['url']
                    })
                
                # Small delay to avoid overwhelming the server
                await asyncio.sleep(1)
            
            # Send completion message
            completion_text = f"""
✅ **डाउनलोड पूर्ण!**

सफल डाउनलोड: {len(successful_downloads)}
विफल डाउनलोड: {len(failed_downloads)}

सभी फ़ाइलें 'downloads' फोल्डर में सेव हो गई हैं।
            """
            
            await processing_msg.edit_text(completion_text)
            
            # Send summary of downloaded files
            if successful_downloads:
                summary_text = "**सफलतापूर्वक डाउनलोड की गई फ़ाइलें:**\n\n"
                for item in successful_downloads[:10]:  # Show first 10
                    summary_text += f"• {item['subject']} - {item['description']} ({item['type']})\n"
                
                if len(successful_downloads) > 10:
                    summary_text += f"\n... और {len(successful_downloads) - 10} और फ़ाइलें"
                
                await update.message.reply_text(summary_text)
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await processing_msg.edit_text(f"❌ एरर आई: {str(e)}")
    
    def run(self):
        """Run the bot"""
        logger.info("Bot starting...")
        self.app.run_polling()

def main():
    # Get bot token from environment variable or config
    BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not BOT_TOKEN:
        print("❌ कृपया TELEGRAM_BOT_TOKEN environment variable सेट करें")
        return
    
    # Create and run bot
    bot = FileDownloaderBot(BOT_TOKEN)
    bot.run()

if __name__ == '__main__':
    main()
