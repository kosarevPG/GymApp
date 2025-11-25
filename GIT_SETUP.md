# Инструкция по настройке Git и загрузке на GitHub

## Шаг 1: Создайте репозиторий на GitHub

1. Зайдите на https://github.com
2. Нажмите **New** (или **+** → **New repository**)
3. Заполните:
   - **Repository name**: `GymApp` (или другое имя)
   - **Description**: `Telegram Mini App для трекинга тренировок`
   - **Visibility**: Public или Private (на ваше усмотрение)
   - **НЕ** ставьте галочки на "Add a README file", "Add .gitignore", "Choose a license" (у нас уже есть эти файлы)
4. Нажмите **Create repository**

## Шаг 2: Подключите remote репозиторий

После создания репозитория GitHub покажет вам команды. Выполните их в терминале:

```bash
# Замените YOUR_USERNAME на ваш GitHub username
git remote add origin https://github.com/YOUR_USERNAME/GymApp.git
git branch -M main
git push -u origin main
```

**Или если используете SSH:**
```bash
git remote add origin git@github.com:YOUR_USERNAME/GymApp.git
git branch -M main
git push -u origin main
```

## Шаг 3: Проверка

После успешного push проверьте на GitHub, что все файлы загружены.

## Если репозиторий уже существует

Если у вас уже есть репозиторий на GitHub, используйте его URL:

```bash
# Удалите старый remote (если был)
git remote remove origin

# Добавьте правильный remote
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git

# Переименуйте ветку в main (если нужно)
git branch -M main

# Загрузите код
git push -u origin main
```

## Если нужно объединить с существующими репозиториями

Если у вас уже есть `GymApp-frontend` и `GymApp-bot`, вы можете:

1. **Вариант 1**: Создать новый репозиторий `GymApp` и загрузить туда весь проект
2. **Вариант 2**: Использовать один из существующих репозиториев и обновить его

