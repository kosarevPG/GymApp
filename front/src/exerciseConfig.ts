/**
 * Input Normalization — ввод веса по легенде Type.
 * Gross/Effective считаются детерминированно из метаданных упражнения (Type, Base_Wt, Multiplier).
 * Пользователь вводит только Input_Wt — остальное вычисляется.
 */

export type WeightInputType = 'barbell' | 'plate_loaded' | 'assisted' | 'dumbbell' | 'machine' | 'bodyweight' | 'standard';

export interface WeightFormula {
  placeholder: string;
  label: string;
  /** input, bodyWeight?, baseWeight? → effective load */
  toEffective: (input: number, userBodyWeight?: number, baseWeight?: number) => number;
  toInput?: (effective: number, userBodyWeight?: number, baseWeight?: number) => number;
}

const USER_BODY_WEIGHT_DEFAULT = 90;

/** Дефолтные Base_Wt по типу (если не заданы в REF_Exercises) */
const DEFAULT_BASE: Record<WeightInputType, number> = {
  barbell: 20,
  plate_loaded: 50,
  assisted: 0,
  dumbbell: 0,
  machine: 0,
  bodyweight: 0,
  standard: 0,
};

export const WEIGHT_FORMULAS: Record<WeightInputType, WeightFormula> = {
  barbell: {
    placeholder: '0',
    label: '×1 блин',
    toEffective: (input, _, base = DEFAULT_BASE.barbell) => input * 2 + base,
    toInput: (effective, _, base = DEFAULT_BASE.barbell) => Math.round((effective - base) / 2),
  },
  plate_loaded: {
    placeholder: '0',
    label: '×1 блин',
    toEffective: (input, _, base = DEFAULT_BASE.plate_loaded) => input * 2 + base,
    toInput: (effective, _, base = DEFAULT_BASE.plate_loaded) => Math.round((effective - base) / 2),
  },
  assisted: {
    placeholder: '0',
    label: 'Плитка',
    toEffective: (input, bw = USER_BODY_WEIGHT_DEFAULT, base = 0) => Math.max(0, bw - input - base),
    toInput: (effective, bw = USER_BODY_WEIGHT_DEFAULT) => Math.round(bw - effective),
  },
  dumbbell: {
    placeholder: '0',
    label: 'кг',
    toEffective: (input, _, base = 0) => input + base,
    toInput: (effective, _, base = 0) => Math.round(effective - base),
  },
  machine: {
    placeholder: '0',
    label: 'кг',
    toEffective: (input, _, base = 0) => input + base,
    toInput: (effective, _, base = 0) => Math.round(effective - base),
  },
  bodyweight: {
    placeholder: '0',
    label: '+кг',
    toEffective: (input, bw = USER_BODY_WEIGHT_DEFAULT, base = 0) => bw + input + base,
    toInput: (effective, bw = USER_BODY_WEIGHT_DEFAULT, base = 0) => Math.round(effective - bw - base),
  },
  standard: {
    placeholder: '0',
    label: 'кг',
    toEffective: (input, _, base = 0) => input + base,
    toInput: (effective, _, base = 0) => Math.round(effective - base),
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
  if (t === 'machine') return 'machine';
  if (t === 'assisted' || t.includes('assist') || t.includes('гравитрон')) return 'assisted';
  return 'standard';
}

export function calcEffectiveWeight(
  inputStr: string,
  type: WeightInputType,
  userBodyWeight?: number,
  baseWeight?: number
): number | null {
  const input = parseFloat(inputStr);
  if (isNaN(input) || input < 0) return null;
  const formula = WEIGHT_FORMULAS[type];
  const base = baseWeight ?? DEFAULT_BASE[type];
  return formula.toEffective(input, userBodyWeight ?? USER_BODY_WEIGHT_DEFAULT, base);
}
