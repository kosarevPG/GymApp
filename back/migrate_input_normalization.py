#!/usr/bin/env python3
"""
Миграция Google Sheets: Input Normalization schema.
Создаёт REF_Exercises, REF_Bio, добавляет колонки и формулу в LOG.

Запуск: python migrate_input_normalization.py
Требует: SPREADSHEET_ID, GOOGLE_CREDENTIALS_PATH или GOOGLE_CREDENTIALS_JSON
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    from google_sheets import GoogleSheetsManager
    
    spreadsheet_id = os.getenv("SPREADSHEET_ID")
    if not spreadsheet_id:
        print("Ошибка: SPREADSHEET_ID не задан")
        sys.exit(1)
    
    try:
        gs = GoogleSheetsManager()
        ss = gs.spreadsheet
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        sys.exit(1)
    
    # 1. REF_Exercises — создаём и заполняем из EXERCISES
    try:
        ref_ex = ss.worksheet('REF_Exercises')
        print("REF_Exercises уже существует")
    except Exception:
        ref_ex = ss.add_worksheet(title='REF_Exercises', rows=500, cols=5)
        ref_ex.append_row(['ID', 'Name', 'Type', 'Base_Wt', 'Multiplier'])
        ex_data = gs.get_all_exercises()
        for ex in ex_data.get('exercises', []):
            eid = ex.get('id', '')
            name = ex.get('name', '')
            eq = (ex.get('equipmentType') or 'dumbbell').lower()
            if eq == 'barbell':
                t, base, mult = 'Barbell', 20, 2
            elif eq == 'machine':
                # По умолчанию Plate_Loaded (жим ногами). Ручная правка на Machine для блочных.
                t, base, mult = 'Plate_Loaded', 50, 2
            elif 'assist' in (name or '').lower() or 'гравитрон' in (name or '').lower():
                t, base, mult = 'Assisted', 0, 1
            else:
                t, base, mult = 'Dumbbell', 0, 1
            ref_ex.append_row([eid, name, t, base, mult])
        print(f"REF_Exercises создан, добавлено {len(ex_data.get('exercises', []))} упражнений")
    
    # 2. REF_Bio
    try:
        ref_bio = ss.worksheet('REF_Bio')
        print("REF_Bio уже существует")
    except Exception:
        ref_bio = ss.add_worksheet(title='REF_Bio', rows=500, cols=2)
        ref_bio.append_row(['Date', 'Body_Weight_Kg'])
        from datetime import datetime
        ref_bio.append_row([datetime.now().strftime('%Y-%m-%d'), 90])
        print("REF_Bio создан (пример: 90 кг)")
    
    # 3. Маппинг EXERCISES.id → REF_Exercises (нужно связать по ID)
    # Пока REF_Exercises — справочник типов. Связь: EXERCISES.equipmentType → Type
    # Для формулы нужен ID из REF_Exercises. Вариант: дублировать EXERCISES в REF_Exercises
    # или использовать EXERCISES как источник Type. Упростим: формула смотрит в EXERCISES.
    
    # 4. Формула для LOG
    # Текущая структура LOG: A=Date, B=Exercise_ID, K=Input_Weight (11-я колонка)
    # Добавляем L=Effective_Load_Kg (12-я) с формулой
    # Но EXERCISES не имеет Type/Base_Wt в том же формате. Нужен REF_Exercises с ID = Exercise_ID.
    # Миграция: копируем EXERCISES в REF_Exercises с нужными колонками.
    
    # 5. Добавляем формулу в LOG (колонка L = 12, Input_Weight в K = 11)
    log = gs.log_sheet
    try:
        l1 = log.cell(1, 12).value
        if not l1 or l1.strip() == '':
            log.update_cell(1, 12, 'Effective_Load_Kg')
        formula = formula_for_h2()
        log.update_acell('L2', formula)
        print("\nФормула добавлена в L2. Протяните вниз.")
    except Exception as e:
        print(f"\nНе удалось добавить формулу: {e}")

    # 6. Total_Weight (M = 13) — нормализованный вес для аналитики и рекордов
    try:
        m1 = log.cell(1, 13).value
        if not m1 or m1.strip() == '':
            log.update_cell(1, 13, 'Total_Weight')
            print("Заголовок Total_Weight добавлен в M1.")
        # Бэкфилл: копируем Weight (D) в Total_Weight (M) батчем
        all_vals = log.get_all_values()
        if len(all_vals) >= 2:
            m_col = []
            for i in range(1, min(len(all_vals), 1000)):
                row = all_vals[i]
                if len(row) >= 4 and row[3]:
                    try:
                        w = float(str(row[3]).replace(',', '.'))
                        m_col.append([w] if w > 0 else [''])
                    except (ValueError, TypeError):
                        m_col.append([''])
                else:
                    m_col.append([''])
            if m_col:
                log.update(f'M2:M{1 + len(m_col)}', m_col, value_input_option='USER_ENTERED')
                print(f"Total_Weight: заполнено {len(m_col)} строк из Weight.")
    except Exception as e:
        print(f"Total_Weight: {e}")

    print("\n--- РУЧНАЯ НАСТРОЙКА ---")
    print("1. REF_Exercises: при необходимости измените Type, Base_Wt для упражнений.")
    print("2. REF_Bio: добавьте даты и вес тела для Assisted упражнений.")


def formula_for_h2():
    """Формула для L2. Input_Weight в K, Effective_Load_Kg в L."""
    return (
        '=IF(OR(K2="",ISBLANK(K2)),"",IFERROR(LET('
        'ex_id,B2,input_wt,VALUE(K2),'
        'dt,IF(ISNUMBER(A2),A2,DATEVALUE(SUBSTITUTE(LEFT(A2,10),".","-"))),'
        'ex_type,IFERROR(VLOOKUP(ex_id,REF_Exercises!A:E,3,FALSE),"Dumbbell"),'
        'base_wt,IFERROR(VLOOKUP(ex_id,REF_Exercises!A:E,4,FALSE),0),'
        'user_wt,IFERROR(VLOOKUP(dt,SORT(REF_Bio!A:B,1,TRUE),2,TRUE),90),'
        'SWITCH(ex_type,"Barbell",(input_wt*2)+base_wt,"Plate_Loaded",(input_wt*2)+base_wt,'
        '"Assisted",MAX(0,user_wt-input_wt),"Bodyweight",user_wt+input_wt,'
        '"Machine",input_wt,"Dumbbell",input_wt,input_wt)'
        '),""))'
    )


if __name__ == '__main__':
    main()
