import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  Search, ChevronRight, Plus, X, Info, 
  Check, Trash2, StickyNote, ChevronDown, Dumbbell, Calendar, 
  Settings, ArrowLeft, Pencil, Trophy,
  History as HistoryIcon, Activity, Link as LinkIcon, BarChart3, AlertTriangle
} from 'lucide-react';
import { getWeightInputType, calcEffectiveWeight, WEIGHT_FORMULAS, BODY_WEIGHT_DEFAULT, WEIGHT_TYPES, allows1rm } from './exerciseConfig';
import { API_BASE_URL, WORKOUT_STORAGE_KEY, EDIT_EXERCISE_DRAFT_KEY, SESSION_ID_KEY, ORDER_COUNTER_KEY, LAST_ACTIVE_KEY, sortGroups } from './constants';
import { createEmptySet, createSetFromHistory } from './utils';
import { ScreenHeader } from './components/ScreenHeader';
import { SetDisplayRow } from './components/SetDisplayRow';
import { ImageUploadSlot } from './components/ImageUploadSlot';
import { motion, AnimatePresence } from 'framer-motion'; 

// --- TYPES ---

type Screen = 'home' | 'exercises' | 'workout' | 'history' | 'analytics';

interface Exercise {
  id: string;
  name: string;
  muscleGroup: string;
  description?: string;
  imageUrl?: string;
  imageUrl2?: string;
  equipmentType?: string;
  weightType?: string;
  baseWeight?: number;
  weightMultiplier?: number;
  /** 1RM методологически некорректен для Assisted/Bodyweight */
  allow_1rm?: boolean;
}

interface WorkoutSet {
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
  effectiveWeight?: number;  // Итоговый вес для аналитики (input * 2 + гриф и т.д.)
}

interface HistoryItem {
  date: string;
  weight: number;
  reps: number;
  rest: number;
  order?: number;
  setGroupId?: string | null;  // ID группы подходов (для суперсетов)
}

interface ExerciseSessionData {
  exercise: Exercise;
  note: string;
  sets: WorkoutSet[];
  history: HistoryItem[];
}

interface GlobalWorkoutSession {
    id: string;
    date: string;
    muscleGroups: string[];
    duration: string;
    exercises: { name: string; sets: any[]; supersetId?: string }[];
}

// --- API SERVICE (REAL FETCH) ---

const api = {
  request: async (endpoint: string, options: RequestInit = {}) => {
      try {
          const res = await fetch(`${API_BASE_URL}/api/${endpoint}`, {
              ...options,
              headers: { 'Content-Type': 'application/json', ...options.headers }
          });
          if (!res.ok) throw new Error('API Error');
          return await res.json();
      } catch (e) {
          console.error(e);
          return null;
      }
  },

  getInit: async () => {
      const data = await api.request('init');
      return data || { groups: [], exercises: [] };
  },

  getHistory: async (exerciseId: string) => {
      const data = await api.request(`history?exercise_id=${exerciseId}`);
      return data || { history: [], note: '' };
  },

  getGlobalHistory: async () => {
      const data = await api.request('global_history');
      return data || [];
  },

  getAnalytics: async (period: number = 14) => {
      const params = new URLSearchParams();
      params.set('period', period.toString());
      const data = await api.request(`analytics?${params.toString()}`);
      return data || null;
  },
  confirmBaseline: async (proposalId: string, action: 'CONFIRM' | 'SNOOZE' | 'DECLINE') => {
      return await api.request('confirm_baseline', {
          method: 'POST',
          body: JSON.stringify({ proposalId, action })
      });
  },

  saveSet: async (data: any) => {
      return await api.request('save_set', { method: 'POST', body: JSON.stringify(data) });
  },

  updateSet: async (data: any) => {
      return await api.request('update_set', { method: 'POST', body: JSON.stringify(data) });
  },

  createExercise: async (name: string, group: string) => {
      return await api.request('create_exercise', { 
          method: 'POST', 
          body: JSON.stringify({ name, group }) 
      });
  },

  updateExercise: async (id: string, updates: Partial<Exercise>) => {
      return await api.request('update_exercise', { 
          method: 'POST', 
          body: JSON.stringify({ id, updates }) 
      });
  },

  ping: async () => {
      return await api.request('ping');
  },

  uploadImage: async (file: File) => {
      const formData = new FormData();
      formData.append('image', file);
      
      try {
          const res = await fetch(`${API_BASE_URL}/api/upload_image`, {
              method: 'POST',
              body: formData
          });
          if (!res.ok) throw new Error('Upload failed');
          return await res.json();
      } catch (e) {
          console.error('Image upload error:', e);
          return null;
      }
  }
};

// --- HOOKS ---

const useTelegram = () => {
  const tg = (window as any).Telegram?.WebApp;
  useEffect(() => {
    tg?.ready();
    tg?.expand();
    if (tg) {
      tg.setHeaderColor('#09090b');
      tg.setBackgroundColor('#09090b');
      // Запрашиваем полноэкранный режим, если доступен
      if (typeof tg.requestFullscreen === 'function') {
        try {
          tg.requestFullscreen();
        } catch (e) {
          // Игнорируем ошибки, если метод недоступен
        }
      }
    }
  }, []);
  const haptic = (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => tg?.HapticFeedback?.impactOccurred(style);
  const notify = (type: 'error' | 'success' | 'warning') => tg?.HapticFeedback?.notificationOccurred(type);
  return { tg, haptic, notify };
};

const useTimer = () => {
  const [time, setTime] = useState(0);
  const [isRunning, setIsRunning] = useState(false);
  const intervalRef = useRef<any>(null);

  const start = () => {
    if (isRunning) return;
    setIsRunning(true);
    const startTime = Date.now() - time;
    intervalRef.current = setInterval(() => setTime(Date.now() - startTime), 50);
  };
  const pause = () => {
    setIsRunning(false);
    clearInterval(intervalRef.current);
  };
  const reset = () => {
    setIsRunning(false);
    clearInterval(intervalRef.current);
    setTime(0);
  };
  const resetAndStart = () => {
    // Сначала останавливаем и очищаем
    clearInterval(intervalRef.current);
    setTime(0);
    // Затем сразу запускаем
    setIsRunning(true);
    const startTime = Date.now();
    intervalRef.current = setInterval(() => setTime(Date.now() - startTime), 50);
  };
  const formatTime = (ms: number) => {
    const totalSeconds = Math.floor(ms / 1000);
    const m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const s = (totalSeconds % 60).toString().padStart(2, '0');
    const ms2 = Math.floor((ms % 1000) / 10).toString().padStart(2, '0');
    return `${m}:${s}.${ms2}`;
  };
  return { time, isRunning, start, pause, reset, resetAndStart, formatTime };
};

// Хук для debounce значения
const useDebounce = <T,>(value: T, delay: number): T => {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
};

const useSession = () => {
  const [sessionId, setSessionId] = useState('');
  const [orderCounter, setOrderCounter] = useState(0);

  useEffect(() => {
    const lastActive = localStorage.getItem(LAST_ACTIVE_KEY);
    const savedSession = localStorage.getItem(SESSION_ID_KEY);
    const savedOrder = localStorage.getItem(ORDER_COUNTER_KEY);
    const now = Date.now();

    if (!lastActive || (now - parseInt(lastActive)) > 14400000 || !savedSession) {
      const newId = crypto.randomUUID();
      setSessionId(newId);
      setOrderCounter(0);
      localStorage.setItem(SESSION_ID_KEY, newId);
    } else {
      setSessionId(savedSession);
      setOrderCounter(parseInt(savedOrder || '0'));
    }
    localStorage.setItem(LAST_ACTIVE_KEY, now.toString());
  }, []);

  const incrementOrder = () => {
    const next = orderCounter + 1;
    setOrderCounter(next);
    localStorage.setItem(ORDER_COUNTER_KEY, next.toString());
    localStorage.setItem(LAST_ACTIVE_KEY, Date.now().toString());
    return next;
  };
  return { sessionId, incrementOrder };
};

// --- UI COMPONENTS ---

const Card = ({ children, className = '', onClick }: any) => (
  <div onClick={onClick} className={`bg-zinc-900 border border-zinc-800 rounded-2xl ${className}`}>
    {children}
  </div>
);

const Button = ({ children, variant = 'primary', className = '', onClick, icon: Icon }: any) => {
  const variants: any = {
    primary: "bg-blue-600 text-white shadow-lg shadow-blue-900/20 hover:bg-blue-500",
    secondary: "bg-zinc-800 text-zinc-50 hover:bg-zinc-700",
    ghost: "bg-transparent text-zinc-400 hover:text-zinc-50 hover:bg-zinc-800/50",
    danger: "bg-red-500/10 text-red-500 hover:bg-red-500/20",
    success: "bg-green-500/10 text-green-500"
  };
  return (
    <button onClick={onClick} className={`flex items-center justify-center font-medium rounded-xl transition-all active:scale-95 disabled:opacity-50 ${variants[variant]} ${className}`}>
      {Icon && <Icon className="w-5 h-5 mr-2" />}
      {children}
    </button>
  );
};

const Input = React.forwardRef<HTMLInputElement, any>((props, ref) => (
  <input ref={ref} {...props} className={`w-full h-12 bg-zinc-900 text-zinc-50 rounded-xl px-4 focus:outline-none focus:ring-1 focus:ring-zinc-600 placeholder:text-zinc-600 transition-all ${props.className}`} />
));
Input.displayName = 'Input';

const Modal = ({ isOpen, onClose, title, children, headerAction }: any) => (
  <AnimatePresence>
    {isOpen && (
      <>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50" />
        <motion.div initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", damping: 25, stiffness: 300 }} className="fixed bottom-4 left-0 right-0 bg-zinc-900 border-t border-zinc-800 rounded-t-3xl z-50 max-h-[85vh] flex flex-col mx-4">
          <div className="p-4 border-b border-zinc-800 flex items-center justify-between shrink-0">
            <h3 className="text-lg font-semibold text-zinc-50 truncate max-w-[70%]">{title}</h3>
            <div className="flex items-center gap-2">
                {headerAction}
                <button onClick={onClose} className="p-2 bg-zinc-800 rounded-full text-zinc-400"><X className="w-5 h-5" /></button>
            </div>
          </div>
          <div className="overflow-y-auto p-4 flex-1 pb-10">{children}</div>
        </motion.div>
      </>
    )}
  </AnimatePresence>
);

// --- FEATURES ---

const TimerBlock = ({ timer, onToggle }: any) => (
  <div className="sticky top-0 z-40 bg-zinc-950/80 backdrop-blur-md pb-4 pt-2 px-4 border-b border-zinc-800/50 mb-4">
    <Card className="flex items-center justify-between p-3 px-5 shadow-xl shadow-black/50">
      <div className="font-mono text-3xl font-bold tracking-wider text-zinc-50 tabular-nums">{timer.formatTime(timer.time)}</div>
      <div className="flex gap-2">
        <Button variant={timer.isRunning ? "danger" : "primary"} onClick={onToggle} className="w-20 h-10 text-sm">{timer.isRunning ? "Стоп" : "Старт"}</Button>
      </div>
    </Card>
  </div>
);

const NoteWidget = ({ initialValue, onChange }: any) => {
  const [isOpen, setIsOpen] = useState(false);
  const [value, setValue] = useState(initialValue);
  useEffect(() => setValue(initialValue), [initialValue]);

  return (
    <div className="mb-4">
      <button onClick={() => setIsOpen(!isOpen)} className="flex items-center gap-2 text-yellow-500 text-sm font-medium mb-2 w-full">
        <StickyNote className="w-4 h-4" /><span>Заметка</span><ChevronDown className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <textarea value={value} onChange={(e) => { setValue(e.target.value); onChange(e.target.value); }} placeholder="Настройки..." className="w-full bg-yellow-500/10 border border-yellow-500/20 rounded-xl p-3 text-yellow-200 text-sm focus:outline-none min-h-[80px]" />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

const HistoryListModal = ({ isOpen, onClose, history, exerciseName }: any) => {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`История: ${exerciseName}`}>
      <div className="space-y-6">
        {history.map((group: any, idx: number) => {
          if (group.isSuperset && group.exercises) {
            // Отображаем суперсет со всеми упражнениями
            return (
              <div key={idx}>
                <div className="flex items-center gap-2 mb-2 sticky top-0 bg-zinc-900 py-1 z-10">
                  <Calendar className="w-4 h-4 text-zinc-500" />
                  <span className="text-sm font-bold text-zinc-400 uppercase tracking-wider">{group.date}</span>
                </div>
                <div className="bg-zinc-800/30 border border-zinc-800 rounded-xl overflow-hidden">
                  <div className="px-3 pt-3 pb-1 text-xs text-blue-400 font-bold flex items-center">
                    <LinkIcon className="w-3 h-3 mr-1" /> СУПЕРСЕТ
                  </div>
                  {group.exercises.map((ex: any, exIdx: number) => (
                    <div key={exIdx}>
                      {exIdx > 0 && <div className="border-t border-zinc-800/50" />}
                      <div className="px-3 pt-2 pb-1 text-sm font-medium text-zinc-300">
                        {ex.exerciseName}
                      </div>
                      {ex.sets.map((set: any, setIdx: number) => {
                        const isLastSet = setIdx === ex.sets.length - 1;
                        const isLastExercise = exIdx === group.exercises.length - 1;
                        const borderClass = isLastSet && isLastExercise ? '' : 'border-b border-zinc-800/50';
                        return (
                          <SetDisplayRow key={setIdx} weight={set.weight} reps={set.reps} rest={set.rest} className={`p-3 border-l-2 border-l-blue-500 bg-blue-500/5 ${borderClass}`} />
                        );
                      })}
                    </div>
                  ))}
                </div>
              </div>
            );
          } else {
            // Обычные подходы (не в суперсете)
            return (
              <div key={idx}>
                <div className="flex items-center gap-2 mb-2 sticky top-0 bg-zinc-900 py-1 z-10">
                  <Calendar className="w-4 h-4 text-zinc-500" />
                  <span className="text-sm font-bold text-zinc-400 uppercase tracking-wider">{group.date}</span>
                </div>
                <div className="bg-zinc-800/30 border border-zinc-800 rounded-xl overflow-hidden">
                  {group.sets.map((set: any, setIdx: number) => {
                    const isLastSet = setIdx === group.sets.length - 1;
                    return (
                      <SetDisplayRow key={setIdx} weight={set.weight} reps={set.reps} rest={set.rest} className={`p-3 ${isLastSet ? '' : 'border-b border-zinc-800/50'}`} />
                    );
                  })}
                </div>
              </div>
            );
          }
        })}
        {history.length === 0 && <div className="text-center text-zinc-500 py-10">История пуста</div>}
      </div>
    </Modal>
  );
};

const SetRow = ({ set, equipmentType, weightType: weightTypeFromRef, baseWeight, weightMultiplier, onUpdate, onDelete, onComplete, onToggleEdit }: { set: any; equipmentType?: string; weightType?: string; baseWeight?: number; weightMultiplier?: number; onUpdate: (sid: string, field: string, value: string) => void; onDelete: (sid: string) => void; onComplete: (sid: string) => void; onToggleEdit: (sid: string) => void }) => {
  const weightType = getWeightInputType(equipmentType, weightTypeFromRef);
  const formula = WEIGHT_FORMULAS[weightType];
  const effectiveWeight = calcEffectiveWeight(set.weight || '', weightType, undefined, baseWeight, weightMultiplier);
  const displayWeight = set.completed ? (set.effectiveWeight ?? (parseFloat(set.weight) || 0)) : (effectiveWeight ?? (parseFloat(set.weight) || 0));
  const show1rm = allows1rm(weightType);
  const oneRM = show1rm && displayWeight && set.reps ? Math.round(displayWeight * (1 + parseInt(set.reps) / 30)) : 0;
  const isAssisted = weightType === 'assisted';
  const asi = isAssisted && displayWeight && displayWeight > 0 ? (displayWeight / BODY_WEIGHT_DEFAULT).toFixed(2) : null;
  const delta = set.prevWeight ? (displayWeight - set.prevWeight) : 0;
  const deltaText = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '0';
  const deltaColor = delta > 0 ? 'text-green-500' : delta < 0 ? 'text-red-500' : 'text-zinc-500';
  const isCompleted = set.completed;
  const isEditing = set.isEditing;
  const inputDisabledClass = isCompleted && !isEditing ? 'opacity-50 pointer-events-none' : '';
  const showTotalBadge = effectiveWeight !== null && effectiveWeight !== parseFloat(set.weight || '0');

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 items-start mb-3">
      <button onClick={() => onComplete(set.id)} className={`w-12 h-12 rounded-full border-2 flex items-center justify-center transition-all duration-200 ${isCompleted ? 'bg-yellow-500 border-yellow-500' : 'bg-transparent border-zinc-700 hover:border-zinc-500'}`}>
        {isCompleted && <Check className="w-6 h-6 text-black stroke-[3]" />}
      </button>
      
      <div className={`flex flex-col gap-1 ${inputDisabledClass}`}>
        <input 
          type="number" 
          inputMode="decimal" 
          min="0"
          step="0.5"
          placeholder={formula.placeholder} 
          value={set.weight} 
          onChange={e => {
            const v = e.target.value;
            if (v === '') { onUpdate(set.id, 'weight', v); return; }
            const num = parseFloat(v);
            if (!isNaN(num) && num >= 0) onUpdate(set.id, 'weight', v);
          }}
          onFocus={e => e.target.select()}
          className="w-full h-12 bg-zinc-800 rounded-xl text-center text-xl font-bold text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums" 
        />
        <div className="flex justify-between items-center px-1 text-[10px] flex-wrap gap-x-2 gap-y-0.5">
          {showTotalBadge && effectiveWeight !== null && effectiveWeight >= 0 && (
            <span className="text-blue-400 font-medium">Итого: {effectiveWeight} кг</span>
          )}
          {show1rm && oneRM > 0 && <span className="text-zinc-500">1PM: {oneRM}</span>}
          {!show1rm && (weightType === 'assisted' || weightType === 'bodyweight') && (
            <span className="text-zinc-600 text-[9px]">1RM не рассчитывается</span>
          )}
          {asi !== null && <span className="text-zinc-500">ASI: {asi}</span>}
          {set.prevWeight !== undefined && displayWeight > 0 && <span className={`${deltaColor} font-medium`}>{deltaText}</span>}
        </div>
      </div>
      <input 
        type="tel" 
        inputMode="numeric" 
        placeholder="0" 
        value={set.reps} 
        onChange={e => onUpdate(set.id, 'reps', e.target.value)}
        onFocus={e => e.target.select()}
        className={`w-full h-12 bg-zinc-800 rounded-xl text-center text-xl font-bold text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums ${inputDisabledClass}`} 
      />
      <input 
        type="number" 
        inputMode="decimal" 
        placeholder="0" 
        value={set.rest} 
        onChange={e => onUpdate(set.id, 'rest', e.target.value)}
        onFocus={e => e.target.select()}
        className={`w-full h-12 bg-zinc-800 rounded-xl text-center text-zinc-400 focus:text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums ${inputDisabledClass}`} 
      />
      {isCompleted ? (
        <button onClick={() => onToggleEdit(set.id)} className={`w-10 h-12 flex items-center justify-center transition-colors ${isEditing ? 'text-yellow-500' : 'text-zinc-600 hover:text-zinc-400'}`}>
          <Pencil className="w-5 h-5" />
        </button>
      ) : (
        <button onClick={() => onDelete(set.id)} className="w-10 h-12 flex items-center justify-center text-zinc-600 hover:text-red-500"><Trash2 className="w-5 h-5" /></button>
      )}
    </motion.div>
  );
};

const WorkoutCard = ({ exerciseData, onAddSet, onUpdateSet, onDeleteSet, onCompleteSet, onToggleEdit, onNoteChange, onAddSuperset, onEditMetadata }: any) => {
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  
  // PR из истории
  const historyPR = useMemo(() => {
    if (!exerciseData.history.length) return 0;
    let maxWeight = 0;
    for (const group of exerciseData.history) {
      // Формат с sets (упрощённый)
      if (group.sets) {
        for (const s of group.sets) {
          if (s.weight > maxWeight) maxWeight = s.weight;
        }
      }
      // Формат с exercises (суперсет - для обратной совместимости)
      if (group.exercises) {
        for (const ex of group.exercises) {
          for (const s of ex.sets || []) {
            if (s.weight > maxWeight) maxWeight = s.weight;
          }
        }
      }
      // Старый плоский формат (для совместимости)
      if (typeof group.weight === 'number' && group.weight > maxWeight) {
        maxWeight = group.weight;
      }
    }
    return maxWeight;
  }, [exerciseData.history]);
  
  // Максимальный вес в текущей сессии (effective для PR)
  const sessionMax = useMemo(() => {
    const completedSets = exerciseData.sets.filter((s: any) => s.completed && (s.weight || s.effectiveWeight));
    if (!completedSets.length) return 0;
    return Math.max(...completedSets.map((s: any) => s.effectiveWeight ?? (parseFloat(s.weight) || 0)));
  }, [exerciseData.sets]);
  
  // Проверяем побит ли PR в текущей сессии
  const isNewPR = sessionMax > historyPR && sessionMax > 0;
  const displayPR = Math.max(historyPR, sessionMax);

  return (
    <Card className="p-4 mb-4">
      <div className="flex justify-between items-start mb-4">
        <div className="flex-1 flex items-center gap-2">
            <button onClick={onEditMetadata} className="p-1.5 rounded-lg text-zinc-500 hover:text-blue-400 hover:bg-zinc-800 transition-colors flex-shrink-0" title="Редактировать расчёт веса"><Pencil className="w-4 h-4" /></button>
            <h2 className="text-xl font-semibold text-zinc-50">{exerciseData.exercise.name}</h2>
        </div>
        {/* PR Badge - крупный и заметный */}
        {displayPR > 0 && (
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-xl ${isNewPR ? 'bg-gradient-to-r from-yellow-500 to-orange-500 animate-pulse' : 'bg-zinc-800'}`}>
            <Trophy className={`w-4 h-4 ${isNewPR ? 'text-white' : 'text-yellow-500'}`} />
            <div className="flex flex-col items-end">
              <span className={`text-sm font-bold ${isNewPR ? 'text-white' : 'text-yellow-500'}`}>{displayPR} кг</span>
              {isNewPR && <span className="text-[10px] text-white/90 font-medium">NEW PR!</span>}
            </div>
          </div>
        )}
        <button onClick={() => setShowHistoryModal(true)} className="p-2 bg-zinc-800/50 rounded-lg text-zinc-400 hover:text-blue-500 ml-2"><Calendar className="w-5 h-5" /></button>
      </div>
      <NoteWidget initialValue={exerciseData.note} onChange={onNoteChange} />
      <HistoryListModal isOpen={showHistoryModal} onClose={() => setShowHistoryModal(false)} history={exerciseData.history} exerciseName={exerciseData.exercise.name} />
      <div className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 mb-2 px-1">
        <div className="w-10" />
        <div className="text-[10px] text-center text-zinc-500 font-bold uppercase">{WEIGHT_FORMULAS[getWeightInputType(exerciseData.exercise.equipmentType, exerciseData.exercise.weightType)].label}</div>
        <div className="text-[10px] text-center text-zinc-500 font-bold uppercase">ПОВТ</div>
        <div className="text-[10px] text-center text-zinc-500 font-bold uppercase">МИН</div>
        <div className="w-8" />
      </div>
      <div className="space-y-1">
        {exerciseData.sets.map((set: any) => (
          <SetRow key={set.id} set={set} equipmentType={exerciseData.exercise.equipmentType} weightType={exerciseData.exercise.weightType} baseWeight={exerciseData.exercise.baseWeight} weightMultiplier={exerciseData.exercise.weightMultiplier} onUpdate={onUpdateSet} onDelete={onDeleteSet} onComplete={onCompleteSet} onToggleEdit={onToggleEdit} />
        ))}
      </div>
      <div className="flex gap-2 mt-4">
        <Button variant="secondary" onClick={onAddSet} className="flex-1 h-12 bg-zinc-800/50 border border-dashed border-zinc-700 text-zinc-400 hover:text-blue-500"><Plus className="w-5 h-5 mr-2" /> Подход</Button>
        <Button variant="ghost" onClick={onAddSuperset} className="w-1/3 h-12 border border-dashed border-zinc-800 text-zinc-500 hover:text-white"><Plus className="w-4 h-4 mr-1" /> Сет</Button>
      </div>
    </Card>
  );
};

// --- SCREENS ---

const HomeScreen = ({ groups, onSearch, onSelectGroup, onAllExercises, onHistory, onAnalytics, searchQuery }: any) => {
  return (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-6">
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <Input placeholder="Найти..." value={searchQuery || ''} onChange={(e: React.ChangeEvent<HTMLInputElement>) => onSearch(e.target.value)} className="pl-12 bg-zinc-900 w-full" />
      </div>
      <button onClick={onAnalytics} className="p-3 bg-zinc-900 rounded-xl text-zinc-400 hover:text-blue-500"><BarChart3 className="w-6 h-6" /></button>
      <button onClick={onHistory} className="p-3 bg-zinc-900 rounded-xl text-zinc-400 hover:text-blue-500"><HistoryIcon className="w-6 h-6" /></button>
    </div>
    <div className="flex flex-col space-y-2">
      {groups.map((group: string) => (
        <Card key={group} onClick={() => onSelectGroup(group)} className="flex items-center p-4 hover:bg-zinc-800 transition-colors active:scale-95 cursor-pointer">
          <div className="w-12 h-12 rounded-xl bg-zinc-800 flex items-center justify-center text-zinc-500 flex-shrink-0"><Dumbbell className="w-6 h-6" /></div>
          <span className="font-medium text-zinc-200 text-lg ml-4 flex-1">{group}</span>
          <ChevronRight className="w-6 h-6 text-zinc-600" />
        </Card>
      ))}
    </div>
    <Button onClick={onAllExercises} variant="secondary" className="w-full h-14 text-lg">Все упражнения</Button>
  </motion.div>
  );
};

// Мемоизированный компонент карточки упражнения
const ExerciseCard = React.memo(({ ex, onSelectExercise, onInfoClick }: { ex: Exercise; onSelectExercise: (ex: Exercise) => void; onInfoClick: (ex: Exercise) => void }) => (
  <div className="flex items-center p-2 rounded-2xl hover:bg-zinc-900 border border-transparent hover:border-zinc-800 transition-all">
    <div onClick={(e) => { e.stopPropagation(); onInfoClick(ex); }} className="w-14 h-14 rounded-xl bg-zinc-800 flex-shrink-0 overflow-hidden cursor-pointer active:scale-90 transition-transform relative group">
      {ex.imageUrl ? <img src={ex.imageUrl} className="w-full h-full object-cover" /> : <div className="w-full h-full flex items-center justify-center text-zinc-600"><Info /></div>}
      <div className="absolute inset-0 bg-black/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"><Settings className="w-5 h-5 text-white" /></div>
    </div>
    <div onClick={() => onSelectExercise(ex)} className="flex-1 px-4 cursor-pointer">
      <div className="font-medium text-zinc-100 text-[17px]">{ex.name}</div>
      <div className="text-xs text-zinc-500">{ex.muscleGroup}</div>
    </div>
    <button onClick={() => onSelectExercise(ex)} className="p-2 text-zinc-600"><ChevronRight className="w-5 h-5" /></button>
  </div>
), (prevProps, nextProps) => prevProps.ex.id === nextProps.ex.id && prevProps.ex.name === nextProps.ex.name && prevProps.ex.muscleGroup === nextProps.ex.muscleGroup && prevProps.ex.imageUrl === nextProps.ex.imageUrl && prevProps.ex.imageUrl2 === nextProps.ex.imageUrl2);

const ExercisesListScreen = ({ exercises, title, onBack, onSelectExercise, onAddExercise, searchQuery, onSearch, allExercises }: any) => {
  const [infoModalExId, setInfoModalExId] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  
  // Получаем актуальные данные упражнения из allExercises
  const infoModalEx = infoModalExId ? allExercises.find((ex: Exercise) => ex.id === infoModalExId) || null : null;
  
  // Автофокус на поле поиска при монтировании, если есть searchQuery
  useEffect(() => {
    if (searchQuery && searchInputRef.current) {
      searchInputRef.current.focus();
      // Устанавливаем курсор в конец текста
      const length = searchInputRef.current.value.length;
      searchInputRef.current.setSelectionRange(length, length);
    }
  }, [searchQuery]);
  
  return (
    <motion.div initial={{ x: 50, opacity: 0 }} animate={{ x: 0, opacity: 1 }} className="flex flex-col h-full">
      <ScreenHeader
        title={title}
        onBack={onBack}
        rightAction={<button onClick={onAddExercise} className="p-2 text-blue-500 hover:bg-zinc-800 rounded-full active:scale-90"><Plus className="w-7 h-7" /></button>}
      >
        {searchQuery ? (
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <Input 
              ref={searchInputRef}
              placeholder="Найти..." 
              value={searchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => onSearch(e.target.value)} 
              className="pl-8 bg-zinc-900 w-full h-9 text-sm" 
            />
          </div>
        ) : (
          <h1 className="text-xl font-bold truncate">{title}</h1>
        )}
      </ScreenHeader>
      <div className="p-4 space-y-2 pb-24">
        {exercises.map((ex: Exercise) => (
          <ExerciseCard key={ex.id} ex={ex} onSelectExercise={onSelectExercise} onInfoClick={(ex: Exercise) => setInfoModalExId(ex.id)} />
        ))}
      </div>
      <Modal isOpen={!!infoModalEx} onClose={() => setInfoModalExId(null)} title={infoModalEx?.name}>
        {infoModalEx && (
          <div className="space-y-4">
             <div className="aspect-square bg-zinc-800 rounded-2xl overflow-hidden">
               {infoModalEx.imageUrl ? (
                 <img src={infoModalEx.imageUrl} className="w-full h-full object-cover" alt="Основное фото" onError={() => {}} />
               ) : (
                 <div className="w-full h-full flex items-center justify-center text-zinc-500">Нет фото</div>
               )}
             </div>
             {infoModalEx.imageUrl2 && infoModalEx.imageUrl2.trim() !== '' ? (
               <div className="aspect-square bg-zinc-800 rounded-2xl overflow-hidden">
                 <img src={infoModalEx.imageUrl2} className="w-full h-full object-cover" alt="Дополнительное фото" onError={() => {}} />
               </div>
             ) : (
               <div className="text-xs text-zinc-500 text-center py-2">Дополнительное фото отсутствует</div>
             )}
             <div className="text-zinc-400 leading-relaxed">{infoModalEx.description || 'Описание отсутствует.'}</div>
             <div className="pt-4"><div className="text-xs text-zinc-500 uppercase font-bold tracking-wider mb-2">Группа</div><div className="px-3 py-1 bg-zinc-800 rounded-lg inline-block text-zinc-300 text-sm">{infoModalEx.muscleGroup}</div></div>
          </div>
        )}
      </Modal>
    </motion.div>
  );
};

const WorkoutScreen = ({ initialExercise, allExercises, onBack, incrementOrder, haptic, notify, onUpdateExercise }: any) => {
  // ВОССТАНОВЛЕНИЕ СОСТОЯНИЯ: Проверяем наличие незавершенной тренировки
  const getSavedSession = () => {
    try {
        const raw = localStorage.getItem(WORKOUT_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  };
  
  const savedSession = useMemo(() => getSavedSession(), []);

  // Если есть сохраненная сессия, используем ее ID, иначе новый
  const [localGroupId] = useState(() => savedSession?.localGroupId || crypto.randomUUID());
  
  const timer = useTimer();
  
  // Инициализируем из сохранения или с начальным упражнением
  const [activeExercises, setActiveExercises] = useState<string[]>(
      savedSession ? savedSession.activeExercises : [initialExercise.id]
  );
  
  // Инициализируем данные упражнений
  const [sessionData, setSessionData] = useState<Record<string, ExerciseSessionData>>(
      savedSession ? savedSession.sessionData : {}
  );

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [supersetSearchQuery, setSupersetSearchQuery] = useState('');
  const [exerciseToEdit, setExerciseToEdit] = useState<Exercise | null>(null);
  const groupsFromExercises = useMemo(() => [...new Set(allExercises.map((e: Exercise) => e.muscleGroup).filter(Boolean))].sort() as string[], [allExercises]);

  // АВТОСОХРАНЕНИЕ: Сохраняем при любом изменении данных
  useEffect(() => {
      // Сохраняем только если есть данные
      if (Object.keys(sessionData).length > 0) {
          const workoutState = {
              localGroupId,
              activeExercises,
              sessionData,
              timestamp: Date.now()
          };
          localStorage.setItem(WORKOUT_STORAGE_KEY, JSON.stringify(workoutState));
      }
  }, [localGroupId, activeExercises, sessionData]);

  const loadExerciseData = async (exId: string) => {
    // Загружаем историю (асинхронно)
    const { history, note } = await api.getHistory(exId);
    
    setSessionData(prev => {
        // Если пользователь уже ввел данные (пока грузилась история), не перезаписываем подходы!
        // Но обновляем историю и заметку
        const currentData = prev[exId];
        const exercise = allExercises.find((e: Exercise) => e.id === exId);
        
        if (!exercise) return prev; // Если упражнение не найдено, выходим

        // Если данные уже были (восстановлены или введены), обновляем только историю/заметку
        if (currentData && currentData.sets && currentData.sets.length > 0) {
             return {
                 ...prev,
                 [exId]: {
                     ...currentData,
                     exercise, // Обновляем объект упражнения на всякий случай
                     history: history, // Подгрузилась история
                     note: currentData.note || note || '' // Заметка: приоритет текущей
                 }
             };
        }
        
        let initialSets: WorkoutSet[] = [];
        if (history.length > 0) {
            // Новая структура: history - массив групп с isSuperset
            // Берем первую группу (самую новую дату)
            const firstGroup = history[0];
            const lastDate = firstGroup?.date;
            
            if (lastDate) {
                // Если это суперсет, находим подходы текущего упражнения
                if (firstGroup.isSuperset && firstGroup.exercises) {
                    const currentExercise = firstGroup.exercises.find((ex: any) => ex.exerciseId === exId);
                    if (currentExercise && currentExercise.sets) {
                        initialSets = currentExercise.sets.map((s: any) => createSetFromHistory(s, s.weight));
                    }
                } else if (firstGroup.sets) {
                    initialSets = firstGroup.sets.map((s: any) => createSetFromHistory(s, s.weight));
                }
                
                if (initialSets.length === 0) {
                    initialSets = [createEmptySet()];
                }
            } else {
                initialSets = [createEmptySet()];
            }
        } else {
            initialSets = [createEmptySet()];
        }
        return { ...prev, [exId]: { exercise: allExercises.find((e: Exercise) => e.id === exId)!, note: note || '', history, sets: initialSets } };
    });
  };

  useEffect(() => { activeExercises.forEach(id => loadExerciseData(id)); }, [activeExercises]);

  const updateSetDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingUpdateRef = useRef<{
    exId: string;
    setId: string;
    setGroupId: string;
    order: number;
    weight: string;
    reps: string;
    rest: string;
    rowNumber?: number;
    equipmentType?: string;
    weightType?: string;
    baseWeight?: number;
    weightMultiplier?: number;
  } | null>(null);
  
  useEffect(() => () => { if (updateSetDebounceRef.current) clearTimeout(updateSetDebounceRef.current); }, []);

  const handleCompleteSet = async (exId: string, setId: string) => {
    const set = sessionData[exId].sets.find(s => s.id === setId);
    if (!set || set.completed) return;
    if (!set.weight || !set.reps) { notify('error'); return; }
    
    const exercise = sessionData[exId].exercise;
    const weightType = getWeightInputType(exercise?.equipmentType, exercise?.weightType);
    const inputWeight = parseFloat(set.weight);
    const effectiveWeight = calcEffectiveWeight(set.weight, weightType, undefined, exercise?.baseWeight, exercise?.weightMultiplier) ?? inputWeight;
    
    haptic('medium');
    const order = incrementOrder();
    setSessionData(prev => ({ ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.map(s => s.id === setId ? { ...s, completed: true, order, setGroupId: localGroupId, effectiveWeight } : s) } }));
    timer.resetAndStart();

    try {
        const result = await api.saveSet({
            exercise_id: exId,
            exercise_name: exercise?.name,
            weight: effectiveWeight,
            input_weight: inputWeight,
            reps: parseInt(set.reps),
            rest: parseFloat(set.rest) || 0,
            note: sessionData[exId].note,
            set_group_id: localGroupId,
            order
        });
        
        if (result?.row_number) {
            setSessionData(prev => ({
                ...prev,
                [exId]: {
                    ...prev[exId],
                    sets: prev[exId].sets.map(s => s.id === setId ? { ...s, rowNumber: result.row_number } : s)
                }
            }));
        }
        
        notify('success');
    } catch (e) {
        notify('error');
    }
  };

  const handleUpdateSet = (exId: string, setId: string, field: string, val: string) => {
    setSessionData(prev => {
      const next = { ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.map(s => s.id === setId ? { ...s, [field]: val } : s) } };
      const set = next[exId].sets.find(s => s.id === setId);
      
      // Если подход выполнен, в режиме редактирования и имеет rowNumber (или fallback на order/setGroupId)
      if (set?.completed && set.isEditing && (set.rowNumber || (set.order != null && set.setGroupId))) {
        const exercise = prev[exId]?.exercise;
        pendingUpdateRef.current = {
          exId,
          setId,
          setGroupId: set.setGroupId || '',
          order: set.order || 0,
          weight: set.weight,
          reps: set.reps,
          rest: set.rest,
          rowNumber: set.rowNumber,
          equipmentType: exercise?.equipmentType,
          weightType: exercise?.weightType,
          baseWeight: exercise?.baseWeight,
          weightMultiplier: exercise?.weightMultiplier
        };
        
        // Очищаем предыдущий таймер и запускаем новый
        if (updateSetDebounceRef.current) clearTimeout(updateSetDebounceRef.current);
        updateSetDebounceRef.current = setTimeout(async () => {
          updateSetDebounceRef.current = null;
          const data = pendingUpdateRef.current;
          if (!data) return;
          
          try {
            const effective = calcEffectiveWeight(data.weight, getWeightInputType(data.equipmentType, data.weightType), undefined, data.baseWeight, data.weightMultiplier) ?? (parseFloat(data.weight) || 0);
            const result = await api.updateSet({
              row_number: data.rowNumber,
              exercise_id: data.exId,
              set_group_id: data.setGroupId,
              order: data.order,
              weight: effective,
              input_weight: parseFloat(data.weight) || 0,
              reps: parseInt(data.reps) || 0,
              rest: parseFloat(data.rest) || 0
            });
            
            if (result?.status === 'success') {
              // После успешного сохранения - карандаш становится серым
              setSessionData(s => ({
                ...s,
                [data.exId]: {
                  ...s[data.exId],
                  sets: s[data.exId].sets.map(st => st.id === data.setId ? { ...st, isEditing: false } : st)
                }
              }));
            }
          } catch {
            // Silent fail for update set
          }
        }, 1500); // 1.5 секунды - теперь не нужно ждать долго
      }
      
      return next;
    });
  };
  
  const handleToggleEdit = (exId: string, setId: string) => {
    setSessionData(prev => ({
      ...prev,
      [exId]: {
        ...prev[exId],
        sets: prev[exId].sets.map(s => s.id === setId ? { ...s, isEditing: !s.isEditing } : s)
      }
    }));
  };

  const handleAddSet = (exId: string) => {
    setSessionData(prev => {
        const currentSets = prev[exId].sets;
        const lastSet = currentSets[currentSets.length - 1];
        const newSet = createEmptySet({ weight: lastSet?.weight || '', reps: lastSet?.reps || '', rest: lastSet?.rest || '' });
        return { ...prev, [exId]: { ...prev[exId], sets: [...currentSets, newSet] } };
    });
  };

  const handleDeleteSet = (exId: string, setId: string) => {
      setSessionData(prev => {
          if (!prev[exId]) return prev;
          const filteredSets = prev[exId].sets.filter(s => s.id !== setId);
          const finalSets = filteredSets.length === 0 ? [createEmptySet()] : filteredSets;
          return { ...prev, [exId]: { ...prev[exId], sets: finalSets } };
      });
  };

  // ЗАВЕРШЕНИЕ: Очищаем сохранение при выходе
  const handleFinish = () => {
      localStorage.removeItem(WORKOUT_STORAGE_KEY);
      onBack();
  };

  return (
    <div className="min-h-screen bg-zinc-950 pb-20">
      <TimerBlock timer={timer} onToggle={() => timer.isRunning ? timer.reset() : timer.start()} />
      <div className="px-4 space-y-4">
        {activeExercises.map(exId => {
            const data = sessionData[exId];
            if (!data) return <div key={exId} className="h-40 bg-zinc-900 rounded-2xl animate-pulse" />;
            return <WorkoutCard key={exId} exerciseData={data} onAddSet={() => handleAddSet(exId)} onUpdateSet={(sid: string, f: string, v: string) => handleUpdateSet(exId, sid, f, v)} onDeleteSet={(sid: string) => handleDeleteSet(exId, sid)} onCompleteSet={(sid: string) => handleCompleteSet(exId, sid)} onToggleEdit={(sid: string) => handleToggleEdit(exId, sid)} onNoteChange={(val: string) => setSessionData(p => ({...p, [exId]: {...p[exId], note: val}}))} onAddSuperset={() => setIsAddModalOpen(true)} onEditMetadata={() => setExerciseToEdit(data.exercise)} />;
        })}
      </div>
      <div className="px-4 mt-8 mb-20"><Button variant="primary" onClick={handleFinish} className="w-full h-14 text-lg font-semibold shadow-xl shadow-blue-900/20">Завершить упражнение</Button></div>
      <Modal isOpen={isAddModalOpen} onClose={() => { setIsAddModalOpen(false); setSupersetSearchQuery(''); }} title="Добавить в суперсет">
        <div className="space-y-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
            <Input 
              placeholder="Поиск упражнения..." 
              value={supersetSearchQuery}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSupersetSearchQuery(e.target.value)}
              onFocus={(e: React.FocusEvent<HTMLInputElement>) => e.target.select()}
              className="pl-10 bg-zinc-900 w-full" 
            />
          </div>
          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {allExercises
              .filter((ex: Exercise) => 
                ex.name.toLowerCase().includes(supersetSearchQuery.toLowerCase())
              )
              .map((ex: Exercise) => (
                <div 
                  key={ex.id} 
                  onClick={() => { 
                    if (!activeExercises.includes(ex.id)) {
                      setActiveExercises([...activeExercises, ex.id]);
                    }
                    setIsAddModalOpen(false);
                    setSupersetSearchQuery('');
                  }} 
                  className="flex items-center p-3 bg-zinc-800/50 rounded-xl border border-zinc-800 cursor-pointer hover:bg-zinc-800 transition-colors"
                >
                  <div className="font-medium text-zinc-200">{ex.name}</div>
                  {activeExercises.includes(ex.id) && <Check className="ml-auto text-green-500 w-5 h-5"/>}
                </div>
              ))}
            {allExercises.filter((ex: Exercise) => 
              ex.name.toLowerCase().includes(supersetSearchQuery.toLowerCase())
            ).length === 0 && (
              <div className="text-center text-zinc-500 py-4 text-sm">Упражнения не найдены</div>
            )}
          </div>
        </div>
      </Modal>
      {exerciseToEdit && (
        <EditExerciseModal
          isOpen={!!exerciseToEdit}
          onClose={() => setExerciseToEdit(null)}
          exercise={exerciseToEdit}
          groups={groupsFromExercises}
          onSave={async (id, updates) => {
            const result = await api.updateExercise(id, updates);
            if (result?.status === 'success') {
              setSessionData(prev => {
                if (!prev[id]) return prev;
                return { ...prev, [id]: { ...prev[id], exercise: { ...prev[id].exercise, ...updates } } };
              });
              onUpdateExercise?.(id, updates);
            }
          }}
        />
      )}
      <div className="fixed bottom-6 left-6 z-20"><button onClick={handleFinish} className="w-12 h-12 rounded-full bg-zinc-800 text-zinc-400 flex items-center justify-center border border-zinc-700 shadow-lg hover:text-white"><ArrowLeft className="w-6 h-6" /></button></div>
    </div>
  );
};

// --- ANALYTICS v4.0 ---
// Регулярность > Прогресс

interface AnalyticsDataV4 {
  mode: 'Вкат' | 'Поддержание' | 'Стабильный';
  frequencyScore: { value: number; status: string; actual: number; target: number };
  maxGap: { value: number; status: string; interpretation: string };
  returnToBaseline: { value: number; visible: boolean } | null;
  stabilityGate: boolean;
  baselines: { exerciseId: string; name: string; baseline: number | null; status: string }[];
  proposals: { exerciseId: string; oldBaseline: number; newBaseline: number; step: number; expiresAt: string; proposalId: string }[];
  meta: { period: number };
}

const AnalyticsScreen = ({ onBack }: any) => {
  const [analytics, setAnalytics] = useState<AnalyticsDataV4 | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState(14);
  const [apiError, setApiError] = useState<string | null>(null);
  
  const fetchAnalytics = () => {
    setLoading(true);
    setApiError(null);
    api.getAnalytics(period).then((data: AnalyticsDataV4 | { error?: string } | null) => {
      if (!data) {
        setAnalytics(null);
        setApiError('Не удалось загрузить данные');
      } else if ('error' in data) {
        setAnalytics(null);
        setApiError(data.error || 'Ошибка API');
      } else {
        setAnalytics(data as AnalyticsDataV4);
      }
      setLoading(false);
    });
  };
  
  useEffect(() => { fetchAnalytics(); }, [period]);

  const handleProposalAction = async (proposalId: string, action: 'CONFIRM' | 'SNOOZE' | 'DECLINE') => {
    await api.confirmBaseline(proposalId, action);
    fetchAnalytics();
  };

  const getFSColor = (status: string) => {
    if (status === 'green') return 'bg-green-500/20 text-green-400';
    if (status === 'yellow') return 'bg-yellow-500/20 text-yellow-400';
    return 'bg-red-500/20 text-red-400';
  };

  const getModeColor = (mode: string) => {
    if (mode === 'Стабильный') return 'bg-green-500/20 border-green-500/50';
    if (mode === 'Вкат') return 'bg-orange-500/20 border-orange-500/50';
    return 'bg-yellow-500/20 border-yellow-500/50';
  };

  const getStatusIcon = (status: string) => {
    if (status === 'locked') return '🔒';
    if (status === 'ready') return '🟢';
    if (status === 'updated') return '⬆️';
    return '🟡';
  };

  return (
    <motion.div initial={{ x: 50, opacity: 0 }} animate={{ x: 0, opacity: 1 }} className="min-h-screen bg-zinc-950">
      <div className="sticky top-0 z-30 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800">
        <ScreenHeader title="Аналитика" onBack={onBack} />
        <div className="flex gap-2 px-4 pb-3">
          {[7, 14, 28].map(p => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                period === p ? 'bg-blue-500 text-white' : 'bg-zinc-800 text-zinc-400 hover:text-white'
              }`}
            >
              {p}д
            </button>
          ))}
        </div>
      </div>
      
      {loading ? (
        <div className="p-4 space-y-4">
          {[1,2,3,4].map(i => <div key={i} className="h-24 bg-zinc-900 rounded-2xl animate-pulse" />)}
        </div>
      ) : apiError ? (
        <div className="p-4 text-center text-red-400 mt-20">
          <AlertTriangle className="w-16 h-16 mx-auto mb-4 opacity-70" />
          <p className="font-medium">{apiError}</p>
          <Button variant="secondary" onClick={fetchAnalytics} className="mt-4">Повторить</Button>
        </div>
      ) : analytics ? (
        <div className="p-4 space-y-4 pb-20">
          <div className="text-center text-xs text-zinc-500 py-1">
            Показатели за последние {period} дней
          </div>

          {/* Режим */}
          <Card className={`p-4 border ${getModeColor(analytics.mode)}`}>
            <div className="text-sm text-zinc-400 mb-1">Режим</div>
            <div className="text-xl font-bold text-zinc-100">{analytics.mode}</div>
          </Card>

          {/* Frequency Score — главный KPI */}
          <Card className="p-4">
            <div className="flex items-center justify-between mb-2">
              <h3 className="font-semibold text-zinc-200">Frequency Score</h3>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${getFSColor(analytics.frequencyScore?.status)}`}>
                {analytics.frequencyScore?.value >= 0.8 ? '🟢' : analytics.frequencyScore?.value >= 0.6 ? '🟡' : '🔴'}
              </span>
            </div>
            <div className="text-3xl font-bold text-zinc-100">
              {Math.round((analytics.frequencyScore?.value || 0) * 100)}%
            </div>
            <div className="text-xs text-zinc-500 mt-2">
              {analytics.frequencyScore?.actual} / {analytics.frequencyScore?.target} тренировок
            </div>
          </Card>

          {/* Max Gap */}
          <Card className="p-4">
            <h3 className="font-semibold text-zinc-200 mb-2">Max Gap</h3>
            <div className="text-2xl font-bold text-zinc-100">{analytics.maxGap?.value} дней</div>
            <div className="text-sm text-zinc-400 mt-1">{analytics.maxGap?.interpretation}</div>
          </Card>

          {/* Return to Baseline */}
          {analytics.returnToBaseline?.visible && (
            <Card className="p-4">
              <h3 className="font-semibold text-zinc-200 mb-2">Return to Baseline</h3>
              <div className="text-2xl font-bold text-zinc-100">{analytics.returnToBaseline?.value} тренировок</div>
            </Card>
          )}

          {/* Stability Gate */}
          <Card className={`p-4 ${analytics.stabilityGate ? 'border-green-500/30' : 'border-zinc-700'}`}>
            <div className="flex items-center justify-between">
              <h3 className="font-semibold text-zinc-200">Stability Gate</h3>
              <span className={analytics.stabilityGate ? 'text-green-500' : 'text-zinc-500'}>
                {analytics.stabilityGate ? '🟢 Открыт' : '🔒 Закрыт'}
              </span>
            </div>
            <div className="text-xs text-zinc-500 mt-1">
              {analytics.stabilityGate ? 'Готов к росту' : 'FS ≥ 0.6, MG ≤ 45, 7 дней с последнего изменения'}
            </div>
          </Card>

          {/* Baseline по упражнениям */}
          {analytics.baselines?.length > 0 && (
            <Card className="p-4">
              <h3 className="font-semibold text-zinc-200 mb-3">Baseline</h3>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {analytics.baselines.filter(b => b.baseline).map(b => (
                  <div key={b.exerciseId} className="flex items-center justify-between py-2 border-b border-zinc-800 last:border-0">
                    <div>
                      <div className="text-sm text-zinc-200">{b.name}</div>
                      <div className="text-xs text-zinc-500">{b.status}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-bold text-zinc-100">{b.baseline} кг</span>
                      <span>{getStatusIcon(b.status)}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Proposals */}
          {analytics.proposals?.length > 0 && (
            <Card className="p-4 border-yellow-500/30">
              <h3 className="font-semibold text-zinc-200 mb-3">Предложения по росту</h3>
              <div className="space-y-3">
                {analytics.proposals.map((p, i) => (
                  <div key={i} className="p-3 bg-zinc-800/50 rounded-lg">
                    <div className="text-sm text-zinc-200 mb-2">
                      {p.oldBaseline} → {p.newBaseline} кг (+{p.step})
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => handleProposalAction(p.proposalId, 'CONFIRM')} className="flex-1 py-2 bg-green-500/20 text-green-400 rounded-lg text-sm font-medium">
                        Подтвердить
                      </button>
                      <button onClick={() => handleProposalAction(p.proposalId, 'SNOOZE')} className="flex-1 py-2 bg-zinc-700 text-zinc-300 rounded-lg text-sm">
                        Отложить
                      </button>
                      <button onClick={() => handleProposalAction(p.proposalId, 'DECLINE')} className="flex-1 py-2 bg-red-500/20 text-red-400 rounded-lg text-sm">
                        Отклонить
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      ) : (
        <div className="p-4 text-center text-zinc-500 mt-20">
          <BarChart3 className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Пока нет данных</p>
          <p className="text-sm mt-2">Начни тренироваться!</p>
        </div>
      )}
    </motion.div>
  );
};

const HistoryScreen = ({ onBack }: any) => {
    const [history, setHistory] = useState<GlobalWorkoutSession[]>([]);
    const [expandedId, setExpandedId] = useState<string | null>(null);
    useEffect(() => { 
        api.getGlobalHistory().then(data => setHistory(data));
    }, []);

    return (
        <motion.div initial={{ x: 50, opacity: 0 }} animate={{ x: 0, opacity: 1 }} className="min-h-screen bg-zinc-950">
            <ScreenHeader title="История" onBack={onBack} />
            <div className="p-4 space-y-4 pb-20">
                {history.map(w => (
                    <Card key={w.id} className="overflow-hidden">
                        <div onClick={() => setExpandedId(expandedId === w.id ? null : w.id)} className="p-4 flex items-center justify-between cursor-pointer active:bg-zinc-800/50">
                            <div>
                                <div className="flex items-center gap-2 mb-1 text-zinc-400 text-sm"><Calendar className="w-3 h-3" />{w.date}<span className="text-zinc-600">•</span>{w.duration}</div>
                                <div className="font-semibold text-zinc-200">{w.muscleGroups.join(' • ')}</div>
                            </div>
                            <ChevronDown className={`w-5 h-5 text-zinc-500 transition-transform ${expandedId === w.id ? 'rotate-180' : ''}`} />
                        </div>
                        <AnimatePresence>
                            {expandedId === w.id && (
                                <motion.div 
                                    initial={{ height: 0, opacity: 0 }} 
                                    animate={{ height: 'auto', opacity: 1 }} 
                                    exit={{ height: 0, opacity: 0 }} 
                                    transition={{ duration: 0.2 }}
                                    className="border-t border-zinc-800 bg-zinc-900/30 overflow-hidden"
                                >
                                    {w.exercises && w.exercises.length > 0 ? (
                                        w.exercises.map((ex: any, i: number) => {
                                            // Определяем, является ли упражнение частью суперсета
                                            const isSuperset = !!ex.supersetId;
                                            const prevSupersetId = i > 0 ? w.exercises[i - 1]?.supersetId : null;
                                            const nextSupersetId = i < w.exercises.length - 1 ? w.exercises[i + 1]?.supersetId : null;
                                            
                                            // Определяем позицию в суперсете
                                            const isSupersetStart = isSuperset && prevSupersetId !== ex.supersetId;
                                            const isSupersetMiddle = isSuperset && prevSupersetId === ex.supersetId && nextSupersetId === ex.supersetId;
                                            
                                            // Стили для визуального отображения суперсета
                                            let borderClass = "border-b border-zinc-800/50";
                                            let paddingClass = "p-4";
                                            let supersetIndicator = null;
                                            
                                            if (isSuperset) {
                                                // Синяя линия слева для суперсета
                                                borderClass = "border-l-2 border-l-blue-500 border-b border-zinc-800/50 bg-blue-500/5";
                                                if (isSupersetStart) {
                                                    // Показываем метку "СУПЕРСЕТ" только в начале
                                                    supersetIndicator = (
                                                        <div className="text-xs text-blue-400 font-bold mb-2 flex items-center">
                                                            <LinkIcon className="w-3 h-3 mr-1" /> СУПЕРСЕТ
                                                        </div>
                                                    );
                                                }
                                                // Убираем нижнюю границу между упражнениями в суперсете
                                                if (isSupersetMiddle) {
                                                    borderClass = "border-l-2 border-l-blue-500 border-b-0 bg-blue-500/5";
                                                }
                                            }
                                            
                                            return (
                                                <div key={i} className={`${paddingClass} ${borderClass} last:border-b-0`}>
                                                    {supersetIndicator}
                                                    <div className="font-medium text-zinc-300 mb-2">{ex.name}</div>
                                                    {ex.sets && Array.isArray(ex.sets) && ex.sets.length > 0 ? (
                                                        <div className="space-y-0">
                                                            {ex.sets.map((s: any, j: number) => {
                                                                const weight = typeof s.weight === 'number' ? s.weight : (s.weight ? parseFloat(String(s.weight)) : 0);
                                                                const reps = typeof s.reps === 'number' ? s.reps : (s.reps ? parseInt(String(s.reps)) : 0);
                                                                const rest = typeof s.rest === 'number' ? s.rest : (s.rest ? parseFloat(String(s.rest)) : 0);
                                                                const isLastSet = j === ex.sets.length - 1;
                                                                const setBorderClass = isLastSet && !isSuperset ? '' : 'border-b border-zinc-800/50';
                                                                return (
                                                                    <SetDisplayRow key={j} weight={weight} reps={reps} rest={rest} className={`p-3 ${setBorderClass}`} />
                                                                );
                                                            })}
                                                        </div>
                                                    ) : (
                                                        <div className="text-xs text-zinc-500">Нет подходов</div>
                                                    )}
                                                </div>
                                            );
                                        })
                                    ) : (
                                        <div className="p-4 text-center text-zinc-500 text-sm">Нет упражнений</div>
                                    )}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </Card>
                ))}
                {history.length === 0 && <div className="text-center text-zinc-500 py-10 flex flex-col items-center"><Activity className="w-12 h-12 mb-3 opacity-20" /><p>Нет данных</p></div>}
            </div>
        </motion.div>
    );
};

const EditExerciseModal = ({ isOpen, onClose, exercise, groups, onSave }: { isOpen: boolean; onClose: () => void; exercise: Exercise | null; groups: string[]; onSave: (id: string, updates: Partial<Exercise>) => void | Promise<void> }) => {
    
    const [name, setName] = useState('');
    const [group, setGroup] = useState('');
    const [description, setDescription] = useState('');
    const [image, setImage] = useState('');
    const [image2, setImage2] = useState('');
    const [weightType, setWeightType] = useState<string>('Dumbbell');
    const [baseWeight, setBaseWeight] = useState(0);
    const [weightMultiplier, setWeightMultiplier] = useState(1);
    const [testInput, setTestInput] = useState('10');
    const [testBodyWt, setTestBodyWt] = useState(90);
    
    // Сохраняем состояние в localStorage при каждом изменении
    useEffect(() => {
        if (exercise && isOpen) {
            const draft = {
                exerciseId: exercise.id,
                name,
                group,
                description,
                image,
                image2,
                weightType,
                baseWeight,
                weightMultiplier
            };
            localStorage.setItem(EDIT_EXERCISE_DRAFT_KEY, JSON.stringify(draft));
        }
    }, [name, group, description, image, image2, weightType, baseWeight, weightMultiplier, exercise, isOpen]);
    
    // Восстанавливаем состояние из localStorage или из exercise
    useEffect(() => { 
        if(exercise && isOpen) {
            // Пытаемся восстановить из localStorage
            const saved = localStorage.getItem(EDIT_EXERCISE_DRAFT_KEY);
            if (saved) {
                try {
                    const draft = JSON.parse(saved);
                    // Проверяем, что это тот же exercise
                    if (draft.exerciseId === exercise.id) {
                        setName(draft.name || exercise.name);
                        setGroup(draft.group || exercise.muscleGroup);
                        setDescription(draft.description || exercise.description || '');
                        setImage(draft.image || exercise.imageUrl || '');
                        setImage2(draft.image2 || exercise.imageUrl2 || '');
                        setWeightType(draft.weightType ?? exercise.weightType ?? 'Dumbbell');
                        setBaseWeight(draft.baseWeight ?? exercise.baseWeight ?? 0);
                        setWeightMultiplier(draft.weightMultiplier ?? exercise.weightMultiplier ?? 1);
                        return;
                    }
                } catch {
                    // Ignore draft parse error
                }
            }
            // Если нет сохраненного или это другой exercise, используем данные из exercise
            setName(exercise.name); 
            setGroup(exercise.muscleGroup); 
            setDescription(exercise.description || '');
            setImage(exercise.imageUrl || ''); 
            setImage2(exercise.imageUrl2 || '');
            setWeightType(exercise.weightType || 'Dumbbell');
            setBaseWeight(exercise.baseWeight ?? 0);
            setWeightMultiplier(exercise.weightMultiplier ?? 1);
        }
    }, [exercise, isOpen]);
    
    // Очищаем сохраненное состояние при закрытии модального окна
    useEffect(() => {
        if (!isOpen) {
            localStorage.removeItem(EDIT_EXERCISE_DRAFT_KEY);
        }
    }, [isOpen]);
    
    // Сохраняем состояние при сворачивании приложения (visibilitychange)
    useEffect(() => {
        if (!isOpen || !exercise) return;
        
        const handleVisibilityChange = () => {
            if (document.hidden) {
                // Приложение свернуто - сохраняем состояние
                const draft = { exerciseId: exercise.id, name, group, description, image, image2, weightType, baseWeight, weightMultiplier };
                localStorage.setItem(EDIT_EXERCISE_DRAFT_KEY, JSON.stringify(draft));
            } else {
                // Приложение снова видимо - восстанавливаем состояние
                const saved = localStorage.getItem(EDIT_EXERCISE_DRAFT_KEY);
                if (saved) {
                    try {
                        const draft = JSON.parse(saved);
                        if (draft.exerciseId === exercise.id) {
                            setName(draft.name || exercise.name);
                            setGroup(draft.group || exercise.muscleGroup);
                            setDescription(draft.description || exercise.description || '');
                            setImage(draft.image || exercise.imageUrl || '');
                            setImage2(draft.image2 || exercise.imageUrl2 || '');
                            setWeightType(draft.weightType ?? exercise.weightType ?? 'Dumbbell');
                            setBaseWeight(draft.baseWeight ?? exercise.baseWeight ?? 0);
                            setWeightMultiplier(draft.weightMultiplier ?? exercise.weightMultiplier ?? 1);
                        }
                    } catch {
                        // Ignore
                    }
                }
            }
        };
        
        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
    }, [isOpen, exercise, name, group, description, image, image2, weightType, baseWeight, weightMultiplier]);
    
    const [uploadingImage1, setUploadingImage1] = useState(false);
    const [uploadingImage2, setUploadingImage2] = useState(false);

    const saveDraft = () => {
        if (exercise) {
            const draft = { exerciseId: exercise.id, name, group, description, image, image2, weightType, baseWeight, weightMultiplier };
            localStorage.setItem(EDIT_EXERCISE_DRAFT_KEY, JSON.stringify(draft));
        }
    };

    const handleUpload = async (file: File, slot: 1 | 2): Promise<string | null> => {
        slot === 1 ? setUploadingImage1(true) : setUploadingImage2(true);
        try {
            const result = await api.uploadImage(file);
            return result?.url ?? null;
        } finally {
            slot === 1 ? setUploadingImage1(false) : setUploadingImage2(false);
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Редактировать">
            <div className="space-y-6">
                <ImageUploadSlot
                    value={image}
                    onChange={setImage}
                    onUpload={(f) => handleUpload(f, 1)}
                    uploading={uploadingImage1}
                    label="Основное фото"
                    inputId="edit-exercise-image-1"
                    onBeforeOpen={saveDraft}
                />
                <ImageUploadSlot
                    value={image2}
                    onChange={setImage2}
                    onUpload={(f) => handleUpload(f, 2)}
                    uploading={uploadingImage2}
                    label="Дополнительное фото"
                    inputId="edit-exercise-image-2"
                    onBeforeOpen={saveDraft}
                />
                <div><label className="text-sm text-zinc-400 mb-1 block">Название</label><Input value={name} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)} /></div>
                
                <div>
                    <label className="text-sm text-zinc-400 mb-1 block">Описание</label>
                    <textarea 
                        value={description} 
                        onChange={(e) => setDescription(e.target.value)} 
                        className="w-full bg-zinc-900 text-zinc-50 rounded-xl px-4 py-3 focus:outline-none focus:ring-1 focus:ring-zinc-600 placeholder:text-zinc-600 transition-all min-h-[100px] resize-none" 
                        placeholder="Добавьте описание..." 
                    />
                </div>

                <div>
                    <label className="text-sm text-zinc-400 mb-1 block">Группа</label>
                    <div className="flex flex-wrap gap-2">{groups.map((g: string) => <button key={g} onClick={() => setGroup(g)} className={`px-3 py-2 rounded-xl text-sm border ${group === g ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-800 border-zinc-700 text-zinc-400'}`}>{g}</button>)}</div>
                </div>

                <div className="pt-4 border-t border-zinc-800">
                    <label className="text-sm text-zinc-400 mb-2 block">Расчёт нагрузки</label>
                    <div className="space-y-3">
                        <div>
                            <span className="text-xs text-zinc-500 block mb-1">Тип</span>
                            <select value={weightType} onChange={e => setWeightType(e.target.value)} className="w-full h-10 bg-zinc-800 rounded-xl px-3 text-zinc-100 text-sm focus:ring-1 focus:ring-blue-500 outline-none">
                                {WEIGHT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                            </select>
                        </div>
                        <div className="flex items-center gap-2">
                            <span className="text-xs text-zinc-500 w-24">База, кг</span>
                            <button type="button" onClick={() => setBaseWeight(Math.max(0, baseWeight - 2.5))} className="w-10 h-10 rounded-lg bg-zinc-800 text-zinc-400 flex items-center justify-center font-bold hover:bg-zinc-700">−</button>
                            <span className="flex-1 text-center font-bold text-zinc-100 tabular-nums">{baseWeight}</span>
                            <button type="button" onClick={() => setBaseWeight(baseWeight + 2.5)} className="w-10 h-10 rounded-lg bg-zinc-800 text-zinc-400 flex items-center justify-center font-bold hover:bg-zinc-700">+</button>
                        </div>
                        <div className="flex gap-2">
                            <span className="text-xs text-zinc-500 self-center">Multiplier</span>
                            <button type="button" onClick={() => setWeightMultiplier(1)} className={`flex-1 py-2 rounded-lg text-sm font-medium ${weightMultiplier === 1 ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>1</button>
                            <button type="button" onClick={() => setWeightMultiplier(2)} className={`flex-1 py-2 rounded-lg text-sm font-medium ${weightMultiplier === 2 ? 'bg-blue-600 text-white' : 'bg-zinc-800 text-zinc-400'}`}>2</button>
                        </div>
                        <div className="pt-2 border-t border-zinc-800/50">
                            <span className="text-xs text-zinc-500 block mb-1">Проверка</span>
                            <div className="flex gap-2 items-center flex-wrap">
                                <input type="number" value={testInput} onChange={e => setTestInput(e.target.value)} placeholder="Input" className="w-16 h-8 bg-zinc-800 rounded px-2 text-zinc-100 text-sm" />
                                {(weightType === 'Assisted' || weightType === 'Bodyweight') && (
                                    <input type="number" value={testBodyWt} onChange={e => setTestBodyWt(Number(e.target.value) || 90)} className="w-16 h-8 bg-zinc-800 rounded px-2 text-zinc-100 text-sm" />
                                )}
                                {(() => {
                                    const wt = getWeightInputType(undefined, weightType);
                                    const f = WEIGHT_FORMULAS[wt];
                                    const eff = !isNaN(parseFloat(testInput) || 0) ? f.toEffective(parseFloat(testInput) || 0, testBodyWt, baseWeight, weightMultiplier) : null;
                                    return eff !== null ? <span className="text-blue-400 text-sm">→ {eff} кг</span> : null;
                                })()}
                            </div>
                        </div>
                    </div>
                </div>

                <Button 
                    onClick={async () => { 
                        if (!exercise) return;
                        localStorage.removeItem(EDIT_EXERCISE_DRAFT_KEY);
                        await onSave(exercise.id, { name, muscleGroup: group, description, imageUrl: image, imageUrl2: image2, weightType, baseWeight, weightMultiplier }); 
                        onClose(); 
                    }} 
                    className="w-full h-12"
                    disabled={uploadingImage1 || uploadingImage2}
                >
                    {uploadingImage1 || uploadingImage2 ? 'Загрузка...' : 'Сохранить'}
                </Button>
            </div>
        </Modal>
    );
};

// --- MAIN ---

const App = () => {
  const { haptic, notify } = useTelegram();
  const { incrementOrder } = useSession();
  const [screen, setScreen] = useState<Screen>('home');
  const [groups, setGroups] = useState<string[]>([]);
  const [allExercises, setAllExercises] = useState<Exercise[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentExercise, setCurrentExercise] = useState<Exercise | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newGroup, setNewGroup] = useState('');

  // 1. АВТОМАТИЧЕСКОЕ ВОССТАНОВЛЕНИЕ ТРЕНИРОВКИ ПРИ СТАРТЕ
  useEffect(() => {
    if (allExercises.length === 0) return; // Ждем, пока загрузятся все упражнения
    
    // Пытаемся найти сохраненную сессию
    const saved = localStorage.getItem(WORKOUT_STORAGE_KEY);
    if (saved) {
        try {
            const session = JSON.parse(saved);
            // Если есть активные упражнения и данные не старше 24 часов
            const isFresh = session.timestamp && (Date.now() - session.timestamp) < 86400000;
            
            if (isFresh && session.activeExercises && session.activeExercises.length > 0) {
                // Находим первое упражнение, чтобы открыть экран тренировки с ним
                const exId = session.activeExercises[0];
                const ex = allExercises.find((e: Exercise) => e.id === exId);
                
                if (ex) {
                    setCurrentExercise(ex);
                    setScreen('workout');
                }
            } else {
                // Если данные устарели или пусты, очищаем
                localStorage.removeItem(WORKOUT_STORAGE_KEY);
            }
        } catch {
            localStorage.removeItem(WORKOUT_STORAGE_KEY);
        }
    }
  }, [allExercises]);

  // Пинг сервера каждые 14 минут, чтобы предотвратить засыпание на бесплатном тарифе Render
  useEffect(() => {
    const pingInterval = setInterval(() => {
      api.ping().catch(err => {
        console.error('Ping failed:', err);
      });
    }, 14 * 60 * 1000); // 14 минут = 840000 мс

    // Пингуем сразу при загрузке
    api.ping().catch(err => {
      console.error('Initial ping failed:', err);
    });

    return () => clearInterval(pingInterval);
  }, []);

  useEffect(() => { 
    api.getInit().then(d => { 
      setGroups(sortGroups(d.groups)); 
      setAllExercises(d.exercises); 
    }); 
  }, []);

  // Debounce для поиска (300 мс)
  const debouncedSearchQuery = useDebounce(searchQuery, 300);

  const filteredExercises = useMemo(() => {
    let list = allExercises;
    if (selectedGroup) list = list.filter(ex => ex.muscleGroup === selectedGroup);
    if (debouncedSearchQuery) list = list.filter(ex => ex.name.toLowerCase().includes(debouncedSearchQuery.toLowerCase()));
    // Сортируем по имени (на случай, если бэкенд не отсортировал)
    return list.sort((a, b) => a.name.localeCompare(b.name, 'ru', { sensitivity: 'base' }));
  }, [allExercises, selectedGroup, debouncedSearchQuery]);

  const handleCreate = async () => {
      if (!newName || !newGroup) return;
      const newEx = await api.createExercise(newName, newGroup);
      if (newEx) { setAllExercises(p => [...p, newEx]); setIsCreateModalOpen(false); setNewName(''); notify('success'); }
  };

  const handleUpdate = async (id: string, updates: Partial<Exercise>) => {
      // Обновляем локально для мгновенного отображения
      setAllExercises(p => p.map(ex => ex.id === id ? { ...ex, ...updates } : ex));
      // Сохраняем на сервере
      const result = await api.updateExercise(id, updates);
      if (result) {
          // Перезагружаем данные с сервера для синхронизации
          const freshData = await api.getInit();
          if (freshData && freshData.exercises) {
              setAllExercises(freshData.exercises);
          }
          notify('success');
      } else {
          notify('error');
      }
  };

  return (
    <div className="bg-zinc-950 min-h-screen text-zinc-50 font-sans selection:bg-blue-500/30 pt-24">
      {screen === 'home' && <HomeScreen groups={groups} onSearch={(q: string) => { setSearchQuery(q); if(q) setScreen('exercises'); }} onSelectGroup={(g: string) => { setSelectedGroup(g); setScreen('exercises'); }} onAllExercises={() => { setSelectedGroup(null); setScreen('exercises'); }} onHistory={() => setScreen('history')} onAnalytics={() => setScreen('analytics')} searchQuery={searchQuery} />}
      {screen === 'analytics' && <AnalyticsScreen onBack={() => setScreen('home')} />}
      {screen === 'history' && <HistoryScreen onBack={() => setScreen('home')} />}
      {screen === 'exercises' && <ExercisesListScreen exercises={filteredExercises} allExercises={allExercises} title={selectedGroup || (searchQuery ? `Поиск: ${searchQuery}` : 'Все упражнения')} searchQuery={searchQuery} onSearch={(q: string) => setSearchQuery(q)} onBack={() => { setSearchQuery(''); setSelectedGroup(null); setScreen('home'); }} onSelectExercise={(ex: Exercise) => { haptic('light'); setCurrentExercise(ex); setScreen('workout'); }} onAddExercise={() => setIsCreateModalOpen(true)} />}
      {screen === 'workout' && currentExercise && <WorkoutScreen initialExercise={currentExercise} allExercises={allExercises} incrementOrder={incrementOrder} haptic={haptic} notify={notify} onBack={() => setScreen('exercises')} onUpdateExercise={handleUpdate} />}
      
      <Modal isOpen={isCreateModalOpen} onClose={() => setIsCreateModalOpen(false)} title="Новое упражнение">
         <div className="space-y-4">
             <div><label className="text-sm text-zinc-400 mb-1 block">Название</label><Input value={newName} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewName(e.target.value)} placeholder="Например: Отжимания" /></div>
             <div><label className="text-sm text-zinc-400 mb-1 block">Группа</label><div className="flex flex-wrap gap-2">{groups.map(g => <button key={g} onClick={() => setNewGroup(g)} className={`px-3 py-2 rounded-xl text-sm border ${newGroup === g ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-800 border-zinc-700 text-zinc-400'}`}>{g}</button>)}</div></div>
             <Button onClick={handleCreate} className="w-full h-12 mt-4">Создать</Button>
         </div>
      </Modal>
    </div>
  );
};

export default App;