// Офлайн-синхронизация: очередь операций и менеджер синхронизации

import { API_BASE_URL } from './constants';

export const PENDING_QUEUE_KEY = 'gym_pending_queue';
export const EXERCISES_CACHE_KEY = 'gym_exercises_cache';

// Типы операций
export type OperationType = 'saveSet' | 'updateSet' | 'createExercise' | 'updateExercise';

export interface PendingOperation {
  id: string;
  type: OperationType;
  data: any;
  createdAt: number;
  retryCount: number;
}

// Статус синхронизации
export type SyncStatus = 'online' | 'offline' | 'syncing';

// Подписчики на изменение статуса
type StatusListener = (status: SyncStatus, pendingCount: number) => void;
const listeners: Set<StatusListener> = new Set();

let currentStatus: SyncStatus = navigator.onLine ? 'online' : 'offline';
let isSyncing = false;

// --- Очередь операций ---

export function getQueue(): PendingOperation[] {
  try {
    const raw = localStorage.getItem(PENDING_QUEUE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveQueue(queue: PendingOperation[]): void {
  localStorage.setItem(PENDING_QUEUE_KEY, JSON.stringify(queue));
  notifyListeners();
}

export function addToQueue(type: OperationType, data: any): string {
  const queue = getQueue();
  const id = `pending_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
  queue.push({
    id,
    type,
    data,
    createdAt: Date.now(),
    retryCount: 0
  });
  saveQueue(queue);
  return id;
}

export function removeFromQueue(id: string): void {
  const queue = getQueue().filter(op => op.id !== id);
  saveQueue(queue);
}

export function updateQueueItem(id: string, updates: Partial<PendingOperation>): void {
  const queue = getQueue().map(op => op.id === id ? { ...op, ...updates } : op);
  saveQueue(queue);
}

export function getPendingCount(): number {
  return getQueue().length;
}

// --- Кэш упражнений ---

export function cacheExercises(data: { groups: string[]; exercises: any[] }): void {
  try {
    localStorage.setItem(EXERCISES_CACHE_KEY, JSON.stringify({
      data,
      cachedAt: Date.now()
    }));
  } catch (e) {
    console.error('Failed to cache exercises:', e);
  }
}

export function getCachedExercises(): { groups: string[]; exercises: any[] } | null {
  try {
    const raw = localStorage.getItem(EXERCISES_CACHE_KEY);
    if (!raw) return null;
    const { data } = JSON.parse(raw);
    return data;
  } catch {
    return null;
  }
}

// --- Статус и подписки ---

export function subscribeToStatus(listener: StatusListener): () => void {
  listeners.add(listener);
  // Сразу уведомляем о текущем статусе
  listener(currentStatus, getPendingCount());
  return () => listeners.delete(listener);
}

function notifyListeners(): void {
  const count = getPendingCount();
  listeners.forEach(listener => listener(currentStatus, count));
}

function setStatus(status: SyncStatus): void {
  if (currentStatus !== status) {
    currentStatus = status;
    notifyListeners();
  }
}

export function isOnline(): boolean {
  return navigator.onLine;
}

export function getStatus(): SyncStatus {
  return currentStatus;
}

// --- Синхронизация ---

async function executeOperation(op: PendingOperation): Promise<{ success: boolean; result?: any }> {
  const endpoints: Record<OperationType, string> = {
    saveSet: 'save_set',
    updateSet: 'update_set',
    createExercise: 'create_exercise',
    updateExercise: 'update_exercise'
  };

  try {
    const res = await fetch(`${API_BASE_URL}/api/${endpoints[op.type]}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(op.data)
    });
    
    if (!res.ok) {
      return { success: false };
    }
    
    const result = await res.json();
    return { success: true, result };
  } catch (e) {
    console.error(`Sync operation failed (${op.type}):`, e);
    return { success: false };
  }
}

export async function syncAll(): Promise<{ synced: number; failed: number }> {
  if (isSyncing || !navigator.onLine) {
    return { synced: 0, failed: 0 };
  }

  isSyncing = true;
  setStatus('syncing');

  const queue = getQueue();
  let synced = 0;
  let failed = 0;

  // Обрабатываем операции по порядку (FIFO)
  for (const op of queue) {
    const { success, result } = await executeOperation(op);
    
    if (success) {
      removeFromQueue(op.id);
      synced++;
      
      // Уведомляем о успешной синхронизации saveSet (для обновления row_number)
      if (op.type === 'saveSet' && result?.row_number && onSaveSetSynced) {
        onSaveSetSynced(op.id, op.data, result.row_number);
      }
    } else {
      // Увеличиваем счётчик попыток
      updateQueueItem(op.id, { retryCount: op.retryCount + 1 });
      failed++;
      
      // Если слишком много попыток, пропускаем (но не удаляем)
      if (op.retryCount >= 5) {
        console.warn(`Operation ${op.id} failed after 5 retries`);
      }
    }
  }

  isSyncing = false;
  setStatus(navigator.onLine ? 'online' : 'offline');

  return { synced, failed };
}

// Колбэк для обновления row_number после синхронизации saveSet
let onSaveSetSynced: ((pendingId: string, data: any, rowNumber: number) => void) | null = null;

export function setOnSaveSetSynced(callback: (pendingId: string, data: any, rowNumber: number) => void): void {
  onSaveSetSynced = callback;
}

// --- Инициализация слушателей сети ---

export function initNetworkListeners(): void {
  window.addEventListener('online', () => {
    setStatus('online');
    // Автоматически синхронизируем при появлении сети
    syncAll();
  });

  window.addEventListener('offline', () => {
    setStatus('offline');
  });

  // Устанавливаем начальный статус
  setStatus(navigator.onLine ? 'online' : 'offline');
}
