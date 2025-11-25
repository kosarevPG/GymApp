# Исправление ошибки деплоя на Render

## Проблема

Ошибка при сборке: `Read-only file system (os error 30)` при попытке компиляции Rust-кода для зависимостей.

## Решение

### Обновите Build Command в настройках Render:

1. Зайдите в настройки сервиса `gym-logger-bot` на Render.com
2. Перейдите в **Settings** → **Build & Deploy**
3. Обновите **Build Command** на:

```bash
cd back && pip install --upgrade pip setuptools wheel && pip install --prefer-binary -r requirements.txt
```

Или более надежный вариант:

```bash
cd back && pip install --upgrade pip && pip install --only-binary :all: -r requirements.txt 2>/dev/null || pip install --prefer-binary -r requirements.txt
```

4. **Start Command** оставьте:
```bash
cd back && python bot.py
```

5. Сохраните изменения

### Альтернативное решение (если первое не работает):

Используйте более новую версию Python. Обновите `back/runtime.txt`:

```
python-3.12.0
```

Или удалите `runtime.txt` совсем - Render использует последнюю стабильную версию Python 3.

### Проверка переменных окружения:

Убедитесь, что установлены:
- `BOT_TOKEN`
- `SPREADSHEET_ID`
- `GOOGLE_CREDENTIALS_JSON`
- `WEBAPP_URL`

Удалите (если есть):
- `PYTHON_VERSION` (не нужна)
- `USE_WEBHOOK` (не используется)

### После обновления:

1. Нажмите **Manual Deploy** → **Deploy latest commit**
2. Проверьте логи - должна быть успешная установка пакетов
3. Дождитесь завершения деплоя

