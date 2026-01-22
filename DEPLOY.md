# Инструкция по развертыванию бота на хостинге

## Варианты хостинга

### 1. **VPS (рекомендуется)**
- **DigitalOcean** ($4-6/мес) - https://www.digitalocean.com
- **Hetzner** (€4-5/мес) - https://www.hetzner.com
- **AWS Lightsail** ($3.50/мес) - https://aws.amazon.com/lightsail
- **Vultr** ($2.50-6/мес) - https://www.vultr.com

### 2. **Облачные платформы (проще, но дороже)**
- **Railway** ($5/мес) - https://railway.app
- **Render** ($7/мес) - https://render.com
- **Fly.io** (бесплатный тариф) - https://fly.io
- **Heroku** ($7/мес) - https://heroku.com

## Развертывание на VPS (Ubuntu/Debian)

### Шаг 1: Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка Python и pip
sudo apt install python3 python3-pip python3-venv git nginx -y

# Создание пользователя для бота
sudo adduser --disabled-password --gecos "" botuser
sudo su - botuser
```

### Шаг 2: Клонирование проекта

```bash
# Создание директории
mkdir -p ~/rofl-bot
cd ~/rofl-bot

# Загрузка проекта (замените на ваш репозиторий или используйте scp)
# Если используете Git:
git clone <ваш-репозиторий> .

# Или загрузите файлы через scp с вашего компьютера:
# scp -r /path/to/project/* botuser@your-server-ip:~/rofl-bot/
```

### Шаг 3: Настройка окружения

```bash
# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install --upgrade pip
pip install -r requirements.txt

# Создание .env файла (или отредактируйте config.py)
nano config.py
# Укажите ваш BOT_TOKEN и другие настройки
```

### Шаг 4: Настройка systemd для автозапуска

```bash
# Выйдите из пользователя botuser
exit

# Создание systemd service
sudo nano /etc/systemd/system/rofl-bot.service
```

Вставьте следующее содержимое:

```ini
[Unit]
Description=ROFL Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/rofl-bot
Environment="PATH=/home/botuser/rofl-bot/venv/bin"
ExecStart=/home/botuser/rofl-bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Перезагрузка systemd и запуск сервиса
sudo systemctl daemon-reload
sudo systemctl enable rofl-bot
sudo systemctl start rofl-bot

# Проверка статуса
sudo systemctl status rofl-bot

# Просмотр логов
sudo journalctl -u rofl-bot -f
```

### Шаг 5: Настройка Nginx для веб-приложения

```bash
sudo nano /etc/nginx/sites-available/rofl-bot
```

Вставьте:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # Замените на ваш домен или IP

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Активация конфигурации
sudo ln -s /etc/nginx/sites-available/rofl-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Шаг 6: Настройка SSL (опционально, но рекомендуется)

```bash
# Установка Certbot
sudo apt install certbot python3-certbot-nginx -y

# Получение SSL сертификата
sudo certbot --nginx -d your-domain.com
```

### Шаг 7: Обновление config.py

```python
# Укажите публичный URL вашего веб-приложения
WEBAPP_URL = "https://your-domain.com/"
# или если используете IP:
WEBAPP_URL = "http://your-server-ip/"
```

## Развертывание на Railway

### Шаг 1: Создание аккаунта
1. Зарегистрируйтесь на https://railway.app
2. Подключите GitHub репозиторий

### Шаг 2: Создание проекта
1. Нажмите "New Project"
2. Выберите "Deploy from GitHub repo"
3. Выберите ваш репозиторий

### Шаг 3: Настройка переменных окружения
В настройках проекта добавьте:
- `BOT_TOKEN` - токен вашего бота
- `OWNER_ID` - ваш Telegram ID
- `REQUIRED_CHANNEL` - канал для подписки
- `REQUIRED_CHANNEL_URL` - URL канала
- `WEBAPP_URL` - будет автоматически сгенерирован Railway

### Шаг 4: Настройка запуска
Railway автоматически определит Python проект. Убедитесь, что:
- `requirements.txt` присутствует
- Точка входа: `bot.py`

## Развертывание на Render

### Шаг 1: Создание Web Service
1. Зарегистрируйтесь на https://render.com
2. Создайте новый "Web Service"
3. Подключите GitHub репозиторий

### Шаг 2: Настройка
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python bot.py`
- **Environment:** Python 3

### Шаг 3: Переменные окружения
Добавьте все необходимые переменные в разделе "Environment"

## Развертывание на Fly.io

### Шаг 1: Установка Fly CLI
```bash
curl -L https://fly.io/install.sh | sh
```

### Шаг 2: Создание Dockerfile
Создайте `Dockerfile` в корне проекта (см. ниже)

### Шаг 3: Развертывание
```bash
fly launch
fly deploy
```

## Полезные команды для управления

```bash
# Перезапуск бота
sudo systemctl restart rofl-bot

# Остановка бота
sudo systemctl stop rofl-bot

# Просмотр логов
sudo journalctl -u rofl-bot -f --lines=100

# Проверка статуса
sudo systemctl status rofl-bot

# Обновление кода
cd ~/rofl-bot
git pull  # или загрузите новые файлы
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart rofl-bot
```

## Мониторинг и безопасность

### Настройка firewall
```bash
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### Рекомендации
1. **Не храните токены в Git** - используйте переменные окружения
2. **Регулярно обновляйте зависимости** - `pip install --upgrade -r requirements.txt`
3. **Настройте резервное копирование** - регулярно сохраняйте `business_connections.json`
4. **Мониторинг** - используйте логи для отслеживания ошибок

## Troubleshooting

### Бот не запускается
```bash
# Проверьте логи
sudo journalctl -u rofl-bot -n 50

# Проверьте права доступа
sudo chown -R botuser:botuser /home/botuser/rofl-bot
```

### Веб-приложение не работает
```bash
# Проверьте, что бот запущен и слушает порт 8080
sudo netstat -tlnp | grep 8080

# Проверьте логи Nginx
sudo tail -f /var/log/nginx/error.log
```

### Проблемы с правами
```bash
# Убедитесь, что файлы принадлежат правильному пользователю
sudo chown -R botuser:botuser /home/botuser/rofl-bot
chmod +x bot.py
```
