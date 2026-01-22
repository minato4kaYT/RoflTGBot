import os

# ⚠️ ВАЖНО: Если это публичный репозиторий, не заливайте config.py с реальными токенами!
# Для публичных репозиториев используйте переменные окружения на хостинге

# Токен бота (приоритет: переменная окружения BOT_TOKEN, затем значение ниже)
BOT_TOKEN = os.getenv("BOT_TOKEN", "8528327165:AAEvpOLcFBp3wKOsoUArisSHACCS1_iKjo8")

# ID твоего аккаунта (число). Сюда будут приходить логи об изменениях/удалениях и бизнес-события.
# Узнать можно, написав /start любому "whoami" боту или через @userinfobot.
OWNER_ID = int(os.getenv("OWNER_ID", "6059673725"))

# Подписка на канал для доступа к боту (укажи @username или числовой chat_id канала).
# Канал должен быть публичным или бот должен иметь доступ к нему, иначе проверка не сработает.
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL", "@qqgram_news")
REQUIRED_CHANNEL_URL = os.getenv("REQUIRED_CHANNEL_URL", "https://t.me/qqgram_news")

# URL мини-приложения (веб-приложения) для Telegram
# Для продакшена укажите ваш домен (Railway автоматически создаст URL)
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://jesica-uncarburetted-unholy.ngrok-free.dev/")
