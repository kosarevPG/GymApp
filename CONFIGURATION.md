# Конфигурация проекта GymApp

## Общая информация

**GymApp** - Telegram Mini App для отслеживания тренировок с интеграцией Google Sheets.

- **Backend**: Python (aiogram, aiohttp) на Render.com
- **Frontend**: React + TypeScript + Vite на GitHub Pages
- **База данных**: Google Sheets
- **Деплой**: Автоматический через GitHub Actions (frontend) и Render (backend)

---

## Структура проекта

```
GymApp/
├── back/                    # Backend (Python)
│   ├── bot.py              # Основной файл бота и API сервера
│   ├── google_sheets.py    # Интеграция с Google Sheets
│   ├── requirements.txt    # Python зависимости
│   ├── runtime.txt         # Версия Python
│   └── build.sh            # Скрипт сборки для Render
│
├── front/                   # Frontend (React)
│   ├── src/
│   │   ├── App.tsx         # Основной компонент приложения
│   │   ├── main.tsx        # Точка входа
│   │   └── index.css       # Стили
│   ├── package.json        # Node.js зависимости
│   ├── vite.config.ts      # Конфигурация Vite
│   ├── tsconfig.json       # TypeScript конфигурация
│   └── tailwind.config.js  # TailwindCSS конфигурация
│
├── .github/
│   └── workflows/
│       └── deploy-frontend.yml  # GitHub Actions для деплоя фронтенда
│
└── README.md
```

---

## Backend конфигурация

### Технологии

- **Python**: 3.11.0
- **aiogram**: 3.1.1 (Telegram Bot API)
- **aiohttp**: 3.8.6 (HTTP сервер)
- **gspread**: 5.12.0 (Google Sheets API)
- **pydantic**: 2.3.0 (валидация данных)

### Файлы конфигурации

#### `back/requirements.txt`
```
aiogram==3.1.1
aiohttp>=3.8.5,<3.9.0
gspread==5.12.0
google-auth==2.23.4
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
python-dotenv==1.0.0
pydantic==2.3.0
pydantic-core==2.6.3
```

#### `back/runtime.txt`
```
python-3.11.0
```

#### `back/build.sh`
Скрипт сборки для Render.com:
- Обновляет pip, setuptools, wheel
- Определяет версию Python
- Устанавливает зависимости с предпочтением бинарных пакетов
- Обрабатывает совместимость Python 3.11 и 3.13

### Переменные окружения (Render.com)

| Переменная | Описание | Пример |
|------------|----------|--------|
| `BOT_TOKEN` | Токен Telegram бота | `1234567890:ABC...` |
| `WEBAPP_URL` | URL фронтенда | `https://kosarevPG.github.io/GymApp/` |
| `SPREADSHEET_ID` | ID Google таблицы | `1abc...xyz` |
| `GOOGLE_CREDENTIALS_JSON` | JSON содержимое credentials.json | `{"type": "service_account", ...}` |
| `PYTHON_VERSION` | Версия Python (опционально) | `3.11.0` |
| `PORT` | Порт сервера (автоматически) | `8000` |

### Настройки деплоя на Render.com

**Build Command:**
```bash
cd back && bash build.sh
```

**Start Command:**
```bash
cd back && python bot.py
```

**Python Version:** `3.11.0` (указывается в переменной окружения или runtime.txt)

### API Endpoints

Backend предоставляет следующие API endpoints:

- `GET /api/init` - Получить список упражнений и групп мышц
- `GET /api/history?exercise_id={id}` - Получить историю упражнения
- `GET /api/global_history` - Получить глобальную историю тренировок
- `POST /api/save_set` - Сохранить выполненный подход
- `POST /api/create_exercise` - Создать новое упражнение
- `POST /api/update_exercise` - Обновить упражнение

Все endpoints поддерживают CORS для работы с фронтендом.

---

## Frontend конфигурация

### Технологии

- **React**: 18.2.0
- **TypeScript**: 5.2.0
- **Vite**: 5.1.0
- **TailwindCSS**: 3.4.0
- **Framer Motion**: 11.18.2 (анимации)
- **Lucide React**: 0.344.0 (иконки)

### Файлы конфигурации

#### `front/vite.config.ts`
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/GymApp/', // GitHub Pages путь
})
```

#### `front/package.json`
Основные зависимости:
- `react`, `react-dom`
- `framer-motion`
- `lucide-react`
- `clsx`, `tailwind-merge`

Dev зависимости:
- `typescript`
- `@vitejs/plugin-react`
- `tailwindcss`, `autoprefixer`, `postcss`

### Переменные окружения

| Переменная | Описание | Значение по умолчанию |
|------------|----------|----------------------|
| `VITE_API_BASE_URL` | URL бэкенда API | `http://localhost:8000` (dev) |

**Для продакшена:**
- Устанавливается в GitHub Actions через secrets
- Или указывается в `.github/workflows/deploy-frontend.yml`

### Настройки деплоя на GitHub Pages

#### GitHub Actions Workflow (`.github/workflows/deploy-frontend.yml`)

**Триггеры:**
- Push в `main` ветку при изменении файлов в `front/`
- Ручной запуск через `workflow_dispatch`

**Процесс:**
1. Checkout кода
2. Setup Node.js 20
3. Install dependencies (`npm ci`)
4. Build (`npm run build`)
5. Deploy to GitHub Pages

**Переменные:**
- `VITE_API_BASE_URL` - берется из secrets или используется дефолтное значение

#### Настройки GitHub Pages

- **Source**: GitHub Actions
- **Branch**: `gh-pages` (автоматически)
- **URL**: `https://kosarevPG.github.io/GymApp/`

---

## Интеграция компонентов

### Схема работы

```
┌─────────────┐
│   Telegram  │
│     Bot     │
└──────┬──────┘
       │
       │ WebApp URL
       ▼
┌─────────────┐      API Requests      ┌─────────────┐
│   Frontend  │◄───────────────────────►│   Backend   │
│ (GitHub     │                         │  (Render)   │
│  Pages)     │                         │             │
└─────────────┘                         └──────┬──────┘
                                               │
                                               │ Google Sheets API
                                               ▼
                                        ┌─────────────┐
                                        │   Google    │
                                        │   Sheets    │
                                        └─────────────┘
```

### Поток данных

1. Пользователь открывает бота в Telegram
2. Бот отправляет кнопку с WebApp URL (фронтенд на GitHub Pages)
3. Фронтенд загружается и делает API запросы к бэкенду на Render
4. Бэкенд обрабатывает запросы и взаимодействует с Google Sheets
5. Данные возвращаются во фронтенд и отображаются пользователю

### Telegram Bot настройки

**BotFather конфигурация:**
- **Web App URL**: `https://kosarevPG.github.io/GymApp/`
- **Direct Link**: `https://t.me/GymAppKPGBot/GymApp`

**Важно:** Бот добавляет cache buster к URL (`?v=timestamp`) для обхода кеша Telegram.

---

## Google Sheets структура

### Листы

1. **Exercises** - список упражнений
   - Колонки: ID, Name, Muscle Group, Description, Image URL

2. **Log** - история тренировок
   - Колонки: Date, Exercise ID, Weight, Reps, Rest, Set Group ID, Order, Note

### Формат данных

**Exercise:**
```json
{
  "id": "ex_123",
  "name": "Отжимания",
  "muscleGroup": "Грудь",
  "description": "Описание",
  "imageUrl": "https://..."
}
```

**Workout Set:**
```json
{
  "exercise_id": "ex_123",
  "weight": 50.0,
  "reps": 10,
  "rest": 60.0,
  "set_group_id": "session_123",
  "order": 1,
  "note": "Примечание"
}
```

---

## Локальная разработка

### Backend

1. Создайте виртуальное окружение:
```bash
cd back
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте `.env` файл:
```env
BOT_TOKEN=your_bot_token
WEBAPP_URL=http://localhost:5173
SPREADSHEET_ID=your_spreadsheet_id
GOOGLE_CREDENTIALS_JSON={"type": "service_account", ...}
```

4. Запустите:
```bash
python bot.py
```

### Frontend

1. Установите зависимости:
```bash
cd front
npm install
```

2. Запустите dev сервер:
```bash
npm run dev
```

3. Откройте `http://localhost:5173`

---

## Деплой

### Backend (Render.com)

1. Подключите репозиторий GitHub
2. Настройте переменные окружения
3. Укажите Build Command: `cd back && bash build.sh`
4. Укажите Start Command: `cd back && python bot.py`
5. Установите Python Version: `3.11.0`

### Frontend (GitHub Pages)

1. Включите GitHub Pages в настройках репозитория
2. Выберите source: GitHub Actions
3. Добавьте secret `VITE_API_BASE_URL` (опционально)
4. При push в `main` автоматически запустится деплой

---

## Важные замечания

### Кеш Telegram

Telegram агрессивно кеширует Web App URL. Решения:
- Бот автоматически добавляет cache buster (`?v=timestamp`)
- Измените название Web App в BotFather
- Очистите кеш Telegram или переустановите приложение

### CORS

Backend настроен на разрешение запросов с любого origin (`*`). Для продакшена можно ограничить до конкретного домена.

### Безопасность

- `BOT_TOKEN` и `GOOGLE_CREDENTIALS_JSON` хранятся только в переменных окружения
- Никогда не коммитьте эти данные в репозиторий
- Используйте `.gitignore` для исключения `.env` файлов

### Версионирование

- **Python**: 3.11.0 (обязательно для совместимости с pydantic)
- **Node.js**: 20 (для GitHub Actions)
- Все зависимости зафиксированы в `requirements.txt` и `package.json`

---

## Troubleshooting

### Backend не деплоится

1. Проверьте, что `PYTHON_VERSION=3.11.0` установлен
2. Проверьте логи сборки на Render
3. Убедитесь, что все переменные окружения установлены

### Frontend не деплоится

1. Проверьте GitHub Actions workflow
2. Убедитесь, что GitHub Pages включен
3. Проверьте, что `base` в `vite.config.ts` соответствует пути репозитория

### Открывается старый фронтенд

1. Проверьте логи бота - какой URL используется
2. Очистите кеш Telegram
3. Измените название Web App в BotFather
4. Проверьте, что фронтенд действительно обновился на GitHub Pages

---

## Контакты и поддержка

- **Репозиторий**: https://github.com/kosarevPG/GymApp
- **Backend URL**: https://gym-logger-bot-y602.onrender.com
- **Frontend URL**: https://kosarevPG.github.io/GymApp/

---

*Последнее обновление: 2024*

