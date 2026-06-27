cat > bot.py << 'EOF'
import os
import telebot
import time

BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не установлен!")
    exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "✅ Бот запущен и работает!\n\nНапиши /check J123 для проверки рейса.")

@bot.message_handler(commands=['check'])
def check(message):
    bot.reply_to(message, "🔍 Проверка рейса... (функция пока в разработке)")

@bot.message_handler(func=lambda m: True)
def all_messages(message):
    bot.reply_to(message, "Принято ✅\nИспользуй /start или /check [номер рейса]")

if __name__ == '__main__':
    print("🚀 AZAL Transit Bot успешно запущен!")
    while True:
        try:
            bot.infinity_polling(none_stop=True)
        except:
            time.sleep(5)
EOF
