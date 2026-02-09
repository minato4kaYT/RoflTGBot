import asyncio
import json
import logging
import os
import random
import io
import re
import time
import hmac
import hashlib
import sqlite3

from urllib.parse import parse_qsl
from config import *

DB_PATH = os.getenv("DB_PATH", "events.db")

_db = sqlite3.connect("events.db", check_same_thread=False)
_db.row_factory = sqlite3.Row
_cur = _db.cursor()

_cur.execute("""
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER,
    event_type TEXT,
    author TEXT,
    content TEXT,
    old_content TEXT,
    timestamp INTEGER
)
""")

# Таблица для отслеживания ботов, которых видели впервые
_cur.execute("""
CREATE TABLE IF NOT EXISTS seen_bots (
    bot_id          INTEGER PRIMARY KEY,          -- id бота (Telegram user id)
    first_seen_at   INTEGER,                       -- unix timestamp первого появления
    first_seen_chat INTEGER                        -- в каком чате (owner_id) впервые увидели
)
""")

_cur.execute("""
CREATE TABLE IF NOT EXISTS scam_bots (
    bot_id TEXT PRIMARY KEY,
    reason TEXT,
    added_by INTEGER,
    added_at INTEGER
)
""")

_db.commit()

from html import escape
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher
from aiohttp import web
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    BusinessConnection,
    BusinessMessagesDeleted,
    BufferedInputFile,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from config import BOT_TOKEN, REQUIRED_CHANNEL, REQUIRED_CHANNEL_URL, WEBAPP_URL

LIVE_CLIENTS: dict[int, list[web.StreamResponse]] = {}


logging.basicConfig(level=logging.INFO)

# --- Safe prank commands (dot-commands) ---
# These are intentionally harmless: no spam, no dox, no scams.
KAWAII_MODE: Dict[int, bool] = {}

# Simple RU<->EN keyboard layout switch (popular mapping)
_RU = "йцукенгшщзхъфывапролджэячсмитьбю."
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,./"
_RU_U = _RU.upper()
_EN_U = _EN.upper()
_RU_TO_EN = {**{r: e for r, e in zip(_RU, _EN)}, **{r: e for r, e in zip(_RU_U, _EN_U)}}
_EN_TO_RU = {**{e: r for r, e in zip(_RU, _EN)}, **{e: r for r, e in zip(_RU_U, _EN_U)}}


def switch_layout(text: str) -> str:
    """Swap RU<->EN keyboard layout for each character when possible."""
    out: List[str] = []
    for ch in text:
        if ch in _RU_TO_EN:
            out.append(_RU_TO_EN[ch])
        elif ch in _EN_TO_RU:
            out.append(_EN_TO_RU[ch])
        else:
            out.append(ch)
    return "".join(out)


def is_kawaii(user_id: Optional[int]) -> bool:
    return bool(user_id and KAWAII_MODE.get(user_id))

def verify_telegram_init_data(init_data: str, bot_token: str) -> bool:
    """
    Проверяет, что запрос пришёл от Telegram Mini App
    """
    try:
        data = dict(parse_qsl(init_data, strict_parsing=True))
        received_hash = data.pop("hash")

        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

        secret_key = hashlib.sha256(bot_token.encode()).digest()
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(calculated_hash, received_hash)
    except Exception:
        return False

async def api_messages(request: web.Request):
    data = await request.json()

    init_data = data.get("initData")
    user_id = data.get("user_id")

    # 🔐 Защита
    if not init_data or not verify_telegram_init_data(init_data, BOT_TOKEN):
        return web.json_response({"error": "unauthorized"}, status=403)

    cur.execute(
        """
        SELECT event_type, author, content, old_content, timestamp
        FROM events
        WHERE owner_id = ?
        ORDER BY timestamp DESC
        LIMIT 500
        """,
        (user_id,)
    )

    rows = cur.fetchall()

    return web.json_response({
        "messages": [
            {
                "type": r["event_type"],
                "author": r["author"],
                "content": r["content"],
                "old_content": r["old_content"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]
    })

async def api_events_stream(request: web.Request):
    params = request.rel_url.query
    user_id = int(params.get("user_id", 0))
    init_data = params.get("initData")

    if not verify_telegram_init_data(init_data, BOT_TOKEN):
        return web.Response(status=403)

    resp = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

    await resp.prepare(request)

    LIVE_CLIENTS.setdefault(user_id, []).append(resp)

    try:
        while True:
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass
    finally:
        LIVE_CLIENTS[user_id].remove(resp)

    return resp

async def api_events_stream_handler(request: web.Request) -> web.StreamResponse:
    user_id = request.rel_url.query.get("user_id")
    init_data = request.rel_url.query.get("initData")

    if not user_id or not init_data:
        return web.Response(status=400)

    if not verify_telegram_init_data(init_data, BOT_TOKEN):
        return web.Response(status=403)

    try:
        user_id = int(user_id)
    except Exception:
        return web.Response(status=400)

    resp = web.StreamResponse(
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

    await resp.prepare(request)

    LIVE_CLIENTS.setdefault(user_id, []).append(resp)

    try:
        while True:
            await asyncio.sleep(60)
    finally:
        LIVE_CLIENTS[user_id].remove(resp)

    return resp


def kawaiify(text: str) -> str:
    # Minimal, safe “cute” flavoring.
    t = text.strip()
    if not t:
        return "nya~"
    suffix = random.choice([" nya~", " uwu", " ^_^", " :3"])
    return f"{t}{suffix}"


def get_prank_inline_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=".type", callback_data="prank_type"),
                InlineKeyboardButton(text=".switch", callback_data="prank_switch"),
            ],
            [
                InlineKeyboardButton(text=".kawaii", callback_data="prank_kawaii"),
                InlineKeyboardButton(text=".love", callback_data="prank_love"),
            ],
            [
                InlineKeyboardButton(text=".iq", callback_data="prank_iq"),
                InlineKeyboardButton(text=".info", callback_data="prank_info"),
            ],
            [InlineKeyboardButton(text=".zaebu", callback_data="prank_zaebu")],
        ]
    )

async def warn_about_new_bot_and_offer_report(message: types.Message):
    """
    Проверяет, упоминается ли / отправляет ли сообщение бот впервые.
    Если да — отправляет предупреждение В ТОТ ЖЕ ЧАТ (бизнес-чат клиента).
    """
    if not message.from_user:
        logging.info("[NEW_BOT] Нет from_user → пропуск")
        return

    # Отладка — куда именно отправляем
    logging.info(
        f"[NEW_BOT] Проверка | "
        f"chat_id={message.chat.id} | "
        f"chat_type={message.chat.type} | "
        f"business_conn={getattr(message, 'business_connection_id', 'нет')} | "
        f"from_id={message.from_user.id} | "
        f"is_bot={message.from_user.is_bot} | "
        f"username=@{message.from_user.username or 'нет'} | "
        f"text={(message.text or message.caption or 'нет текста')[:80]!r}"
    )

    # Собираем кандидатов на "бот" (username в нижнем регистре)
    bot_candidates = set()

    # 1. Прямое сообщение от бота
    if message.from_user.is_bot and message.from_user.username:
        bot_candidates.add(message.from_user.username.lower())

    # 2. Форвард от бота
    if message.forward_from and message.forward_from.is_bot and message.forward_from.username:
        bot_candidates.add(message.forward_from.username.lower())

    # 3. Упоминания в тексте (@name_bot / @name_robot / @name_bot_)
    if message.text or message.caption:
        text = message.text or message.caption or ""
        mentions = re.findall(r'@([a-zA-Z0-9_]{5,32}(?:_?bot|_?robot))\b', text, re.IGNORECASE)
        for m in mentions:
            bot_candidates.add(m.lower())

    # 4. Скрытый форвард (имя содержит bot/robot)
    if message.forward_sender_name:
        name_lower = message.forward_sender_name.lower()
        if "bot" in name_lower or "robot" in name_lower:
            pseudo = name_lower.replace(" ", "_").replace(".", "")
            if pseudo.endswith(("bot", "robot")):
                bot_candidates.add(pseudo)

    if not bot_candidates:
        logging.info("[NEW_BOT] Кандидаты не найдены → пропуск")
        return

    # Обрабатываем каждого нового
    for uname_lower in bot_candidates:
        key = f"bot_{uname_lower}"

        # Уже видели?
        _cur.execute("SELECT 1 FROM seen_bots WHERE bot_id = ?", (key,))
        if _cur.fetchone():
            logging.info(f"[NEW_BOT] Уже видели {uname_lower} → пропуск")
            continue

        # Новый → запоминаем
        now = int(time.time())
        _cur.execute(
            "INSERT OR IGNORE INTO seen_bots (bot_id, first_seen_at, first_seen_chat) VALUES (?, ?, ?)",
            (key, now, message.chat.id)
        )
        _db.commit()

        logging.info(f"[NEW_BOT] Новый бот добавлен в БД: {uname_lower}")

        # Отображаемое имя
        display_name = f"@{uname_lower.lstrip('@')}"
        if uname_lower.startswith("bot_"):
            display_name = f"@{uname_lower[4:]} (найден в сообщении)"

        warning_text = (
            f"🤔 EternalMOD видит бота {display_name} впервые.\n\n"
            f"Будьте аккуратны, если вам пишет незнакомый человек и "
            f"получить подарок/использовать его «гаранта».\n\n"
            f"Настоятельно рекомендуем обратиться в чат @savemod_chat и "
            f"попросить помочь с данной ситуацией.\n\n"
            f"Чтобы отправить бота на проверку команде EternalMOD, нажмите кнопку ниже."
        )

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Отправить на проверку",
                    callback_data=f"report_new_bot_{key}_{message.chat.id}"
                )
            ]
        ])

        try:
            await message.bot.send_message(
                chat_id=message.chat.id,           # ← именно сюда пришло сообщение
                text=warning_text,
                reply_markup=kb,
                disable_web_page_preview=True,
                parse_mode=None
            )
            logging.info(f"[NEW_BOT] Предупреждение успешно отправлено в чат {message.chat.id}")
        except Exception as e:
            logging.error(f"[NEW_BOT] Ошибка отправки в чат {message.chat.id}: {e}")

async def on_report_new_bot(callback: types.CallbackQuery):
    if not callback.data.startswith("report_new_bot_"):
        return

    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    reported_bot_id = int(parts[3])
    chat_id = int(parts[4])  # чат владельца

    # Получаем информацию о боте (можно расширить)
    bot_username = "неизвестно"
    try:
        bot_user = await callback.bot.get_chat(reported_bot_id)
        bot_username = bot_user.username or f"ID {reported_bot_id}"
    except:
        pass

    # Уведомление тебе (админу)
    admin_text = (
        f"📩 Новая проверка бота от пользователя {chat_id}\n\n"
        f"Бот: @{bot_username} (ID: {reported_bot_id})\n"
        f"Чат владельца: {chat_id}\n"
        f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Дальше решай сам: безопасен / скам / забанить и т.д."
    )

    # Можно добавить кнопки, если хочешь автоматизировать решение
    # admin_kb = InlineKeyboardMarkup(inline_keyboard=[
    #     [
    #         InlineKeyboardButton("Одобрить", callback_data=f"approve_bot_{reported_bot_id}_{chat_id}"),
    #         InlineKeyboardButton("Скам / Заблокировать", callback_data=f"block_bot_{reported_bot_id}_{chat_id}"),
    #     ]
    # ])

    try:
        await callback.bot.send_message(
            OWNER_ID,
            admin_text,
            # reply_markup=admin_kb,   # раскомментируй, если нужны кнопки
            disable_web_page_preview=True
        )
        await callback.answer("Бот отправлен на проверку!")
    except Exception as e:
        logging.error(f"Ошибка отправки админу: {e}")
        await callback.answer("Не удалось отправить на проверку", show_alert=True)

async def cmd_prank_menu(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    
    # Удаляем сообщение ".команды"
    try:
        await message.delete()
    except Exception as e:
        logging.debug(f"Could not delete message: {e}")
    
    await message.answer(
        "🎛 <b>Пранк-меню (безопасное)</b>\n\n"
        "Выбери команду или набери её текстом (например: <code>.type привет</code>).",
        reply_markup=get_prank_inline_kb(),
    )


async def cmd_prank_menu_nogate(message: types.Message) -> None:
    """Same menu, but without subscription gate (used inside business chats for the owner)."""
    remember_message(message)
    
    # Удаляем сообщение ".команды"
    try:
        await message.delete()
    except Exception as e:
        logging.debug(f"Could not delete message: {e}")
    
    await message.answer(
        "🎛 <b>Пранк-меню (безопасное)</b>\n\n"
        "Выбери команду или набери её текстом (например: <code>.type привет</code>).",
        reply_markup=get_prank_inline_kb(),
    )


async def handle_dot_command(message: types.Message) -> bool:
    """Returns True if handled as a dot-command."""
    if not await require_subscription_message(message):
        return True

    text = (message.text or "").strip()
    if not text.startswith("."):
        return False

    remember_message(message)
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == ".type":
        if not arg:
            await message.answer("Команда: <b>.type</b>\nПример: <code>.type привет</code>", reply_markup=MAIN_KEYBOARD)
            return True
        # Simulate typing a bit
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
        except Exception:
            pass
        await asyncio.sleep(min(2.0, 0.02 * len(arg) + 0.2))
        out = arg
        if is_kawaii(message.from_user.id if message.from_user else None):
            out = kawaiify(out)
        await message.answer(out, reply_markup=MAIN_KEYBOARD)
        return True

    if cmd == ".switch":
        # Если есть аргумент, используем его
        if arg:
            await message.answer(switch_layout(arg), reply_markup=MAIN_KEYBOARD)
            return True
        
        # Если нет аргумента, проверяем reply_to_message
        if message.reply_to_message:
            replied_text = message.reply_to_message.text or message.reply_to_message.caption
            logging.info(
                f".switch command: reply_to_message exists, text={replied_text is not None}, "
                f"caption={message.reply_to_message.caption is not None if message.reply_to_message.caption else False}"
            )
            if replied_text:
                result = switch_layout(replied_text)
                await message.answer(result, reply_markup=MAIN_KEYBOARD)
                return True
            else:
                await message.answer("❌ В сообщении, на которое ты ответил, нет текста.", reply_markup=MAIN_KEYBOARD)
                return True
        
        # Если reply_to_message есть, но текст недоступен, попробуем получить из кэша
        if message.reply_to_message:
            reply_key = (message.reply_to_message.chat.id, message.reply_to_message.message_id)
            cached = MESSAGE_LOG.get(reply_key)
            if cached and cached.get("content"):
                result = switch_layout(cached["content"])
                await message.answer(result, reply_markup=MAIN_KEYBOARD)
                return True
        
        # Нет ни аргумента, ни reply
        logging.info(f".switch command: no arg and no reply_to_message (reply_to_message={message.reply_to_message is not None})")
        await message.answer(
            "Команда: <b>.switch</b>\n\n"
            "Использование:\n"
            "• <code>.switch ghbdtn</code> — перевести текст\n"
            "• Ответь на сообщение с неправильной раскладкой и напиши <code>.switch</code>",
            reply_markup=MAIN_KEYBOARD
        )
        return True

    if cmd in (".команды", ".commands"):
        await cmd_prank_menu(message)
        return True

    if cmd == ".kawaii":
        uid = message.from_user.id if message.from_user else None
        if not uid:
            return True
        KAWAII_MODE[uid] = not KAWAII_MODE.get(uid, False)
        state = "включён" if KAWAII_MODE[uid] else "выключен"
        await message.answer(f"🐾 Kawaii-режим <b>{state}</b>.", reply_markup=MAIN_KEYBOARD)
        return True

    if cmd == ".love":
        msg = random.choice(
            [
                "💘 Любовь запущена… *пик* …готово!",
                "❤️ Сердечко доставлено адресату. Если адресата нет — ну… сам виноват 😄",
                "💞 Режим романтики активирован на 10 секунд (примерно).",
            ]
        )
        await message.answer(msg, reply_markup=MAIN_KEYBOARD)
        return True

    if cmd == ".iq":
        iq = random.randint(40, 200)
        await message.answer(f"🧠 Твой IQ сегодня: <b>{iq}</b>", reply_markup=MAIN_KEYBOARD)
        return True

    if cmd == ".zaebu":
        await message.answer("Заебушка ✨", reply_markup=MAIN_KEYBOARD)
        return True

    if cmd == ".тест":
        if not message.from_user:
            return True
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Проверяем подписку
        is_sub = await is_subscribed(message.bot, user_id)
        
        if is_sub:
            await message.answer(
                "✅ Ты подписан на канал.\n\n"
                "Чтобы протестировать уведомление:\n"
                "1. Отпишись от канала @qqgram_news\n"
                "2. Подожди 10 секунд (cooldown)\n"
                "3. Измени или удали сообщение в бизнес-чате\n"
                "4. Или используй команду .тест снова",
                reply_markup=MAIN_KEYBOARD
            )
        else:
            # Вызываем функцию уведомления напрямую (для теста)
            # Сбрасываем cooldown для теста
            LAST_SUBSCRIPTION_NOTIFICATION[user_id] = 0
            await send_subscription_required_notification(message.bot, chat_id, user_id)
            await message.answer(
                "📤 Отправлено тестовое уведомление о необходимости подписки.\n\n"
                "Если уведомление не пришло, возможно не прошло 10 секунд с последнего уведомления.",
                reply_markup=MAIN_KEYBOARD
            )
        return True

    if cmd == ".info":
        u = message.from_user
        if not u:
            return True
        bc_id = getattr(message, "business_connection_id", None)
        bc_state = "неизвестно"
        if bc_id and bc_id in BUSINESS_LOG_CHATS:
            bc_state = "подключён (бизнес)"
        await message.answer(
            "ℹ️ <b>Инфо</b>\n"
            f"• id: <code>{u.id}</code>\n"
            f"• username: <code>{escape(u.username or '-')}</code>\n"
            f"• business: <b>{bc_state}</b>",
            reply_markup=MAIN_KEYBOARD,
        )
        return True

    # Blocked / not supported (we keep a friendly response)
    await message.answer(
        "Эта команда недоступна в этом боте 🙂\n"
        "Открой «📋 Описание команд» → «Пранк-меню», там только безопасные штуки.",
        reply_markup=MAIN_KEYBOARD,
    )
    return True


ROFL_LINES: List[str] = [
    "Бот не тупит, он просто думает асинхронно.",
    "На свете два вида людей: те, кто ждёт ответ от бота… и я.",
    "Если бы у меня были руки, я бы хлопал тебе. Но нет.",
    "Люди шутят, когда нервничают. Я шучу, когда обновляют pip.",
    "Я не баг — я сюрпризный фичер.",
    "Главное — не путать «/stop» с «/стоп»… хотя у меня все равно нет /stop.",
    "Оптимист видит стакан наполовину полным. Пессимист — наполовину пустым. Я вижу стакан и думаю: 'А где мой токен?'",
    "Жизнь как код: работает на тестовом окружении, падает на проде.",
    "Почему программисты не любят природу? Там слишком много багов.",
    "Что общего у программиста и алкоголика? Оба ищут баг в коде.",
    "Программист умер и попал в ад. Дьявол говорит: 'Твой код будет работать вечно'. Программист: 'Это и есть ад!'",
    "Почему программисты предпочитают тёмную тему? Потому что свет притягивает баги.",
    "Как программист решает проблемы? Он их игнорирует до тех пор, пока они не решатся сами.",
    "Что такое оптимизм для программиста? 'Это работает на моей машине'.",
    "Почему программисты не любят ходить на природу? Там нет Wi‑Fi и слишком много багов.",
    "Программист читает книгу о самоубийстве. Глава 1: 'Введение'. Программист: 'Слишком сложно, пропускаю'.",
    "Что общего у программиста и кота? Оба думают, что они боги, пока не увидят ошибку.",
    "Почему программисты не любят пляж? Там слишком много песка, а песок — это стекло, а стекло — это баги.",
    "Программист заходит в бар и заказывает -1 пива. Бармен: 'Такого не бывает'. Программист: 'Тогда null'.",
    "Как программист решает проблему? Он её игнорирует, пока она не станет критической.",
    "Почему программисты не любят природу? Там нет Ctrl+Z.",
    "Программист умер и попал в рай. Бог говорит: 'Твой код работает без багов'. Программист: 'Это точно рай?'",
    "Что такое бесконечный цикл для программиста? Его жизнь.",
    "Почему программисты не любят выходные? Потому что в понедельник код не работает.",
    "Программист читает мануал. Страница 1: 'Введение'. Программист: 'Слишком сложно, гуглю'.",
    "Что общего у программиста и философа? Оба думают о смысле жизни, но программист хотя бы получает за это деньги.",
    "Почему программисты не любят ходить на свидания? Там нет автодополнения.",
    "Программист заходит в бар и заказывает напиток. Бармен: 'Какой?'. Программист: 'Любой, главное чтобы работало'.",
    "Что такое счастье для программиста? Когда код работает с первого раза.",
    "Почему программисты не любят природу? Там нет интернета, а без интернета они как рыба без воды.",
    "Программист умер и попал в чистилище. Ангел говорит: 'Твой код будет работать, но медленно'. Программист: 'Это и есть чистилище!'",
    "Что общего у программиста и детектива? Оба ищут баги.",
    "Почему программисты не любят спорт? Там нет кнопки 'Отменить последнее действие'.",
    "Программист читает книгу о счастье. Глава 1: 'Введение'. Программист: 'Слишком сложно, удаляю'.",
    "Что такое ад для программиста? Когда код работает на всех машинах, кроме его.",
    "Почему программисты не любят ходить в кино? Там нельзя поставить breakpoint.",
    "Программист заходит в бар и заказывает напиток. Бармен: 'Какой?'. Программист: 'Тот, что в документации'.",
    "Что общего у программиста и художника? Оба создают искусство, но программист хотя бы знает, что делает.",
    "Почему программисты не любят природу? Там нет автодополнения и слишком много багов.",
    "Программист умер и попал в ад. Дьявол говорит: 'Твой код будет работать, но только на Windows 95'. Программист: 'Это и есть ад!'",
    "Что такое оптимизм для программиста? 'Это работает на моей машине, значит работает везде'.",
    "Почему программисты не любят ходить на вечеринки? Там нет кнопки 'Отменить последнее действие'.",
    "Программист читает мануал. Страница 1: 'Введение'. Программист: 'Слишком сложно, Stack Overflow'.",
    "Что общего у программиста и врача? Оба ищут баги, но врач хотя бы знает, где искать.",
    "Почему программисты не любят спорт? Там нет кнопки 'Отменить последнее действие' и слишком много багов.",
    "Программист заходит в бар и заказывает напиток. Бармен: 'Какой?'. Программист: 'Тот, что работает'.",
    "Что такое счастье для программиста? Когда код работает с первого раза и нет багов.",
    "Почему программисты не любят природу? Там нет интернета, а без интернета они как рыба без воды и багов.",
    "Программист умер и попал в чистилище. Ангел говорит: 'Твой код будет работать, но медленно и с багами'. Программист: 'Это и есть чистилище!'",
]

# Черные рофлы (dark humor)
DARK_ROFL_LINES: List[str] = [
    "Колобок повесился.",
    "Газпром. Мечты сбываются.",
    "Пессимист видит стакан наполовину пустым. Оптимист видит стакан наполовину полным. Реалист видит стакан и думает: 'Кто его здесь оставил?'",
    "Жизнь прекрасна, пока не проснёшься.",
    "Всё будет хорошо. Просто не с тобой.",
    "Улыбайся! Завтра будет хуже.",
    "Надежда умирает последней. Но она всё равно умрёт.",
    "Всё к лучшему. Просто лучшее ещё не пришло.",
    "Завтра будет лучше. Но сегодня уже не будет.",
    "Жизнь как зебра: чёрная полоса, белая полоса, чёрная полоса, белая полоса... а потом тебя сбивает грузовик.",
    "Всё проходит. И это тоже пройдёт. И ты тоже пройдёшь.",
    "Оптимист видит свет в конце туннеля. Пессимист видит свет в конце туннеля и понимает, что это поезд.",
    "Жизнь даёт тебе лимоны. Но лимоны гнилые, и у тебя аллергия на цитрусовые.",
    "Всё будет хорошо. Просто не сегодня. И не завтра. И вообще никогда.",
    "Улыбайся! Мир не такой плохой, каким кажется. Он хуже.",
    "Надежда — это последнее, что умирает. Поэтому она и умирает последней.",
    "Жизнь прекрасна. Просто не твоя.",
    "Всё к лучшему. Просто лучшее — это смерть.",
    "Завтра будет новый день. Но сегодня всё ещё сегодня.",
    "Жизнь как шоколад: горькая, и её мало.",
    "Всё проходит. И это тоже пройдёт. И ты тоже пройдёшь. И никто не заметит.",
    "Оптимист видит стакан наполовину полным. Пессимист видит стакан наполовину пустым. Я вижу стакан и думаю: 'Кто его здесь оставил и почему он не мой?'",
    "Жизнь даёт тебе возможности. Но они все упущены.",
    "Всё будет хорошо. Просто хорошо — это относительно.",
    "Улыбайся! Завтра будет хуже, но ты этого не увидишь.",
    "Надежда умирает последней. Но она всё равно умрёт, и ты останешься один.",
    "Жизнь прекрасна. Просто не для тебя. И не для меня. Вообще ни для кого.",
    "Всё к лучшему. Просто лучшее — это когда всё закончится.",
    "Завтра будет лучше. Но сегодня уже не будет, и завтра тоже не будет.",
    "Жизнь как зебра: полосатая, и тебя всё равно собьют.",
    "Всё проходит. И это тоже пройдёт. И ты тоже пройдёшь. И никто не вспомнит.",
    "Оптимист видит свет в конце туннеля. Пессимист видит поезд. Реалист видит, что это не туннель, а могила.",
    "Жизнь даёт тебе лимоны. Но лимоны гнилые, у тебя аллергия, и лимоны стоят дорого.",
    "Всё будет хорошо. Просто хорошо — это когда ты уже не чувствуешь боль.",
    "Улыбайся! Мир не такой плохой. Он хуже. Намного хуже.",
    "Надежда — это последнее, что умирает. Поэтому она и умирает последней, оставляя тебя в полной безнадёжности.",
    "Жизнь прекрасна. Просто не твоя. И не моя. Вообще ничья.",
    "Всё к лучшему. Просто лучшее — это когда всё закончится, и ты больше не будешь страдать.",
    "Завтра будет новый день. Но сегодня всё ещё сегодня, и завтра тоже будет сегодня.",
    "Жизнь как шоколад: горькая, её мало, и она стоит дорого.",
    "Всё проходит. И это тоже пройдёт. И ты тоже пройдёшь. И никто не заметит. И никто не вспомнит.",
    "Колобок повесился. А заяц так и не понял, почему.",
    "Газпром. Мечты сбываются. Твои — нет.",
    "Жизнь прекрасна. Просто не для тебя. И не для меня. Вообще ни для кого. Особенно не для тебя.",
    "Всё будет хорошо. Просто хорошо — это когда ты уже мёртв.",
    "Улыбайся! Завтра будет хуже, но ты этого не увидишь, потому что завтра не будет.",
    "Надежда умирает последней. Но она всё равно умрёт, и ты останешься один. В полной безнадёжности.",
    "Жизнь даёт тебе возможности. Но они все упущены. И ты их упустил.",
    "Всё к лучшему. Просто лучшее — это когда всё закончится, и ты больше не будешь страдать. Но ты всё равно будешь страдать.",
    "Завтра будет лучше. Но сегодня уже не будет, и завтра тоже не будет. И вообще ничего не будет.",
    "Жизнь как зебра: полосатая, и тебя всё равно собьют. И никто не поможет.",
    "Всё проходит. И это тоже пройдёт. И ты тоже пройдёшь. И никто не заметит. И никто не вспомнит. И никто не будет скучать.",
    "Оптимист видит стакан наполовину полным. Пессимист видит стакан наполовину пустым. Я вижу стакан и думаю: 'Кто его здесь оставил, почему он не мой, и почему я вообще здесь?'",
    "Жизнь даёт тебе лимоны. Но лимоны гнилые, у тебя аллергия, лимоны стоят дорого, и ты всё равно умрёшь.",
    "Всё будет хорошо. Просто хорошо — это когда ты уже не чувствуешь боль. Но ты всё равно будешь чувствовать боль.",
    "Улыбайся! Мир не такой плохой. Он хуже. Намного хуже. И становится ещё хуже.",
    "Надежда — это последнее, что умирает. Поэтому она и умирает последней, оставляя тебя в полной безнадёжности. И ты остаёшься один.",
    "Жизнь прекрасна. Просто не твоя. И не моя. Вообще ничья. Особенно не твоя. И точно не моя.",
    "Всё к лучшему. Просто лучшее — это когда всё закончится, и ты больше не будешь страдать. Но ты всё равно будешь страдать. До самого конца.",
    "Завтра будет новый день. Но сегодня всё ещё сегодня, и завтра тоже будет сегодня. И вообще всё сегодня.",
    "Жизнь как шоколад: горькая, её мало, она стоит дорого, и ты всё равно умрёшь. Но хотя бы шоколад был вкусным.",
    "Всё проходит. И это тоже пройдёт. И ты тоже пройдёшь. И никто не заметит. И никто не вспомнит. И никто не будет скучать. И это нормально.",
    "Колобок повесился. А заяц так и не понял, почему. И никто не понял. И никто не будет понимать.",
    "Газпром. Мечты сбываются. Твои — нет. И не сбудутся. Никогда.",
    "Жизнь прекрасна. Просто не для тебя. И не для меня. Вообще ни для кого. Особенно не для тебя. И точно не для меня. И вообще ни для кого.",
    "— Мама, что такое черный юмор?\n — Сынок, видишь вон там мужчину без рук? Вели ему похлопать в ладоши.\n — Мама! Я же слепой!\n — Вот именно.",
    "— Будешь выходить — труп вынеси!\n — Может быть, мусор?\n — Может — мусор, может — сантехник, бог его знает…",
    "Одну девочку в школе называли Крокодилом. Но не потому, что  она была некрасивая, а потому, что один раз затащила в реку оленя и  сожрала его.",
    "— Почему-то, когда вы улыбаетесь, один глаз у вас веселый, а другой грустный-грустный такой.\n — Веселый — это искусственный.",
    "Из записи в «Книге жалоб и предложений» супермаркета:\n «Товары  расположены не очень удобно. Например, веревки в хозяйственном отделе,  мыло в косметическом, табуретки вообще на другом этаже, в мебельном».",
    "— Ура, я поступила в автошколу, скоро будет на одного пешехода меньше!\n — А может, и не на одного.",
    "Когда я вижу вырезанные на деревьях имена влюбленных, я не  нахожу это романтичным. Кошмарно, что люди ходят на свидания с ножами.",
    "Когда изобретатель USB-порта умрет, его гроб сначала опустят в  яму, потом поднимут и перевернут и опустят снова правильной стороной.",
    "— Моя девушка порвала со мной, и я забрал ее кресло-каталку. Угадайте, кто приполз ко мне на коленях?",
    "Вчера я узнал, что 20 рыбок-пираний могут обглодать человека  до костей за 15 минут. К сожалению, из-за этого я потерял работу в  плавательном бассейне",
    "Акробат умер на батуте, но еще какое-то время продолжал радовать публику.",
    "Шутки про утопленников обычно несмешные, потому что лежат на поверхности.",
    "— Кот умер год назад. Так я до сих пор замедляю шаг в  коридоре, там, где он любил лежать, чтобы не споткнуться об него в  темноте.\n — Может, пора его похоронить?",
    "— Доктор, я съел пиццу вместе с упаковкой. Я умру?\n — Ну, все когда-нибудь умрут…\n — Все умрут! Ужас, что я наделал!",
    "Однорукий человек заплакал, увидев магазин «секонд-хенд».",
    "Одноглазый, одноухий, одноногий мужчина без одной руки, ищет свою половину.",
    "У моей девушки сдохла собачка, и, чтобы взбодрить ее, я нашел и  принес ей точно такую же. Она расплакалась и спросила меня: «Зачем мне  две дохлые собачки?»",
    "— Извините, а какой здесь пароль от вайфая?\n — Это же похороны!\n — «Похороны» с маленькой или большой?",
    "Чтобы проверить, курю я или нет, родители перед уходом оставляли газ включенным.",
    "Фальшивого дрессировщика в цирке быстро раскусили.",
    "Прочитал, что на Кавказе каждые две минуты протыкают ножом человека. Крайне жаль этого бедолагу.",
    "Задолбали соседи. Пьянки, гулянки, то поют, то дерутся. Решил  переехать. Только надо поймать момент, когда они вместе дорогу  переходить будут.",
    "На распродаже человеческих органов началась драка. Я еле успел унести ноги.",
    "— Доктор, у вас есть что-нибудь от головы?\n — Вот, возьмите ухо.",
    "Умер как-то продавец-консультант. На его могилу до сих пор тянутся люди — просто посмотреть.",
    "— Послала своего за картошкой, а его сбила машина.\n — Ужас! И что ты теперь будешь делать?\n — Не знаю. Рис, наверное.",
    "Слепой заходит в магазин, берет собаку-поводыря и начинает раскручивать ее над головой.\n — Что вы делаете?!\n — Да так, осматриваюсь.",
    "У каждой домохозяйки есть свой маленький секретик. Надежда  Константиновна, например, выводит пятна уксусом, а Татьяна Андреевна  отравила своего мужа.",
    "Одна девочка так сильно боялась прыгать с парашютом, что прыгнула без него.",
    "— Мам, смотри голубь! У тебя хлеб есть?\n — Без хлеба ешь!",
    "— У вас есть литература о дискриминации карликов?\n — Посмотрите в углу на верхней полке.",
    "Охотника-промысловика Сидорова, легко попадавшего со ста метров белке в глаз, загрызла стая одноглазых белок.",
    "Находчивые браконьеры подожгли егеря, и он показал им дорогу к озеру.",
    "Когда мне исполнилось шестнадцать, мой отец сказал: «Лучше это произойдет с тобой дома, чем в подворотне» — и пырнул меня ножом.",
    "Чтобы не перепутать, бабушка назвала одного новорожденного котенка Барсиком, а второго утопила.",
    "Проводи каждый день своей жизни, как будто он последний: лежи на кровати, кашляй, собери родственников, обоссысь.",
    "Моя девушка смеялась, когда я сказал ей, что у меня тело 18-летнего парня. Пока не открыла холодильник…",
    "Если бы моя бабушка знала как хорошо мне удалось сэкономить на ее похоронах, она бы а канаве перевернулась.",
    "Ехали по пустыне два армянских инвалида-колясочника, и увидели лампу,  потерли её и предстал перед ними джин. И сказал им джин: 'я выполню любое  ваше желание, но одно на двоих, общее, подумайте, что вы оба хотите  больше всего на свете'. И сказали армяне: 'больше всего на свете мы  хотим ходить!' И воскликнул джин: 'да будет так!', дал им нарды и  сказал: 'ходите'.",
    "Весенне утро, солнышко светит. Палата в  роддоме. Открывается дверь, входят медсестры, врач с ребенком на руках.  Все улыбаются. Роженица тоже. И вдруг туча нашла на солнце, темнеет.  Все меняются в лицах. Врач разрывает пеленки и хватает ребенка за ногу и  начинает бить им о стены и мебель. Роженица кричит в ужасе.",
    "Одна из медсестер: - Не бойтесь, это врач шутит! Ребенок все равно мертвым родился!",
    "Мясник устроился работать помощником акушера. И вот, прошли роды\n нормально, акушер говорит мяснику: 'Пойди взвесь ребенка'. Через 5 минут\n мясник возвращается вспотевший. Акушер спрашивает:\n - Ну как?\n - Три двести........ без костей.",
    "Усопшего так нахваливали в процессе похоронный церемонии, что его  вдова несколько раз подходила к гробу, чтобы проверить, кто там лежит.",
    "Я воспитывался как единственный ребенок в семье. Это очень расстраивало мою старшую сестру",
    "Черный юмор, он как дети антипрививочников - никогда ее стареет"
]

MESSAGE_LOG: Dict[Tuple[int, int], Dict[str, str]] = {}
# business_connection_id -> {chat_id: int, owner_id: int}
BUSINESS_LOG_CHATS: Dict[str, Dict[str, int]] = {}
BUSINESS_CONNECTIONS_FILE = "business_connections.json"
# Для отслеживания последнего уведомления о подписке (чтобы не спамить)
# owner_id -> timestamp последнего уведомления
LAST_SUBSCRIPTION_NOTIFICATION: Dict[int, float] = {} 
SUBSCRIPTION_NOTIFICATION_COOLDOWN = 3600  # 1 час в секундах
# История событий для мини-приложения: owner_id -> List[Dict]
EVENTS_HISTORY: Dict[int, List[Dict[str, Any]]] = {}


def load_business_connections() -> None:
    """Загрузить бизнес-подключения из файла."""
    global BUSINESS_LOG_CHATS
    if os.path.exists(BUSINESS_CONNECTIONS_FILE):
        try:
            with open(BUSINESS_CONNECTIONS_FILE, "r", encoding="utf-8") as f:
                raw: Any = json.load(f)

            # Backward compatible миграция:
            # старый формат: { bc_id: chat_id }
            # новый формат: { bc_id: { "chat_id": int, "owner_id": int } }
            migrated: Dict[str, Dict[str, int]] = {}
            if isinstance(raw, dict):
                for k, v in raw.items():
                    if isinstance(v, dict) and "chat_id" in v:
                        migrated[str(k)] = {
                            "chat_id": int(v.get("chat_id")),
                            "owner_id": int(v.get("owner_id", 0)),
                        }
                    else:
                        # old schema (chat_id only)
                        try:
                            migrated[str(k)] = {"chat_id": int(v), "owner_id": 0}
                        except Exception:
                            continue
            BUSINESS_LOG_CHATS = migrated
            logging.info(f"Loaded {len(BUSINESS_LOG_CHATS)} business connections from file")
        except Exception as e:
            logging.error(f"Error loading business connections: {e}")
            BUSINESS_LOG_CHATS = {}


def save_business_connections() -> None:
    """Сохранить бизнес-подключения в файл."""
    try:
        with open(BUSINESS_CONNECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(BUSINESS_LOG_CHATS, f, ensure_ascii=False, indent=2)
        logging.debug(f"Saved {len(BUSINESS_LOG_CHATS)} business connections to file")
    except Exception as e:
        logging.error(f"Error saving business connections: {e}")


def get_log_chat_id(bc_id: Optional[str]) -> Optional[int]:
    if not bc_id:
        return None
    rec = BUSINESS_LOG_CHATS.get(bc_id)
    if not rec:
        return None
    return rec.get("chat_id")


def get_owner_id(bc_id: Optional[str]) -> Optional[int]:
    if not bc_id:
        return None
    rec = BUSINESS_LOG_CHATS.get(bc_id)
    if not rec:
        return None
    oid = rec.get("owner_id") or 0
    return oid or None


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🎭 Рофл"),
            KeyboardButton(text="🧽 Mock текст"),
        ],
        [
            KeyboardButton(text="🖤 Черные рофлы"),
            KeyboardButton(text="🪙 Подбросить монетку"),
        ],
        [
            KeyboardButton(text="📖 Инструкция"),
            KeyboardButton(text="📋 Описание команд"),
        ],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери рофл или напиши своё сообщение...",
)


SUBSCRIBE_KB = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Подписаться", url=REQUIRED_CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
    ]
)


def _is_member_status(status: str) -> bool:
    return status in ("member", "administrator", "creator")


async def is_subscribed(bot: Bot, user_id: int) -> bool:
    """Return True if user is subscribed to REQUIRED_CHANNEL."""
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return _is_member_status(getattr(member, "status", ""))
    except Exception as e:
        logging.warning("Subscription check failed: user_id=%s error=%r", user_id, e)
        # Fail closed: if we can't check, deny access to avoid bypass
        return False


async def require_subscription_message(message: types.Message) -> bool:
    """Gate for Message handlers. Returns True if allowed."""
    if not message.from_user:
        return False
    if await is_subscribed(message.bot, message.from_user.id):
        return True
    await message.answer(
        "⚠️ <b>Требуется подписка</b>\n\n"
        "Для продолжения работы с ботом подпишись на канал и нажми «Проверить подписку».",
        reply_markup=SUBSCRIBE_KB,
    )
    return False


async def require_subscription_callback(callback: types.CallbackQuery) -> bool:
    """Gate for Callback handlers. Returns True if allowed."""
    if not callback.from_user:
        return False
    if await is_subscribed(callback.bot, callback.from_user.id):
        return True
    await callback.message.answer(
        "⚠️ <b>Требуется подписка</b>\n\n"
        "Для продолжения работы с ботом подпишись на канал и нажми «Проверить подписку».",
        reply_markup=SUBSCRIBE_KB,
    )
    await callback.answer()
    return False


async def send_subscription_required_notification(bot: Bot, chat_id: int, owner_id: int) -> None:
    """Отправить уведомление о необходимости подписки (с защитой от спама)."""
    current_time = time.time()
    last_notification = LAST_SUBSCRIPTION_NOTIFICATION.get(owner_id, 0)
    
    # Проверяем, прошло ли достаточно времени с последнего уведомления
    if current_time - last_notification < SUBSCRIPTION_NOTIFICATION_COOLDOWN:
        return
    
    # Обновляем время последнего уведомления
    LAST_SUBSCRIPTION_NOTIFICATION[owner_id] = current_time
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ <b>Доступ к функциям бизнес-бота закрыт</b>\n\n"
                "Для использования функций отслеживания изменённых, удалённых и исчезающих сообщений "
                "необходимо подписаться на канал.\n\n"
                "Подпишись на канал и нажми «Проверить подписку» для восстановления доступа."
            ),
            reply_markup=SUBSCRIBE_KB,
        )
    except Exception as e:
        logging.warning(f"Failed to send subscription notification to {chat_id}: {e}")


def user_mention(user: Optional[types.User]) -> str:
    if not user:
        return "кто-то"
    name = escape(user.full_name)
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def format_text_diff(old_text: str, new_text: str) -> str:
    """Форматирует различия между старым и новым текстом: старый зачёркнут, новый жирным."""
    if old_text == new_text:
        return escape(new_text)
    
    # Используем SequenceMatcher для более точного определения различий
    matcher = SequenceMatcher(None, old_text, new_text)
    result_parts = []
    old_pos = 0
    new_pos = 0
    prev_was_delete = False
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # Неизменённая часть
            result_parts.append(escape(old_text[i1:i2]))
            old_pos = i2
            new_pos = j2
            prev_was_delete = False
        elif tag == 'replace':
            # Заменённая часть: старый текст зачёркнут (не жирным), новый жирным, рядом друг с другом
            old_part = escape(old_text[i1:i2])
            new_part = escape(new_text[j1:j2])
            if old_part:
                result_parts.append(f"<s>{old_part}</s>")
            if new_part:
                result_parts.append(f"<b>{new_part}</b>")
            old_pos = i2
            new_pos = j2
            prev_was_delete = False
        elif tag == 'delete':
            # Удалённая часть - зачёркнута
            result_parts.append(f"<s>{escape(old_text[i1:i2])}</s>")
            old_pos = i2
            prev_was_delete = True
        elif tag == 'insert':
            # Вставленная часть - жирным, рядом с зачёркнутым если был delete
            if prev_was_delete:
                result_parts.append(f"<b>{escape(new_text[j1:j2])}</b>")
            else:
                result_parts.append(f"<b>{escape(new_text[j1:j2])}</b>")
            new_pos = j2
            prev_was_delete = False
    
    return "".join(result_parts)

async def push_live_event(owner_id: int, event: dict) -> None:
    """
    Отправляет событие всем подключённым Mini App клиентам (SSE)
    """
    clients = LIVE_CLIENTS.get(owner_id)
    if not clients:
        return

    dead = []

    for resp in clients:
        try:
            await resp.write(
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode()
            )
        except Exception:
            dead.append(resp)

    # чистим мёртвые соединения
    for resp in dead:
        try:
            clients.remove(resp)
        except ValueError:
            pass


def save_event(
    owner_id: int,
    event_type: str,
    author: str,
    content: str,
    old_content: Optional[str] = None
) -> None:
    global _cur, _db

    ts = int(time.time())

    # ========= 1. ПАМЯТЬ (совместимость, ничего не ломаем) =========
    history = EVENTS_HISTORY.setdefault(owner_id, [])

    event = {
        "type": event_type,
        "author": author,
        "content": content,
        "old_content": old_content,
        "timestamp": ts,
    }

    history.append(event)

    # ограничение истории
    if len(history) > 1000:
        del history[:-1000]

    # ========= 2. БАЗА ДАННЫХ =========
    try:
        _cur.execute(
            """
            INSERT INTO events
            (owner_id, event_type, author, content, old_content, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                event_type,
                author,
                content,
                old_content,
                ts,
            )
        )
        _db.commit()
    except Exception:
        logging.exception("save_event: DB error")

    # ========= 3. LIVE-ОБНОВЛЕНИЕ (НЕ БЛОКИРУЕТ БОТА) =========
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(push_live_event(owner_id, event))
    except RuntimeError:
        pass




def remember_message(message: types.Message) -> None:
    """Store last seen version of a message to show on edit/delete."""
    content = message.text or message.caption or "<без текста>"
    mention = user_mention(message.from_user)
    bc_id = getattr(message, "business_connection_id", None)

    media_type: Optional[str] = None
    media_file_id: Optional[str] = None
    if message.photo:
        # Берём самое большое фото
        media_type = "photo"
        media_file_id = message.photo[-1].file_id
    elif message.video:
        media_type = "video"
        media_file_id = message.video.file_id
    elif message.voice:
        media_type = "voice"
        media_file_id = message.voice.file_id
    elif message.video_note:
        media_type = "video_note"
        media_file_id = message.video_note.file_id
    elif message.animation:
        media_type = "animation"
        media_file_id = message.animation.file_id
    elif message.document:
        media_type = "document"
        media_file_id = message.document.file_id

    MESSAGE_LOG[(message.chat.id, message.message_id)] = {
        "content": content,
        "user": mention,
        "business_connection_id": bc_id,
        "media_type": media_type,
        "media_file_id": media_file_id,
    }
    if bc_id:
        logging.debug(f"Remembered message: chat_id={message.chat.id}, msg_id={message.message_id}, bc_id={bc_id}")


def remember_foreign_message(
    *,
    chat_id: int,
    message_id: int,
    from_user: Optional[types.User],
    text: Optional[str],
    caption: Optional[str],
    bc_id: Optional[str],
    media_type: Optional[str],
    media_file_id: Optional[str],
) -> None:
    """Store a message-like payload (e.g. reply_to_message) with explicit bc_id."""
    content = text or caption or "<без текста>"
    mention = user_mention(from_user)
    MESSAGE_LOG[(chat_id, message_id)] = {
        "content": content,
        "user": mention,
        "business_connection_id": bc_id,
        "media_type": media_type,
        "media_file_id": media_file_id,
    }


def is_media_message(message: Optional[types.Message]) -> bool:
    """Detect media types we want to preserve when someone replies (incl. disappearing media)."""
    if not message:
        return False
    return bool(
        message.photo
        or message.video
        or message.voice
        or message.video_note
        or message.animation
        or message.document
    )


async def send_cached_media(
    bot: Bot,
    *,
    target_chat_id: int,
    cached: Dict[str, str],
    caption: Optional[str] = None,
) -> bool:
    """Send media by cached file_id. Returns True if sent."""
    media_type = cached.get("media_type")
    file_id = cached.get("media_file_id")
    if not media_type or not file_id:
        return False
    try:
        if media_type == "photo":
            await bot.send_photo(chat_id=target_chat_id, photo=file_id, caption=caption)
        elif media_type == "video":
            await bot.send_video(chat_id=target_chat_id, video=file_id, caption=caption)
        elif media_type == "voice":
            await bot.send_voice(chat_id=target_chat_id, voice=file_id, caption=caption)
        elif media_type == "video_note":
            # У video_note нет caption
            await bot.send_video_note(chat_id=target_chat_id, video_note=file_id)
            if caption:
                await bot.send_message(chat_id=target_chat_id, text=caption)
        elif media_type == "animation":
            await bot.send_animation(chat_id=target_chat_id, animation=file_id, caption=caption)
        elif media_type == "document":
            await bot.send_document(chat_id=target_chat_id, document=file_id, caption=caption)
        else:
            return False
        return True
    except Exception as e:
        # Для self-destructing медиа Telegram может запретить использование file_id напрямую.
        err_text = str(e)
        if "SelfDestructing" in err_text or "selfdestruct" in err_text.lower():
            logging.info("Trying download+reupload for self-destructing media: type=%s", media_type)
            return await download_and_reupload_media(
                bot,
                target_chat_id=target_chat_id,
                media_type=media_type,
                file_id=file_id,
                caption=caption,
            )
        logging.warning("Failed to send cached media: type=%s error=%r", media_type, e)
        return False


async def download_and_reupload_media(
    bot: Bot,
    *,
    target_chat_id: int,
    media_type: str,
    file_id: str,
    caption: Optional[str],
) -> bool:
    """Download by file_id and reupload as a new file (works for self-destructing media in many cases)."""
    try:
        tg_file = await bot.get_file(file_id)
        buf = io.BytesIO()
        await bot.download_file(tg_file.file_path, destination=buf)
        data = buf.getvalue()
        if not data:
            return False

        # Derive a filename
        ext = "bin"
        if tg_file.file_path and "." in tg_file.file_path:
            ext = tg_file.file_path.rsplit(".", 1)[-1]
        filename = f"media.{ext}"
        upl = BufferedInputFile(file=data, filename=filename)

        if media_type == "photo":
            await bot.send_photo(chat_id=target_chat_id, photo=upl, caption=caption)
        elif media_type == "video":
            await bot.send_video(chat_id=target_chat_id, video=upl, caption=caption)
        elif media_type == "voice":
            await bot.send_voice(chat_id=target_chat_id, voice=upl, caption=caption)
        elif media_type == "video_note":
            await bot.send_video_note(chat_id=target_chat_id, video_note=upl)
            if caption:
                await bot.send_message(chat_id=target_chat_id, text=caption)
        elif media_type == "animation":
            await bot.send_animation(chat_id=target_chat_id, animation=upl, caption=caption)
        elif media_type == "document":
            await bot.send_document(chat_id=target_chat_id, document=upl, caption=caption)
        else:
            logging.warning("download_and_reupload_media: unsupported media_type=%s", media_type)
            return False
        logging.info("download_and_reupload_media succeeded: type=%s file_id=%s", media_type, file_id)
        return True
    except Exception as e:
        logging.warning("download_and_reupload_media failed: type=%s error=%r", media_type, e)
        return False


async def try_copy_to_log_chat(
    bot: Bot,
    *,
    from_chat_id: int,
    message_id: int,
    target_chat_id: int,
    caption: Optional[str] = None,
) -> bool:
    """Copy a message to user's DM with the bot. Returns True if copied."""
    try:
        await bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=caption,
        )
        return True
    except Exception as e:
        logging.warning(
            "Failed to copy message to log chat: from_chat_id=%s message_id=%s target_chat_id=%s error=%r",
            from_chat_id,
            message_id,
            target_chat_id,
            e,
        )
        return False

def get_rofl_inline_kb() -> InlineKeyboardMarkup:
    """Красивые кнопки для выбора типа рофла (в ряд)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎭 Ещё шутка",
                    callback_data="more_rofl",
                ),
                InlineKeyboardButton(
                    text="🖤 Черные шутки",
                    callback_data="dark_rofl",
                ),
            ]
        ]
    )


def get_dark_rofl_inline_kb() -> InlineKeyboardMarkup:
    """Красивые кнопки для черных рофлов (в ряд)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖤 Ещё черную шутку",
                    callback_data="more_dark_rofl",
                ),
                InlineKeyboardButton(
                    text="🎭 Обычные шутки",
                    callback_data="more_rofl",
                ),
            ]
        ]
    )


def to_mock(text: str) -> str:
    """Return Spongebob-ish mocking text."""
    res = []
    upper = True
    for ch in text:
        if ch.isalpha():
            res.append(ch.upper() if upper else ch.lower())
            upper = not upper
        else:
            res.append(ch)
    return "".join(res)


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Поздороваться и узнать, что я умею"),
        BotCommand(command="rofl", description="Случайный рофл/шутейка"),
        BotCommand(command="mock", description="Сделать спонжбоб-насмешку из текста"),
        BotCommand(command="coin", description="Подбросить монетку"),
        BotCommand(command="help", description="Напомню, что я умею"),
        BotCommand(command="instruction", description="Как подключить бота как бизнес-бота"),
        BotCommand(command="commands", description="Описание всех команд"),
    ]
    await bot.set_my_commands(commands)


async def cmd_start(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    
    start_text = (
        "Йоу! Я EternalMod.\n\n"
        "🎯 <b>Что я умею:</b>\n"
        "• /rofl — случайная шуточка\n"
        "• /mock [текст] — передразнить\n"
        "• /coin — орёл или решка\n"
        "• /help — подсказка\n"
        "• /instruction — как подключить как бизнес-бота"
    )
    
    # Красивые инлайн-кнопки для быстрого доступа
    start_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎭 Рофл",
                    callback_data="quick_rofl",
                ),
                InlineKeyboardButton(
                    text="🪙 Монетка",
                    callback_data="quick_coin",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📖 Инструкция",
                    callback_data="quick_instruction",
                ),
                InlineKeyboardButton(
                    text="❓ Помощь",
                    callback_data="quick_help",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Дашборд",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                ),
            ],
        ]
    )
    
    await message.answer(
        start_text,
        reply_markup=start_keyboard,
    )
    
    # Отправляем reply-клавиатуру отдельным сообщением
    # await message.answer(
    #     "👇 Или используй кнопки ниже:",
    #     reply_markup=MAIN_KEYBOARD,
    # )


async def cmd_help(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)

    help_text = (
        "🤖 <b>EternalMod — Центр помощи</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🎭 <b>Пранк-команды</b>\n"
        "• <b>/rofl</b> — случайный рофл\n"
        "• <b>/mock &lt;текст&gt;</b> — передразнить (SpongeBob)\n"
        "• <b>/coin</b> — орёл или решка\n\n"

        "🕵️ <b>Бизнес-функции (PRO)</b>\n"
        "• Просмотр <b>удалённых сообщений</b>\n"
        "• Просмотр <b>изменённых сообщений</b>\n"
        "• Логи действий в чатах\n\n"

        "⚠️ <b>Требования для PRO:</b>\n"
        "• Подписка на канал\n"
        "• Подключение как <b>бизнес-бот</b>\n"
        "• Права на <b>управление сообщениями</b>\n\n"

        "📎 <b>Навигация:</b>\n"
        "Используй кнопки ниже для быстрого доступа 👇"
    )

    help_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Инструкция",
                    callback_data="quick_instruction",
                ),
                InlineKeyboardButton(
                    text="📢 Канал",
                    url=REQUIRED_CHANNEL_URL,
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎭 Рофл",
                    callback_data="quick_rofl",
                ),
                InlineKeyboardButton(
                    text="🪙 Монетка",
                    callback_data="quick_coin",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Дашборд",
                    web_app=WebAppInfo(url=WEBAPP_URL),
                ),
            ],
        ]
    )

    await message.answer(
        help_text,
        reply_markup=help_keyboard,
    )

async def cmd_about(message: types.Message) -> None:
    about_text = (
        "🤖 <b>EternalMod</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"

        "🎯 <b>Назначение:</b>\n"
        "EternalMod — это пранк и бизнес-бот,\n"
        "который помогает:\n"
        "• Развлекаться\n"
        "• Контролировать переписку\n"
        "• Видеть то, что пытаются скрыть\n\n"

        "🧩 <b>Основные возможности:</b>\n"
        "• Пранк-команды\n"
        "• Эхо-ответы с подколом\n"
        "• Просмотр удалённых сообщений\n"
        "• Просмотр изменённых сообщений\n\n"

        "🔐 <b>Ограничения:</b>\n"
        "Некоторые функции доступны только при:\n"
        "• Подписке на канал\n"
        "• Подключении как бизнес-бот\n"
        "• Выдаче прав на управление сообщениями\n\n"

        "🛡 <b>Важно:</b>\n"
        "Бот работает только в рамках\n"
        "разрешений Telegram.\n"
        "Никакого взлома или скрытого доступа.\n\n"

        "😎 <b>EternalMod</b> — юмор + контроль."
    )

    about_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📖 Инструкция",
                    callback_data="quick_instruction",
                ),
                InlineKeyboardButton(
                    text="❓ Помощь",
                    callback_data="quick_help",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📢 Канал",
                    url=REQUIRED_CHANNEL_URL,
                ),
            ],
        ]
    )

    await message.answer(
        about_text,
        reply_markup=about_keyboard,
    )



async def cmd_rofl(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    await message.answer(
        random.choice(ROFL_LINES),
        reply_markup=get_rofl_inline_kb(),
    )


async def cmd_dark_rofl(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    await message.answer(
        random.choice(DARK_ROFL_LINES),
        reply_markup=get_dark_rofl_inline_kb(),
    )


async def cmd_mock(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Дай текст после /mock, чтобы я смог его передразнить.")
        return
    await message.answer(to_mock(parts[1]), reply_markup=MAIN_KEYBOARD)


async def cmd_coin(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    side = random.choice(["Орёл", "Решка"])
    await message.answer(f"Подбрасываю монетку... {side}!", reply_markup=MAIN_KEYBOARD)


async def cmd_commands_description(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    
    commands_text = (
        "📋 <b>Описание команд</b>\n\n"
        "Выбери команду, чтобы узнать подробнее:\n\n"
        "🎭 <b>/rofl</b> — случайная шутейка\n"
        "🧽 <b>/mock [текст]</b> — превратить текст в спонжбоб-насмешку\n"
        "🪙 <b>/coin</b> — подбросить монетку (орёл или решка)\n"
        "📖 <b>/instruction</b> — инструкция по подключению как бизнес-бота\n"
        "❓ <b>/help</b> — справка по командам\n"
        "🚀 <b>/start</b> — начать работу с ботом"
    )
    
    # Интерактивные кнопки для каждой команды
    commands_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎭 /rofl",
                    callback_data="cmd_desc_rofl",
                ),
                InlineKeyboardButton(
                    text="🧽 /mock",
                    callback_data="cmd_desc_mock",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🪙 /coin",
                    callback_data="cmd_desc_coin",
                ),
                InlineKeyboardButton(
                    text="📖 /instruction",
                    callback_data="cmd_desc_instruction",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❓ /help",
                    callback_data="cmd_desc_help",
                ),
                InlineKeyboardButton(
                    text="🚀 /start",
                    callback_data="cmd_desc_start",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎛 Пранк-меню (.команды)",
                    callback_data="open_prank_menu",
                )
            ],
        ]
    )
    
    await message.answer(
        commands_text,
        reply_markup=commands_keyboard,
    )


async def cmd_instruction(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    remember_message(message)
    
    # Получаем информацию о боте
    try:
        bot_info = await message.bot.get_me()
        bot_username = bot_info.username or "этого бота"
        bot_mention = f"@{bot_username}" if bot_username != "этого бота" else "этого бота"
    except Exception:
        bot_username = "этого бота"
        bot_mention = "этого бота"
    
    instruction_text = (
        "📖 <b>Инструкция по подключению бота как бизнес-бота</b>\n\n"
        "Чтобы бот мог видеть изменённые и удалённые сообщения в твоих бизнес-чатах, "
        "нужно подключить его как бизнес-бота.\n\n"
        "🔹 <b>Шаг 1:</b> Открой настройки Telegram\n"
        "   • Нажми на три полоски (☰) в левом верхнем углу\n"
        "   • Выбери «Настройки» → «Telegram Business»\n\n"
        "🔹 <b>Шаг 2:</b> Подключи бота\n"
        "   • Нажми «Подключить бота» или «Chatbots»\n"
        f"   • Выбери {bot_mention} из списка\n"
        f"   • Или введи @{bot_username}\n\n"
        "🔹 <b>Шаг 3:</b> Выдай все разрешения\n"
        "   • Включи <b>все</b> разрешения на управление сообщениями:\n"
        "     ✓ Read messages\n"
        "     ✓ Reply to messages\n"
        "     ✓ Mark messages as read\n"
        "     ✓ Delete sent messages\n"
        "     ✓ Delete received messages\n\n"
        "🔹 <b>Шаг 4:</b> Готово!\n"
        "   • Бот получит уведомление о подключении\n"
        "   • Теперь он будет видеть все изменения и удаления\n"
        "   • Уведомления будут приходить тебе в личку с ботом\n\n"
        "💡 <i>После перезапуска бота нужно переподключить его заново.</i>"
    )
    
    # Красивые инлайн-кнопки под инструкцией
    instruction_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📱 Открыть настройки Telegram Business",
                    url="tg://settings/business",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить инструкцию",
                    callback_data="refresh_instruction",
                ),
                InlineKeyboardButton(
                    text="❓ Помощь",
                    callback_data="help_instruction",
                ),
            ],
        ]
    )
    
    await message.answer(
        instruction_text,
        reply_markup=instruction_keyboard,
    )


async def handle_echo(message: types.Message) -> None:
    if not await require_subscription_message(message):
        return
    text = message.text or ""
    remember_message(message)

    # Safe dot-commands like ".type hello"
    if text.strip().startswith("."):
        handled = await handle_dot_command(message)
        if handled:
            return

    if text == "🎭 Рофл":
        await cmd_rofl(message)
        return
    if text == "🖤 Черные рофлы":
        await cmd_dark_rofl(message)
        return
    if text == "🧽 Mock текст":
        await message.answer(
            "Напиши: /mock твой текст — и я сделаю из него спонжбоб-насмешку 😉",
            reply_markup=MAIN_KEYBOARD,
        )
        return
    if text == "🪙 Подбросить монетку":
        await cmd_coin(message)
        return
    if text == "📖 Инструкция":
        await cmd_instruction(message)
        return
    if text == "📋 Описание команд":
        await cmd_commands_description(message)
        return

    await message.answer(
        (kawaiify(f"Эхо, но с подколом: {text}\n/rofl — если надо поугарать")
         if is_kawaii(message.from_user.id if message.from_user else None)
         else f"Эхо, но с подколом: {text}\n/rofl — если надо поугарать"),
        reply_markup=MAIN_KEYBOARD,
    )


async def on_edited_message(message: types.Message) -> None:
    # ← Добавляем проверку нового бота здесь
    await warn_about_new_bot_and_offer_report(message)

    key = (message.chat.id, message.message_id)
    old = MESSAGE_LOG.get(key)
    new_text = message.text or message.caption or "<без текста>"
    remember_message(message)

    # Определяем business_connection_id из сообщения или из сохранённых данных
    bc_id = getattr(message, "business_connection_id", None)
    if not bc_id and old:
        bc_id = old.get("business_connection_id")
    # Иногда в edited update bc_id может отсутствовать, но если это бизнес-чат, мы всё равно
    # должны слать уведомление владельцу подключения. Если не нашли — просто пропускаем.

    logging.info(
        f"Edited message: chat_id={message.chat.id}, msg_id={message.message_id}, "
        f"bc_id={bc_id}, old_exists={old is not None}, "
        f"bc_in_logs={bc_id in BUSINESS_LOG_CHATS if bc_id else False}, "
        f"all_bc_ids={list(BUSINESS_LOG_CHATS.keys())}"
    )

    # Если это бизнес-сообщение, отправляем уведомление
    if bc_id:
        # Пытаемся найти чат для этого бизнес-подключения
        target_chat = get_log_chat_id(bc_id)
        
        if not target_chat:
            # Если соединение не найдено, пропускаем уведомление
            # (бот был перезапущен после подключения или соединение не было сохранено)
            logging.warning(
                f"Business connection {bc_id} not found in logs, skipping notification. "
                f"Нужно переподключить бота как бизнес-бота."
            )
            return
        
        # Проверяем подписку владельца бизнес-подключения
        owner_id = get_owner_id(bc_id)
        if owner_id and not await is_subscribed(message.bot, owner_id):
            logging.info(f"Owner {owner_id} of business connection {bc_id} is not subscribed, skipping notification")
            await send_subscription_required_notification(message.bot, target_chat, owner_id)
            return
        
        logging.info(f"Sending edit notification to chat_id={target_chat}")

        if not old:
            stars_text = (
                "\n\n"
                f"<a href=\"https://t.me/SaveModStarsBot\">Telegram Stars со скидкой</a> 🌟"
            )
            await message.bot.send_message(
                chat_id=target_chat,
                text=(
                    f"{escape('Сообщение изменено, но старой версии нет в кэше.')}\n"
                    f"Новое: <blockquote>{escape(new_text)}</blockquote>"
                    f"{stars_text}"
                ),
            )
            return

        # Используем сохранённую ссылку на автора из old['user'], а не создаём новую
        author_mention = old.get('user', user_mention(message.from_user))
        
        stars_text = (
            "\n\n"
            f"<a href=\"https://t.me/SaveModStarsBot\">Telegram Stars со скидкой</a> 🌟"
        )
        
        # Форматируем изменения для строчки "Изменилось:"
        changed_text = format_text_diff(old['content'], new_text)
        
        await message.bot.send_message(
            chat_id=target_chat,
            text=(
                f"🔏 {author_mention} {escape('изменил сообщение.')}\n\n"
                f"<b>Старый текст:</b> <blockquote>{escape(old['content'])}</blockquote>\n"
                f"<b>Новый текст:</b> <blockquote>{escape(new_text)}</blockquote>\n"
                f"Изменилось:\n<blockquote>{changed_text}</blockquote>"
                f"{stars_text}"
            ),
        )
        
        # Сохраняем событие в историю
        if owner_id:
            # Извлекаем имя автора из HTML ссылки
            author_name = old.get('user', 'Неизвестно')
            if '<a href' in author_name:
                # Парсим имя из HTML
                match = re.search(r'>([^<]+)<', author_name)
                author_name = match.group(1) if match else 'Неизвестно'
            save_event(owner_id, 'edited', author_name, new_text, old['content'])
    else:
        # Это не бизнес-сообщение - не отправляем уведомление
        logging.debug(f"Not a business message, skipping notification")


async def on_deleted_business_messages(
    event: BusinessMessagesDeleted,
    bot: Bot,
) -> None:
    chat = event.chat
    deleted_ids = event.message_ids
    
    # Получаем business_connection_id из события
    bc_id = getattr(event, "business_connection_id", None)

    # Фолбэк: иногда bc_id может не прийти в update — попробуем восстановить по кэшу сообщений
    if not bc_id:
        for mid in deleted_ids:
            cached = MESSAGE_LOG.get((chat.id, mid))
            if cached and cached.get("business_connection_id"):
                bc_id = cached.get("business_connection_id")
                break
    
    logging.info(
        f"Deleted business messages: chat_id={chat.id}, msg_ids={deleted_ids}, "
        f"bc_id={bc_id}, bc_in_logs={bc_id in BUSINESS_LOG_CHATS if bc_id else False}, "
        f"all_bc_ids={list(BUSINESS_LOG_CHATS.keys())}"
    )
    
    # Если это бизнес-сообщение, отправляем уведомление
    if bc_id:
        # Пытаемся найти чат для этого бизнес-подключения
        target_chat = get_log_chat_id(bc_id)
        
        if not target_chat:
            # Если соединение не найдено, пропускаем уведомление
            # (бот был перезапущен после подключения или соединение не было сохранено)
            logging.warning(
                f"Business connection {bc_id} not found in logs, skipping notification. "
                f"Нужно переподключить бота как бизнес-бота."
            )
            return
        
        # Проверяем подписку владельца бизнес-подключения
        owner_id = get_owner_id(bc_id)
        if owner_id and not await is_subscribed(bot, owner_id):
            logging.info(f"Owner {owner_id} of business connection {bc_id} is not subscribed, skipping notification")
            await send_subscription_required_notification(bot, target_chat, owner_id)
            return
        
        logging.info(f"Sending deleted messages notification to chat_id={target_chat}")
        lines = []
        for mid in deleted_ids:
            key = (chat.id, mid)
            cached = MESSAGE_LOG.get(key)
            if cached:
                # Используем сохранённую ссылку на автора из cached['user']
                author_mention = cached.get('user', 'кто-то')
                lines.append(
                    f"🗑️ {escape('Это сообщение было удалено')}\n\n"
                    f"<blockquote>{author_mention}\n{escape(cached['content'])}</blockquote>"
                )
                
                # Сохраняем событие в историю
                if owner_id:
                    # Извлекаем имя автора из HTML ссылки
                    author_name = cached.get('user', 'Неизвестно')
                    if '<a href' in author_name:
                        match = re.search(r'>([^<]+)<', author_name)
                        author_name = match.group(1) if match else 'Неизвестно'
                    save_event(owner_id, 'deleted', author_name, cached['content'])
            else:
                # Сообщение не было сохранено (удалено слишком быстро или не было обработано)
                logging.debug(f"Deleted message {mid} in chat {chat.id} was not cached - likely deleted before bot processed it")
                # Не показываем уведомление о несохранённых сообщениях, чтобы не шуметь

        if lines:
            stars_text = (
                "\n\n"
                f"<a href=\"https://t.me/SaveModStarsBot\">Telegram Stars со скидкой</a> 🌟"
            )
            report = "\n\n".join(lines) + stars_text
            await bot.send_message(target_chat, report)
        else:
            # Все удалённые сообщения были без кэша - не отправляем пустое уведомление
            logging.debug(f"All {len(deleted_ids)} deleted messages were not cached, skipping notification")
    else:
        # Без bc_id мы не можем понять, в чью личку слать уведомление.
        logging.warning(
            "No business_connection_id in deleted messages event and could not restore from cache; "
            "skipping notification"
        )


async def on_business_message(message: types.Message) -> None:
    # Логируем бизнес-сообщение, но не отвечаем, чтобы не шуметь.
    bc_id = getattr(message, "business_connection_id", None)
    logging.info(
        f"Business message received: chat_id={message.chat.id}, msg_id={message.message_id}, "
        f"bc_id={bc_id}, bc_in_logs={bc_id in BUSINESS_LOG_CHATS if bc_id else False}"
    )

    await warn_about_new_bot_and_offer_report(message)
    remember_message(message)
    
    # Обрабатываем dot-команды в бизнес-чатах (для владельца бизнес-подключения) во всех чатах
    text = (message.text or "").strip()
    if text.startswith("."):
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        owner_id = get_owner_id(bc_id)
        sender_id = message.from_user.id if message.from_user else None
        if owner_id and sender_id != owner_id:
            # Команды разрешаем только владельцу business-аккаунта
            return
        if not owner_id:
            # Если старый формат без owner_id — разрешаем (но лучше переподключить)
            logging.info("Business dot-command: owner_id is unknown (old connection schema); allowing.")
        
        # Обработка .switch в бизнес-чатах
        if cmd == ".switch":
            # Если есть аргумент, используем его
            if arg:
                result = switch_layout(arg)
                await message.answer(result)
                return
            
            # Если нет аргумента, проверяем reply_to_message
            if message.reply_to_message:
                replied_text = message.reply_to_message.text or message.reply_to_message.caption
                if replied_text:
                    result = switch_layout(replied_text)
                    await message.answer(result)
                    return
                else:
                    # Пробуем получить из кэша
                    reply_key = (message.reply_to_message.chat.id, message.reply_to_message.message_id)
                    cached = MESSAGE_LOG.get(reply_key)
                    if cached and cached.get("content"):
                        result = switch_layout(cached["content"])
                        await message.answer(result)
                        return
                    else:
                        await message.answer("❌ В сообщении, на которое ты ответил, нет текста.")
                        return
            
            # Нет ни аргумента, ни reply
            await message.answer(
                "Команда: <b>.switch</b>\n\n"
                "Использование:\n"
                "• <code>.switch ghbdtn</code> — перевести текст\n"
                "• Ответь на сообщение с неправильной раскладкой и напиши <code>.switch</code>"
            )
            return

        if cmd in (".команды", ".commands"):
            await cmd_prank_menu_nogate(message)
            return

        # Остальные безопасные dot-команды в бизнес-чатах
        # (не используем подписку, иначе в разных чатах будет ломаться)
        if cmd == ".type":
            if not arg:
                await message.answer("Команда: <b>.type</b>\nПример: <code>.type привет</code>")
                return
            try:
                await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
            except Exception:
                pass
            await asyncio.sleep(min(2.0, 0.02 * len(arg) + 0.2))
            out = arg
            if is_kawaii(sender_id):
                out = kawaiify(out)
            await message.answer(out)
            return

        if cmd == ".kawaii":
            if sender_id:
                KAWAII_MODE[sender_id] = not KAWAII_MODE.get(sender_id, False)
                state = "включён" if KAWAII_MODE[sender_id] else "выключен"
                await message.answer(f"🐾 Kawaii-режим <b>{state}</b>.")
            return

        if cmd == ".love":
            await message.answer(random.choice(["💘 *пик* — любовь доставлена!", "❤️ Романтика активирована.", "💞 Сердечки полетели!"]))
            return

        if cmd == ".iq":
            iq = random.randint(40, 200)
            await message.answer(f"🧠 Твой IQ сегодня: <b>{iq}</b>")
            return

        if cmd == ".zaebu":
            await message.answer("Заебушка ✨")
            return

        if cmd == ".info":
            u = message.from_user
            if u:
                await message.answer(
                    "ℹ️ <b>Инфо</b>\n"
                    f"• id: <code>{u.id}</code>\n"
                    f"• username: <code>{escape(u.username or '-')}</code>"
                )
            return

        if cmd == ".тест":
            if not message.from_user:
                return
            user_id = message.from_user.id
            target_chat_id = get_log_chat_id(bc_id)
            if not target_chat_id:
                return
            
            # Проверяем подписку
            is_sub = await is_subscribed(message.bot, user_id)
            
            if is_sub:
                await message.answer(
                    "✅ Ты подписан на канал.\n\n"
                    "Чтобы протестировать уведомление:\n"
                    "1. Отпишись от канала @qqgram_news\n"
                    "2. Подожди 10 секунд (cooldown)\n"
                    "3. Измени или удали сообщение в бизнес-чате\n"
                    "4. Или используй команду .тест снова"
                )
            else:
                # Вызываем функцию уведомления напрямую (для теста)
                # Сбрасываем cooldown для теста
                LAST_SUBSCRIPTION_NOTIFICATION[user_id] = 0
                await send_subscription_required_notification(message.bot, target_chat_id, user_id)
                await message.answer(
                    "📤 Отправлено тестовое уведомление о необходимости подписки.\n\n"
                    "Если уведомление не пришло, возможно не прошло 10 секунд с последнего уведомления."
                )
            return

        await message.answer("Эта команда недоступна 🙂\nПопробуй <code>.команды</code> для списка.")
        return

    # Если это ответ на медиа (в т.ч. исчезающее фото/видео/voice), сохраняем медиа в чат с ботом
    if bc_id and bc_id in BUSINESS_LOG_CHATS and is_media_message(message.reply_to_message):
        target_chat_id = get_log_chat_id(bc_id)
        if not target_chat_id:
            return
        
        # Проверяем подписку владельца бизнес-подключения
        owner_id = get_owner_id(bc_id)
        if owner_id and not await is_subscribed(message.bot, owner_id):
            logging.info(f"Owner {owner_id} of business connection {bc_id} is not subscribed, skipping media save")
            await send_subscription_required_notification(message.bot, target_chat_id, owner_id)
            return
        replied = message.reply_to_message
        # reply_to_message может не содержать business_connection_id — запомним вручную
        r_media_type = None
        r_media_file_id = None
        if replied.photo:
            r_media_type = "photo"
            r_media_file_id = replied.photo[-1].file_id
        elif replied.video:
            r_media_type = "video"
            r_media_file_id = replied.video.file_id
        elif replied.voice:
            r_media_type = "voice"
            r_media_file_id = replied.voice.file_id
        elif replied.video_note:
            r_media_type = "video_note"
            r_media_file_id = replied.video_note.file_id
        elif replied.animation:
            r_media_type = "animation"
            r_media_file_id = replied.animation.file_id
        elif replied.document:
            r_media_type = "document"
            r_media_file_id = replied.document.file_id
        remember_foreign_message(
            chat_id=message.chat.id,
            message_id=replied.message_id,
            from_user=replied.from_user,
            text=replied.text,
            caption=replied.caption,
            bc_id=bc_id,
            media_type=r_media_type,
            media_file_id=r_media_file_id,
        )
        stars_text = (
            "\n\n"
            f"<a href=\"https://t.me/SaveModStarsBot\">Telegram Stars со скидкой</a> 🌟"
        )
        note = (
            f"🧷 {escape('Сохранено медиа из ответа (возможное исчезающее).')}\n"
            f"{escape('Автор:')} {user_mention(replied.from_user)}"
            f"{stars_text}"
        )
        ok = await try_copy_to_log_chat(
            message.bot,
            from_chat_id=message.chat.id,
            message_id=replied.message_id,
            target_chat_id=target_chat_id,
            caption=note,
        )
        if not ok:
            # Фолбэк: если копирование недоступно, пробуем отправить по сохранённому file_id
            cached = MESSAGE_LOG.get((message.chat.id, replied.message_id))
            if cached and cached.get("media_file_id"):
                await send_cached_media(
                    message.bot,
                    target_chat_id=target_chat_id,
                    cached=cached,
                    caption=note,
                )
            else:
                stars_text = (
                    "\n\n"
                    f"<a href=\"https://t.me/SaveModStarsBot\">Telegram Stars со скидкой</a> 🌟"
                )
                await message.bot.send_message(
                    chat_id=target_chat_id,
                    text=(
                        "⚠️ Не смог сохранить медиа из ответа (сообщение недоступно).\n"
                        "Если хочешь, отправь это медиа ещё раз без исчезания."
                        f"{stars_text}"
                    ),
                )


async def on_business_connection(
    connection: BusinessConnection,
    bot: Bot,
) -> None:
    status_text = "подключили" if connection.is_enabled else "отключили"
    can_reply = connection.can_reply
    chat_id = connection.user_chat_id

    logging.info(
        "Business connection update: id=%s user=%s status=%s can_reply=%s chat_id=%s",
        connection.id,
        connection.user.id if connection.user else None,
        status_text,
        can_reply,
        chat_id,
    )

    owner_id = connection.user.id if connection.user else 0

    if connection.is_enabled and chat_id:
        # Запоминаем, куда слать логи по этому бизнес-подключению + кто владелец
        BUSINESS_LOG_CHATS[connection.id] = {"chat_id": chat_id, "owner_id": owner_id}
        save_business_connections()
        logging.info(f"Added business connection: id={connection.id}, chat_id={chat_id}, total_connections={len(BUSINESS_LOG_CHATS)}")
    elif not connection.is_enabled:
        # Удаляем из списка при отключении, чтобы не отправлять уведомления
        BUSINESS_LOG_CHATS.pop(connection.id, None)
        save_business_connections()
        logging.info(f"Removed business connection: id={connection.id}, remaining_connections={len(BUSINESS_LOG_CHATS)}")

    if not chat_id:
        return

    if connection.is_enabled and not can_reply:
        # Путь к изображению с инструкцией по разрешениям
        img_dir = Path(__file__).parent / "img"
        # Пробуем разные варианты имени файла
        permissions_image_path = None
        for filename in ["permission.jpg", "permissions.png", "permission.png", "permissions.jpg"]:
            path = img_dir / filename
            if path.exists():
                permissions_image_path = path
                break
        
        text = "⚙️ Вы не выдали боту необходимый набор разрешений, поэтому он не может отвечать на команды"
        
        # Если изображение существует, отправляем с фото, иначе только текст
        if permissions_image_path:
            try:
                photo = FSInputFile(permissions_image_path)
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo,
                    caption=text,
                    reply_markup=MAIN_KEYBOARD,
                )
            except Exception as e:
                logging.warning(f"Failed to send permissions image: {e}")
                # Fallback: отправляем только текст
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=MAIN_KEYBOARD,
                )
        else:
            # Если изображения нет, отправляем только текст
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=MAIN_KEYBOARD,
            )
        return

    if connection.is_enabled and can_reply:
        # Создаем клавиатуру с кнопкой "Команды и функционал"
        welcome_keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❓ Команды и функционал",
                        callback_data="open_prank_menu",
                    ),
                ],
            ]
        )
        
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "👍🏻 Вы подключили официальное зеркало <b>EternalMod</b>\n\n"
                "ℹ️ <b>Что вы получаете:</b>\n\n"
                "⚠️ <b>Надёжная защита от мошенников.</b> Если вам отправят вредоносного бота — мы сразу вас предупредим. "
                "Защита работает в реальном времени и блокирует популярные схемы, включая кражу подарков.\n\n"
                "💨 <b>Мгновенные уведомления.</b> Кто-то удалил или отредактировал сообщение? Вы узнаете сразу — "
                "уведомление придет прямо в личку.\n\n"
                "🔍 <b>Эксклюзивные функции.</b> Уникальные инструменты и возможности. Мы не просто сохраняем сообщения — "
                "мы уровень выше."
            ),
            reply_markup=welcome_keyboard,
        )
        return

    # is_enabled == False
    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🚫 EternalMod был отключён.\n\n"
            "Если вы это сделали для подключения другого бота по просьбе малознакомого пользователя "
            "для проведения сделки/получения подарка или под другим предлогом — советуем вам написать админу "
            "в ЛС @un1quexd и описать происходящую ситуацию.\n\n"
            "Возможно вас хотят побрить и не лезь блять дебил сука ебаный - она тебя сожрёт."
        ),
        reply_markup=MAIN_KEYBOARD,
    )
async def on_callback_rofl(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    try:
        await callback.message.edit_text(
            random.choice(ROFL_LINES),
            reply_markup=get_rofl_inline_kb(),
        )
    except Exception as e:
        # Если редактирование не удалось (например, сообщение слишком старое), отправляем новое
        logging.warning(f"Failed to edit message, sending new one: {e}")
        await callback.message.answer(
            random.choice(ROFL_LINES),
            reply_markup=get_rofl_inline_kb(),
        )
    await callback.answer()


async def on_callback_dark_rofl(callback: types.CallbackQuery) -> None:
    """Черные рофлы из кнопки."""
    if not await require_subscription_callback(callback):
        return
    try:
        await callback.message.edit_text(
            random.choice(DARK_ROFL_LINES),
            reply_markup=get_dark_rofl_inline_kb(),
        )
    except Exception as e:
        # Если редактирование не удалось, отправляем новое
        logging.warning(f"Failed to edit message, sending new one: {e}")
        await callback.message.answer(
            random.choice(DARK_ROFL_LINES),
            reply_markup=get_dark_rofl_inline_kb(),
        )
    await callback.answer()


async def on_callback_more_dark_rofl(callback: types.CallbackQuery) -> None:
    """Ещё черный рофл из кнопки."""
    if not await require_subscription_callback(callback):
        return
    try:
        await callback.message.edit_text(
            random.choice(DARK_ROFL_LINES),
            reply_markup=get_dark_rofl_inline_kb(),
        )
    except Exception as e:
        # Если редактирование не удалось, отправляем новое
        logging.warning(f"Failed to edit message, sending new one: {e}")
        await callback.message.answer(
            random.choice(DARK_ROFL_LINES),
            reply_markup=get_dark_rofl_inline_kb(),
        )
    await callback.answer()


async def on_callback_refresh_instruction(callback: types.CallbackQuery) -> None:
    """Обновить инструкцию."""
    if not await require_subscription_callback(callback):
        return
    await cmd_instruction(callback.message)
    await callback.answer("Инструкция обновлена ✨")


async def on_callback_help_instruction(callback: types.CallbackQuery) -> None:
    """Помощь по инструкции."""
    if not await require_subscription_callback(callback):
        return
    help_text = (
        "❓ <b>Помощь по подключению</b>\n\n"
        "Если у тебя возникли проблемы:\n\n"
        "🔸 <b>Не вижу «Telegram Business» в настройках?</b>\n"
        "   • Убедись, что у тебя включён бизнес-профиль\n"
        "   • Бизнес-профиль доступен не во всех странах\n\n"
        "🔸 <b>Бот не видит изменения/удаления?</b>\n"
        "   • Проверь, что выданы <b>все</b> разрешения\n"
        "   • Переподключи бота после выдачи прав\n"
        "   • После перезапуска бота нужно переподключить\n\n"
        "🔸 <b>Уведомления не приходят?</b>\n"
        "   • Уведомления приходят в личку с ботом\n"
        "   • Убедись, что бот подключён с полными правами\n"
    )
    await callback.message.answer(help_text)
    await callback.answer()


async def on_callback_quick_rofl(callback: types.CallbackQuery) -> None:
    """Быстрый рофл из кнопки."""
    if not await require_subscription_callback(callback):
        return
    await callback.message.answer(
        random.choice(ROFL_LINES),
        reply_markup=get_rofl_inline_kb(),
    )
    await callback.answer("Рофл отправлен! 🎭")


async def on_callback_quick_coin(callback: types.CallbackQuery) -> None:
    """Быстрая монетка из кнопки."""
    if not await require_subscription_callback(callback):
        return
    side = random.choice(["Орёл", "Решка"])
    await callback.message.answer(f"Подбрасываю монетку... {side}! 🪙")
    await callback.answer()


async def on_callback_quick_instruction(callback: types.CallbackQuery) -> None:
    """Быстрая инструкция из кнопки."""
    if not await require_subscription_callback(callback):
        return
    await cmd_instruction(callback.message)
    await callback.answer()


async def on_callback_quick_help(callback: types.CallbackQuery) -> None:
    """Быстрая помощь из кнопки."""
    if not await require_subscription_callback(callback):
        return
    await cmd_help(callback.message)
    await callback.answer()


async def on_callback_cmd_desc_rofl(callback: types.CallbackQuery) -> None:
    """Описание команды /rofl."""
    if not await require_subscription_callback(callback):
        return
    desc_text = (
        "🎭 <b>Команда: /rofl</b>\n\n"
        "<blockquote>Случайная шутейка или рофл. "
        "Бот пришлёт тебе случайную шутку из своей коллекции.</blockquote>"
    )
    await callback.message.answer(desc_text)
    await callback.answer()


async def on_callback_cmd_desc_mock(callback: types.CallbackQuery) -> None:
    """Описание команды /mock."""
    if not await require_subscription_callback(callback):
        return
    desc_text = (
        "🧽 <b>Команда: /mock [текст]</b>\n\n"
        "<blockquote>Превратить текст в спонжбоб-насмешку. "
        "Напиши /mock и свой текст — бот сделает из него смешную чередующуюся раскладку "
        "типа \"ТаКоВоГо ВиДа\".</blockquote>"
    )
    await callback.message.answer(desc_text)
    await callback.answer()


async def on_callback_cmd_desc_coin(callback: types.CallbackQuery) -> None:
    """Описание команды /coin."""
    if not await require_subscription_callback(callback):
        return
    desc_text = (
        "🪙 <b>Команда: /coin</b>\n\n"
        "<blockquote>Подбросить монетку. "
        "Бот случайно выберет \"Орёл\" или \"Решка\" и пришлёт результат.</blockquote>"
    )
    await callback.message.answer(desc_text)
    await callback.answer()


async def on_callback_cmd_desc_instruction(callback: types.CallbackQuery) -> None:
    """Описание команды /instruction."""
    if not await require_subscription_callback(callback):
        return
    desc_text = (
        "📖 <b>Команда: /instruction</b>\n\n"
        "<blockquote>Инструкция по подключению бота как бизнес-бота. "
        "Покажет пошаговую инструкцию, как подключить бота в Telegram Business "
        "и выдать ему права на управление сообщениями.</blockquote>"
    )
    await callback.message.answer(desc_text)
    await callback.answer()


async def on_callback_cmd_desc_help(callback: types.CallbackQuery) -> None:
    """Описание команды /help."""
    if not await require_subscription_callback(callback):
        return
    desc_text = (
        "❓ <b>Команда: /help</b>\n\n"
        "<blockquote>Получить справку по командам. "
        "Бот напомнит, какие команды доступны и что они делают.</blockquote>"
    )
    await callback.message.answer(desc_text)
    await callback.answer()


async def on_callback_cmd_desc_start(callback: types.CallbackQuery) -> None:
    """Описание команды /start."""
    if not await require_subscription_callback(callback):
        return
    desc_text = (
        "🚀 <b>Команда: /start</b>\n\n"
        "<blockquote>Начать работу с ботом. "
        "Покажет приветственное сообщение и список доступных команд. "
        "Также можно использовать для перезапуска бота.</blockquote>"
    )
    await callback.message.answer(desc_text)
    await callback.answer()


async def on_callback_open_prank_menu(callback: types.CallbackQuery) -> None:
    """Open safe prank menu (.commands)."""
    message = callback.message
    if not message:
        await callback.answer()
        return
    
    # Проверяем, есть ли у пользователя активное бизнес-подключение
    user_id = callback.from_user.id if callback.from_user else None
    has_business_connection = False
    if user_id:
        # Проверяем, есть ли у пользователя активное бизнес-подключение
        for bc_data in BUSINESS_LOG_CHATS.values():
            if bc_data.get("owner_id") == user_id:
                has_business_connection = True
                break
    
    if has_business_connection:
        # Если у пользователя есть бизнес-подключение, не требуем подписку
        await cmd_prank_menu_nogate(message)
    else:
        # В обычных чатах проверяем подписку
        if not await require_subscription_callback(callback):
            return
        await cmd_prank_menu(message)
    
    await callback.answer()


async def on_callback_prank_type(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    await callback.message.answer("Команда: <b>.type</b>\nПример: <code>.type привет</code>")
    await callback.answer()


async def on_callback_prank_switch(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    await callback.message.answer(
        "Команда: <b>.switch</b>\n\n"
        "Использование:\n"
        "• <code>.switch ghbdtn</code> — перевести текст\n"
        "• Ответь на сообщение с неправильной раскладкой и напиши <code>.switch</code>"
    )
    await callback.answer()


async def on_callback_prank_kawaii(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    uid = callback.from_user.id if callback.from_user else None
    if uid:
        KAWAII_MODE[uid] = not KAWAII_MODE.get(uid, False)
        state = "включён" if KAWAII_MODE[uid] else "выключен"
        await callback.message.answer(f"🐾 Kawaii-режим <b>{state}</b>.", reply_markup=MAIN_KEYBOARD)
    await callback.answer()


async def on_callback_prank_love(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    await callback.message.answer(random.choice(["💘 *пик* — любовь доставлена!", "❤️ Романтика активирована.", "💞 Сердечки полетели!"]), reply_markup=MAIN_KEYBOARD)
    await callback.answer()


async def on_callback_prank_iq(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    iq = random.randint(40, 200)
    await callback.message.answer(f"🧠 Твой IQ сегодня: <b>{iq}</b>", reply_markup=MAIN_KEYBOARD)
    await callback.answer()


async def on_callback_prank_info(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    u = callback.from_user
    if u:
        await callback.message.answer(
            "ℹ️ <b>Инфо</b>\n"
            f"• id: <code>{u.id}</code>\n"
            f"• username: <code>{escape(u.username or '-')}</code>",
            reply_markup=MAIN_KEYBOARD,
        )
    await callback.answer()


async def on_callback_prank_zaebu(callback: types.CallbackQuery) -> None:
    if not await require_subscription_callback(callback):
        return
    await callback.message.answer("Заебушка ✨", reply_markup=MAIN_KEYBOARD)
    await callback.answer()


async def on_callback_check_sub(callback: types.CallbackQuery) -> None:
    if not callback.from_user:
        return
    ok = await is_subscribed(callback.bot, callback.from_user.id)
    if ok:
        await callback.message.answer("✅ Подписка найдена! Доступ открыт.", reply_markup=MAIN_KEYBOARD)
    else:
        await callback.message.answer("❌ Подписка не найдена. Подпишись и попробуй снова.", reply_markup=SUBSCRIBE_KB)
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("report_new_bot_"))
async def on_report_new_bot(callback: types.CallbackQuery):
    """Когда юзер жмёт "Отправить на проверку" — тебе приходит сообщение с кнопками"""
    parts = callback.data.split("_")
    if len(parts) < 4:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    bot_key = parts[3]          # bot_royaltrust_robot или mention_...
    chat_id = int(parts[4])     # чат владельца

    # Достаём читаемое имя из ключа
    bot_display = bot_key.replace("bot_", "@").replace("mention_", "@")

    admin_text = (
        f"📩 Новая проверка бота от пользователя {chat_id}\n\n"
        f"Бот: {bot_display}\n"
        f"Ключ в БД: {bot_key}\n"
        f"Чат владельца: {chat_id}\n"
        f"Время: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"Что делать?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_bot_{bot_key}_{chat_id}"),
            InlineKeyboardButton("🚫 Скам",     callback_data=f"mark_scam_{bot_key}_{chat_id}"),
        ],
        [
            InlineKeyboardButton("❌ Игнорировать", callback_data=f"ignore_bot_{bot_key}_{chat_id}"),
        ]
    ])

    try:
        await callback.bot.send_message(
            chat_id=OWNER_ID,
            text=admin_text,
            reply_markup=kb,
            disable_web_page_preview=True
        )
        await callback.answer("Бот отправлен на проверку владельцу!")
    except Exception as e:
        await callback.answer(f"Ошибка: {str(e)}", show_alert=True)


@dp.callback_query(lambda c: c.data.startswith("approve_bot_"))
async def on_approve_bot(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец может решать", show_alert=True)
        return

    parts = callback.data.split("_")
    bot_key = parts[2]
    chat_id = int(parts[3])

    # Удаляем из seen_bots — больше предупреждений не будет
    _cur.execute("DELETE FROM seen_bots WHERE bot_id = ?", (bot_key,))
    _db.commit()

    # Уведомляем владельца чата
    await callback.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Бот {bot_key.replace('bot_', '@').replace('mention_', '@')} одобрен владельцем — безопасен."
    )

    # Редактируем сообщение у админа
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ Одобрено владельцем"
    )
    await callback.answer("Одобрено!")


@dp.callback_query(lambda c: c.data.startswith("mark_scam_"))
async def on_mark_scam(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец может решать", show_alert=True)
        return

    parts = callback.data.split("_")
    bot_key = parts[2]
    chat_id = int(parts[3])

    # Добавляем в scam_bots
    _cur.execute(
        "INSERT OR REPLACE INTO scam_bots (bot_id, reason, added_by, added_at) VALUES (?, ?, ?, ?)",
        (bot_key, "Помечен как скам владельцем", OWNER_ID, int(time.time()))
    )
    _db.commit()

    # Уведомляем владельца чата
    await callback.bot.send_message(
        chat_id=chat_id,
        text=f"🚫 Бот {bot_key.replace('bot_', '@').replace('mention_', '@')} помечен как **скам**! Не взаимодействуйте."
    )

    # Редактируем сообщение у админа
    await callback.message.edit_text(
        callback.message.text + "\n\n🚫 Помечен как скам"
    )
    await callback.answer("Помечен как скам!")


@dp.callback_query(lambda c: c.data.startswith("ignore_bot_"))
async def on_ignore_bot(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Только владелец может решать", show_alert=True)
        return

    parts = callback.data.split("_")
    bot_key = parts[2]
    chat_id = int(parts[3])

    # Редактируем сообщение у админа
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ Игнорировано владельцем"
    )
    await callback.answer("Игнорировано")

# HTTP сервер для мини-приложения
async def api_messages_handler(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"messages": []})

    init_data = data.get("initData")
    user_id = data.get("user_id")

    # 🔐 Защита Telegram Mini App
    if not init_data or not verify_telegram_init_data(init_data, BOT_TOKEN):
        return web.json_response({"error": "unauthorized"}, status=403)

    try:
        user_id = int(user_id)
    except Exception:
        return web.json_response({"messages": []})

    # 📦 ЧТЕНИЕ ИЗ БД
    try:
        _cur.execute(
            """
            SELECT event_type, author, content, old_content, timestamp
            FROM events
            WHERE owner_id = ?
            ORDER BY timestamp DESC
            LIMIT 500
            """,
            (user_id,)
        )
        rows = _cur.fetchall()
    except Exception as e:
        logging.error(f"DB read error: {e}")
        rows = []

    return web.json_response({
        "messages": [
            {
                "type": r["event_type"],
                "author": r["author"],
                "content": r["content"],
                "old_content": r["old_content"],
                "timestamp": r["timestamp"],
            }
            for r in rows
        ]
    })


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Middleware для обработки CORS запросов."""
    if request.method == 'OPTIONS':
        response = web.Response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response
    return await handler(request)


async def static_handler(request: web.Request) -> web.Response:
    """Обработчик статических файлов."""
    path = request.match_info.get('path', 'index.html')
    file_path = Path(__file__).parent / 'webapp' / path
    
    if not file_path.exists() or not file_path.is_file():
        return web.Response(status=404)
    
    content_type = 'text/html'
    if path.endswith('.css'):
        content_type = 'text/css'
    elif path.endswith('.js'):
        content_type = 'application/javascript'
    elif path.endswith('.json'):
        content_type = 'application/json'
    
    return web.Response(
        body=file_path.read_bytes(),
        content_type=content_type
    )


async def start_http_server(port: Optional[int] = None) -> None:
    """Запустить HTTP сервер для мини-приложения."""
    # Порт можно задать через переменную окружения PORT (для облачных платформ)
    if port is None:
        port = int(os.getenv("PORT", "8080"))
    
    app = web.Application(middlewares=[cors_middleware])
    
    # API эндпоинты
    app.router.add_post('/api/messages', api_messages_handler)
    app.router.add_options('/api/messages', api_messages_handler)
    app.router.add_get('/api/events/stream', api_events_stream_handler)
    
    # Статические файлы
    app.router.add_get('/', static_handler)
    app.router.add_get('/{path:.*}', static_handler)
    
    runner = web.AppRunner(app)
    await runner.setup()
    # Используем 0.0.0.0 чтобы сервер был доступен извне
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"HTTP server started on http://0.0.0.0:{port}")


async def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_TOKEN_HERE":
        raise RuntimeError("Укажи реальный токен бота в config.py (BOT_TOKEN)")

    # Загружаем сохранённые бизнес-подключения
    load_business_connections()

    # Запускаем HTTP сервер для мини-приложения
    # Порт можно задать через переменную окружения PORT
    await start_http_server()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher()

    dp.callback_query.register(on_callback_rofl, lambda c: c.data == "more_rofl")
    dp.callback_query.register(on_callback_dark_rofl, lambda c: c.data == "dark_rofl")
    dp.callback_query.register(on_callback_more_dark_rofl, lambda c: c.data == "more_dark_rofl")
    dp.callback_query.register(on_callback_refresh_instruction, lambda c: c.data == "refresh_instruction")
    dp.callback_query.register(on_callback_help_instruction, lambda c: c.data == "help_instruction")
    dp.callback_query.register(on_callback_quick_rofl, lambda c: c.data == "quick_rofl")
    dp.callback_query.register(on_callback_quick_coin, lambda c: c.data == "quick_coin")
    dp.callback_query.register(on_callback_quick_instruction, lambda c: c.data == "quick_instruction")
    dp.callback_query.register(on_callback_quick_help, lambda c: c.data == "quick_help")
    dp.callback_query.register(on_callback_cmd_desc_rofl, lambda c: c.data == "cmd_desc_rofl")
    dp.callback_query.register(on_callback_cmd_desc_mock, lambda c: c.data == "cmd_desc_mock")
    dp.callback_query.register(on_callback_cmd_desc_coin, lambda c: c.data == "cmd_desc_coin")
    dp.callback_query.register(on_callback_cmd_desc_instruction, lambda c: c.data == "cmd_desc_instruction")
    dp.callback_query.register(on_callback_cmd_desc_help, lambda c: c.data == "cmd_desc_help")
    dp.callback_query.register(on_callback_cmd_desc_start, lambda c: c.data == "cmd_desc_start")
    dp.callback_query.register(on_callback_open_prank_menu, lambda c: c.data == "open_prank_menu")
    dp.callback_query.register(on_callback_prank_type, lambda c: c.data == "prank_type")
    dp.callback_query.register(on_callback_prank_switch, lambda c: c.data == "prank_switch")
    dp.callback_query.register(on_callback_prank_kawaii, lambda c: c.data == "prank_kawaii")
    dp.callback_query.register(on_callback_prank_love, lambda c: c.data == "prank_love")
    dp.callback_query.register(on_callback_prank_iq, lambda c: c.data == "prank_iq")
    dp.callback_query.register(on_callback_prank_info, lambda c: c.data == "prank_info")
    dp.callback_query.register(on_callback_prank_zaebu, lambda c: c.data == "prank_zaebu")
    dp.callback_query.register(on_callback_check_sub, lambda c: c.data == "check_sub")

    # ← твои новые обработчики (оставляем только один раз каждый)
    dp.callback_query.register(on_report_new_bot, lambda c: c.data.startswith("report_new_bot_"))
    dp.callback_query.register(on_approve_bot,    lambda c: c.data.startswith("approve_bot_"))
    dp.callback_query.register(on_mark_scam,      lambda c: c.data.startswith("mark_scam_"))
    dp.callback_query.register(on_ignore_bot,     lambda c: c.data.startswith("ignore_bot_"))

    dp.message.register(handle_echo)

    await set_commands(bot)
    logging.info("Bot starting polling...")
    logging.info(
        f"Bot is ready to be used as a Telegram Business bot. "
        f"Загружено {len(BUSINESS_LOG_CHATS)} бизнес-подключений. "
        f"Подключи его в настройках Telegram Business и выдай права на управление сообщениями."
    )
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())