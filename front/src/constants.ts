export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
export const WORKOUT_STORAGE_KEY = 'gym_workout_state_v2';
export const EDIT_EXERCISE_DRAFT_KEY = 'gym_edit_exercise_draft';
export const SESSION_ID_KEY = 'gym_session_id';
export const ORDER_COUNTER_KEY = 'gym_order_counter';
export const LAST_ACTIVE_KEY = 'gym_last_active';

export const GROUP_ORDER = ['Спина', 'Ноги', 'Грудь', 'Плечи', 'Трицепс', 'Бицепс', 'Пресс', 'Кардио'];

export function sortGroups(groupsList: string[]): string[] {
  const sorted: string[] = [];
  const remaining = [...groupsList];
  GROUP_ORDER.forEach(groupName => {
    const index = remaining.indexOf(groupName);
    if (index !== -1) {
      sorted.push(groupName);
      remaining.splice(index, 1);
    }
  });
  sorted.push(...remaining);
  return sorted;
}
