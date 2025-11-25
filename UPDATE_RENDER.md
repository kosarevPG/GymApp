# Обновление существующего сервиса на Render.com

## Обновление бэкенда (gym-logger-bot)

### Шаг 1: Обновление репозитория

1. Зайдите в настройки вашего сервиса `gym-logger-bot` на Render.com
2. Перейдите в раздел **Settings**
3. Найдите секцию **GitHub**
4. Нажмите **Change Repository**
5. Выберите репозиторий: `kosarevPG / GymApp`
6. Выберите ветку: `main`
7. Сохраните изменения

### Шаг 2: Обновление команд сборки и запуска

1. В разделе **Settings** найдите секцию **Build & Deploy**
2. Обновите команды:
   - **Build Command**: `cd back && chmod +x build.sh && ./build.sh`
   - **Start Command**: `cd back && python bot.py`
3. Убедитесь, что **Python Version** установлен на `3.11.0` (или оставьте пустым, если используется `runtime.txt`)
4. Сохраните изменения

### Шаг 3: Проверка переменных окружения

Убедитесь, что в разделе **Environment** установлены следующие переменные:

- ✅ `BOT_TOKEN` - токен Telegram бота
- ✅ `SPREADSHEET_ID` - ID Google таблицы
- ✅ `GOOGLE_CREDENTIALS_JSON` - JSON содержимое credentials.json
- ✅ `WEBAPP_URL` - URL фронтенда (обновите после деплоя фронтенда)
- ❌ Удалите `PYTHON_VERSION` (не нужна, используется runtime.txt)
- ❌ Удалите `USE_WEBHOOK` (не используется в текущей версии)

### Шаг 4: Запуск деплоя

1. После обновления настроек Render автоматически запустит новый деплой
2. Или нажмите **Manual Deploy** → **Deploy latest commit**
3. Дождитесь завершения деплоя (проверьте логи)

### Шаг 5: Деплой фронтенда

Если у вас еще нет фронтенда на Render:

1. Создайте новый **Static Site**
2. Подключите репозиторий: `kosarevPG / GymApp`
3. Настройки:
   - **Name**: `gymapp-frontend`
   - **Build Command**: `cd front && npm install && npm run build`
   - **Publish Directory**: `front/dist`
4. Добавьте переменную:
   - `VITE_API_BASE_URL` = `https://gym-logger-bot-y602.onrender.com` (ваш URL бэкенда)
5. После деплоя обновите `WEBAPP_URL` в бэкенде на URL фронтенда

## Проверка работы

1. Проверьте логи бэкенда в разделе **Logs**
2. Убедитесь, что сервер запустился: должно быть сообщение "Server running at http://0.0.0.0:PORT"
3. Проверьте, что Google Sheets подключился: должно быть "Google Sheets connected successfully"
4. Откройте бота в Telegram и проверьте работу

