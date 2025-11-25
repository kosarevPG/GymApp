import asyncio
import logging
import os
import json
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from google_sheets import GoogleSheetsManager

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL")
# Render автоматически устанавливает PORT через переменную окружения
PORT = int(os.getenv("PORT", 8000))
CREDENTIALS_PATH = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

try:
    sheets = GoogleSheetsManager(credentials_path=CREDENTIALS_PATH, spreadsheet_id=SPREADSHEET_ID)
except Exception as e:
    logger.critical(f"Failed to init sheets: {e}")
    sheets = None

@dp.message(Command("start"))
async def cmd_start(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Открыть GymApp", web_app=WebAppInfo(url=WEBAPP_URL))
    ]])
    await message.answer("Привет! Жми кнопку, чтобы начать тренировку 👇", reply_markup=kb)

def json_response(data, status=200):
    return web.json_response(
        data, 
        status=status, 
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        }
    )

async def handle_options(request):
    return json_response({"status": "ok"})

async def api_init(request):
    try:
        data = sheets.get_all_exercises()
        return json_response(data)
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def api_history(request):
    ex_id = request.query.get('exercise_id')
    if not ex_id: return json_response({"error": "Missing exercise_id"}, 400)
    try:
        data = sheets.get_exercise_history(ex_id)
        return json_response(data)
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def api_global_history(request):
    try:
        data = sheets.get_global_history()
        return json_response(data)
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def api_save_set(request):
    try:
        data = await request.json()
        if sheets.save_workout_set(data):
            return json_response({"status": "success"})
        return json_response({"error": "Failed to save"}, 500)
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def api_create_exercise(request):
    try:
        data = await request.json()
        if not data.get('name') or not data.get('group'):
            return json_response({"error": "Missing fields"}, 400)
        new_ex = sheets.create_exercise(data['name'], data['group'])
        return json_response(new_ex)
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def api_update_exercise(request):
    try:
        data = await request.json()
        if sheets.update_exercise(data.get('id'), data.get('updates')):
            return json_response({"status": "success"})
        return json_response({"error": "Failed"}, 500)
    except Exception as e:
        return json_response({"error": str(e)}, 500)

async def on_startup(app):
    asyncio.create_task(dp.start_polling(bot))

async def main():
    app = web.Application()
    app.router.add_routes([
        web.get('/api/init', api_init),
        web.get('/api/history', api_history),
        web.get('/api/global_history', api_global_history),
        web.post('/api/save_set', api_save_set),
        web.post('/api/create_exercise', api_create_exercise),
        web.post('/api/update_exercise', api_update_exercise),
        web.options('/{tail:.*}', handle_options),
    ])
    
    app.on_startup.append(on_startup)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    print(f"Server running at http://0.0.0.0:{PORT}")
    await site.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
