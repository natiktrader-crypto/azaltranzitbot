import os
import telebot

# Получаем токен из переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Инициализируем бота
bot = telebot.TeleBot(BOT_TOKEN)

# Обработка команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = (
        "Приветствую! ✈️\n\n"
        "Я бот-ассистент по транзитным пассажирам.\n"
        "Скоро здесь можно будет проверять статусы рейсов и списки PAX."
    )
    bot.reply_to(message, welcome_text)

# Обработка текстовых сообщений
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, "Принято. Функция обработки данных рейсов находится в разработке.")

# Запуск бота
if __name__ == '__main__':
    print("Бот успешно запущен...")
    bot.infinity_polling()
