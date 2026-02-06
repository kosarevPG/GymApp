/**
 * Input Normalization — ввод веса одной стороны/гантели, расчёт эффективной нагрузки.
 * Сохраняем оба значения: inputWeight (что ввёл) и effectiveWeight (итог для аналитики).
 */

export type WeightInputType = 'barbell' | 'plate_loaded' | 'assisted' | 'dumbbell' | 'standard';

export interface WeightFormula {
  /** Подсказка для поля ввода (напр. "Блин с одной стороны") */
  placeholder: string;
  /** Вычисляет effectiveWeight из inputWeight */
  toEffective: (input: number, userBodyWeight?: number) => number;
  /** Вычисляет inputWeight из effectiveWeight (для отображения при загрузке старых данных) */
  toInput?: (effective: number, userBodyWeight?: number) => number;
}

const USER_BODY_WEIGHT_DEFAULT = 90; // TODO: из профиля пользователя

export const WEIGHT_FORMULAS: Record<WeightInputType, WeightFormula> = {
  barbell: {
    placeholder: 'Блин с одной стороны',
    toEffective: (input) => input * 2 + 20, // 20 кг гриф
    toInput: (effective) => Math.round((effective - 20) / 2),
  },
  plate_loaded: {
    placeholder: 'Блин с одной стороны',
    toEffective: (input) => input * 2 + 50, // 50 кг каретка
    toInput: (effective) => Math.round((effective - 50) / 2),
  },
  assisted: {
    placeholder: 'Помощь (кг)',
    toEffective: (input, bw = USER_BODY_WEIGHT_DEFAULT) => Math.max(0, bw - input),
    toInput: (effective, bw = USER_BODY_WEIGHT_DEFAULT) => Math.round(bw - effective),
  },
  dumbbell: {
    placeholder: 'Кг',
    toEffective: (input) => input,
    toInput: (effective) => effective,
  },
  standard: {
    placeholder: 'Кг',
    toEffective: (input) => input,
    toInput: (effective) => effective,
  },
};

/** Маппинг equipmentType из API → WeightInputType */
export function getWeightInputType(equipmentType?: string): WeightInputType {
  const t = (equipmentType || '').toLowerCase();
  if (t === 'barbell') return 'barbell';
  if (t === 'machine') return 'plate_loaded';
  if (t === 'dumbbell') return 'dumbbell';
  if (t === 'assisted' || t.includes('assist') || t.includes('гравитрон')) return 'assisted';
  return 'standard';
}

export function calcEffectiveWeight(
  inputStr: string,
  type: WeightInputType,
  userBodyWeight?: number
): number | null {
  const input = parseFloat(inputStr);
  if (isNaN(input) || input < 0) return null;
  const formula = WEIGHT_FORMULAS[type];
  return formula.toEffective(input, userBodyWeight ?? USER_BODY_WEIGHT_DEFAULT);
}
