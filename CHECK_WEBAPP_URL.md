# Проверка URL фронтенда - Пошаговая инструкция

## Проблема
Из бота открывается старый фронтенд, хотя URL обновлен.

## Места, где может быть прописан URL:

### 1. ✅ Render.com - Переменная окружения WEBAPP_URL

**Проверка:**
1. Зайдите в сервис `gym-logger-bot` на Render.com
2. Settings → Environment
3. Найдите переменную `WEBAPP_URL`
4. **Должно быть:** `https://kosarevPG.github.io/GymApp/` (без `/frontend` в конце!)

**Если неправильно:**
- Обновите на правильный URL
- Сохраните
- **ВАЖНО:** Перезапустите сервис (Manual Deploy → Deploy latest commit)

### 2. ✅ BotFather - Настройки бота в Telegram

**Проверка:**
1. Откройте @BotFather в Telegram
2. Отправьте `/myapps`
3. Выберите вашего бота (GymAppKPGBot)
4. Проверьте "Web App URL"
5. **Должно быть:** `https://kosarevPG.github.io/GymApp/`

**Если неправильно:**
- Нажмите "Edit Web App URL"
- Отправьте правильный URL: `https://kosarevPG.github.io/GymApp/`
- Дождитесь подтверждения "Success!"

### 3. ✅ Кеш Telegram

Telegram может кешировать старый URL. Попробуйте:

**Вариант A:**
1. Полностью закройте Telegram (не просто сверните)
2. Откройте заново
3. Попробуйте снова

**Вариант B:**
1. Удалите бота из списка чатов
2. Найдите бота заново через поиск
3. Отправьте `/start`

**Вариант C:**
1. Очистите кеш Telegram (Настройки → Данные и хранилище → Очистить кеш)
2. Перезапустите Telegram

### 4. ✅ Проверка логов бота

После добавления логирования в код:

1. Зайдите в Render.com → ваш сервис → Logs
2. Отправьте `/start` боту
3. В логах должно быть:
   ```
   Command /start received. Using WEBAPP_URL: https://kosarevPG.github.io/GymApp/
   ```

Если в логах другой URL - значит проблема в переменной окружения на Render.

### 5. ✅ Проверка реального URL фронтенда

Убедитесь, что фронтенд действительно доступен по адресу:
- Откройте в браузере: `https://kosarevPG.github.io/GymApp/`
- Должна открыться ваша мини-апп

Если не открывается:
- Проверьте настройки GitHub Pages
- Убедитесь, что деплой прошел успешно
- Проверьте, что в `vite.config.ts` указан правильный `base: '/GymApp/'`

## Правильный URL должен быть:

```
https://kosarevPG.github.io/GymApp/
```

**НЕ:**
- ❌ `https://kosarevPG.github.io/GymApp-frontend/`
- ❌ `https://kosarevPG.github.io/GymApp/frontend/`
- ❌ `http://localhost:5173`

## После исправления:

1. Обновите `WEBAPP_URL` в Render
2. Обновите URL в BotFather
3. Перезапустите сервис на Render
4. Очистите кеш Telegram
5. Попробуйте снова

## Если все еще не работает:

Проверьте логи бота на Render - там будет видно, какой URL используется.

