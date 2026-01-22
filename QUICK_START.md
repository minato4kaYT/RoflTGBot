# Быстрый старт - Развертывание за 5 минут

## Вариант 1: Railway (самый простой) ⚡

1. **Зарегистрируйтесь** на https://railway.app (можно через GitHub)

2. **Создайте новый проект:**
   - Нажмите "New Project"
   - Выберите "Deploy from GitHub repo"
   - Подключите ваш репозиторий

3. **Добавьте переменные окружения:**
   - `BOT_TOKEN` - токен вашего бота
   - `OWNER_ID` - ваш Telegram ID
   - `REQUIRED_CHANNEL` - канал для подписки (например: `@qqgram_news`)
   - `REQUIRED_CHANNEL_URL` - URL канала (например: `https://t.me/qqgram_news`)
   - `WEBAPP_URL` - Railway автоматически создаст URL, скопируйте его сюда

4. **Готово!** Бот запустится автоматически.

## Вариант 2: Render (простой) 🚀

1. **Зарегистрируйтесь** на https://render.com

2. **Создайте Web Service:**
   - New → Web Service
   - Подключите GitHub репозиторий

3. **Настройки:**
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Environment:** Python 3

4. **Добавьте переменные окружения** (как в Railway)

5. **Готово!**

## Вариант 3: VPS (самый дешевый) 💰

### Быстрая установка на Ubuntu:

```bash
# 1. Подключитесь к серверу по SSH
ssh root@your-server-ip

# 2. Установите зависимости
apt update && apt install -y python3 python3-pip python3-venv git

# 3. Создайте пользователя
adduser --disabled-password --gecos "" botuser
su - botuser

# 4. Клонируйте проект (или загрузите файлы)
git clone <ваш-репозиторий> rofl-bot
cd rofl-bot

# 5. Создайте виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 6. Настройте config.py
nano config.py
# Укажите ваш BOT_TOKEN и другие настройки

# 7. Выйдите из пользователя
exit

# 8. Установите systemd service
sudo cp rofl-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rofl-bot
sudo systemctl start rofl-bot

# 9. Проверьте статус
sudo systemctl status rofl-bot
```

## Проверка работы

После развертывания:

1. Откройте Telegram
2. Найдите вашего бота
3. Отправьте `/start`
4. Проверьте, что бот отвечает

## Обновление бота

### Railway/Render:
- Просто сделайте `git push` - автоматически перезапустится

### VPS:
```bash
cd ~/rofl-bot
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart rofl-bot
```

## Полезные ссылки

- **DigitalOcean** (VPS): https://www.digitalocean.com
- **Hetzner** (VPS, дешево): https://www.hetzner.com
- **Railway**: https://railway.app
- **Render**: https://render.com

## Поддержка

Если что-то не работает:
1. Проверьте логи: `sudo journalctl -u rofl-bot -f` (VPS)
2. Проверьте переменные окружения
3. Убедитесь, что токен бота правильный
