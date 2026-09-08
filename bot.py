from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import ClientSession, ClientTimeout
from aiohttp.web import Application, Response, TCPSite, AppRunner
import asyncio
import logging
import os
import json
import re

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# ===== ПРОВЕРКА КЛЮЧЕЙ =====
if not DEEPSEEK_API_KEY:
    logging.warning("DEEPSEEK_API_KEY not set")
if not OPENROUTER_API_KEY:
    logging.warning("OPENROUTER_API_KEY not set")

# ===== ИНИЦИАЛИЗАЦИЯ =====
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ===== КНОПКИ =====
START_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🚀 Начать"]],
    resize_keyboard=True
)

OK_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="✅ ОК, понял"]],
    resize_keyboard=True
)

# ===== СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ =====
user_states = {}  # user_id -> "waiting_ok" или None

# ===== РОУТИНГ (ВЫБОР НЕЙРОСЕТИ) =====
def route_request(text: str) -> dict:
    """
    Возвращает словарь с выбором модели и провайдера
    """
    text_lower = text.lower()
    
    # Признаки сложного кода/технического вопроса
    code_keywords = ['код', 'функция', 'класс', 'def ', 'import ', 'return ', 'ошибка', 'debug', 'отладка', 'синтаксис', 'алгоритм']
    if any(keyword in text_lower for keyword in code_keywords):
        return {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "reason": "🔧 Код/техническая задача → DeepSeek"
        }
    
    # Признаки творчества
    creative_keywords = ['стих', 'рассказ', 'сценарий', 'творчество', 'креатив', 'сочини', 'придумай']
    if any(keyword in text_lower for keyword in creative_keywords):
        return {
            "provider": "openrouter",
            "model": "anthropic/claude-3-haiku",
            "reason": "🎨 Творчество → Claude"
        }
    
    # Длинный текст (>3000 символов) — дешевле через DeepSeek
    if len(text) > 3000:
        return {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "reason": "📄 Длинный текст → DeepSeek (экономия)"
        }
    
    # По умолчанию — OpenRouter (GPT-4o-mini, дёшево и универсально)
    return {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "reason": "💡 Общий вопрос → GPT-4o-mini"
    }

# ===== ВЫЗОВ API =====
async def call_deepseek_api(prompt: str, history: list = None) -> str:
    """Вызов DeepSeek API"""
    if not DEEPSEEK_API_KEY:
        return "❌ API-ключ DeepSeek не настроен. Обратитесь к администратору."
    
    messages = []
    if history:
        # Добавляем историю (последние 5 сообщений)
        for msg in history[-5:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    async with ClientSession(timeout=ClientTimeout(total=60)) as session:
        try:
            async with session.post("https://api.deepseek.com/chat/completions", headers=headers, json=data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return f"❌ Ошибка DeepSeek: {resp.status} - {error_text[:200]}"
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"❌ Ошибка при запросе к DeepSeek: {str(e)[:200]}"

async def call_openrouter_api(prompt: str, model: str, history: list = None) -> str:
    """Вызов OpenRouter API"""
    if not OPENROUTER_API_KEY:
        return "❌ API-ключ OpenRouter не настроен. Обратитесь к администратору."
    
    messages = []
    if history:
        for msg in history[-5:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": prompt})
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me/neiro_aggregator_bot",
        "X-Title": "Neuro Aggregator"
    }
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    async with ClientSession(timeout=ClientTimeout(total=60)) as session:
        try:
            async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    return f"❌ Ошибка OpenRouter: {resp.status} - {error_text[:200]}"
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"❌ Ошибка при запросе к OpenRouter: {str(e)[:200]}"

# ===== ОБРАБОТЧИК КОМАНДЫ /start =====
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    user_states[user_id] = "waiting_start"
    
    welcome_text = (
        "🤖 *Привет! Это лучший бесплатный бот-агрегатор нейросетей!*\n\n"
        "Я объединяю в себе возможности *GPT-4o, Claude, DeepSeek, Gemini, Llama* и других топовых моделей.\n\n"
        "✅ *Полностью бесплатно*\n"
        "✅ *Без подписок и лимитов*\n"
        "✅ *Умный выбор нейросети для каждой задачи*\n\n"
        "Нажми кнопку ниже, чтобы начать!"
    )
    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=START_KEYBOARD)

# ===== ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ =====
@dp.message()
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    text = message.text
    
    # Обработка кнопки "Начать"
    if text == "🚀 Начать":
        user_states[user_id] = "waiting_ok"
        explain_text = (
            "🧠 *Как это работает:*\n\n"
            "Я *автоматически анализирую* твой запрос и выбираю *лучшую нейросеть*:\n"
            "• 🔧 *Код/техника* → DeepSeek\n"
            "• 🎨 *Творчество* → Claude\n"
            "• 💡 *Общие вопросы* → GPT-4o-mini\n"
            "• 📄 *Длинные тексты* → DeepSeek (экономия)\n\n"
            "Это повышает *качество ответа* и экономит бюджет, чтобы сервис оставался *бесплатным* для тебя.\n\n"
            "Нажми *«ОК, понял»* и просто пиши свои вопросы!"
        )
        await message.answer(explain_text, parse_mode="Markdown", reply_markup=OK_KEYBOARD)
        return
    
    # Обработка кнопки "ОК, понял"
    if text == "✅ ОК, понял":
        user_states[user_id] = None
        await message.answer(
            "🔥 *Отлично!*\n\n"
            "Теперь просто *пиши любые вопросы* — я отвечу тебе с помощью лучшей нейросети!\n\n"
            "📌 *Примеры запросов:*\n"
            "• «Напиши код на Python для парсинга сайта»\n"
            "• «Сочини стих про осень»\n"
            "• «Объясни теорию относительности простыми словами»\n\n"
            "Приятного пользования! 🚀",
            parse_mode="Markdown"
        )
        return
    
    # Проверка, прошёл ли пользователь приветствие
    if user_id in user_states and user_states[user_id] is not None:
        await message.answer("⚠️ Сначала нажми «🚀 Начать» и «✅ ОК, понял», чтобы начать пользоваться ботом.")
        return
    
    # ===== ОСНОВНАЯ ЛОГИКА (РОУТИНГ) =====
    # Отправляем статус "печатает"
    await bot.send_chat_action(message.chat.id, "typing")
    
    # Выбор нейросети
    routing = route_request(text)
    
    # Уведомление о выборе
    await message.answer(f"🤔 {routing['reason']}...")
    
    # История сообщений (храним в памяти, можно заменить на Redis)
    if not hasattr(message.chat, "history"):
        message.chat.history = []
    
    # Вызов API
    try:
        if routing["provider"] == "deepseek":
            response = await call_deepseek_api(text, message.chat.history)
        else:  # openrouter
            response = await call_openrouter_api(text, routing["model"], message.chat.history)
    except Exception as e:
        response = f"❌ Критическая ошибка: {str(e)[:200]}\nПопробуйте позже."
    
    # Сохраняем историю
    message.chat.history.append({"role": "user", "content": text})
    message.chat.history.append({"role": "assistant", "content": response})
    if len(message.chat.history) > 20:  # ограничиваем историю
        message.chat.history = message.chat.history[-20:]
    
    # Отправляем ответ
    await message.answer(response)

# ===== ВЕБ-СЕРВЕР ДЛЯ RENDER =====
async def health_check(request):
    return Response(text="OK")

async def start_web_server():
    app = Application()
    app.router.add_get("/", health_check)
    runner = AppRunner(app)
    await runner.setup()
    site = TCPSite(runner, "0.0.0.0", port=int(os.environ.get("PORT", 10000)))
    await site.start()
    logging.info(f"Web server started on port {os.environ.get('PORT', 10000)}")
    await asyncio.Event().wait()

# ===== ЗАПУСК =====
async def main():
    await asyncio.gather(
        start_web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())
