export interface WorkoutSetBase {
  id: string;
  weight: string;
  reps: string;
  rest: string;
  completed: boolean;
  prevWeight?: number;
  order?: number;
  setGroupId?: string;
  isEditing?: boolean;
  rowNumber?: number;
  effectiveWeight?: number;
}

export function createEmptySet(overrides?: Partial<WorkoutSetBase>): WorkoutSetBase {
  return {
    id: crypto.randomUUID(),
    weight: '',
    reps: '',
    rest: '',
    completed: false,
    prevWeight: 0,
    ...overrides
  };
}

export function createSetFromHistory(s: { weight: number; inputWeight?: number; reps: number; rest: number }, prevWeight?: number): WorkoutSetBase {
  const weightStr = s.inputWeight !== undefined && s.inputWeight !== null
    ? String(s.inputWeight)
    : String(s.weight);
  return createEmptySet({
    weight: weightStr,
    reps: s.reps.toString(),
    rest: s.rest.toString(),
    prevWeight: prevWeight ?? s.weight
  });
}
