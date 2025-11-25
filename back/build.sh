#!/bin/bash
set -e

# Обновляем pip
pip install --upgrade pip setuptools wheel

# Устанавливаем pydantic с предкомпилированными wheels
pip install --only-binary pydantic,pydantic-core pydantic==2.5.3

# Устанавливаем остальные зависимости
pip install -r requirements.txt

