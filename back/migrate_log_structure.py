#!/usr/bin/env python3
"""
Миграция структуры LOG: переход на 10 колонок.
Было: Date, Exercise_ID, Exercise_Name_Calc, Weight, Reps, Rest, Set_Group_ID, Note, Order, [RIR], Input_Weight, Effective_Load_Kg, Total_Weight
Стало: Date, Exercise_ID, Exercise_Name_Calc, Input_Weight, Total_Weight, Reps, Rest, Set_Group_ID, Note, Order

Запуск: python migrate_log_structure.py
"""

import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

def find_col(headers, candidates):
    for i, h in enumerate(headers):
        hl = str(h).lower().strip().replace(' ', '_').replace('-', '_')
        for c in candidates:
            if c in hl:
                return i
    return -1


def extract_value(row, idx, default=''):
    if idx < len(row) and row[idx] is not None and str(row[idx]).strip():
        return str(row[idx]).strip()
    return default


def extract_float(row, idx, default=0):
    try:
        val = extract_value(row, idx, '')
        if val:
            return float(str(val).replace(',', '.'))
    except (ValueError, TypeError):
        pass
    return default


def main():
    from google_sheets import GoogleSheetsManager

    if not os.getenv("SPREADSHEET_ID"):
        print("Ошибка: SPREADSHEET_ID не задан")
        sys.exit(1)

    try:
        gs = GoogleSheetsManager()
        log = gs.log_sheet
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        sys.exit(1)

    all_rows = log.get_all_values()
    if len(all_rows) < 2:
        print("LOG пуст или содержит только заголовок")
        sys.exit(0)

    headers = all_rows[0]
    data_rows = all_rows[1:]

    def col(h, candidates, default):
        r = find_col(headers, candidates)
        return r if r >= 0 else default

    old_date = col(headers, ['date', 'дата'], 0)
    old_ex_id = col(headers, ['exercise_id', 'ex_id'], 1)
    old_name = col(headers, ['exercise_name', 'name_calc', 'name'], 2)
    old_weight = col(headers, ['weight', 'вес'], 3)
    old_reps = col(headers, ['reps', 'повтор'], 4)
    old_rest = col(headers, ['rest', 'отдых'], 5)
    old_set_group = col(headers, ['set_group', 'group'], 6)
    old_note = col(headers, ['note', 'заметка'], 7)
    old_order = col(headers, ['order'], 8)
    old_input = col(headers, ['input_weight', 'inputweight'], 10)
    old_effective = col(headers, ['effective', 'effective_load'], 11)
    old_total = col(headers, ['total_weight', 'totalweight'], 12)

    new_headers = ['Date', 'Exercise_ID', 'Exercise_Name_Calc', 'Input_Weight', 'Total_Weight', 'Reps', 'Rest', 'Set_Group_ID', 'Note', 'Order']

    new_rows = [new_headers]
    for row in data_rows:
        if len(row) < 4:
            continue
        date_val = extract_value(row, old_date)
        ex_id = extract_value(row, old_ex_id)
        ex_name = extract_value(row, old_name)
        input_wt = extract_float(row, old_input)
        if input_wt == 0:
            input_wt = extract_float(row, old_weight)
        total_wt = extract_float(row, old_total)
        if total_wt == 0:
            total_wt = extract_float(row, old_effective)
        if total_wt == 0:
            total_wt = extract_float(row, old_weight)
        reps = int(extract_float(row, old_reps))
        rest = extract_float(row, old_rest)
        set_group = extract_value(row, old_set_group)
        note = extract_value(row, old_note)
        order = int(extract_float(row, old_order))

        new_rows.append([
            date_val,
            ex_id,
            ex_name,
            input_wt if input_wt else '',
            total_wt if total_wt else '',
            reps,
            rest,
            set_group,
            note,
            order
        ])

    log.clear()
    if len(new_rows) > 1:
        log.update('A1', new_rows, value_input_option='USER_ENTERED')
        print(f"Мигрировано {len(new_rows) - 1} строк в новую структуру LOG")
    else:
        log.update('A1', [new_headers])
        print("Обновлены заголовки LOG. Данных для миграции не было.")
    print("Структура LOG: Date, Exercise_ID, Exercise_Name_Calc, Input_Weight, Total_Weight, Reps, Rest, Set_Group_ID, Note, Order")


if __name__ == '__main__':
    main()
