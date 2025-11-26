# Изображения упражнений

Эта папка содержит изображения (GIF, PNG, JPG) для упражнений.

## Как использовать

1. Поместите изображения в эту папку
2. В Google Sheets в колонке `Image_URL` укажите путь к изображению:
   - Для GitHub Pages: `/GymApp/images/exercises/название-файла.gif`
   - Для локальной разработки: `/images/exercises/название-файла.gif`

## Примеры

- `/GymApp/images/exercises/push-ups.gif`
- `/GymApp/images/exercises/pull-ups.gif`
- `/GymApp/images/exercises/squats.png`

## Важно

- Файлы из папки `public/` в Vite доступны по корневому пути
- При деплое на GitHub Pages путь должен начинаться с `/GymApp/` (из-за base path в vite.config.ts)
- Используйте понятные имена файлов (латиница, без пробелов)


