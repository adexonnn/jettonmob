# bot.py
import asyncio
import logging
import time
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, API_URL, ADMIN_ID
from database import conn, cursor, get_last_price, update_last_price, is_banned, block_user

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

last_price = get_last_price()
user_message_times = {}

# Клавиатура
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Ввести количество токенов")],
        [KeyboardButton(text="Остановить мониторинг")]
    ],
    resize_keyboard=True
)

start_message = (
    "👋 Приветствую!\n"
    "В этом боте ты можешь отслеживать стоимость своих активов в токене YOUR_TOKEN. "
    "Чтобы начать мониторинг цены, введи количество своих токенов и следи за изменениями в боте!\n\n"
    "Поддержка бота: <a href='https://t.me/your_username'>@yourusername</a>\n\n"
    "❗️ Бот находится в тестировании, могут быть ошибки. Если нашли - пишите в поддержку.\n\n"
    "<a href='https://t.me/your_channel'><b>Канал</b></a> | "
    "<a href='https://t.me/your_chat'><b>Чат</b></a>"
)

def get_fpi_price():
    try:
        response = requests.get(API_URL).json()
        if response and response.get("pairs"):
            pair_data = response["pairs"][0]
            price_usd = round(float(pair_data["priceUsd"]), 5)
            price_ton = round(float(pair_data["priceNative"]), 5)
            return price_usd, price_ton
        else:
            logging.warning("❗️ Некорректный ответ от API")
            return None, None
    except Exception as e:
        logging.error(f"Ошибка при получении данных: {e}")
        return None, None

async def is_spamming(user_id: int):
    global user_message_times
    current_time = time.time()
    if user_id in user_message_times:
        last_message_time = user_message_times[user_id]
        if current_time - last_message_time < 1:
            return True
    user_message_times[user_id] = current_time
    return False

async def monitoring_task():
    global last_price
    rub_exchange_rate = 96.78

    while True:
        cursor.execute("SELECT user_id, tokens FROM users WHERE monitoring=1")
        users = cursor.fetchall()
        price_usd, price_ton = get_fpi_price()

        if price_usd is not None and price_ton is not None:
            change_text = ""
            if last_price is not None:
                change_percent = round(((price_usd - last_price) / last_price) * 100, 2) if last_price != 0 else 0
                if abs(change_percent) > 0.01:  # Показываем только при изменении > 0.01%
                    if change_percent > 0:
                        change_text = f"\n⚙️ Изменение: +{change_percent}% 🟢\n"
                    elif change_percent < 0:
                        change_text = f"\n⚙️ Изменение: {change_percent}% 🔴\n"
                    # Если изменение <= 0.01%, change_text остаётся пустым
            last_price = price_usd
            update_last_price(last_price)

            fdv = round(price_usd * 1_000_000_000 / 1_000_000, 1)
            fdv_text = f"{fdv}M USD₮"

            for user_id, tokens in users:
                if is_banned(user_id):
                    continue

                total_value = round(tokens * price_usd, 2)
                msg = (
                    f"Стоимость: <b>{int(total_value) if total_value.is_integer() else total_value} USD₮</b>\n"
                    f"Ваши токены: {int(tokens) if tokens.is_integer() else tokens}\n\n"
                    f"💰 Цена токена: {price_usd} USD₮ ≈ {round(price_usd * rub_exchange_rate, 2)} RUB\n"
                    f"💎 Цена в TON: {price_ton} TON\n"
                    f"⛽️ Капитализация: {fdv_text}\n"
                )
                if change_text:
                    msg += f"{change_text}"

                try:
                    await bot.send_message(user_id, msg, parse_mode="HTML")
                except Exception as e:
                    logging.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        await asyncio.sleep(60)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if is_banned(message.from_user.id):
        await message.answer("❗️ Вы заблокированы и не можете использовать бота.")
        return
    await bot.send_message(
        message.from_user.id,
        start_message,
        parse_mode='HTML',
        disable_web_page_preview=True,
        reply_markup=keyboard
    )

@dp.message(lambda msg: msg.text == "Ввести количество токенов")
async def enter_tokens(message: types.Message):
    if await is_spamming(message.from_user.id):
        return
    await message.answer("Введите количество токенов:")

@dp.message(lambda msg: msg.text.replace('.', '', 1).isdigit())
async def save_tokens(message: types.Message):
    if await is_spamming(message.from_user.id):
        return
    if is_banned(message.from_user.id):
        await message.answer("❗️ Вы заблокированы и не можете использовать бота.")
        return
    tokens = float(message.text)
    cursor.execute("INSERT INTO users (user_id, tokens, monitoring) VALUES (?, ?, 1) ON CONFLICT(user_id) DO UPDATE SET tokens=?, monitoring=1", (message.from_user.id, tokens, tokens))
    conn.commit()
    await message.answer("❗️ Мониторинг включен! Бот будет отправлять уведомления каждую минуту.")

@dp.message(lambda msg: msg.text == "Остановить мониторинг")
async def stop_monitoring(message: types.Message):
    if await is_spamming(message.from_user.id):
        return
    if is_banned(message.from_user.id):
        await message.answer("❗️ Вы заблокированы и не можете использовать бота.")
        return
    cursor.execute("SELECT monitoring FROM users WHERE user_id=?", (message.from_user.id,))
    result = cursor.fetchone()
    if result and result[0] == 0:
        await message.answer("❗️ Вы не начали мониторинг.")
    else:
        cursor.execute("UPDATE users SET monitoring=0 WHERE user_id=?", (message.from_user.id,))
        conn.commit()
        await message.answer("❗️ Мониторинг отключен.")

@dp.message(lambda msg: msg.text.startswith("/block"))
async def block_user_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❗️ У вас нет прав для выполнения этой команды.")
        return
    parts = message.text.split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("❗️ Неверный формат команды. Используйте: /block <ID>")
        return
    user_id_to_block = int(parts[1])
    block_user(user_id_to_block)
    await message.answer(f"❗️ Пользователь с ID {user_id_to_block} заблокирован.")

async def start_bot():
    asyncio.create_task(monitoring_task())
    await dp.start_polling(bot)