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
            
            result_history = []
            for date_val, items in grouped_by_date.items():
                items.sort(key=lambda x: x.get('order', 0))
                
                # Упрощенная группировка по суперсетам
                by_group = {}
                standalone = []
                
                for item in items:
                    sg_id = item.get('setGroupId')
                    if sg_id:
                        if sg_id not in by_group: by_group[sg_id] = []
                        by_group[sg_id].append(item)
                    else:
                        standalone.append(item)
                
                # Добавляем суперсеты
                for sg_id, group_items in by_group.items():
                    if len(group_items) > 0:
                         result_history.append({
                            'date': date_val,
                            'setGroupId': sg_id,
                            'isSuperset': True,
                            'exercises': [{
                                'exerciseId': exercise_id, 
                                'exerciseName': 'Current Exercise', 
                                'sets': group_items
                            }] 
                        })
                
                # Добавляем обычные сеты
                if standalone:
                    result_history.append({
                        'date': date_val,
                        'setGroupId': None,
                        'isSuperset': False,
                        'sets': standalone
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
        Возвращает продвинутую аналитику:
        - exerciseStats: e1RM, динамика силы, плато по упражнениям
        - muscleGroupStats: частота, объём по группам мышц
        - balance: Push/Pull/Legs баланс
        - alerts: предупреждения
        """
        try:
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                return {"exerciseStats": {}, "muscleGroupStats": {}, "balance": {}, "alerts": []}
            
            all_ex_data = self.get_all_exercises()
            exercises_map = {e['id']: e for e in all_ex_data['exercises']}
            
            # Маппинг групп мышц на категории
            MUSCLE_CATEGORY = {
                'Грудь': 'push', 'Плечи': 'push', 'Трицепс': 'push',
                'Спина': 'pull', 'Бицепс': 'pull',
                'Ноги': 'legs', 'Пресс': 'core', 'Кардио': 'cardio'
            }
            
            data_rows = all_values[1:]
            ex_id_idx, date_idx, weight_idx, reps_idx = 1, 0, 3, 4
            
            # Собираем данные по упражнениям
            exercise_data = {}  # exercise_id -> {name, muscleGroup, sessions: [{date, weight, reps, e1rm, volume}]}
            muscle_dates = {}   # muscleGroup -> set of dates
            
            for row in data_rows:
                if len(row) <= 8:
                    continue
                
                date_str = str(row[date_idx]).split(',')[0].strip()
                if not date_str:
                    continue
                
                ex_id = str(row[ex_id_idx]).strip()
                ex_info = exercises_map.get(ex_id, {})
                ex_name = ex_info.get('name', 'Unknown')
                muscle_group = ex_info.get('muscleGroup', 'Other')
                
                weight = DataParser.to_float(row[weight_idx])
                reps = DataParser.to_int(row[reps_idx])
                
                if weight <= 0 or reps <= 0:
                    continue
                
                # e1RM по формуле Epley
                e1rm = round(weight * (1 + reps / 30), 1)
                volume = weight * reps
                
                if ex_id not in exercise_data:
                    exercise_data[ex_id] = {
                        "name": ex_name,
                        "muscleGroup": muscle_group,
                        "sessions": []
                    }
                
                exercise_data[ex_id]["sessions"].append({
                    "date": date_str,
                    "weight": weight,
                    "reps": reps,
                    "e1rm": e1rm,
                    "volume": volume
                })
                
                # Трекаем даты для частоты
                if muscle_group not in muscle_dates:
                    muscle_dates[muscle_group] = set()
                muscle_dates[muscle_group].add(date_str)
            
            # Обрабатываем статистику по упражнениям
            exercise_stats = {}
            for ex_id, data in exercise_data.items():
                sessions = data["sessions"]
                if not sessions:
                    continue
                
                # Группируем по датам (берём макс e1RM за день)
                daily_e1rm = {}
                daily_volume = {}
                for s in sessions:
                    d = s["date"]
                    if d not in daily_e1rm or s["e1rm"] > daily_e1rm[d]:
                        daily_e1rm[d] = s["e1rm"]
                    daily_volume[d] = daily_volume.get(d, 0) + s["volume"]
                
                # Сортируем по дате
                sorted_dates = sorted(daily_e1rm.keys())
                history = [{"date": d, "e1rm": daily_e1rm[d], "volume": daily_volume.get(d, 0)} for d in sorted_dates]
                
                current_e1rm = history[-1]["e1rm"] if history else 0
                best_e1rm = max(daily_e1rm.values()) if daily_e1rm else 0
                
                # Изменение за неделю (последние 7 дней vs предыдущие 7)
                weekly_change = 0
                if len(history) >= 2:
                    recent = [h["e1rm"] for h in history[-3:]]  # последние записи
                    older = [h["e1rm"] for h in history[:-3][-3:]] if len(history) > 3 else []
                    if recent and older:
                        avg_recent = sum(recent) / len(recent)
                        avg_older = sum(older) / len(older)
                        if avg_older > 0:
                            weekly_change = round((avg_recent - avg_older) / avg_older * 100, 1)
                
                # Определяем плато (e1RM не вырос > 2% за последние 4 записи)
                plateau_weeks = 0
                if len(history) >= 4:
                    last_4 = [h["e1rm"] for h in history[-4:]]
                    max_last_4 = max(last_4)
                    min_last_4 = min(last_4)
                    if max_last_4 > 0 and (max_last_4 - min_last_4) / max_last_4 < 0.02:
                        plateau_weeks = 4
                
                exercise_stats[ex_id] = {
                    "name": data["name"],
                    "muscleGroup": data["muscleGroup"],
                    "history": history[-10:],  # последние 10 записей
                    "currentE1RM": current_e1rm,
                    "bestE1RM": best_e1rm,
                    "weeklyChange": weekly_change,
                    "plateauWeeks": plateau_weeks
                }
            
            # Статистика по группам мышц
            muscle_group_stats = {}
            total_volume_all = 0
            category_volume = {"push": 0, "pull": 0, "legs": 0, "core": 0, "cardio": 0}
            
            # Считаем количество уникальных недель для частоты
            all_dates = set()
            for dates in muscle_dates.values():
                all_dates.update(dates)
            total_weeks = max(1, len(all_dates) / 7)  # приблизительно
            
            for muscle, dates in muscle_dates.items():
                frequency = round(len(dates) / total_weeks, 1)
                
                # Считаем объём для этой мышцы
                muscle_volume = 0
                for ex_id, data in exercise_data.items():
                    if data["muscleGroup"] == muscle:
                        muscle_volume += sum(s["volume"] for s in data["sessions"])
                
                category = MUSCLE_CATEGORY.get(muscle, "other")
                if category in category_volume:
                    category_volume[category] += muscle_volume
                total_volume_all += muscle_volume
                
                muscle_group_stats[muscle] = {
                    "weeklyFrequency": frequency,
                    "totalVolume": round(muscle_volume),
                    "category": category
                }
            
            # Push/Pull/Legs баланс
            balance = {}
            if total_volume_all > 0:
                balance = {
                    "push": round(category_volume["push"] / total_volume_all * 100),
                    "pull": round(category_volume["pull"] / total_volume_all * 100),
                    "legs": round(category_volume["legs"] / total_volume_all * 100)
                }
            
            # Генерируем алерты
            alerts = []
            
            # Алерт на плато
            for ex_id, stats in exercise_stats.items():
                if stats["plateauWeeks"] >= 3:
                    alerts.append({
                        "type": "plateau",
                        "exercise": stats["name"],
                        "weeks": stats["plateauWeeks"]
                    })
                # Алерт на падение силы
                if stats["weeklyChange"] < -5:
                    alerts.append({
                        "type": "strength_drop",
                        "exercise": stats["name"],
                        "change": stats["weeklyChange"]
                    })
            
            # Алерт на дисбаланс Push/Pull
            if balance.get("push", 0) and balance.get("pull", 0):
                diff = abs(balance["push"] - balance["pull"])
                if diff > 15:
                    alerts.append({
                        "type": "imbalance",
                        "message": f"Push/Pull дисбаланс: {balance['push']}% / {balance['pull']}%"
                    })
            
            # Алерт на низкую частоту
            for muscle, stats in muscle_group_stats.items():
                if stats["weeklyFrequency"] < 1 and stats["totalVolume"] > 0:
                    alerts.append({
                        "type": "low_frequency",
                        "muscle": muscle,
                        "frequency": stats["weeklyFrequency"]
                    })
            
            return {
                "exerciseStats": exercise_stats,
                "muscleGroupStats": muscle_group_stats,
                "balance": balance,
                "alerts": alerts
            }
            
        except Exception as e:
            logger.error(f"Analytics data error: {e}", exc_info=True)
            return {"exerciseStats": {}, "muscleGroupStats": {}, "balance": {}, "alerts": []}
