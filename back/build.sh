#!/bin/bash
set -e

# Обновляем pip
pip install --upgrade pip setuptools wheel

# Устанавливаем pydantic с предкомпилированными wheels (совместим с aiogram 3.1.1)
pip install --prefer-binary "pydantic>=2.1.1,<2.4"

# Устанавливаем остальные зависимости
pip install --prefer-binary -r requirements.txt

