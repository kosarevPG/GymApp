#!/usr/bin/env python3
"""
Миграция: перенос Type, Base_Wt, Multiplier из REF_Exercises в EXERCISES.
Запуск: python migrate_ref_to_exercises.py
После миграции REF_Exercises можно удалить вручную.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    from google_sheets import GoogleSheetsManager
    
    if not os.getenv("SPREADSHEET_ID"):
        print("Ошибка: SPREADSHEET_ID не задан")
        sys.exit(1)
    
    try:
        gs = GoogleSheetsManager()
        ex_sheet = gs.exercises_sheet
        headers = ex_sheet.row_values(1)
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        sys.exit(1)
    
    # 1. Добавить заголовки Weight_Type, Base_Wt, Multiplier в EXERCISES если нет
    need_headers = []
    if not any(str(h).lower().replace(' ', '_') in ('weight_type', 'weighttype') for h in headers):
        need_headers.append('Weight_Type')
    if not any(str(h).lower().replace(' ', '_') in ('base_wt', 'base_weight', 'baseweight') for h in headers):
        need_headers.append('Base_Wt')
    if not any(str(h).lower().replace(' ', '_') == 'multiplier' for h in headers):
        need_headers.append('Multiplier')
    
    if need_headers:
        col = len(headers) + 1
        for h in need_headers:
            ex_sheet.update_cell(1, col, h)
            col += 1
        print(f"Добавлены заголовки: {need_headers}")
    
    # 2. Миграция данных из REF_Exercises в EXERCISES
    try:
        ref_ex = gs.spreadsheet.worksheet('REF_Exercises')
        ref_rows = ref_ex.get_all_values()
    except Exception:
        print("REF_Exercises не найден — пропуск миграции данных")
        sys.exit(0)
    
    if len(ref_rows) < 2:
        print("REF_Exercises пуст")
        sys.exit(0)
    
    ex_rows = ex_sheet.get_all_values()
    if len(ex_rows) < 2:
        print("EXERCISES пуст")
        sys.exit(0)
    
    ex_headers = ex_rows[0]
    id_col = next((i for i, h in enumerate(ex_headers) if str(h).strip().lower() == 'id'), 0)
    wt_col = next((i for i, h in enumerate(ex_headers) if str(h).lower().replace(' ', '_') in ('weight_type', 'weighttype')), -1)
    base_col = next((i for i, h in enumerate(ex_headers) if str(h).lower().replace(' ', '_') in ('base_wt', 'base_weight', 'baseweight')), -1)
    mult_col = next((i for i, h in enumerate(ex_headers) if str(h).lower().replace(' ', '_') == 'multiplier'), -1)
    
    if wt_col < 0 or base_col < 0 or mult_col < 0:
        print("Колонки Weight_Type/Base_Wt/Multiplier не найдены в EXERCISES")
        sys.exit(1)
    
    ref_map = {}
    for row in ref_rows[1:]:
        if len(row) >= 5 and str(row[0]).strip():
            ref_map[str(row[0]).strip()] = {
                'type': str(row[2]).strip() if len(row) > 2 else '',
                'base_wt': float(str(row[3]).replace(',', '.')) if len(row) > 3 and row[3] else 0,
                'multiplier': int(float(str(row[4]).replace(',', '.'))) if len(row) > 4 and row[4] else 1
            }
    
    updated = 0
    for i, row in enumerate(ex_rows[1:], start=2):
        if len(row) <= id_col:
            continue
        ex_id = str(row[id_col]).strip()
        ref_data = ref_map.get(ex_id)
        if not ref_data:
            continue
        ex_sheet.update_cell(i, wt_col + 1, ref_data['type'])
        ex_sheet.update_cell(i, base_col + 1, ref_data['base_wt'])
        ex_sheet.update_cell(i, mult_col + 1, ref_data['multiplier'])
        updated += 1
    
    print(f"Мигрировано {updated} упражнений из REF_Exercises в EXERCISES")
    print("REF_Exercises можно удалить вручную из таблицы.")

if __name__ == '__main__':
    main()
