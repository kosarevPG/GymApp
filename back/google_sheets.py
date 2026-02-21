"""
Модуль для работы с Google Sheets API.
Версия для продакшена: чтение credentials из файла.
"""

import gspread
from google.oauth2.service_account import Credentials
from typing import List, Dict, Optional, Any, Tuple
import logging
import os
import json
import uuid
from datetime import datetime, timezone, timedelta

# Московское время (UTC+3)
MOSCOW_TZ = timezone(timedelta(hours=3))

# Группы по умолчанию для выбора при создании упражнения (если в EXERCISES ещё нет строк)
DEFAULT_GROUPS = ['Спина', 'Ноги', 'Грудь', 'Плечи', 'Трицепс', 'Бицепс', 'Пресс', 'Кардио']

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
            self._baseline_sheet = None
            self._baseline_proposals_sheet = None
            
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
    
    def _get_baseline_sheet(self):
        """Получить лист BASELINE, создать если не существует"""
        if self._baseline_sheet is None:
            try:
                self._baseline_sheet = self.spreadsheet.worksheet('BASELINE')
            except Exception:
                self._baseline_sheet = self.spreadsheet.add_worksheet('BASELINE', rows=100, cols=6)
                self._baseline_sheet.append_row(['exercise_id', 'baseline_weight', 'last_updated', 'peak_90d', 'status'])
        return self._baseline_sheet
    
    def _get_baseline_proposals_sheet(self):
        """Получить лист BASELINE_PROPOSALS, создать если не существует"""
        if self._baseline_proposals_sheet is None:
            try:
                self._baseline_proposals_sheet = self.spreadsheet.worksheet('BASELINE_PROPOSALS')
            except Exception:
                self._baseline_proposals_sheet = self.spreadsheet.add_worksheet('BASELINE_PROPOSALS', rows=50, cols=9)
                self._baseline_proposals_sheet.append_row(['exercise_id', 'old_baseline', 'new_baseline', 'step', 'evidence', 'created_at', 'expires_at', 'status', 'proposal_id'])
        return self._baseline_proposals_sheet

    def _get_weight_from_row(self, row: List, weight_idx: int, total_weight_idx: int) -> float:
        """Извлечь вес из строки: приоритет Total_Weight, иначе Weight."""
        tw = DataParser.to_float(row[total_weight_idx]) if total_weight_idx < len(row) else 0
        w = DataParser.to_float(row[weight_idx]) if weight_idx < len(row) else 0
        return tw if tw and tw > 0 else w

    def _infer_weight_metadata(self, name: str, equipment: str) -> Tuple[str, float, int]:
        """Infer (type, base_wt, multiplier) from equipment and name."""
        n = (name or '').lower()
        eq = (equipment or '').lower()
        if 'assist' in n or 'гравитрон' in n:
            return 'Assisted', 0, 1
        if eq == 'barbell':
            return 'Barbell', 20, 2
        if eq == 'machine':
            return 'Plate_Loaded', 50, 2
        if eq == 'dumbbell':
            return 'Dumbbell', 0, 1
        return 'Dumbbell', 0, 1

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
    
    def _infer_equipment(self, name: str, image_url: str) -> str:
        """Infer equipment_type from name or image URL"""
        s = (name + ' ' + image_url).upper()
        if 'DB_' in s or 'DUMBBELL' in s or 'ГАНТЕЛ' in s:
            return 'dumbbell'
        if any(x in s for x in ['LEG_', 'CABLE', 'MACHINE', 'MAG_', 'LAT_', 'SEATED', 'DEC_', 'INC_', 'HACK', 'LGE_', 'PAR_', 'FACE_', 'OA_', 'PREA_', 'TRICEPS', 'PULL_DOWN', 'PULLDOWN', 'LEG_PRESS', 'LEG_CURL']):
            return 'machine'
        return 'barbell'
    
    def _infer_exercise_type(self, name: str) -> str:
        """Infer exercise_type: compound vs isolation"""
        s = name.upper()
        if any(x in s for x in ['CURL', 'FLY', 'EXTENSION', 'RAISE', 'KICKBACK', 'PULLOVER']):
            return 'isolation'
        return 'compound'

    def get_all_exercises(self) -> Dict:
        try:
            records = self.exercises_sheet.get_all_records()
            exercises = []
            groups = set()
            
            # Логируем заголовки для отладки
            if records:
                logger.info(f"Column headers in EXERCISES sheet: {list(records[0].keys())}")
            
            for r in records:
                id_val = self._find_key_case_insensitive(r, ['ID', 'id'])
                name_val = self._find_key_case_insensitive(r, ['Name', 'name', 'Название'])
                
                if not id_val and not name_val: continue
                    
                group = self._find_key_case_insensitive(r, ['Muscle Group', 'muscle_group', 'Group', 'group', 'Группа'])
                if group: groups.add(group)
                
                description = self._find_key_case_insensitive(r, ['Description', 'description', 'Desc', 'Описание', 'Note', 'Заметка'])
                image_url = self._find_key_case_insensitive(r, ['Image_URL', 'image_url', 'Image', 'image', 'Фото'])
                image_url2 = self._find_key_case_insensitive(r, ['Image_URL2', 'image_url2', 'Image2', 'Фото 2', 'Фото2'])
                equipment = self._find_key_case_insensitive(r, ['Equipment_Type', 'equipment_type', 'Equipment', 'equipment'])
                ex_type = self._find_key_case_insensitive(r, ['Exercise_Type', 'exercise_type', 'Type', 'type'])
                
                if not equipment or equipment not in ('barbell', 'dumbbell', 'machine'):
                    equipment = self._infer_equipment(name_val or '', image_url or '')
                if not ex_type or ex_type not in ('compound', 'isolation'):
                    ex_type = self._infer_exercise_type(name_val or '')
                
                # Метаданные веса из EXERCISES (Weight_Type, Base_Wt, Multiplier)
                weight_type = self._find_key_case_insensitive(r, ['Weight_Type', 'weight_type'])
                base_wt = DataParser.to_float(
                    self._find_key_case_insensitive(r, ['Base_Wt', 'base_wt', 'Base_Weight', 'base_weight']) or 0, 0
                )
                mult_val = self._find_key_case_insensitive(r, ['Multiplier', 'multiplier'])
                multiplier = DataParser.to_int(mult_val, 1) if mult_val else 1
                if multiplier not in (1, 2):
                    multiplier = 1
                if not weight_type or weight_type.lower() in ('compound', 'isolation'):
                    weight_type, base_wt, multiplier = self._infer_weight_metadata(name_val or '', equipment or '')
                
                # 1RM методологически некорректен для Assisted/Bodyweight (гравитрон, свой вес)
                allow_1rm = weight_type not in ('Assisted', 'Bodyweight')
                
                exercises.append({
                    'id': id_val,
                    'name': name_val,
                    'muscleGroup': group,
                    'description': description,
                    'imageUrl': image_url,
                    'imageUrl2': image_url2,
                    'equipmentType': equipment or 'barbell',
                    'exerciseType': ex_type or 'compound',
                    'weightType': weight_type,
                    'baseWeight': base_wt,
                    'weightMultiplier': multiplier,
                    'allow_1rm': allow_1rm
                })
            
            # Сортируем упражнения по имени (Name)
            exercises.sort(key=lambda x: x.get('name', '').lower())
            
            # Группы — уникальные значения из столбца Muscle Group; если пусто — список по умолчанию
            groups_list = sorted(list(groups)) if groups else DEFAULT_GROUPS
            return {"groups": groups_list, "exercises": exercises}
        except Exception as e:
            logger.error(f"Get exercises error: {e}")
            return {"groups": DEFAULT_GROUPS, "exercises": []}

    def create_exercise(self, name: str, group: str, equipment_type: str = None, exercise_type: str = None) -> Dict:
        new_id = str(uuid.uuid4())
        eq = equipment_type or self._infer_equipment(name, '')
        ex_t = exercise_type or self._infer_exercise_type(name)
        w_type, base_wt, mult = self._infer_weight_metadata(name, eq)
        # ID, Name, Muscle Group, Description, Image_URL, Image_URL2, Equipment_Type, Exercise_Type, Weight_Type, Base_Wt, Multiplier
        row = [new_id, name, group, "", "", "", eq, ex_t, w_type, base_wt, mult]
        try:
            self.exercises_sheet.append_row(row)
            allow_1rm = w_type not in ('Assisted', 'Bodyweight')
            return {"id": new_id, "name": name, "muscleGroup": group, "description": "", "imageUrl": "", "imageUrl2": "", "equipmentType": eq, "exerciseType": ex_t, "weightType": w_type, "baseWeight": base_wt, "weightMultiplier": mult, "allow_1rm": allow_1rm}
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
            headers = self.exercises_sheet.row_values(1)
            
            name_col = 2
            group_col = 3
            description_col = 4
            image_url_col = 5
            image_url2_col = 6
            equipment_col = 7
            exercise_type_col = 8
            weight_type_col = 9
            base_wt_col = 10
            multiplier_col = 11
            
            for i, header in enumerate(headers, 1):
                header_lower = str(header).lower().strip().replace(' ', '_').replace('-', '_')
                if header_lower in ['name', 'название'] and i > 1: name_col = i
                elif header_lower in ['muscle_group', 'group', 'группа'] and i > 1: group_col = i
                elif header_lower in ['description', 'описание', 'desc', 'note'] and i > 1: description_col = i
                elif header_lower in ['image_url', 'image', 'фото']: image_url_col = i
                elif header_lower in ['image_url2', 'image2', 'фото2', 'фото_2']: image_url2_col = i
                elif header_lower in ['equipment_type', 'equipment']: equipment_col = i
                elif header_lower in ['exercise_type']: exercise_type_col = i
                elif header_lower in ['weight_type', 'weighttype', 'type']: weight_type_col = i
                elif header_lower in ['base_wt', 'base_weight', 'baseweight']: base_wt_col = i
                elif header_lower in ['multiplier']: multiplier_col = i
            
            if 'name' in data: 
                self.exercises_sheet.update_cell(row_num, name_col, data['name'])
            if 'muscleGroup' in data: 
                self.exercises_sheet.update_cell(row_num, group_col, data['muscleGroup'])
            
            if 'description' in data:
                description = data['description'] if data['description'] is not None else ''
                self.exercises_sheet.update_cell(row_num, description_col, description)
                
            if 'imageUrl' in data: 
                image_url = data['imageUrl'] if data['imageUrl'] is not None else ''
                self.exercises_sheet.update_cell(row_num, image_url_col, image_url)
                
            if 'imageUrl2' in data: 
                image_url2 = data['imageUrl2'] if data['imageUrl2'] is not None else ''
                self.exercises_sheet.update_cell(row_num, image_url2_col, image_url2)
            
            if 'equipmentType' in data and equipment_col <= len(headers):
                eq = data['equipmentType'] or 'barbell'
                if eq in ('barbell', 'dumbbell', 'machine'):
                    self.exercises_sheet.update_cell(row_num, equipment_col, eq)
            if 'exerciseType' in data and exercise_type_col <= len(headers):
                et = data['exerciseType'] or 'compound'
                if et in ('compound', 'isolation'):
                    self.exercises_sheet.update_cell(row_num, exercise_type_col, et)
            
            if 'weightType' in data and data['weightType']:
                self.exercises_sheet.update_cell(row_num, weight_type_col, str(data['weightType']))
            if 'baseWeight' in data:
                self.exercises_sheet.update_cell(row_num, base_wt_col, float(data.get('baseWeight', 0)))
            if 'weightMultiplier' in data:
                m = int(data.get('weightMultiplier', 1))
                self.exercises_sheet.update_cell(row_num, multiplier_col, m if m in (1, 2) else 1)
                
            return True
        except Exception as e:
            logger.error(f"Update exercise error: {e}", exc_info=True)
            return False

    def save_workout_set(self, data: Dict) -> Dict:
        """Сохранить подход и вернуть номер строки для последующего update"""
        try:
            timestamp = datetime.now(MOSCOW_TZ).strftime('%Y.%m.%d, %H:%M')
            exercise_name = data.get('exercise_name') or ''
            if not exercise_name and data.get('exercise_id'):
                try:
                    ex_cell = self.exercises_sheet.find(str(data.get('exercise_id')))
                    headers = self.exercises_sheet.row_values(1)
                    name_col = 2
                    for i, h in enumerate(headers, 1):
                        if str(h).lower().strip() in ('name', 'название') and i > 1:
                            name_col = i
                            break
                    exercise_name = self.exercises_sheet.cell(ex_cell.row, name_col).value or ''
                except Exception:
                    pass
            input_weight = data.get('input_weight')
            input_weight_cell = DataParser.to_float(input_weight) if input_weight is not None and str(input_weight).strip() != '' else ''
            total_weight = DataParser.to_float(data.get('weight'))
            row = [
                timestamp,
                data.get('exercise_id'),
                exercise_name,
                input_weight_cell,
                total_weight,
                DataParser.to_int(data.get('reps')),
                DataParser.to_float(data.get('rest')),
                data.get('set_group_id'),
                data.get('note', ''),
                DataParser.to_int(data.get('order')),
            ]
            result = self.log_sheet.append_row(row, table_range='A1')
            self._invalidate_log_cache()
            row_number = None
            if result and 'updates' in result:
                import re
                updated_range = result['updates'].get('updatedRange', '')
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
            
            # A=Date, B=Ex_ID, C=Name, D=Input_Weight, E=Total_Weight, F=Reps, G=Rest, H=Set_Group, I=Note, J=Order
            input_weight_col, total_weight_col, reps_col, rest_col, note_col, order_col = 4, 5, 6, 7, 9, 10

            if row_num and isinstance(row_num, int) and row_num > 1:
                total_weight = DataParser.to_float(data.get('weight'))
                reps = DataParser.to_int(data.get('reps'))
                rest = DataParser.to_float(data.get('rest'))
                self.log_sheet.update_cell(row_num, total_weight_col, total_weight)
                self.log_sheet.update_cell(row_num, reps_col, reps)
                self.log_sheet.update_cell(row_num, rest_col, rest)
                if 'input_weight' in data and data.get('input_weight') is not None:
                    self.log_sheet.update_cell(row_num, input_weight_col, DataParser.to_float(data.get('input_weight')))
                if 'note' in data:
                    self.log_sheet.update_cell(row_num, note_col, data.get('note', '') or '')
                if 'order' in data:
                    self.log_sheet.update_cell(row_num, order_col, DataParser.to_int(data.get('order')))
                self._invalidate_log_cache()
                logger.info(f"Updated workout set row {row_num}: total_weight={total_weight}, reps={reps}")
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

        ex_id_idx, set_group_idx, order_idx = 1, 7, 9
        input_weight_idx, total_weight_idx, reps_idx, rest_idx = 3, 4, 5, 6

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
                    total_weight = DataParser.to_float(data.get('weight'))
                    reps = DataParser.to_int(data.get('reps'))
                    rest = DataParser.to_float(data.get('rest'))
                    if 'input_weight' in data and data.get('input_weight') is not None:
                        self.log_sheet.update_cell(row_num, input_weight_idx + 1, DataParser.to_float(data.get('input_weight')))
                    self.log_sheet.update_cell(row_num, total_weight_idx + 1, total_weight)
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
            total_weight_idx = None
            reps_idx = None
            rest_idx = None
            note_idx = None
            order_idx = None
            set_group_idx = None
            input_weight_idx = None
            
            for i, header in enumerate(headers):
                header_lower = str(header).lower().strip().replace(' ', '_').replace('-', '_')
                if 'exercise' in header_lower and 'id' in header_lower and ex_id_idx is None:
                    ex_id_idx = i
                elif 'date' in header_lower and date_idx is None:
                    date_idx = i
                elif 'input' in header_lower and 'weight' in header_lower and input_weight_idx is None:
                    input_weight_idx = i
                elif ('total_weight' in header_lower or 'totalweight' in header_lower) and total_weight_idx is None:
                    total_weight_idx = i
                elif 'weight' in header_lower and weight_idx is None and 'total' not in header_lower:
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
            
            # A=Date, B=Ex_ID, C=Name, D=Input_Weight, E=Total_Weight, F=Reps, G=Rest, H=Set_Group, I=Note, J=Order
            if ex_id_idx is None: ex_id_idx = 1
            if date_idx is None: date_idx = 0
            if total_weight_idx is None: total_weight_idx = 4
            if weight_idx is None: weight_idx = 4
            if reps_idx is None: reps_idx = 5
            if rest_idx is None: rest_idx = 6
            if set_group_idx is None: set_group_idx = 7
            if note_idx is None: note_idx = 8
            if order_idx is None: order_idx = 9
            if input_weight_idx is None: input_weight_idx = 3
            
            history_items = []
            last_note = ""
            exercise_id_str = str(exercise_id).strip()
            
            # Собираем все записи для данного упражнения
            for row in data_rows:
                if len(row) <= max(ex_id_idx, date_idx, total_weight_idx or 0, reps_idx, rest_idx, note_idx or 0, order_idx or 0, set_group_idx or 0):
                    continue
                
                # Получаем ID упражнения из строки
                record_ex_id = str(row[ex_id_idx]).strip() if ex_id_idx < len(row) else ''
                
                if record_ex_id == exercise_id_str:
                    # Получаем заметку
                    if not last_note and note_idx < len(row) and row[note_idx]:
                        last_note = str(row[note_idx]).strip()
                    
                    date_val = str(row[date_idx]).split(',')[0].strip() if date_idx < len(row) and row[date_idx] else ''
                    weight = self._get_weight_from_row(row, total_weight_idx or 4, total_weight_idx if total_weight_idx is not None else 4)
                    reps = DataParser.to_int(row[reps_idx] if reps_idx < len(row) else '')
                    rest = DataParser.to_float(row[rest_idx] if rest_idx < len(row) else '')
                    order = DataParser.to_int(row[order_idx] if order_idx and order_idx < len(row) else '', 0)
                    set_group_id = str(row[set_group_idx]).strip() if set_group_idx < len(row) and row[set_group_idx] else ''
                    
                    # input_weight из колонки K (если есть)
                    raw_input_wt = row[input_weight_idx] if input_weight_idx < len(row) else ''
                    input_wt = DataParser.to_float(raw_input_wt) if raw_input_wt and str(raw_input_wt).strip() else None
                    
                    item = {
                        'date': date_val,
                        'weight': weight,
                        'reps': reps,
                        'rest': rest,
                        'order': order,
                        'setGroupId': set_group_id if set_group_id else None,
                    }
                    if input_wt is not None:
                        item['inputWeight'] = input_wt
                    history_items.append(item)
            
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
            
            # A=Date, B=Ex_ID, C=Name, D=Input_Weight, E=Total_Weight, F=Reps, G=Rest, H=Set_Group, I=Note, J=Order
            ex_id_idx, date_idx, total_weight_idx, reps_idx, rest_idx, order_idx, set_group_idx = 1, 0, 4, 5, 6, 9, 7
            days = {}
            for row in data_rows:
                if len(row) <= 9: continue
                date_val = str(row[date_idx]).split(',')[0].strip()
                if not date_val: continue
                
                ex_id = str(row[ex_id_idx]).strip()
                ex_info = exercises_map.get(ex_id, {})
                ex_name = ex_info.get('name', 'Unknown')
                muscle = ex_info.get('muscleGroup', 'Other')
                
                weight_val = self._get_weight_from_row(row, total_weight_idx, total_weight_idx)
                
                if date_val not in days:
                    days[date_val] = {"date": date_val, "muscleGroups": set(), "exercises": []}
                
                days[date_val]["muscleGroups"].add(muscle)
                days[date_val]["exercises"].append({
                    "exerciseName": ex_name,
                    "weight": weight_val,
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

    def _resolve_log_columns(self, headers: List) -> Dict[str, int]:
        """Определяет индексы колонок LOG. Новая структура: A=Date, B=Ex_ID, C=Name, D=Input_Weight, E=Total_Weight, F=Reps, G=Rest, H=Set_Group, I=Note, J=Order."""
        date_idx = ex_id_idx = total_weight_idx = input_weight_idx = weight_legacy = reps_idx = rest_idx = -1
        for i, header in enumerate(headers):
            h = str(header).lower().strip().replace(' ', '_').replace('-', '_')
            if (date_idx < 0) and ('date' in h or 'дата' in h or 'время' in h): date_idx = i
            elif (ex_id_idx < 0) and ('exercise_id' in h or ('exercise' in h and 'id' in h and 'name' not in h and 'calc' not in h)): ex_id_idx = i
            elif ('total_weight' in h or 'totalweight' in h) and total_weight_idx < 0: total_weight_idx = i
            elif ('input_weight' in h or 'inputweight' in h) and input_weight_idx < 0: input_weight_idx = i
            elif (weight_legacy < 0) and ('weight' in h or 'вес' in h or 'кг' in h) and 'total' not in h and 'input' not in h: weight_legacy = i
            elif (reps_idx < 0) and ('reps' in h or 'repetitions' in h or 'повтор' in h): reps_idx = i
            elif (rest_idx < 0) and ('rest' in h or 'отдых' in h): rest_idx = i
        if date_idx < 0: date_idx = 0
        if ex_id_idx < 0: ex_id_idx = 1
        if total_weight_idx < 0: total_weight_idx = 4
        if input_weight_idx < 0: input_weight_idx = 3
        if weight_legacy < 0: weight_legacy = total_weight_idx if total_weight_idx >= 0 else 4
        if reps_idx < 0: reps_idx = 5
        if rest_idx < 0: rest_idx = 6
        return {'date': date_idx, 'ex_id': ex_id_idx, 'weight': weight_legacy, 'total_weight': total_weight_idx, 'reps': reps_idx, 'rest': rest_idx}
    
    def _parse_date_flexible(self, raw) -> tuple:
        """Парсинг даты: строки, Google Sheets serial, разные форматы"""
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            return None, ''
        s = str(raw).strip()
        # Google Sheets date serial (число)
        try:
            serial = float(s.replace(',', '.'))
            if 1000 < serial < 100000:  # разумный диапазон дат
                base = datetime(1899, 12, 30)
                dt = base + timedelta(days=int(serial))
                return dt, dt.strftime('%Y.%m.%d')
        except (ValueError, TypeError):
            pass
        s = s.split(',')[0].strip()
        if not s:
            return None, ''
        for fmt in ['%Y.%m.%d', '%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d.%m.%y', '%m/%d/%Y']:
            try:
                dt = datetime.strptime(s, fmt)
                return dt, dt.strftime('%Y.%m.%d')
            except ValueError:
                continue
        return None, s
    
    def get_analytics_v4(self, period: int = 14, debug: bool = False) -> Dict:
        """
        Аналитика v4.0 — Регулярность > Прогресс.
        
        Метрики: Frequency Score, Max Gap, Return to Baseline, Baseline, Stability Gate.
        """
        from datetime import datetime, timedelta
        import statistics
        
        try:
            all_values = self.log_sheet.get_all_values()
            if not all_values or len(all_values) < 2:
                empty = self._empty_analytics_v4(period)
                if debug:
                    empty['_debug'] = {'reason': 'no_data', 'total_rows': len(all_values) if all_values else 0}
                return empty
            
            # EXERCISES: id, Name — наименования упражнений
            all_ex_data = self.get_all_exercises()
            exercises_map = {e['id']: e for e in all_ex_data['exercises']}
            
            # Определяем, есть ли строка заголовков (первая ячейка — не дата)
            first_cell = str(all_values[0][0]).strip() if all_values and all_values[0] else ''
            first_looks_like_date = bool(first_cell) and (
                (len(first_cell) >= 10 and first_cell[4] in '.-/' and first_cell[7] in '.-/') or
                any(x in first_cell for x in ['2024', '2025', '2026', '2023'])
            )
            if first_looks_like_date:
                data_rows = all_values[0:]
                cols = {'date': 0, 'ex_id': 1, 'weight': 4, 'total_weight': 4, 'reps': 5, 'rest': 6}
            else:
                headers = all_values[0]
                cols = self._resolve_log_columns(headers)
                data_rows = all_values[1:]
            
            date_idx = cols['date']
            ex_id_idx = cols['ex_id']
            weight_idx = cols.get('weight', 4)
            total_weight_idx = cols.get('total_weight', 4)
            reps_idx = cols['reps']
            rest_idx = cols['rest']
            rir_idx = -1
            
            all_sets = []
            for row in data_rows:
                if len(row) <= max(date_idx, ex_id_idx, weight_idx, total_weight_idx, reps_idx):
                    continue
                date_obj, date_str = self._parse_date_flexible(row[date_idx] if date_idx < len(row) else '')
                if not date_str:
                    continue
                weight = self._get_weight_from_row(row, weight_idx, total_weight_idx)
                reps = DataParser.to_int(row[reps_idx] if reps_idx < len(row) else 0)
                if weight <= 0 or reps <= 0:
                    continue
                rir = DataParser.to_int(row[rir_idx]) if rir_idx >= 0 and rir_idx < len(row) and row[rir_idx] else None
                # LOG: Exercise_ID (колонка B) — связь с EXERCISES
                ex_id = str(row[ex_id_idx]).strip() if ex_id_idx < len(row) else ''
                ex_info = exercises_map.get(ex_id, {})  # name из EXERCISES.Name
                
                all_sets.append({
                    'date': date_obj,
                    'date_str': date_str,
                    'ex_id': ex_id,
                    'weight': weight,
                    'reps': reps,
                    'rir': rir,
                    'equipment_type': ex_info.get('equipmentType', 'barbell'),
                    'exercise_type': ex_info.get('exerciseType', 'compound')
                })
            
            if not all_sets:
                empty = self._empty_analytics_v4(period)
                if debug:
                    empty['_debug'] = {'total_rows': len(all_values), 'data_rows': len(data_rows), 'all_sets_count': 0, 'cols': cols, 'first_row_sample': data_rows[0][:6] if data_rows else None}
                return empty
            
            today = datetime.now()
            has_dates = any(s['date'] for s in all_sets)
            if not has_dates:
                empty = self._empty_analytics_v4(period)
                if debug:
                    empty['_debug'] = {'total_rows': len(all_values), 'data_rows': len(data_rows), 'all_sets_count': len(all_sets), 'parsed_dates_none': True, 'cols': cols}
                return empty
            
            window = today - timedelta(days=period)
            sets_in_period = [s for s in all_sets if s['date'] and s['date'] >= window]
            
            # Sessions = уникальные даты с тренировками
            session_dates = sorted(set(s['date_str'] for s in sets_in_period if s['date_str']))
            
            # ========== Frequency Score ==========
            target_sessions = max(1, int(period / 7 * 3))  # 3/нед
            actual_sessions = len(session_dates)
            fs_value = round(actual_sessions / target_sessions, 2) if target_sessions > 0 else 0
            
            if fs_value >= 0.8:
                fs_status = 'green'
            elif fs_value >= 0.6:
                fs_status = 'yellow'
            else:
                fs_status = 'red'
            
            # ========== Max Gap ==========
            unique_dates = sorted(set(s['date'] for s in all_sets if s['date']))
            max_gap = 0
            if len(unique_dates) >= 2:
                gaps = [(unique_dates[i] - unique_dates[i-1]).days for i in range(1, len(unique_dates))]
                max_gap = max(gaps) if gaps else 0
            
            if max_gap <= 4:
                mg_status = 'ok'
                mg_interpretation = 'Регулярно'
            elif max_gap <= 7:
                mg_status = 'warning'
                mg_interpretation = 'Потребуется адаптация'
            else:
                mg_status = 'vkat'
                mg_interpretation = 'Режим Вкат'
            
            # ========== Режим ==========
            if max_gap > 7:
                mode = 'Вкат'
            elif fs_value < 0.6:
                mode = 'Поддержание'
            else:
                mode = 'Стабильный'
            
            # ========== Return to Baseline ==========
            return_to_baseline = None
            if max_gap > 7:
                # Считаем тренировки до первого достижения baseline
                baselines = self._get_baselines_map()
                if baselines:
                    # Упрощённо: считаем по первой тренировке после паузы
                    return_to_baseline = {'value': 0, 'visible': True}
            
            # ========== Baseline по упражнениям ==========
            baselines_map = self._get_baselines_map()
            baselines_list = []
            for ex_id, ex_info in exercises_map.items():
                bl = self._calc_baseline_for_exercise(ex_id, ex_info, all_sets)
                stored = baselines_map.get(ex_id, {})
                status = stored.get('status', 'holding') if stored else ('ready' if bl else 'locked')
                baselines_list.append({
                    'exerciseId': ex_id,
                    'name': ex_info.get('name', 'Unknown'),  # EXERCISES.Name
                    'baseline': bl or stored.get('baseline_weight'),
                    'status': status
                })
            
            # ========== Stability Gate ==========
            days_since_baseline_change = 999  # TODO: from BASELINE sheet
            stability_gate = fs_value >= 0.6 and max_gap <= 45 and days_since_baseline_change >= 7
            
            # ========== Proposals ==========
            proposals = self._get_pending_proposals()
            
            result = {
                'mode': mode,
                'frequencyScore': {
                    'value': fs_value,
                    'status': fs_status,
                    'actual': actual_sessions,
                    'target': target_sessions
                },
                'maxGap': {
                    'value': max_gap,
                    'status': mg_status,
                    'interpretation': mg_interpretation
                },
                'returnToBaseline': return_to_baseline,
                'stabilityGate': stability_gate,
                'baselines': baselines_list,
                'proposals': proposals,
                'meta': {'period': period}
            }
            if debug:
                result['_debug'] = {
                    'total_rows': len(all_values),
                    'data_rows': len(data_rows),
                    'all_sets_count': len(all_sets),
                    'sets_in_period_count': len(sets_in_period),
                    'session_dates': session_dates[:10],
                    'cols': cols,
                    'first_row_sample': data_rows[0][:6] if data_rows else None,
                    'window': window.strftime('%Y-%m-%d') if has_dates else None
                }
            return result
            
        except Exception as e:
            logger.error(f"Analytics v4 error: {e}", exc_info=True)
            empty = self._empty_analytics_v4(period)
            empty['_debug'] = {'error': str(e), 'error_type': type(e).__name__}
            return empty
    
    def _get_baselines_map(self) -> Dict:
        """Читает сохранённые baseline из листа"""
        try:
            sheet = self._get_baseline_sheet()
            rows = sheet.get_all_values()
            if len(rows) < 2:
                return {}
            result = {}
            for row in rows[1:]:
                if len(row) >= 5:
                    result[row[0]] = {
                        'baseline_weight': DataParser.to_float(row[1]),
                        'last_updated': row[2] if len(row) > 2 else '',
                        'peak_90d': DataParser.to_float(row[3]) if len(row) > 3 else 0,
                        'status': row[4] if len(row) > 4 else 'active'
                    }
            return result
        except Exception as e:
            logger.warning(f"Could not read BASELINE sheet: {e}")
            return {}
    
    def _calc_baseline_for_exercise(self, ex_id: str, ex_info: Dict, all_sets: List) -> Optional[float]:
        """Расчёт Baseline для упражнения по последним 8 тренировкам"""
        import statistics
        ex_sets = [s for s in all_sets if s['ex_id'] == ex_id]
        if not ex_sets:
            return None
        
        eq_type = ex_info.get('equipmentType', 'barbell')
        ex_type = ex_info.get('exerciseType', 'compound')
        reps_min, reps_max = (6, 12) if ex_type == 'compound' else (8, 15)
        
        # Группируем по дате, берём лучший сет за день
        by_date = {}
        for s in ex_sets:
            if not s['date']:
                continue
            d = s['date_str']
            if reps_min <= s['reps'] <= reps_max:
                if d not in by_date or s['weight'] > by_date[d]['weight']:
                    rir_ok = s['rir'] is None or (1 <= s['rir'] <= 3)
                    if rir_ok or s['rir'] is None:
                        by_date[d] = {'weight': s['weight'], 'reps': s['reps']}
        
        # Берём последние 8 тренировок
        sorted_dates = sorted(by_date.keys(), reverse=True)[:8]
        candidates = [by_date[d]['weight'] for d in sorted_dates]
        
        if len(candidates) < 4:
            return None
        
        # Удаление пиков
        if len(candidates) >= 10:
            candidates = sorted(candidates)[:-max(1, len(candidates) // 10)]
        elif len(candidates) >= 4:
            candidates = sorted(candidates)[:-1]
        
        if not candidates:
            return None
        
        baseline = statistics.median(candidates)
        step = 2.5 if eq_type == 'barbell' else 1
        baseline = round(baseline / step) * step
        return round(baseline, 1)
    
    def _get_pending_proposals(self) -> List:
        """Читает активные proposals"""
        try:
            sheet = self._get_baseline_proposals_sheet()
            rows = sheet.get_all_values()
            if len(rows) < 2:
                return []
            result = []
            for row in rows[1:]:
                if len(row) >= 8 and row[7] == 'PENDING':
                    result.append({
                        'exerciseId': row[0],
                        'oldBaseline': DataParser.to_float(row[1]),
                        'newBaseline': DataParser.to_float(row[2]),
                        'step': DataParser.to_float(row[3]),
                        'expiresAt': row[6] if len(row) > 6 else '',
                        'proposalId': row[8] if len(row) > 8 else ''
                    })
            return result
        except Exception as e:
            return []
    
    def confirm_baseline_proposal(self, proposal_id: str, action: str) -> Dict:
        """CONFIRM | SNOOZE | DECLINE proposal"""
        try:
            sheet = self._get_baseline_proposals_sheet()
            rows = sheet.get_all_values()
            if len(rows) < 2:
                return {"success": False, "error": "No proposals"}
            
            for i, row in enumerate(rows[1:], start=2):
                if len(row) > 8 and row[8] == proposal_id:
                    sheet.update_cell(i, 8, action)  # status column
                    if action == 'CONFIRM':
                        ex_id = row[0]
                        new_baseline = row[2]
                        # Update BASELINE sheet
                        bl_sheet = self._get_baseline_sheet()
                        bl_rows = bl_sheet.get_all_values()
                        for j, bl_row in enumerate(bl_rows[1:], start=2):
                            if bl_row and bl_row[0] == ex_id:
                                bl_sheet.update_cell(j, 2, new_baseline)
                                bl_sheet.update_cell(j, 3, datetime.now(MOSCOW_TZ).strftime('%Y-%m-%d'))
                                bl_sheet.update_cell(j, 5, 'updated')
                                break
                        else:
                            bl_sheet.append_row([ex_id, new_baseline, datetime.now(MOSCOW_TZ).strftime('%Y-%m-%d'), '', 'updated'])
                    return {"success": True, "action": action}
            return {"success": False, "error": "Proposal not found"}
        except Exception as e:
            logger.error(f"confirm_baseline_proposal error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _empty_analytics_v4(self, period: int = 14) -> Dict:
        target = max(1, int(period / 7 * 3))
        return {
            'mode': 'Поддержание',
            'frequencyScore': {'value': 0, 'status': 'red', 'actual': 0, 'target': target},
            'maxGap': {'value': 0, 'status': 'ok', 'interpretation': 'Нет данных'},
            'returnToBaseline': None,
            'stabilityGate': False,
            'baselines': [],
            'proposals': [],
            'meta': {'period': period}
        }
