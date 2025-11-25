"""
Модуль для работы с Google Sheets API.
Версия для продакшена: чтение credentials из файла.
"""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Optional, Any
import logging
import os
import json
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

class DataParser:
    @staticmethod
    def to_float(value: Any, default: float = 0.0) -> float:
        if not value: return default
        try:
            clean_val = str(value).replace(',', '.').strip()
            return float(clean_val)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def to_int(value: Any, default: int = 0) -> int:
        try:
            return int(DataParser.to_float(value, default))
        except (ValueError, TypeError):
            return default

class GoogleSheetsManager:
    def __init__(self, credentials_path: str = None, spreadsheet_id: str = None):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            
            creds_path = credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH")
            
            if creds_path and os.path.exists(creds_path):
                creds = Credentials.from_service_account_file(creds_path, scopes=scope)
            else:
                creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
                if creds_json:
                    creds = Credentials.from_service_account_info(json.loads(creds_json), scopes=scope)
                else:
                    raise ValueError("Credentials not found. Check GOOGLE_CREDENTIALS_PATH.")
            
            self.client = gspread.authorize(creds)
            
            self.spreadsheet_id = spreadsheet_id or os.getenv("SPREADSHEET_ID")
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            
            self.log_sheet = self.spreadsheet.worksheet('LOG')
            self.exercises_sheet = self.spreadsheet.worksheet('EXERCISES')
            
            logger.info("Google Sheets connected successfully")
        except Exception as e:
            logger.critical(f"GSheets Connection Error: {e}")
            raise

    def get_all_exercises(self) -> Dict:
        try:
            records = self.exercises_sheet.get_all_records()
            exercises = []
            groups = set()
            
            for r in records:
                if not r.get('ID') and not r.get('Name'): continue
                    
                group = r.get('Muscle Group', '').strip()
                if group: groups.add(group)
                
                exercises.append({
                    'id': str(r.get('ID', '')),
                    'name': r.get('Name', ''),
                    'muscleGroup': group,
                    'description': r.get('Description', ''),
                    'imageUrl': r.get('Image_URL', '')
                })
            
            return {"groups": sorted(list(groups)), "exercises": exercises}
        except Exception as e:
            logger.error(f"Get exercises error: {e}")
            return {"groups": [], "exercises": []}

    def create_exercise(self, name: str, group: str) -> Dict:
        new_id = str(uuid.uuid4())
        row = [new_id, name, group, "", "", ""]
        try:
            self.exercises_sheet.append_row(row)
            return {"id": new_id, "name": name, "muscleGroup": group, "description": "", "imageUrl": ""}
        except Exception as e:
            logger.error(f"Create exercise error: {e}")
            raise

    def update_exercise(self, ex_id: str, data: Dict) -> bool:
        try:
            cell = self.exercises_sheet.find(ex_id)
            if not cell: return False
            
            row_num = cell.row
            if 'name' in data: self.exercises_sheet.update_cell(row_num, 2, data['name'])
            if 'muscleGroup' in data: self.exercises_sheet.update_cell(row_num, 3, data['muscleGroup'])
            if 'imageUrl' in data: self.exercises_sheet.update_cell(row_num, 5, data['imageUrl'])
            return True
        except Exception as e:
            logger.error(f"Update exercise error: {e}")
            return False

    def save_workout_set(self, data: Dict) -> bool:
        try:
            timestamp = datetime.now().strftime('%Y.%m.%d, %H:%M')
            row = [
                timestamp,
                data.get('exercise_id'),
                "", 
                DataParser.to_float(data.get('weight')),
                DataParser.to_int(data.get('reps')),
                DataParser.to_float(data.get('rest')),
                data.get('set_group_id'),
                data.get('note', ''),
                DataParser.to_int(data.get('order'))
            ]
            self.log_sheet.append_row(row)
            return True
        except Exception as e:
            logger.error(f"Save set error: {e}")
            return False

    def get_exercise_history(self, exercise_id: str, limit: int = 50) -> Dict:
        try:
            # Используем get_all_values() вместо get_all_records() для работы с дублирующимися заголовками
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return {"history": [], "note": ""}
            
            # Первая строка - заголовки
            headers = all_values[0]
            # Остальные строки - данные
            data_rows = all_values[1:]
            
            # Находим индексы нужных колонок
            ex_id_idx = None
            date_idx = None
            weight_idx = None
            reps_idx = None
            rest_idx = None
            note_idx = None
            order_idx = None
            
            for i, header in enumerate(headers):
                header_lower = str(header).lower().strip().replace(' ', '_').replace('-', '_')
                if 'exercise' in header_lower and 'id' in header_lower and ex_id_idx is None:
                    ex_id_idx = i
                elif 'date' in header_lower and date_idx is None:
                    date_idx = i
                elif 'weight' in header_lower and weight_idx is None:
                    weight_idx = i
                elif ('reps' in header_lower or 'repetitions' in header_lower) and reps_idx is None:
                    reps_idx = i
                elif 'rest' in header_lower and rest_idx is None:
                    rest_idx = i
                elif 'note' in header_lower and note_idx is None:
                    note_idx = i
                elif 'order' in header_lower and order_idx is None:
                    order_idx = i
            
            # Если не нашли автоматически, используем стандартные индексы (A-I)
            # Порядок колонок: Date, Exercise_ID, (пустая), Weight, Reps, Rest, Set_Group_ID, Note, Order
            if ex_id_idx is None:
                ex_id_idx = 1  # Колонка B
            if date_idx is None:
                date_idx = 0  # Колонка A
            if weight_idx is None:
                weight_idx = 3  # Колонка D
            if reps_idx is None:
                reps_idx = 4  # Колонка E
            if rest_idx is None:
                rest_idx = 5  # Колонка F
            if note_idx is None:
                note_idx = 7  # Колонка H
            if order_idx is None:
                order_idx = 8  # Колонка I
            
            logger.info(f"Looking for exercise_id: {exercise_id}")
            logger.info(f"Headers: {headers}")
            logger.info(f"Column indices - ex_id: {ex_id_idx}, date: {date_idx}, weight: {weight_idx}, reps: {reps_idx}, rest: {rest_idx}, note: {note_idx}, order: {order_idx}")
            
            history_items = []
            last_note = ""
            exercise_id_str = str(exercise_id).strip()
            
            # Собираем все записи для данного упражнения
            for row in data_rows:
                if len(row) <= max(ex_id_idx, date_idx, weight_idx, reps_idx, rest_idx, note_idx, order_idx or 0):
                    continue
                
                # Получаем ID упражнения из строки
                record_ex_id = str(row[ex_id_idx]).strip() if ex_id_idx < len(row) else ''
                
                if record_ex_id == exercise_id_str:
                    # Получаем заметку (только первую найденную - берем самую раннюю по ORDER)
                    if not last_note and note_idx < len(row) and row[note_idx]:
                        last_note = str(row[note_idx]).strip()
                    
                    # Получаем дату
                    date_val = ''
                    if date_idx < len(row) and row[date_idx]:
                        date_val = str(row[date_idx]).split(',')[0].strip()
                    
                    # Получаем данные подхода
                    weight = DataParser.to_float(row[weight_idx] if weight_idx < len(row) else '')
                    reps = DataParser.to_int(row[reps_idx] if reps_idx < len(row) else '')
                    rest = DataParser.to_float(row[rest_idx] if rest_idx < len(row) else '')
                    
                    # Получаем ORDER для сортировки
                    order = DataParser.to_int(row[order_idx] if order_idx and order_idx < len(row) else '', 0)
                    
                    history_items.append({
                        'date': date_val,
                        'weight': weight,
                        'reps': reps,
                        'rest': rest,
                        'order': order,  # Добавляем ORDER для сортировки на фронтенде
                    })
            
            # Сортируем по ORDER от меньшего к большему (от старых к новым)
            history_items.sort(key=lambda x: x.get('order', 0))
            
            # Ограничиваем количество записей
            if len(history_items) > limit:
                history_items = history_items[:limit]
            
            logger.info(f"Found {len(history_items)} history items for exercise_id: {exercise_id}")
            return {"history": history_items, "note": last_note}
        except Exception as e:
            logger.error(f"Get history error: {e}", exc_info=True)
            return {"history": [], "note": ""}

    def get_global_history(self) -> List[Dict]:
        try:
            # Используем get_all_values() вместо get_all_records() для работы с дублирующимися заголовками
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return []
            
            # Первая строка - заголовки
            headers = all_values[0]
            # Остальные строки - данные
            data_rows = all_values[1:]
            
            all_ex_data = self.get_all_exercises()
            exercises_map = {e['id']: e for e in all_ex_data['exercises']}
            
            # Находим индексы нужных колонок
            ex_id_idx = None
            date_idx = None
            weight_idx = None
            reps_idx = None
            rest_idx = None
            order_idx = None
            set_group_idx = None
            
            for i, header in enumerate(headers):
                header_lower = str(header).lower().strip().replace(' ', '_').replace('-', '_')
                if 'exercise' in header_lower and 'id' in header_lower and ex_id_idx is None:
                    ex_id_idx = i
                elif 'date' in header_lower and date_idx is None:
                    date_idx = i
                elif 'weight' in header_lower and weight_idx is None:
                    weight_idx = i
                elif ('reps' in header_lower or 'repetitions' in header_lower) and reps_idx is None:
                    reps_idx = i
                elif 'rest' in header_lower and rest_idx is None:
                    rest_idx = i
                elif 'order' in header_lower and order_idx is None:
                    order_idx = i
                elif ('set' in header_lower and 'group' in header_lower) or 'group_id' in header_lower:
                    if set_group_idx is None:
                        set_group_idx = i
            
            # Если не нашли автоматически, используем стандартные индексы (A-I)
            # Порядок колонок: Date, Exercise_ID, (пустая), Weight, Reps, Rest, Set_Group_ID, Note, Order
            if ex_id_idx is None:
                ex_id_idx = 1  # Колонка B
            if date_idx is None:
                date_idx = 0  # Колонка A
            if weight_idx is None:
                weight_idx = 3  # Колонка D
            if reps_idx is None:
                reps_idx = 4  # Колонка E
            if rest_idx is None:
                rest_idx = 5  # Колонка F
            if set_group_idx is None:
                set_group_idx = 6  # Колонка G
            if order_idx is None:
                order_idx = 8  # Колонка I
            
            # Группируем по дате
            days = {}
            
            for row in data_rows:
                if len(row) <= max(ex_id_idx, date_idx, weight_idx, reps_idx, rest_idx, order_idx or 0):
                    continue
                
                # Получаем дату
                date_val = ''
                if date_idx < len(row) and row[date_idx]:
                    date_val = str(row[date_idx]).split(',')[0].strip()
                
                if not date_val:
                    continue
                
                # Получаем данные упражнения
                ex_id = str(row[ex_id_idx]).strip() if ex_id_idx < len(row) else ''
                if not ex_id:
                    continue
                
                ex_info = exercises_map.get(ex_id, {})
                ex_name = ex_info.get('name', 'Unknown')
                muscle = ex_info.get('muscleGroup', 'Other')
                
                # Инициализируем день, если его еще нет
                if date_val not in days:
                    days[date_val] = {
                        "date": date_val,
                        "muscleGroups": set(),
                        "exercises": []  # Список всех подходов в порядке выполнения
                    }
                
                # Добавляем группу мышц
                days[date_val]["muscleGroups"].add(muscle)
                
                # Получаем данные подхода
                weight = DataParser.to_float(row[weight_idx] if weight_idx < len(row) else '')
                reps = DataParser.to_int(row[reps_idx] if reps_idx < len(row) else '')
                rest = DataParser.to_float(row[rest_idx] if rest_idx < len(row) else '')
                order = DataParser.to_int(row[order_idx] if order_idx and order_idx < len(row) else '', 0)
                set_group_id = str(row[set_group_idx]).strip() if set_group_idx < len(row) and row[set_group_idx] else ''
                
                # Добавляем подход в общий список (для сортировки по ORDER)
                days[date_val]["exercises"].append({
                    "exerciseName": ex_name,
                    "exerciseId": ex_id,
                    "muscleGroup": muscle,
                    "weight": weight,
                    "reps": reps,
                    "rest": rest,
                    "order": order,
                    "setGroupId": set_group_id
                })
            
            # Формируем результат
            result = []
            for date_val, day_data in days.items():
                # Сортируем все подходы по ORDER (порядок выполнения)
                day_data["exercises"].sort(key=lambda x: x.get('order', 0))
                
                logger.info(f"Processing date {date_val}: {len(day_data['exercises'])} total sets")
                
                # Группируем подходы по Set_Group_ID, затем по упражнениям
                # Это позволяет группировать суперсеты вместе
                supersets_dict = {}  # {set_group_id: {exercise_name: [sets]}}
                standalone_exercises = {}  # {exercise_name: [sets]} для упражнений без Set_Group_ID
                
                for set_data in day_data["exercises"]:
                    ex_name = set_data["exerciseName"]
                    if not ex_name or ex_name == 'Unknown':
                        logger.warning(f"Skipping set with unknown exercise: {set_data}")
                        continue
                    
                    set_group_id = set_data.get("setGroupId", "")
                    set_item = {
                        "weight": float(set_data["weight"]) if set_data["weight"] is not None else 0.0,
                        "reps": int(set_data["reps"]) if set_data["reps"] is not None else 0,
                        "rest": float(set_data["rest"]) if set_data["rest"] is not None else 0.0,
                        "order": set_data.get("order", 0)
                    }
                    
                    if set_group_id:
                        # Это часть суперсета
                        if set_group_id not in supersets_dict:
                            supersets_dict[set_group_id] = {}
                        if ex_name not in supersets_dict[set_group_id]:
                            supersets_dict[set_group_id][ex_name] = []
                        supersets_dict[set_group_id][ex_name].append(set_item)
                    else:
                        # Обычное упражнение без суперсета
                        if ex_name not in standalone_exercises:
                            standalone_exercises[ex_name] = []
                        standalone_exercises[ex_name].append(set_item)
                
                # Формируем список упражнений
                exercises_list = []
                
                # Сначала добавляем суперсеты (группируем упражнения из одного Set_Group_ID)
                for set_group_id, exercises_in_superset in supersets_dict.items():
                    # Сортируем упражнения в суперсете по первому ORDER
                    sorted_exercises = sorted(
                        exercises_in_superset.items(),
                        key=lambda x: min(s.get("order", 0) for s in x[1]) if x[1] else 0
                    )
                    
                    # Добавляем каждое упражнение из суперсета с идентификатором суперсета
                    for ex_name, sets in sorted_exercises:
                        # Сортируем подходы по ORDER
                        sets.sort(key=lambda s: s.get("order", 0))
                        exercises_list.append({
                            "name": ex_name,
                            "sets": [{"weight": s["weight"], "reps": s["reps"], "rest": s["rest"]} for s in sets],
                            "supersetId": set_group_id  # Добавляем идентификатор суперсета
                        })
                
                # Затем добавляем обычные упражнения
                for ex_name, sets in standalone_exercises.items():
                    # Сортируем подходы по ORDER
                    sets.sort(key=lambda s: s.get("order", 0))
                    exercises_list.append({
                        "name": ex_name,
                        "sets": [{"weight": s["weight"], "reps": s["reps"], "rest": s["rest"]} for s in sets]
                    })
                
                # Сортируем весь список по минимальному ORDER в каждом упражнении
                exercises_list.sort(key=lambda ex: min(s.get("order", 0) for s in ex["sets"]) if ex["sets"] else 0)
                
                # Подсчитываем примерную длительность (5 минут на упражнение)
                duration_minutes = len(exercises_list) * 5
                
                logger.info(f"Date {date_val}: {len(exercises_list)} exercises, total sets: {sum(len(ex['sets']) for ex in exercises_list)}")
                for ex in exercises_list:
                    logger.info(f"  Exercise '{ex['name']}': {len(ex['sets'])} sets")
                    # Логируем первый сет для проверки структуры
                    if ex['sets'] and len(ex['sets']) > 0:
                        logger.info(f"    First set: {ex['sets'][0]}")
                
                result.append({
                    "id": date_val,  # Используем дату как ID
                    "date": date_val,
                    "muscleGroups": sorted(list(day_data["muscleGroups"])),
                    "duration": f"{duration_minutes}м",
                    "exercises": exercises_list
                })
            
            # Сортируем по дате (от новых к старым)
            result.sort(key=lambda x: x.get('date', ''), reverse=True)
            return result
        except Exception as e:
            logger.error(f"Global history error: {e}", exc_info=True)
            return []
