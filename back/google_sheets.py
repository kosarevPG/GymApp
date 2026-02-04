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
from datetime import datetime, timezone, timedelta

# Московское время (UTC+3)
MOSCOW_TZ = timezone(timedelta(hours=3))

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

    def _find_key_case_insensitive(self, record: Dict, candidates: List[str]) -> str:
        """Поиск значения в словаре по списку ключей (без учета регистра и пробелов)"""
        record_keys = {k.lower().strip(): k for k in record.keys()}
        
        for candidate in candidates:
            candidate_clean = candidate.lower().strip()
            if candidate_clean in record_keys:
                real_key = record_keys[candidate_clean]
                val = record.get(real_key)
                if val: return str(val) # Возвращаем только если значение не пустое
        return ""

    def get_all_exercises(self) -> Dict:
        try:
            records = self.exercises_sheet.get_all_records()
            exercises = []
            groups = set()
            
            # Логируем заголовки для отладки
            if records:
                logger.info(f"Column headers in EXERCISES sheet: {list(records[0].keys())}")
            
            for r in records:
                # Робастный поиск полей
                id_val = self._find_key_case_insensitive(r, ['ID', 'id'])
                name_val = self._find_key_case_insensitive(r, ['Name', 'name', 'Название'])
                
                if not id_val and not name_val: continue
                    
                group = self._find_key_case_insensitive(r, ['Muscle Group', 'muscle_group', 'Group', 'group', 'Группа'])
                if group: groups.add(group)
                
                description = self._find_key_case_insensitive(r, ['Description', 'description', 'Desc', 'Описание', 'Note', 'Заметка'])
                image_url = self._find_key_case_insensitive(r, ['Image_URL', 'image_url', 'Image', 'image', 'Фото'])
                image_url2 = self._find_key_case_insensitive(r, ['Image_URL2', 'image_url2', 'Image2', 'Фото 2', 'Фото2'])
                
                exercises.append({
                    'id': id_val,
                    'name': name_val,
                    'muscleGroup': group,
                    'description': description,
                    'imageUrl': image_url,
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
        # Предполагаем структуру: ID, Name, Muscle Group, Description, Image_URL, Image_URL2
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
            
            # Определяем индексы колонок (по умолчанию как в вашем шаблоне)
            name_col = 2
            group_col = 3
            description_col = 4 # D
            image_url_col = 5   # E
            image_url2_col = 6  # F
            
            # Пытаемся найти колонки динамически по заголовкам
            for i, header in enumerate(headers, 1):
                header_lower = str(header).lower().strip().replace(' ', '_').replace('-', '_')
                
                if header_lower in ['name', 'название'] and i > 1: name_col = i
                elif header_lower in ['muscle_group', 'group', 'группа'] and i > 1: group_col = i
                elif header_lower in ['description', 'описание', 'desc', 'note'] and i > 1: description_col = i
                elif header_lower in ['image_url', 'image', 'фото']: image_url_col = i
                elif header_lower in ['image_url2', 'image2', 'фото2', 'фото_2']: image_url2_col = i
            
            logger.info(f"Columns map: Desc={description_col}, Img1={image_url_col}, Img2={image_url2_col}")
            logger.info(f"Data keys received: {list(data.keys())}")
            logger.info(f"Description in data: {'description' in data}")
            if 'description' in data:
                logger.info(f"Description value type: {type(data['description'])}, value: {repr(data['description'])[:50]}")
            
            if 'name' in data: 
                self.exercises_sheet.update_cell(row_num, name_col, data['name'])
                logger.info(f"Updated name")
            if 'muscleGroup' in data: 
                self.exercises_sheet.update_cell(row_num, group_col, data['muscleGroup'])
                logger.info(f"Updated muscleGroup")
            
            # ВАЖНО: Запись описания
            if 'description' in data:
                # Если пришел null или undefined, пишем пустую строку
                description = data['description'] if data['description'] is not None else ''
                logger.info(f"Writing description to column {description_col}: {repr(description)[:50]}")
                self.exercises_sheet.update_cell(row_num, description_col, description)
                logger.info(f"Updated description: {description[:20] if description else 'empty'}...")
                # Проверяем сохранение
                saved_desc = self.exercises_sheet.cell(row_num, description_col).value
                logger.info(f"Verified saved description: {repr(saved_desc)[:50] if saved_desc else 'empty'}")
            else:
                logger.warning("Description NOT in data dict!")
                
            if 'imageUrl' in data: 
                image_url = data['imageUrl'] if data['imageUrl'] is not None else ''
                self.exercises_sheet.update_cell(row_num, image_url_col, image_url)
                
            if 'imageUrl2' in data: 
                image_url2 = data['imageUrl2'] if data['imageUrl2'] is not None else ''
                self.exercises_sheet.update_cell(row_num, image_url2_col, image_url2)
                
            return True
        except Exception as e:
            logger.error(f"Update exercise error: {e}", exc_info=True)
            return False

    def save_workout_set(self, data: Dict) -> Dict:
        """Сохранить подход и вернуть номер строки для последующего update"""
        try:
            timestamp = datetime.now(MOSCOW_TZ).strftime('%Y.%m.%d, %H:%M')
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
            result = self.log_sheet.append_row(row)
            self._invalidate_log_cache()
            
            # Извлекаем номер строки из ответа gspread
            # result['updates']['updatedRange'] имеет формат 'LOG!A123:I123'
            row_number = None
            if result and 'updates' in result:
                updated_range = result['updates'].get('updatedRange', '')
                # Парсим номер строки из range типа 'LOG!A650:I650'
                import re
                match = re.search(r'!A(\d+):', updated_range)
                if match:
                    row_number = int(match.group(1))
                    logger.info(f"Saved workout set at row {row_number}")
            
            return {"success": True, "row_number": row_number}
        except Exception as e:
            logger.error(f"Save set error: {e}")
            return {"success": False, "error": str(e)}

    def update_workout_set(self, data: Dict) -> bool:
        """
        Обновить запись подхода в LOG.
        Если передан row_number - обновляем напрямую (быстро и надёжно).
        Иначе ищем по set_group_id, exercise_id, order (fallback).
        """
        try:
            row_num = data.get('row_number')
            logger.info(f"update_workout_set called with row_number={row_num}, data keys={list(data.keys())}")
            
            # Стандартные индексы колонок
            weight_idx = 3  # D
            reps_idx = 4    # E
            rest_idx = 5    # F
            
            # Если row_number передан - используем напрямую (надёжный способ)
            if row_num and isinstance(row_num, int) and row_num > 1:
                weight = DataParser.to_float(data.get('weight'))
                reps = DataParser.to_int(data.get('reps'))
                rest = DataParser.to_float(data.get('rest'))
                
                # Обновляем ячейки напрямую по номеру строки
                self.log_sheet.update_cell(row_num, weight_idx + 1, weight)
                self.log_sheet.update_cell(row_num, reps_idx + 1, reps)
                self.log_sheet.update_cell(row_num, rest_idx + 1, rest)
                
                self._invalidate_log_cache()
                logger.info(f"Updated workout set row {row_num} directly: weight={weight}, reps={reps}, rest={rest}")
                return True
            
            # Fallback: поиск по exercise_id + set_group_id + order
            logger.warning("update_workout_set: row_number not provided, falling back to search")
            return self._update_workout_set_by_search(data)
            
        except Exception as e:
            logger.error(f"Update workout set error: {e}", exc_info=True)
            return False
    
    def _update_workout_set_by_search(self, data: Dict) -> bool:
        """Fallback метод: поиск строки по exercise_id + set_group_id + order"""
        import time
        
        set_group_id = str(data.get('set_group_id', '')).strip()
        exercise_id = str(data.get('exercise_id', '')).strip()
        order_val = DataParser.to_int(data.get('order'), -1)
        
        if not set_group_id or not exercise_id or order_val < 0:
            logger.error("_update_workout_set_by_search: missing required fields")
            return False

        weight_idx, reps_idx, rest_idx = 3, 4, 5
        ex_id_idx, set_group_idx, order_idx = 1, 6, 8

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    time.sleep(attempt * 2)
                
                all_values = self.log_sheet.get_all_values()
                if not all_values or len(all_values) < 2:
                    continue

                data_rows = all_values[1:]
                row_num = None
                
                for idx, row in enumerate(data_rows):
                    if len(row) <= max(ex_id_idx, set_group_idx, order_idx):
                        continue
                    r_ex = str(row[ex_id_idx]).strip()
                    r_sg = str(row[set_group_idx]).strip()
                    r_ord = DataParser.to_int(row[order_idx] if order_idx < len(row) else '', -1)
                    
                    if r_ex == exercise_id and r_sg == set_group_id and r_ord == order_val:
                        row_num = idx + 2
                        break

                if row_num:
                    weight = DataParser.to_float(data.get('weight'))
                    reps = DataParser.to_int(data.get('reps'))
                    rest = DataParser.to_float(data.get('rest'))
                    
                    self.log_sheet.update_cell(row_num, weight_idx + 1, weight)
                    self.log_sheet.update_cell(row_num, reps_idx + 1, reps)
                    self.log_sheet.update_cell(row_num, rest_idx + 1, rest)
                    
                    self._invalidate_log_cache()
                    logger.info(f"Updated workout set row {row_num} by search")
                    return True
                    
            except Exception as e:
                logger.error(f"Search update error (attempt {attempt + 1}): {e}")
        
        logger.error(f"_update_workout_set_by_search: row not found for exercise_id={exercise_id}, set_group_id={set_group_id}, order={order_val}")
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
            if ex_id_idx is None: ex_id_idx = 1
            if date_idx is None: date_idx = 0
            if weight_idx is None: weight_idx = 3
            if reps_idx is None: reps_idx = 4
            if rest_idx is None: rest_idx = 5
            if set_group_idx is None: set_group_idx = 6
            if note_idx is None: note_idx = 7
            if order_idx is None: order_idx = 8
            
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
                    # Получаем заметку
                    if not last_note and note_idx < len(row) and row[note_idx]:
                        last_note = str(row[note_idx]).strip()
                    
                    date_val = str(row[date_idx]).split(',')[0].strip() if date_idx < len(row) and row[date_idx] else ''
                    weight = DataParser.to_float(row[weight_idx] if weight_idx < len(row) else '')
                    reps = DataParser.to_int(row[reps_idx] if reps_idx < len(row) else '')
                    rest = DataParser.to_float(row[rest_idx] if rest_idx < len(row) else '')
                    order = DataParser.to_int(row[order_idx] if order_idx and order_idx < len(row) else '', 0)
                    set_group_id = str(row[set_group_idx]).strip() if set_group_idx < len(row) and row[set_group_idx] else ''
                    
                    history_items.append({
                        'date': date_val,
                        'weight': weight,
                        'reps': reps,
                        'rest': rest,
                        'order': order,
                        'setGroupId': set_group_id if set_group_id else None,
                    })
            
            # Сортировка по дате (от новых к старым) и ORDER
            history_items.sort(key=lambda x: (x.get('date', ''), x.get('order', 0)), reverse=True)
            
            # Группировка по дате
            grouped_by_date = {}
            for item in history_items:
                date_val = item['date']
                if date_val not in grouped_by_date:
                    grouped_by_date[date_val] = []
                grouped_by_date[date_val].append(item)
            
            # Упрощенный формат: просто подходы сгруппированные по дате
            # Для истории одного упражнения суперсеты не имеют смысла
            result_history = []
            for date_val, items in grouped_by_date.items():
                items.sort(key=lambda x: x.get('order', 0))
                result_history.append({
                    'date': date_val,
                    'sets': items  # Просто список подходов
                })

            result_history.sort(key=lambda x: x.get('date', ''), reverse=True)
            return {"history": result_history[:limit], "note": last_note}
            
        except Exception as e:
            logger.error(f"Get history error: {e}", exc_info=True)
            return {"history": [], "note": ""}

    def get_global_history(self) -> List[Dict]:
        try:
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2: return []
            
            headers = all_values[0]
            data_rows = all_values[1:]
            
            all_ex_data = self.get_all_exercises()
            exercises_map = {e['id']: e for e in all_ex_data['exercises']}
            
            # Индексы (упрощенно)
            ex_id_idx, date_idx, weight_idx, reps_idx, rest_idx, order_idx, set_group_idx = 1, 0, 3, 4, 5, 8, 6
            
            days = {}
            for row in data_rows:
                if len(row) <= 8: continue
                date_val = str(row[date_idx]).split(',')[0].strip()
                if not date_val: continue
                
                ex_id = str(row[ex_id_idx]).strip()
                ex_info = exercises_map.get(ex_id, {})
                ex_name = ex_info.get('name', 'Unknown')
                muscle = ex_info.get('muscleGroup', 'Other')
                
                if date_val not in days:
                    days[date_val] = {"date": date_val, "muscleGroups": set(), "exercises": []}
                
                days[date_val]["muscleGroups"].add(muscle)
                days[date_val]["exercises"].append({
                    "exerciseName": ex_name,
                    "weight": DataParser.to_float(row[weight_idx]),
                    "reps": DataParser.to_int(row[reps_idx]),
                    "rest": DataParser.to_float(row[rest_idx]),
                    "order": DataParser.to_int(row[order_idx]),
                    "setGroupId": str(row[set_group_idx]).strip()
                })
            
            result = []
            for date_val, day_data in days.items():
                raw_exercises = day_data["exercises"]
                raw_exercises.sort(key=lambda x: x.get('order', 0))
                
                # Группируем подходы по упражнениям
                exercises_grouped = {}
                for ex in raw_exercises:
                    ex_name = ex["exerciseName"]
                    set_group_id = ex.get("setGroupId", "")
                    
                    # Ключ группировки: имя упражнения + setGroupId
                    key = f"{ex_name}_{set_group_id}" if set_group_id else ex_name
                    
                    if key not in exercises_grouped:
                        exercises_grouped[key] = {
                            "name": ex_name,
                            "setGroupId": set_group_id,
                            "sets": []
                        }
                    
                    exercises_grouped[key]["sets"].append({
                        "weight": ex["weight"],
                        "reps": ex["reps"],
                        "rest": ex["rest"]
                    })
                
                # Определяем суперсеты: группы где несколько РАЗНЫХ упражнений имеют одинаковый setGroupId
                set_group_exercise_count = {}
                for ex_data in exercises_grouped.values():
                    sg = ex_data.get("setGroupId", "")
                    if sg:
                        set_group_exercise_count[sg] = set_group_exercise_count.get(sg, 0) + 1
                
                # Назначаем supersetId только если в группе > 1 разных упражнений
                grouped_list = []
                for ex_data in exercises_grouped.values():
                    sg = ex_data.get("setGroupId", "")
                    is_superset = sg and set_group_exercise_count.get(sg, 0) > 1
                    grouped_list.append({
                        "name": ex_data["name"],
                        "supersetId": sg if is_superset else None,
                        "sets": ex_data["sets"]
                    })
                
                result.append({
                    "id": date_val,
                    "date": date_val,
                    "muscleGroups": sorted(list(day_data["muscleGroups"])),
                    "duration": f"{len(raw_exercises) * 2}м",  # Примерная оценка
                    "exercises": grouped_list
                })
            
            result.sort(key=lambda x: x['date'], reverse=True)
            return result
        except Exception as e:
            logger.error(f"Global history error: {e}")
            return []

    def get_analytics_data(self, period: int = 14, anchor_ids: list = None) -> Dict:
        """
        Аналитика v3.0 — Универсальная система с 5 инвариантными метриками.
        
        Метрики:
        ① Strength Trend (ST) — изменение силы в якорных упражнениях
        ② Stimulus Volume (SV) — суммарный эффективный стимул от hard sets
        ③ Fatigue Accumulation (FA) — соотношение стимула к результату
        ④ Efficiency Index (EI) — главный KPI: ST / SV
        ⑤ Consistency (C) — стабильность тренировок
        
        Параметры:
        - period: количество дней для анализа (7, 14, 21, 28)
        - anchor_ids: список ID якорных упражнений для расчёта ST
        """
        from datetime import datetime, timedelta
        import statistics
        
        try:
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return self._empty_analytics_v3()
            
            all_ex_data = self.get_all_exercises()
            exercises_map = {e['id']: e for e in all_ex_data['exercises']}
            
            data_rows = all_values[1:]
            ex_id_idx, date_idx, weight_idx, reps_idx = 1, 0, 3, 4
            
            logger.info(f"Analytics v3: {len(data_rows)} rows, period={period}d, anchors={anchor_ids}")
            
            # ========== ПАРСИНГ ДАТ ==========
            def parse_date(date_str_raw: str):
                date_str = date_str_raw.split(',')[0].strip()
                if not date_str:
                    return None, ''
                for fmt in ['%Y.%m.%d', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']:
                    try:
                        return datetime.strptime(date_str, fmt), date_str
                    except ValueError:
                        continue
                return None, date_str
            
            # ========== СБОР ДАННЫХ ==========
            all_sets = []
            for row in data_rows:
                if len(row) < 5:
                    continue
                
                date_obj, date_str = parse_date(str(row[date_idx]).strip())
                if not date_str:
                    continue
                
                ex_id = str(row[ex_id_idx]).strip()
                ex_info = exercises_map.get(ex_id, {})
                weight = DataParser.to_float(row[weight_idx])
                reps = DataParser.to_int(row[reps_idx])
                
                if weight <= 0 or reps <= 0:
                    continue
                
                # e1RM по Epley (НЕ МЕНЯЕТСЯ)
                e1rm = round(weight * (1 + reps / 30), 1)
                
                all_sets.append({
                    'date': date_obj,
                    'date_str': date_str,
                    'ex_id': ex_id,
                    'ex_name': ex_info.get('name', 'Unknown'),
                    'muscle_group': ex_info.get('muscleGroup', 'Other'),
                    'weight': weight,
                    'reps': reps,
                    'e1rm': e1rm,
                    'volume': weight * reps
                })
            
            if not all_sets:
                logger.warning("Analytics v3: no sets collected")
                return self._empty_analytics_v3()
            
            # ========== BEST e1RM ДЛЯ КАЖДОГО УПРАЖНЕНИЯ ==========
            best_e1rm_by_ex = {}
            for s in all_sets:
                ex_id = s['ex_id']
                if ex_id not in best_e1rm_by_ex or s['e1rm'] > best_e1rm_by_ex[ex_id]:
                    best_e1rm_by_ex[ex_id] = s['e1rm']
            
            # ========== INTENSITY И HARD SETS ==========
            for s in all_sets:
                best = best_e1rm_by_ex.get(s['ex_id'], s['e1rm'])
                s['intensity'] = round(s['weight'] / best, 3) if best > 0 else 0
                # Hard set: intensity >= 70% e1RM (спец требование)
                s['is_hard_set'] = s['intensity'] >= 0.70
            
            # ========== ВРЕМЕННЫЕ ОКНА ==========
            today = datetime.now()
            has_dates = any(s['date'] is not None for s in all_sets)
            
            if has_dates:
                window_T = today - timedelta(days=period)
                window_prev_T = today - timedelta(days=period * 2)
                window_7d = today - timedelta(days=7)
                
                sets_T = [s for s in all_sets if s['date'] and s['date'] >= window_T]
                sets_prev_T = [s for s in all_sets if s['date'] and window_prev_T <= s['date'] < window_T]
                sets_7d = [s for s in all_sets if s['date'] and s['date'] >= window_7d]
            else:
                # Fallback без дат
                mid = len(all_sets) // 2
                sets_T = all_sets[mid:]
                sets_prev_T = all_sets[:mid]
                sets_7d = all_sets[-max(1, len(all_sets)//4):]
            
            # ========== ① STRENGTH TREND (ST) ==========
            # Медиана e1RM якорных упражнений, сравнение периодов
            
            def calc_median_e1rm(sets_list, ex_ids):
                """Медиана max e1RM по дням для заданных упражнений"""
                if not ex_ids:
                    # Если нет якорей — используем все упражнения
                    ex_ids = list(best_e1rm_by_ex.keys())
                
                daily_max = {}  # ex_id -> {date -> max_e1rm}
                for s in sets_list:
                    if s['ex_id'] not in ex_ids:
                        continue
                    ex_id = s['ex_id']
                    d = s['date_str']
                    if ex_id not in daily_max:
                        daily_max[ex_id] = {}
                    if d not in daily_max[ex_id] or s['e1rm'] > daily_max[ex_id][d]:
                        daily_max[ex_id][d] = s['e1rm']
                
                # Медиана по каждому упражнению
                medians = []
                for ex_id, days in daily_max.items():
                    if days:
                        medians.append(statistics.median(days.values()))
                
                return statistics.median(medians) if medians else 0
            
            median_T = calc_median_e1rm(sets_T, anchor_ids)
            median_prev_T = calc_median_e1rm(sets_prev_T, anchor_ids)
            
            if median_prev_T > 0:
                strength_trend = round((median_T - median_prev_T) / median_prev_T * 100, 2)
            else:
                strength_trend = 0
            
            # Направление ST
            if strength_trend > 1:
                st_direction = 'up'
            elif strength_trend < -1:
                st_direction = 'down'
            else:
                st_direction = 'stable'
            
            # ========== ② STIMULUS VOLUME (SV) ==========
            # Сумма intensity для всех hard sets за период
            
            hard_sets_T = [s for s in sets_T if s['is_hard_set']]
            stimulus_volume = round(sum(s['intensity'] for s in hard_sets_T), 2)
            
            # Сравнение с предыдущим периодом для статуса
            hard_sets_prev = [s for s in sets_prev_T if s['is_hard_set']]
            sv_prev = sum(s['intensity'] for s in hard_sets_prev) if hard_sets_prev else 0
            
            # Статус SV (по историческому распределению)
            if sv_prev > 0:
                sv_ratio = stimulus_volume / sv_prev
                if sv_ratio < 0.7:
                    sv_status = 'low'
                elif sv_ratio > 1.3:
                    sv_status = 'high'
                else:
                    sv_status = 'ok'
            else:
                sv_status = 'ok' if stimulus_volume > 0 else 'low'
            
            # ========== ③ FATIGUE ACCUMULATION (FA) ==========
            # FA = SV_7d / |ST_period|
            
            hard_sets_7d = [s for s in sets_7d if s['is_hard_set']]
            sv_7d = sum(s['intensity'] for s in hard_sets_7d)
            
            epsilon = 0.1  # Малое число чтобы избежать деления на 0
            fatigue_raw = sv_7d / (abs(strength_trend) + epsilon)
            
            # Нормализация FA
            if fatigue_raw < 5:
                fa_status = 'low'
            elif fatigue_raw < 20:
                fa_status = 'moderate'
            else:
                fa_status = 'high'
            
            # ========== ④ EFFICIENCY INDEX (EI) ==========
            # EI = ST / SV — главный KPI
            
            if stimulus_volume > 0:
                efficiency_index = round(strength_trend / stimulus_volume, 3)
            else:
                efficiency_index = 0
            
            # Направление EI
            if efficiency_index > 0.1:
                ei_direction = 'positive'
            elif efficiency_index < -0.1:
                ei_direction = 'negative'
            else:
                ei_direction = 'neutral'
            
            # ========== ⑤ CONSISTENCY (C) ==========
            # C = 1 - CV(volume_per_week)
            
            # Группируем объём по неделям
            weekly_volumes = {}
            for s in all_sets:
                if s['date']:
                    week = s['date'].isocalendar()[1]
                    year = s['date'].year
                    key = f"{year}-W{week}"
                    weekly_volumes[key] = weekly_volumes.get(key, 0) + s['volume']
            
            if len(weekly_volumes) >= 2:
                volumes = list(weekly_volumes.values())
                mean_vol = statistics.mean(volumes)
                stdev_vol = statistics.stdev(volumes) if len(volumes) > 1 else 0
                cv = stdev_vol / mean_vol if mean_vol > 0 else 0
                consistency = round(max(0, 1 - cv), 2)
            else:
                consistency = 1.0  # Недостаточно данных
            
            # Статус consistency
            if consistency >= 0.8:
                c_status = 'stable'
            else:
                c_status = 'unstable'
            
            # ========== СПИСОК УПРАЖНЕНИЙ ДЛЯ ВЫБОРА ЯКОРЕЙ ==========
            exercise_list = []
            for ex_id, best in best_e1rm_by_ex.items():
                ex_info = exercises_map.get(ex_id, {})
                exercise_list.append({
                    'id': ex_id,
                    'name': ex_info.get('name', 'Unknown'),
                    'muscleGroup': ex_info.get('muscleGroup', 'Other'),
                    'bestE1RM': best,
                    'isAnchor': ex_id in (anchor_ids or [])
                })
            exercise_list.sort(key=lambda x: x['bestE1RM'], reverse=True)
            
            # ========== РЕЗУЛЬТАТ ==========
            return {
                'strengthTrend': {
                    'value': strength_trend,
                    'direction': st_direction,
                    'medianCurrent': round(median_T, 1),
                    'medianPrevious': round(median_prev_T, 1),
                    'tooltip': 'Strength Trend — изменение оценочной силы в якорных упражнениях за выбранный период. Считается по e1RM (Epley), сглажено медианой.'
                },
                'stimulusVolume': {
                    'value': stimulus_volume,
                    'status': sv_status,
                    'hardSetsCount': len(hard_sets_T),
                    'tooltip': 'Stimulus Volume — суммарный эффективный стимул, полученный от тяжёлых подходов. Учитывает только подходы с intensity ≥ 70% e1RM.'
                },
                'fatigueAccumulation': {
                    'value': round(fatigue_raw, 2),
                    'status': fa_status,
                    'sv7d': round(sv_7d, 2),
                    'tooltip': 'Fatigue Accumulation показывает, сколько стимула требуется для изменения силы. Высокие значения — признак накопленной усталости или низкой адаптации.'
                },
                'efficiencyIndex': {
                    'value': efficiency_index,
                    'direction': ei_direction,
                    'tooltip': 'Efficiency Index — сколько изменения силы ты получаешь на единицу тренировочного стимула. Работает одинаково при наборе, сушке и поддержании.'
                },
                'consistency': {
                    'value': consistency,
                    'status': c_status,
                    'weeksAnalyzed': len(weekly_volumes),
                    'tooltip': 'Consistency отражает регулярность тренировок и стабильность нагрузки. Низкая консистентность снижает доверие к остальным показателям.'
                },
                'exercises': exercise_list,
                'meta': {
                    'period': period,
                    'anchorIds': anchor_ids or [],
                    'totalSets': len(all_sets),
                    'setsInPeriod': len(sets_T),
                    'hardSetsInPeriod': len(hard_sets_T),
                    'formula': 'e1RM = weight × (1 + reps / 30) [Epley]'
                }
            }
            
        except Exception as e:
            logger.error(f"Analytics v3 error: {e}", exc_info=True)
            return self._empty_analytics_v3()
    
    def _empty_analytics_v3(self) -> Dict:
        """Пустой результат аналитики v3"""
        return {
            'strengthTrend': {'value': 0, 'direction': 'stable', 'medianCurrent': 0, 'medianPrevious': 0, 'tooltip': ''},
            'stimulusVolume': {'value': 0, 'status': 'low', 'hardSetsCount': 0, 'tooltip': ''},
            'fatigueAccumulation': {'value': 0, 'status': 'low', 'sv7d': 0, 'tooltip': ''},
            'efficiencyIndex': {'value': 0, 'direction': 'neutral', 'tooltip': ''},
            'consistency': {'value': 0, 'status': 'unstable', 'weeksAnalyzed': 0, 'tooltip': ''},
            'exercises': [],
            'meta': {'period': 14, 'anchorIds': [], 'totalSets': 0, 'setsInPeriod': 0, 'hardSetsInPeriod': 0, 'formula': ''}
        }
