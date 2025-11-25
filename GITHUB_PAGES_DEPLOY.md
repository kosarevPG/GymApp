# Деплой фронтенда на GitHub Pages

## Настройка GitHub Pages

### Шаг 1: Включите GitHub Pages в настройках репозитория

1. Зайдите на https://github.com/kosarevPG/GymApp
2. Перейдите в **Settings** → **Pages**
3. В разделе **Source** выберите:
   - **Source**: `GitHub Actions`
4. Сохраните изменения

### Шаг 2: Добавьте секрет для API URL (опционально)

1. В репозитории перейдите в **Settings** → **Secrets and variables** → **Actions**
2. Нажмите **New repository secret**
3. Добавьте:
   - **Name**: `VITE_API_BASE_URL`
   - **Value**: `https://gym-logger-bot-y602.onrender.com` (URL вашего бэкенда)
4. Нажмите **Add secret**

### Шаг 3: Запустите деплой

1. После включения GitHub Pages и добавления workflow файла
2. GitHub Actions автоматически запустит деплой при следующем push в `main`
3. Или перейдите в **Actions** и запустите workflow вручную

### Шаг 4: Получите URL фронтенда

После успешного деплоя ваш фронтенд будет доступен по адресу:
```
https://kosarevPG.github.io/GymApp/
```

### Шаг 5: Обновите WEBAPP_URL в бэкенде

1. Зайдите в настройки вашего сервиса на Render.com
2. Перейдите в **Environment**
3. Обновите переменную `WEBAPP_URL` на:
   ```
   https://kosarevPG.github.io/GymApp/
   ```
4. Сохраните изменения (Render автоматически перезапустит)

## Обновление API URL

Если нужно изменить URL бэкенда:

1. Обновите секрет `VITE_API_BASE_URL` в GitHub
2. Или обновите значение в `.github/workflows/deploy-frontend.yml` (строка с `VITE_API_BASE_URL`)
3. Запустите workflow заново

## Преимущества GitHub Pages

- ✅ Бесплатно
- ✅ Автоматический деплой при каждом push
- ✅ HTTPS из коробки
- ✅ Быстрая загрузка
- ✅ Не нужно настраивать отдельный сервис на Render

## Проверка работы

1. После деплоя откройте https://kosarevPG.github.io/GymApp/
2. Проверьте, что приложение загружается
3. Проверьте консоль браузера (F12) - не должно быть ошибок подключения к API
4. Откройте бота в Telegram и проверьте работу Mini App

