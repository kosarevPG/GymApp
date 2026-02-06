# Input Normalization — миграция Google Sheets

## Структура листов

### 1. REF_Exercises (справочник логики)
| A: ID | B: Name | C: Type | D: Base_Wt | E: Multiplier |
|-------|---------|---------|------------|---------------|
| UUID из EXERCISES | Название | Barbell / Dumbbell / Machine / Assisted / Plate_Loaded / Bodyweight | Вес грифа/каретки (20 для штанги) | 2 для штанги, 1 для остальных |

### 2. REF_Bio (вес тела)
| A: Date | B: Body_Weight_Kg |
|---------|-------------------|
| 2025-02-03 | 90 |

### 3. LOG (дополнительные колонки)
- **K: Input_Weight** — что ввёл пользователь (например, 20 для блина)
- **L: Effective_Load_Kg** — формула (см. ниже)

## Автоматическая миграция

```bash
cd back
python migrate_input_normalization.py
```

Скрипт создаст REF_Exercises и REF_Bio (если нет), заполнит REF_Exercises из EXERCISES, добавит формулу в L2.

## Ручная вставка формулы

Если скрипт не сработал, вставьте в **L2** (одной строкой):

```
=IF(OR(K2="",ISBLANK(K2)),"",IFERROR(LET(ex_id,B2,input_wt,VALUE(K2),dt,IF(ISNUMBER(A2),A2,DATEVALUE(SUBSTITUTE(LEFT(A2,10),".","-"))),ex_type,IFERROR(VLOOKUP(ex_id,REF_Exercises!A:E,3,FALSE),"Dumbbell"),base_wt,IFERROR(VLOOKUP(ex_id,REF_Exercises!A:E,4,FALSE),0),user_wt,IFERROR(VLOOKUP(dt,SORT(REF_Bio!A:B,1,TRUE),2,TRUE),90),SWITCH(ex_type,"Barbell",(input_wt*2)+base_wt,"Plate_Loaded",(input_wt*2)+base_wt,"Assisted",MAX(0,user_wt-input_wt),"Bodyweight",user_wt+input_wt,input_wt)),""))
```

Затем протяните формулу вниз (L2 → выделить → перетащить за правый нижний угол).

## Важно

- **REF_Bio**: даты должны быть в формате, совместимом с LOG (A). Для VLOOKUP с TRUE данные должны быть отсортированы по Date по возрастанию.
- **REF_Exercises**: ID должен совпадать с Exercise_ID в LOG (колонка B).
- Если вес тела не найден, используется 90 кг по умолчанию.
