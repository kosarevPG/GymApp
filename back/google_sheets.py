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
            
            # Кэш для последних строк LOG листа
            self._log_cache = None
            self._log_cache_timestamp = None
            self._log_cache_ttl = 300  # 5 минут в секундах
            
            logger.info("Google Sheets connected successfully")
        except Exception as e:
            logger.critical(f"GSheets Connection Error: {e}")
            raise
    
    def _get_log_values_cached(self, max_rows: int = 1000):
        """Получить последние N строк LOG листа с кэшированием"""
        import time
        current_time = time.time()
        
        # Проверяем, актуален ли кэш
        if (self._log_cache is not None and 
            self._log_cache_timestamp is not None and 
            (current_time - self._log_cache_timestamp) < self._log_cache_ttl):
            return self._log_cache
        
        # Читаем данные из Google Sheets
        try:
            # Получаем количество строк
            all_values = self.log_sheet.get_all_values()
            
            # Берем последние max_rows строк (или все, если меньше)
            if len(all_values) > max_rows:
                # Берем заголовок + последние max_rows строк
                cached_values = [all_values[0]] + all_values[-max_rows:]
            else:
                cached_values = all_values
            
            # Обновляем кэш
            self._log_cache = cached_values
            self._log_cache_timestamp = current_time
            
            logger.info(f"LOG cache updated: {len(cached_values)} rows (last {max_rows} rows)")
            return cached_values
        except Exception as e:
            logger.error(f"Error reading LOG sheet: {e}")
            # В случае ошибки возвращаем старый кэш, если есть
            if self._log_cache is not None:
                logger.warning("Using stale cache due to error")
                return self._log_cache
            return []
    
    def _invalidate_log_cache(self):
        """Инвалидировать кэш LOG листа (вызывать при записи новых данных)"""
        self._log_cache = None
        self._log_cache_timestamp = None
        logger.debug("LOG cache invalidated")

    def get_all_exercises(self) -> Dict:
        try:
            records = self.exercises_sheet.get_all_records()
            exercises = []
            groups = set()
            
            # Логируем заголовки для отладки
            if records:
                logger.info(f"Column headers in EXERCISES sheet: {list(records[0].keys())}")
            
            for r in records:
                if not r.get('ID') and not r.get('Name'): continue
                    
                group = r.get('Muscle Group', '').strip()
                if group: groups.add(group)
                
                image_url2 = r.get('Image_URL2', '') or r.get('Image_URL2 ', '')  # Проверяем с пробелом на конце
                if image_url2:
                    logger.debug(f"Found imageUrl2 for exercise {r.get('Name')}: {image_url2[:50]}...")
                
                exercises.append({
                    'id': str(r.get('ID', '')),
                    'name': r.get('Name', ''),
                    'muscleGroup': group,
                    'description': r.get('Description', ''),
                    'imageUrl': r.get('Image_URL', ''),
                    'imageUrl2': image_url2
                })
            
            # Сортируем упражнения по имени (Name)
            exercises.sort(key=lambda x: x.get('name', '').lower())
            
            return {"groups": sorted(list(groups)), "exercises": exercises}
        except Exception as e:
            logger.error(f"Get exercises error: {e}")
            return {"groups": [], "exercises": []}

    def create_exercise(self, name: str, group: str) -> Dict:
        new_id = str(uuid.uuid4())
        row = [new_id, name, group, "", "", ""]
        try:
            self.exercises_sheet.append_row(row)
            return {"id": new_id, "name": name, "muscleGroup": group, "description": "", "imageUrl": "", "imageUrl2": ""}
        except Exception as e:
            logger.error(f"Create exercise error: {e}")
            raise

    def update_exercise(self, ex_id: str, data: Dict) -> bool:
        try:
            cell = self.exercises_sheet.find(ex_id)
            if not cell: 
                logger.error(f"Exercise with ID {ex_id} not found")
                return False
            
            row_num = cell.row
            logger.info(f"Updating exercise at row {row_num}")
            
            # Получаем заголовки для проверки структуры
            headers = self.exercises_sheet.row_values(1)
            logger.info(f"Sheet headers: {headers}")
            
            # Определяем индексы колонок
            image_url_col = None
            image_url2_col = None
            
            for i, header in enumerate(headers, 1):
                header_lower = str(header).lower().strip().replace(' ', '_').replace('-', '_')
                if 'image' in header_lower and 'url' in header_lower:
                    if '2' in header_lower or header_lower.endswith('2'):
                        image_url2_col = i
                    elif image_url_col is None:
                        image_url_col = i
            
            # Если не нашли автоматически, используем стандартные индексы
            if image_url_col is None:
                image_url_col = 5  # Колонка E
            if image_url2_col is None:
                image_url2_col = 6  # Колонка F
            
            logger.info(f"Using columns: imageUrl={image_url_col}, imageUrl2={image_url2_col}")
            
            if 'name' in data: 
                self.exercises_sheet.update_cell(row_num, 2, data['name'])
                logger.debug(f"Updated name: {data['name']}")
            if 'muscleGroup' in data: 
                self.exercises_sheet.update_cell(row_num, 3, data['muscleGroup'])
                logger.debug(f"Updated muscleGroup: {data['muscleGroup']}")
            if 'imageUrl' in data: 
                image_url = data['imageUrl'] or ''
                self.exercises_sheet.update_cell(row_num, image_url_col, image_url)
                logger.info(f"Updated imageUrl in column {image_url_col} (length: {len(image_url)}): {image_url[:100] if image_url else 'empty'}...")
            if 'imageUrl2' in data: 
                image_url2 = data['imageUrl2'] or ''
                self.exercises_sheet.update_cell(row_num, image_url2_col, image_url2)
                logger.info(f"Updated imageUrl2 in column {image_url2_col} (length: {len(image_url2)}): {image_url2[:100] if image_url2 else 'empty'}...")
                # Проверяем, что значение сохранилось
                saved_value = self.exercises_sheet.cell(row_num, image_url2_col).value
                logger.info(f"Verified saved imageUrl2 value: {saved_value[:100] if saved_value else 'empty'}...")
            return True
        except Exception as e:
            logger.error(f"Update exercise error: {e}", exc_info=True)
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
            # Инвалидируем кэш при записи новых данных
            self._invalidate_log_cache()
            return True
        except Exception as e:
            logger.error(f"Save set error: {e}")
            return False

    def get_exercise_history(self, exercise_id: str, limit: int = 50) -> Dict:
        try:
            # Используем кэшированное чтение вместо get_all_values() для производительности
            all_values = self._get_log_values_cached(max_rows=1000)
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
                elif 'note' in header_lower and note_idx is None:
                    note_idx = i
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
                if len(row) <= max(ex_id_idx, date_idx, weight_idx, reps_idx, rest_idx, note_idx, order_idx or 0, set_group_idx or 0):
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
                    
                    # Получаем Set_Group_ID для определения суперсета
                    set_group_id = str(row[set_group_idx]).strip() if set_group_idx < len(row) and row[set_group_idx] else ''
                    
                    history_items.append({
                        'date': date_val,
                        'weight': weight,
                        'reps': reps,
                        'rest': rest,
                        'order': order,  # Добавляем ORDER для сортировки на фронтенде
                        'setGroupId': set_group_id if set_group_id else None,  # Добавляем setGroupId для индикации суперсета
                    })
            
            # Сортируем сначала по дате (от новых к старым), затем по ORDER внутри каждой даты
            # Преобразуем дату в формат для сортировки (YYYY.MM.DD)
            def sort_key(item):
                date_str = item.get('date', '')
                order = item.get('order', 0)
                # Если дата в формате YYYY.MM.DD, она уже сортируется лексикографически
                # Инвертируем для сортировки от новых к старым (reverse=True)
                return (date_str, order)
            
            # Сортируем по дате (от новых к старым), затем по ORDER
            history_items.sort(key=sort_key, reverse=True)
            
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
                
                # Логируем set_group_id для отладки (только первые несколько записей)
                if len(days[date_val]["exercises"]) < 3:
                    raw_value = row[set_group_idx] if set_group_idx < len(row) else 'N/A'
                    logger.info(f"  Set data: ex='{ex_name}', set_group_id='{set_group_id}', order={order}, raw_value='{raw_value}', set_group_idx={set_group_idx}")
                
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
                    
                    if set_group_id and set_group_id.strip():
                        # Это часть суперсета
                        logger.debug(f"Found superset set: exercise='{ex_name}', set_group_id='{set_group_id}', order={set_item['order']}")
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
                
                logger.info(f"Supersets dict: {len(supersets_dict)} groups")
                if supersets_dict:
                    logger.info(f"Supersets dict keys: {list(supersets_dict.keys())}")
                    for sg_id, exercises in supersets_dict.items():
                        logger.info(f"  Superset '{sg_id}': exercises={list(exercises.keys())}")
                else:
                    logger.info("No supersets found in this date")
                
                # Формируем список упражнений с сохранением группировки суперсетов
                exercises_list = []
                
                # Создаем список для сортировки: (min_order, is_superset, items)
                superset_groups = []  # [(min_order, [exercises])]
                standalone_list = []  # [(min_order, exercise)]
                
                # Обрабатываем суперсеты
                for set_group_id, exercises_in_superset in supersets_dict.items():
                    # Проверяем: если в группе только одно упражнение, это не суперсет
                    if len(exercises_in_superset) <= 1:
                        # Обрабатываем как обычное упражнение (без supersetId)
                        for ex_name, sets in exercises_in_superset.items():
                            sets.sort(key=lambda s: s.get("order", 0))
                            min_order = min(s.get("order", 0) for s in sets) if sets else 0
                            standalone_list.append((min_order, {
                                "name": ex_name,
                                "sets": [{"weight": s["weight"], "reps": s["reps"], "rest": s["rest"]} for s in sets]
                            }))
                        continue
                    
                    # Это настоящий суперсет (2+ упражнения)
                    # Сортируем упражнения в суперсете по первому ORDER
                    sorted_exercises = sorted(
                        exercises_in_superset.items(),
                        key=lambda x: min(s.get("order", 0) for s in x[1]) if x[1] else 0
                    )
                    
                    # Собираем упражнения суперсета
                    superset_exercises = []
                    min_order_in_superset = float('inf')
                    
                    for ex_name, sets in sorted_exercises:
                        # Сортируем подходы по ORDER
                        sets.sort(key=lambda s: s.get("order", 0))
                        exercise_data = {
                            "name": ex_name,
                            "sets": [{"weight": s["weight"], "reps": s["reps"], "rest": s["rest"]} for s in sets],
                            "supersetId": set_group_id  # Добавляем идентификатор суперсета только для настоящих суперсетов
                        }
                        superset_exercises.append(exercise_data)
                        # Находим минимальный ORDER в суперсете для сортировки
                        if sets:
                            min_order = min(s.get("order", 0) for s in sets)
                            min_order_in_superset = min(min_order_in_superset, min_order)
                    
                    if superset_exercises:
                        superset_groups.append((min_order_in_superset, superset_exercises))
                
                # Обрабатываем обычные упражнения
                for ex_name, sets in standalone_exercises.items():
                    # Сортируем подходы по ORDER
                    sets.sort(key=lambda s: s.get("order", 0))
                    min_order = min(s.get("order", 0) for s in sets) if sets else 0
                    standalone_list.append((min_order, {
                        "name": ex_name,
                        "sets": [{"weight": s["weight"], "reps": s["reps"], "rest": s["rest"]} for s in sets]
                    }))
                
                # Сортируем суперсеты по минимальному ORDER
                superset_groups.sort(key=lambda x: x[0])
                # Сортируем обычные упражнения по ORDER
                standalone_list.sort(key=lambda x: x[0])
                
                # Объединяем: сначала суперсеты, затем обычные упражнения, все по порядку ORDER
                all_items = [(order, items, True) for order, items in superset_groups] + \
                           [(order, [item], False) for order, item in standalone_list]
                all_items.sort(key=lambda x: x[0])
                
                # Формируем финальный список, сохраняя группировку суперсетов
                for order, items, is_superset_group in all_items:
                    exercises_list.extend(items)
                
                logger.info(f"Date {date_val}: {len(superset_groups)} superset groups, {len(standalone_list)} standalone exercises")
                for ex in exercises_list:
                    superset_id = ex.get('supersetId', 'none')
                    logger.info(f"  Exercise '{ex['name']}': {len(ex['sets'])} sets, supersetId: {superset_id}")
                    if superset_id != 'none':
                        logger.info(f"    -> Part of superset: {superset_id}")
                
                # Подсчитываем примерную длительность (5 минут на упражнение)
                duration_minutes = len(exercises_list) * 5
                
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
