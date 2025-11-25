#!/bin/bash
set -e

# Обновляем pip
pip install --upgrade pip setuptools wheel

# Проверяем версию Python
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo "Python version: $PYTHON_VERSION"

# Для Python 3.13 используем более новую версию pydantic с wheels
if [[ "$PYTHON_VERSION" == "3.13" ]]; then
    echo "Python 3.13 detected - using compatible pydantic version"
    # Устанавливаем aiogram без pydantic (он установит свою версию)
    pip install --prefer-binary aiogram==3.1.1 --no-deps
    # Устанавливаем совместимую версию pydantic вручную
    pip install --prefer-binary "pydantic>=2.1.1,<2.4" || pip install --only-binary :all: "pydantic>=2.1.1,<2.4"
else
    # Для Python 3.11 используем стандартную установку
    echo "Python 3.11 or earlier - using standard installation"
    pip install --prefer-binary -r requirements.txt
fi

# Устанавливаем остальные зависимости
pip install --prefer-binary "aiohttp>=3.8.5,<3.9.0" gspread==5.12.0 google-auth==2.23.4 google-auth-oauthlib==1.1.0 google-auth-httplib2==0.1.1 python-dotenv==1.0.0

