#!/usr/bin/env python3
"""Скрипт для проверки конфигурации перед развертыванием."""

import sys
import os

def check_config():
    """Проверяет конфигурацию бота."""
    errors = []
    warnings = []
    
    try:
        from config import BOT_TOKEN, OWNER_ID, REQUIRED_CHANNEL, REQUIRED_CHANNEL_URL, WEBAPP_URL
    except ImportError as e:
        print(f"❌ Ошибка импорта config.py: {e}")
        print("   Убедитесь, что файл config.py существует и содержит все необходимые переменные.")
        return False
    
    # Проверка BOT_TOKEN
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or BOT_TOKEN == "PASTE_YOUR_TOKEN_HERE":
        errors.append("BOT_TOKEN не установлен или имеет значение по умолчанию")
    elif len(BOT_TOKEN) < 40:
        warnings.append("BOT_TOKEN выглядит слишком коротким. Проверьте правильность токена.")
    
    # Проверка OWNER_ID
    if not OWNER_ID or OWNER_ID == 0:
        errors.append("OWNER_ID не установлен")
    elif not isinstance(OWNER_ID, int):
        errors.append("OWNER_ID должен быть числом")
    
    # Проверка REQUIRED_CHANNEL
    if not REQUIRED_CHANNEL:
        warnings.append("REQUIRED_CHANNEL не установлен (опционально)")
    
    # Проверка WEBAPP_URL
    if not WEBAPP_URL or WEBAPP_URL == "https://your-domain.com/":
        warnings.append("WEBAPP_URL не настроен. Мини-приложение не будет работать.")
    elif not WEBAPP_URL.startswith(('http://', 'https://')):
        errors.append("WEBAPP_URL должен начинаться с http:// или https://")
    
    # Проверка файлов
    if not os.path.exists('bot.py'):
        errors.append("Файл bot.py не найден")
    
    if not os.path.exists('requirements.txt'):
        errors.append("Файл requirements.txt не найден")
    
    if not os.path.exists('webapp/index.html'):
        warnings.append("Директория webapp не найдена. Мини-приложение не будет работать.")
    
    # Вывод результатов
    if errors:
        print("❌ Ошибки конфигурации:")
        for error in errors:
            print(f"   • {error}")
        print("\nИсправьте ошибки перед развертыванием!")
        return False
    
    if warnings:
        print("⚠️  Предупреждения:")
        for warning in warnings:
            print(f"   • {warning}")
        print()
    
    print("✅ Конфигурация выглядит правильно!")
    print(f"\nТекущие настройки:")
    print(f"   BOT_TOKEN: {'*' * 20}...{BOT_TOKEN[-10:] if len(BOT_TOKEN) > 10 else '***'}")
    print(f"   OWNER_ID: {OWNER_ID}")
    print(f"   REQUIRED_CHANNEL: {REQUIRED_CHANNEL}")
    print(f"   WEBAPP_URL: {WEBAPP_URL}")
    
    return True

if __name__ == "__main__":
    success = check_config()
    sys.exit(0 if success else 1)
