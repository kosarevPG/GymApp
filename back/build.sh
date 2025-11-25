#!/bin/bash
set -e

# Обновляем pip
pip install --upgrade pip setuptools wheel

# Устанавливаем зависимости, предпочитая бинарные пакеты
pip install --prefer-binary -r requirements.txt

