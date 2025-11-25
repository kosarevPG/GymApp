#!/bin/bash
set -e

# Обновляем pip
pip install --upgrade pip setuptools wheel

# Устанавливаем зависимости, предпочитая бинарные пакеты
pip install --upgrade --only-binary :all: -r requirements.txt || pip install -r requirements.txt

