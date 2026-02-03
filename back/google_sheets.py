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

    def get_analytics_data(self) -> Dict:
        """
        Продвинутая аналитика v2.0
        
        Принцип: не добавляем метрики, меняем интерпретацию.
        Каждая метрика должна вести к действию.
        
        Возвращает:
        - status: progressIndex, fatigueIndex (главные индикаторы)
        - inefficiencies: упражнения с низкой эффективностью
        - recommendations: конкретные действия
        - muscleBalance: симметрия и стимул по группам
        - patterns: тренды по паттернам (жимы/тяги/ноги)
        """
        from datetime import datetime, timedelta
        
        try:
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return self._empty_analytics()
            
            all_ex_data = self.get_all_exercises()
            exercises_map = {e['id']: e for e in all_ex_data['exercises']}
            
            # Категории мышц
            MUSCLE_CATEGORY = {
                'Грудь': 'push', 'Плечи': 'push', 'Трицепс': 'push',
                'Спина': 'pull', 'Бицепс': 'pull',
                'Ноги': 'legs', 'Квадрицепс': 'legs', 'Бицепс бедра': 'legs',
                'Пресс': 'core', 'Кардио': 'cardio'
            }
            
            # Антагонисты для симметрии
            ANTAGONISTS = [
                ('push', 'pull'),
                ('Квадрицепс', 'Бицепс бедра'),
                ('Грудь', 'Спина'),
                ('Бицепс', 'Трицепс')
            ]
            
            data_rows = all_values[1:]
            ex_id_idx, date_idx, weight_idx, reps_idx = 1, 0, 3, 4
            
            logger.info(f"Analytics v2: {len(data_rows)} rows, {len(exercises_map)} exercises")
            
            # Логируем первые строки для отладки
            if data_rows:
                sample = data_rows[0][:6] if len(data_rows[0]) >= 6 else data_rows[0]
                logger.info(f"Analytics v2: first row sample: {sample}")
            
            # ========== ШАГ 1: Сбор сырых данных ==========
            all_sets = []  # Все подходы с производными полями
            
            # Функция парсинга даты
            def parse_date(date_str_raw: str):
                """Парсит дату, возвращает (datetime_obj, date_str) или (None, date_str)"""
                date_str = date_str_raw.split(',')[0].strip()
                if not date_str:
                    return None, ''
                
                DATE_FORMATS = [
                    '%Y.%m.%d',      # 2026.02.03 (наш формат записи!)
                    '%Y-%m-%d',      # 2026-02-03
                    '%d.%m.%Y',      # 03.02.2026
                    '%d/%m/%Y',      # 03/02/2026
                    '%m/%d/%Y',      # 02/03/2026 (US format)
                    '%d-%m-%Y',      # 03-02-2026
                ]
                
                for fmt in DATE_FORMATS:
                    try:
                        return datetime.strptime(date_str, fmt), date_str
                    except ValueError:
                        continue
                
                return None, date_str
            
            skipped = 0
            for row in data_rows:
                if len(row) < 5:
                    continue
                
                date_str_raw = str(row[date_idx]).strip()
                date_obj, date_str = parse_date(date_str_raw)
                
                # Даже если не распарсили дату, продолжаем сбор данных
                # (используем строку для группировки)
                
                ex_id = str(row[ex_id_idx]).strip()
                ex_info = exercises_map.get(ex_id, {})
                ex_name = ex_info.get('name', 'Unknown')
                muscle_group = ex_info.get('muscleGroup', 'Other')
                category = MUSCLE_CATEGORY.get(muscle_group, 'other')
                
                weight = DataParser.to_float(row[weight_idx])
                reps = DataParser.to_int(row[reps_idx])
                
                if weight <= 0 or reps <= 0:
                    continue
                
                # Производные поля
                e1rm = round(weight * (1 + reps / 30), 1)  # Epley
                volume = weight * reps
                
                if not date_str:
                    skipped += 1
                    continue
                    
                all_sets.append({
                    'date': date_obj,  # может быть None
                    'date_str': date_str,
                    'ex_id': ex_id,
                    'ex_name': ex_name,
                    'muscle_group': muscle_group,
                    'category': category,
                    'weight': weight,
                    'reps': reps,
                    'e1rm': e1rm,
                    'volume': volume
                })
            
            # Статистика парсинга
            parsed_count = sum(1 for s in all_sets if s['date'] is not None)
            logger.info(f"Analytics v2: collected {len(all_sets)} sets, {parsed_count} with parsed dates, {skipped} skipped")
            
            if not all_sets:
                logger.warning("Analytics v2: no sets collected, returning empty")
                return self._empty_analytics()
            
            # ========== ШАГ 2: Вычисляем best e1RM и intensity ==========
            # Для каждого упражнения находим лучший e1RM (для расчёта intensity)
            best_e1rm_by_ex = {}
            for s in all_sets:
                ex_id = s['ex_id']
                if ex_id not in best_e1rm_by_ex or s['e1rm'] > best_e1rm_by_ex[ex_id]:
                    best_e1rm_by_ex[ex_id] = s['e1rm']
            
            # Добавляем intensity и is_hard_set
            for s in all_sets:
                best = best_e1rm_by_ex.get(s['ex_id'], s['e1rm'])
                s['intensity'] = round(s['weight'] / best, 2) if best > 0 else 0
                # Hard set: >= 6 reps при intensity >= 0.7 (прокси для ~2 RIR)
                s['is_hard_set'] = s['reps'] >= 6 and s['intensity'] >= 0.7
            
            # ========== ШАГ 3: Скользящие окна ==========
            today = datetime.now()
            window_7d = today - timedelta(days=7)
            window_14d = today - timedelta(days=14)
            window_21d = today - timedelta(days=21)
            
            # Если даты распарсились - используем datetime, иначе берём всё
            has_dates = any(s['date'] is not None for s in all_sets)
            
            if has_dates:
                sets_7d = [s for s in all_sets if s['date'] and s['date'] >= window_7d]
                sets_14d = [s for s in all_sets if s['date'] and s['date'] >= window_14d]
                sets_21d = [s for s in all_sets if s['date'] and s['date'] >= window_21d]
                sets_older = [s for s in all_sets if s['date'] and s['date'] < window_21d]
            else:
                # Fallback: все данные считаем "недавними"
                logger.warning("Analytics v2: no parsed dates, using all data as recent")
                sets_7d = all_sets
                sets_14d = all_sets
                sets_21d = all_sets
                sets_older = []
            
            # ========== ШАГ 4: Агрегаты по упражнениям ==========
            exercise_stats = {}
            
            # Группируем по упражнениям
            ex_sets = {}
            for s in all_sets:
                ex_id = s['ex_id']
                if ex_id not in ex_sets:
                    ex_sets[ex_id] = []
                ex_sets[ex_id].append(s)
            
            for ex_id, sets in ex_sets.items():
                if not sets:
                    continue
                
                ex_name = sets[0]['ex_name']
                muscle_group = sets[0]['muscle_group']
                
                # Группируем по датам
                daily_data = {}
                for s in sets:
                    d = s['date_str']
                    if d not in daily_data:
                        daily_data[d] = {'e1rm': 0, 'volume': 0, 'hard_sets': 0, 'intensity_sum': 0, 'count': 0}
                    if s['e1rm'] > daily_data[d]['e1rm']:
                        daily_data[d]['e1rm'] = s['e1rm']
                    daily_data[d]['volume'] += s['volume']
                    daily_data[d]['hard_sets'] += 1 if s['is_hard_set'] else 0
                    daily_data[d]['intensity_sum'] += s['intensity']
                    daily_data[d]['count'] += 1
                
                sorted_dates = sorted(daily_data.keys())
                history = []
                for d in sorted_dates:
                    dd = daily_data[d]
                    history.append({
                        'date': d,
                        'e1rm': dd['e1rm'],
                        'volume': dd['volume'],
                        'hard_sets': dd['hard_sets'],
                        'avg_intensity': round(dd['intensity_sum'] / dd['count'], 2) if dd['count'] > 0 else 0
                    })
                
                # Метрики за окна
                if has_dates:
                    sets_14d_ex = [s for s in sets if s['date'] and s['date'] >= window_14d]
                    sets_21d_ex = [s for s in sets if s['date'] and s['date'] >= window_21d]
                    sets_older_ex = [s for s in sets if s['date'] and s['date'] < window_14d]
                else:
                    # Fallback: делим по индексу (новые = последняя половина)
                    mid = len(sets) // 2
                    sets_14d_ex = sets[mid:]
                    sets_21d_ex = sets
                    sets_older_ex = sets[:mid] if mid > 0 else []
                
                # e1RM тренд (14 дней)
                e1rm_recent = max([s['e1rm'] for s in sets_14d_ex]) if sets_14d_ex else 0
                e1rm_older = max([s['e1rm'] for s in sets_older_ex]) if sets_older_ex else e1rm_recent
                e1rm_delta = round((e1rm_recent - e1rm_older) / e1rm_older * 100, 1) if e1rm_older > 0 else 0
                
                # Volume за 21 день
                volume_21d = sum(s['volume'] for s in sets_21d_ex)
                
                # Training Efficiency = Δ e1RM / volume (higher = better)
                efficiency = round(e1rm_delta / (volume_21d / 1000 + 0.1), 2) if volume_21d > 0 else 0
                
                exercise_stats[ex_id] = {
                    'name': ex_name,
                    'muscleGroup': muscle_group,
                    'history': history[-10:],
                    'currentE1RM': history[-1]['e1rm'] if history else 0,
                    'bestE1RM': best_e1rm_by_ex.get(ex_id, 0),
                    'e1rmTrend': e1rm_delta,  # % изменения за 14 дней
                    'volume21d': round(volume_21d),
                    'efficiency': efficiency,  # прогресс на единицу объёма
                    'hardSets21d': sum(1 for s in sets_21d_ex if s['is_hard_set'])
                }
            
            # ========== ШАГ 5: Fatigue Index ==========
            # Fatigue = (hard_sets_7d × avg_intensity) / (Δ e1RM_14d + ε)
            hard_sets_7d = sum(1 for s in sets_7d if s['is_hard_set'])
            avg_intensity_7d = sum(s['intensity'] for s in sets_7d) / len(sets_7d) if sets_7d else 0
            
            # Средний e1RM delta по всем упражнениям
            e1rm_deltas = [stats['e1rmTrend'] for stats in exercise_stats.values() if stats['e1rmTrend'] != 0]
            avg_e1rm_delta = sum(e1rm_deltas) / len(e1rm_deltas) if e1rm_deltas else 0
            
            fatigue_raw = (hard_sets_7d * avg_intensity_7d) / (abs(avg_e1rm_delta) + 1)
            
            # Нормализуем в шкалу 0-100
            # Эмпирически: fatigue_raw ~5-10 = норма, >15 = высокая, <3 = низкая
            if fatigue_raw < 3:
                fatigue_index = 'low'
                fatigue_value = round(fatigue_raw / 3 * 30)
            elif fatigue_raw < 10:
                fatigue_index = 'ok'
                fatigue_value = round(30 + (fatigue_raw - 3) / 7 * 40)
            else:
                fatigue_index = 'high'
                fatigue_value = min(100, round(70 + (fatigue_raw - 10) / 10 * 30))
            
            # ========== ШАГ 6: Progress Index ==========
            # Основан на среднем e1RM тренде по паттернам
            if avg_e1rm_delta > 2:
                progress_index = 'up'
            elif avg_e1rm_delta < -2:
                progress_index = 'down'
            else:
                progress_index = 'stable'
            
            progress_value = round(50 + avg_e1rm_delta * 5)  # Центрировано на 50
            progress_value = max(0, min(100, progress_value))
            
            # ========== ШАГ 7: Детектор плато (по паттернам) ==========
            patterns_plateau = {}
            for category in ['push', 'pull', 'legs']:
                cat_stats = [s for s in exercise_stats.values() if MUSCLE_CATEGORY.get(s['muscleGroup']) == category]
                if len(cat_stats) >= 2:
                    avg_trend = sum(s['e1rmTrend'] for s in cat_stats) / len(cat_stats)
                    avg_volume = sum(s['volume21d'] for s in cat_stats) / len(cat_stats)
                    # Плато: тренд ~0, но объём не падает
                    is_plateau = abs(avg_trend) < 1 and avg_volume > 0
                    patterns_plateau[category] = {
                        'avgTrend': round(avg_trend, 1),
                        'isPlateau': is_plateau
                    }
            
            # ========== ШАГ 8: Баланс по стимулу (hard sets) ==========
            category_hard_sets = {'push': 0, 'pull': 0, 'legs': 0, 'core': 0}
            total_hard_sets = 0
            
            for s in sets_21d:
                if s['is_hard_set']:
                    cat = s['category']
                    if cat in category_hard_sets:
                        category_hard_sets[cat] += 1
                    total_hard_sets += 1
            
            stimulus_balance = {}
            if total_hard_sets > 0:
                stimulus_balance = {
                    cat: round(count / total_hard_sets * 100)
                    for cat, count in category_hard_sets.items()
                    if cat in ['push', 'pull', 'legs']
                }
            
            # Целевые диапазоны (не фиксированные проценты!)
            TARGET_RANGES = {
                'push': (25, 35),
                'pull': (30, 45),
                'legs': (25, 40)
            }
            
            balance_status = {}
            for cat, (low, high) in TARGET_RANGES.items():
                val = stimulus_balance.get(cat, 0)
                if val < low:
                    balance_status[cat] = 'low'
                elif val > high:
                    balance_status[cat] = 'high'
                else:
                    balance_status[cat] = 'ok'
            
            # ========== ШАГ 9: Симметрия антагонистов ==========
            symmetry = []
            for a, b in ANTAGONISTS:
                # Могут быть категории или группы мышц
                if a in category_hard_sets and b in category_hard_sets:
                    sets_a = category_hard_sets[a]
                    sets_b = category_hard_sets[b]
                else:
                    # Группы мышц
                    sets_a = sum(1 for s in sets_21d if s['is_hard_set'] and s['muscle_group'] == a)
                    sets_b = sum(1 for s in sets_21d if s['is_hard_set'] and s['muscle_group'] == b)
                
                if sets_a > 0 or sets_b > 0:
                    ratio = round(sets_a / sets_b, 2) if sets_b > 0 else float('inf')
                    is_balanced = 0.6 <= ratio <= 1.6 if ratio != float('inf') else False
                    symmetry.append({
                        'pair': f"{a}/{b}",
                        'ratio': ratio if ratio != float('inf') else 'n/a',
                        'isBalanced': is_balanced
                    })
            
            # ========== ШАГ 10: Неэффективные упражнения ==========
            # Топ-3 с низкой эффективностью и высокой усталостью
            inefficiencies = []
            for ex_id, stats in exercise_stats.items():
                # Низкая эффективность: много объёма, мало прогресса
                if stats['volume21d'] > 0 and stats['efficiency'] < 1 and stats['e1rmTrend'] <= 0:
                    inefficiencies.append({
                        'exerciseId': ex_id,
                        'name': stats['name'],
                        'muscleGroup': stats['muscleGroup'],
                        'efficiency': stats['efficiency'],
                        'e1rmTrend': stats['e1rmTrend'],
                        'volume21d': stats['volume21d'],
                        'reason': 'high_volume_no_progress'
                    })
            
            # Сортируем по эффективности (худшие первые)
            inefficiencies.sort(key=lambda x: x['efficiency'])
            inefficiencies = inefficiencies[:3]
            
            # ========== ШАГ 11: Рекомендации ==========
            recommendations = []
            
            # Рекомендация при высокой усталости
            if fatigue_index == 'high':
                recommendations.append({
                    'type': 'reduce_volume',
                    'priority': 'high',
                    'message': 'Снизь объём на 20-30% — усталость накапливается быстрее, чем адаптация',
                    'action': 'deload'
                })
            
            # Рекомендация при низкой усталости и стабильном прогрессе
            if fatigue_index == 'low' and progress_index == 'stable':
                recommendations.append({
                    'type': 'increase_intensity',
                    'priority': 'medium',
                    'message': 'Можно увеличить интенсивность — есть запас восстановления',
                    'action': 'progress'
                })
            
            # Рекомендация при плато
            for cat, data in patterns_plateau.items():
                if data['isPlateau']:
                    recommendations.append({
                        'type': 'plateau',
                        'priority': 'high',
                        'message': f'Плато в паттерне {cat}: попробуй сменить диапазон повторений или вариации упражнений',
                        'action': 'variation'
                    })
            
            # Рекомендация по дисбалансу
            for cat, status in balance_status.items():
                if status == 'low':
                    recommendations.append({
                        'type': 'balance',
                        'priority': 'medium',
                        'message': f'Недостаточно стимула для {cat} — добавь 2-3 hard sets в неделю',
                        'action': 'add_volume'
                    })
            
            # Рекомендация по неэффективным упражнениям
            for ineff in inefficiencies:
                recommendations.append({
                    'type': 'inefficiency',
                    'priority': 'low',
                    'message': f'{ineff["name"]}: много объёма без прогресса — замени или снизь объём',
                    'action': 'replace_exercise'
                })
            
            # Сортируем по приоритету
            priority_order = {'high': 0, 'medium': 1, 'low': 2}
            recommendations.sort(key=lambda x: priority_order.get(x['priority'], 3))
            recommendations = recommendations[:5]  # Максимум 5 рекомендаций
            
            # ========== РЕЗУЛЬТАТ ==========
            return {
                'status': {
                    'progressIndex': progress_index,
                    'progressValue': progress_value,
                    'fatigueIndex': fatigue_index,
                    'fatigueValue': fatigue_value,
                    'avgE1rmTrend': round(avg_e1rm_delta, 1)
                },
                'muscleBalance': {
                    'stimulus': stimulus_balance,
                    'status': balance_status,
                    'targetRanges': TARGET_RANGES,
                    'symmetry': symmetry
                },
                'patterns': patterns_plateau,
                'inefficiencies': inefficiencies,
                'recommendations': recommendations,
                'exerciseStats': exercise_stats,  # Для детальных графиков
                'meta': {
                    'totalSets': len(all_sets),
                    'hardSets7d': hard_sets_7d,
                    'avgIntensity7d': round(avg_intensity_7d, 2),
                    'daysAnalyzed': (today - min(s['date'] for s in all_sets)).days if all_sets else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Analytics v2 error: {e}", exc_info=True)
            return self._empty_analytics()
    
    def _empty_analytics(self) -> Dict:
        """Пустой результат аналитики"""
        return {
            'status': {'progressIndex': 'stable', 'progressValue': 50, 'fatigueIndex': 'ok', 'fatigueValue': 50, 'avgE1rmTrend': 0},
            'muscleBalance': {'stimulus': {}, 'status': {}, 'targetRanges': {}, 'symmetry': []},
            'patterns': {},
            'inefficiencies': [],
            'recommendations': [],
            'exerciseStats': {},
            'meta': {'totalSets': 0, 'hardSets7d': 0, 'avgIntensity7d': 0, 'daysAnalyzed': 0}
        }
