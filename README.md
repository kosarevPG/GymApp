# GymApp - Telegram Mini App для трекинга тренировок

Telegram Mini App для отслеживания тренировок с интеграцией Google Sheets.

## Структура проекта

- `back/` - Python бэкенд (aiogram + aiohttp + gspread)
- `front/` - React фронтенд (Vite + TypeScript + TailwindCSS)

## Локальная разработка

### Бэкенд

```bash
cd back
python -m venv venv
venv\Scripts\activate  # Windows
# или
source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt

# Создайте .env файл с переменными:
# BOT_TOKEN=your_telegram_bot_token
# WEBAPP_URL=http://localhost:5173
# PORT=8000
# GOOGLE_CREDENTIALS_PATH=credentials.json
# SPREADSHEET_ID=your_google_sheet_id

python bot.py
```

### Фронтенд

```bash
cd front
npm install
npm run dev
```

## Деплой на Render.com

### Шаг 1: Подготовка GitHub репозитория

1. Создайте репозиторий на GitHub
2. Закоммитьте код:
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/yourusername/gymapp.git
git push -u origin main
```

### Шаг 2: Деплой бэкенда

1. Зайдите на [Render.com](https://render.com) и создайте новый **Web Service**
2. Подключите ваш GitHub репозиторий
3. Настройки:
   - **Name**: `gymapp-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `cd back && pip install -r requirements.txt`
   - **Start Command**: `cd back && python bot.py`
   - **Plan**: Free или выше
4. Добавьте переменные окружения в разделе **Environment**:
   - `BOT_TOKEN` - токен вашего Telegram бота (получите у @BotFather)
   - `WEBAPP_URL` - будет обновлен после деплоя фронтенда (пока оставьте пустым или временный URL)
   - `SPREADSHEET_ID` - ID вашей Google таблицы (из URL: `https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit`)
   - `GOOGLE_CREDENTIALS_JSON` - полное содержимое файла `credentials.json` как JSON строка (скопируйте весь JSON)
   - `PORT` - Render устанавливает автоматически, но можно оставить пустым
5. Нажмите **Create Web Service**
6. Дождитесь деплоя и скопируйте URL (например: `https://gymapp-backend.onrender.com`)

### Шаг 3: Деплой фронтенда

1. На Render.com создайте новый **Static Site**
2. Подключите тот же GitHub репозиторий
3. Настройки:
   - **Name**: `gymapp-frontend`
   - **Build Command**: `cd front && npm install && npm run build`
   - **Publish Directory**: `front/dist`
4. Добавьте переменную окружения:
   - `VITE_API_BASE_URL` - URL вашего бэкенда (например: `https://gymapp-backend.onrender.com`)
5. Нажмите **Create Static Site**
6. Дождитесь деплоя и скопируйте URL (например: `https://gymapp-frontend.onrender.com`)

### Шаг 4: Обновление настроек

1. Вернитесь в настройки бэкенда на Render.com
2. Обновите переменную `WEBAPP_URL` на URL вашего фронтенда
3. Сохраните изменения (Render автоматически перезапустит сервис)

### Шаг 5: Настройка Telegram бота

1. Откройте [@BotFather](https://t.me/BotFather) в Telegram
2. Отправьте `/mybots` и выберите вашего бота
3. Выберите **Bot Settings** → **Menu Button**
4. Нажмите **Configure Menu Button**
5. Введите URL вашего фронтенда (например: `https://gymapp-frontend.onrender.com`)
6. Готово! Теперь в вашем боте появится кнопка меню, открывающая Mini App

## Переменные окружения

### Бэкенд (.env)

```
BOT_TOKEN=your_telegram_bot_token
WEBAPP_URL=https://your-frontend.onrender.com
PORT=8000
GOOGLE_CREDENTIALS_PATH=credentials.json
# или
GOOGLE_CREDENTIALS_JSON={"type":"service_account",...}
SPREADSHEET_ID=your_google_sheet_id
```

### Google Sheets Setup

1. Создайте Google Cloud проект
2. Включите Google Sheets API
3. Создайте Service Account
4. Скачайте credentials.json
5. Поделитесь Google таблицей с email из Service Account
6. Таблица должна содержать листы: `LOG` и `EXERCISES`

## Структура Google Таблицы

### Лист EXERCISES
- Колонка A: ID
- Колонка B: Name
- Колонка C: Muscle Group
- Колонка D: Description
- Колонка E: Image_URL

### Лист LOG
- Колонка A: Date
- Колонка B: Exercise_ID
- Колонка C: (пустая)
- Колонка D: Weight
- Колонка E: Reps
- Колонка F: Rest
- Колонка G: Set_Group_ID
- Колонка H: Note
- Колонка I: Order

## Лицензия

MIT

