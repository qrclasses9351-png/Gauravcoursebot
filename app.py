from flask import Flask
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running on Render!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render का port
    app.run(host="0.0.0.0", port=port)
