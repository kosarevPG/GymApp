/**
 * Input Normalization — ввод веса по легенде Type.
 * Barbell/Plate_Loaded: Ввод × 2 + База (блины с одной стороны)
 * Dumbbell/Machine: Ввод (гантель / цифра на плитке)
 * Assisted: Вес тела − Ввод (гравитрон)
 * Bodyweight: Вес тела + Ввод (пояс с гирей)
 */

export type WeightInputType = 'barbell' | 'plate_loaded' | 'assisted' | 'dumbbell' | 'machine' | 'bodyweight' | 'standard';

export interface WeightFormula {
  placeholder: string;
  label: string;
  toEffective: (input: number, userBodyWeight?: number) => number;
  toInput?: (effective: number, userBodyWeight?: number) => number;
}

const USER_BODY_WEIGHT_DEFAULT = 90;

export const WEIGHT_FORMULAS: Record<WeightInputType, WeightFormula> = {
  barbell: {
    placeholder: '0',
    label: '×1 блин',
    toEffective: (input) => input * 2 + 20, // 20 кг гриф
    toInput: (effective) => Math.round((effective - 20) / 2),
  },
  plate_loaded: {
    placeholder: '0',
    label: '×1 блин',
    toEffective: (input) => input * 2 + 50, // 50 кг каретка по умолчанию
    toInput: (effective) => Math.round((effective - 50) / 2),
  },
  assisted: {
    placeholder: '0',
    label: 'Плитка',
    toEffective: (input, bw = USER_BODY_WEIGHT_DEFAULT) => Math.max(0, bw - input),
    toInput: (effective, bw = USER_BODY_WEIGHT_DEFAULT) => Math.round(bw - effective),
  },
  dumbbell: {
    placeholder: '0',
    label: 'кг',
    toEffective: (input) => input,
    toInput: (effective) => effective,
  },
  machine: {
    placeholder: '0',
    label: 'кг',
    toEffective: (input) => input,
    toInput: (effective) => effective,
  },
  bodyweight: {
    placeholder: '0',
    label: '+кг',
    toEffective: (input, bw = USER_BODY_WEIGHT_DEFAULT) => bw + input,
    toInput: (effective, bw = USER_BODY_WEIGHT_DEFAULT) => Math.round(effective - bw),
  },
  standard: {
    placeholder: '0',
    label: 'кг',
    toEffective: (input) => input,
    toInput: (effective) => effective,
  },
};

/** equipmentType/weightType из API → WeightInputType */
export function getWeightInputType(equipmentType?: string, weightType?: string): WeightInputType {
  const wt = (weightType || '').toLowerCase();
  if (wt === 'barbell') return 'barbell';
  if (wt === 'plate_loaded') return 'plate_loaded';
  if (wt === 'machine') return 'machine';
  if (wt === 'dumbbell') return 'dumbbell';
  if (wt === 'assisted') return 'assisted';
  if (wt === 'bodyweight') return 'bodyweight';

  const t = (equipmentType || '').toLowerCase();
  if (t === 'barbell') return 'barbell';
  if (t === 'dumbbell') return 'dumbbell';
  if (t === 'machine') return 'machine'; // блочные тренажеры: ввод как есть
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
