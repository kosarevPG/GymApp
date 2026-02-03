import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  Search, ChevronRight, Plus, X, Info, 
  Check, Trash2, StickyNote, ChevronDown, Dumbbell, Calendar, 
  ChevronLeft, Settings, ArrowLeft, Camera, Pencil, Trophy,
  History as HistoryIcon, Activity, Link as LinkIcon
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// --- CONFIG ---
// Используем переменную окружения или localhost для разработки
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const WORKOUT_STORAGE_KEY = 'gym_workout_state_v2'; // Ключ для хранения сессии тренировки 

// --- TYPES ---

type Screen = 'home' | 'exercises' | 'workout' | 'history';

interface Exercise {
  id: string;
  name: string;
  muscleGroup: string;
  description?: string;
  imageUrl?: string;
  imageUrl2?: string;
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
    const lastActive = localStorage.getItem('gym_last_active');
    const savedSession = localStorage.getItem('gym_session_id');
    const savedOrder = localStorage.getItem('gym_order_counter');
    const now = Date.now();

    if (!lastActive || (now - parseInt(lastActive)) > 14400000 || !savedSession) {
      const newId = crypto.randomUUID();
      setSessionId(newId);
      setOrderCounter(0);
      localStorage.setItem('gym_session_id', newId);
    } else {
      setSessionId(savedSession);
      setOrderCounter(parseInt(savedOrder || '0'));
    }
    localStorage.setItem('gym_last_active', now.toString());
  }, []);

  const incrementOrder = () => {
    const next = orderCounter + 1;
    setOrderCounter(next);
    localStorage.setItem('gym_order_counter', next.toString());
    localStorage.setItem('gym_last_active', Date.now().toString());
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
  // Логируем структуру данных для отладки
  useEffect(() => {
    if (isOpen && history) {
      console.log('HistoryListModal - history data:', history);
      console.log('HistoryListModal - history type:', Array.isArray(history) ? 'array' : typeof history);
      if (Array.isArray(history) && history.length > 0) {
        console.log('HistoryListModal - first item:', history[0]);
      }
    }
  }, [isOpen, history]);

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
                          <div 
                            key={setIdx} 
                            className={`p-3 border-l-2 border-l-blue-500 bg-blue-500/5 ${borderClass} flex items-center justify-between`}
                          >
                            <div>
                              <div className="text-lg font-medium text-zinc-200">
                                {set.weight} <span className="text-sm text-zinc-500">кг</span> × {set.reps} <span className="text-sm text-zinc-500">повторений</span>
                              </div>
                            </div>
                            <div className="text-zinc-500 font-mono text-sm bg-zinc-900/50 px-2 py-1 rounded">
                              отдых {set.rest}м
                            </div>
                          </div>
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
                      <div 
                        key={setIdx} 
                        className={`p-3 ${isLastSet ? '' : 'border-b border-zinc-800/50'} flex items-center justify-between`}
                      >
                        <div>
                          <div className="text-lg font-medium text-zinc-200">
                            {set.weight} <span className="text-sm text-zinc-500">кг</span> × {set.reps} <span className="text-sm text-zinc-500">повторений</span>
                          </div>
                        </div>
                        <div className="text-zinc-500 font-mono text-sm bg-zinc-900/50 px-2 py-1 rounded">
                          отдых {set.rest}м
                        </div>
                      </div>
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

const SetRow = ({ set, onUpdate, onDelete, onComplete, onToggleEdit }: { set: any; onUpdate: (sid: string, field: string, value: string) => void; onDelete: (sid: string) => void; onComplete: (sid: string) => void; onToggleEdit: (sid: string) => void }) => {
  const oneRM = set.weight && set.reps ? Math.round(parseFloat(set.weight) * (1 + parseInt(set.reps) / 30)) : 0;
  const delta = set.prevWeight ? (parseFloat(set.weight) - set.prevWeight) : 0;
  const deltaText = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '0';
  const deltaColor = delta > 0 ? 'text-green-500' : delta < 0 ? 'text-red-500' : 'text-zinc-500';
  const isCompleted = set.completed;
  const isEditing = set.isEditing;
  // Для выполненных подходов: поля disabled если НЕ в режиме редактирования
  const inputDisabledClass = isCompleted && !isEditing ? 'opacity-50 pointer-events-none' : '';

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 items-start mb-3">
      <button onClick={() => onComplete(set.id)} className={`w-12 h-12 rounded-full border-2 flex items-center justify-center transition-all duration-200 ${isCompleted ? 'bg-yellow-500 border-yellow-500' : 'bg-transparent border-zinc-700 hover:border-zinc-500'}`}>
        {isCompleted && <Check className="w-6 h-6 text-black stroke-[3]" />}
      </button>
      
      <div className={`flex flex-col gap-1 ${inputDisabledClass}`}>
        <input 
          type="number" 
          inputMode="decimal" 
          placeholder="0" 
          value={set.weight} 
          onChange={e => onUpdate(set.id, 'weight', e.target.value)}
          onFocus={e => e.target.select()}
          className="w-full h-12 bg-zinc-800 rounded-xl text-center text-xl font-bold text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums" 
        />
        {(oneRM > 0 || set.prevWeight) && (
          <div className="flex justify-between px-1 text-[10px]">
            {oneRM > 0 && <span className="text-zinc-500">1PM:{oneRM}</span>}
            {set.prevWeight !== undefined && <span className={`${deltaColor} font-medium`}>{deltaText}</span>}
          </div>
        )}
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

const WorkoutCard = ({ exerciseData, onAddSet, onUpdateSet, onDeleteSet, onCompleteSet, onToggleEdit, onNoteChange, onAddSuperset }: any) => {
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const personalRecord = useMemo(() => {
    if (!exerciseData.history.length) return 0;
    return Math.max(...exerciseData.history.map((h: HistoryItem) => h.weight));
  }, [exerciseData.history]);

  return (
    <Card className="p-4 mb-4">
      <div className="flex justify-between items-start mb-4">
        <div>
            <h2 className="text-xl font-semibold text-zinc-50">{exerciseData.exercise.name}</h2>
            {personalRecord > 0 && (
                <div className="flex items-center gap-1 text-yellow-500 text-xs font-medium mt-1">
                    <Trophy className="w-3 h-3" /><span>PR: {personalRecord} кг</span>
                </div>
            )}
        </div>
        <button onClick={() => setShowHistoryModal(true)} className="p-2 bg-zinc-800/50 rounded-lg text-zinc-400 hover:text-blue-500"><Calendar className="w-5 h-5" /></button>
      </div>
      <NoteWidget initialValue={exerciseData.note} onChange={onNoteChange} />
      <HistoryListModal isOpen={showHistoryModal} onClose={() => setShowHistoryModal(false)} history={exerciseData.history} exerciseName={exerciseData.exercise.name} />
      <div className="grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 mb-2 px-1">
        <div className="w-10" />
        <div className="text-[10px] text-center text-zinc-500 font-bold uppercase">КГ</div>
        <div className="text-[10px] text-center text-zinc-500 font-bold uppercase">ПОВТ</div>
        <div className="text-[10px] text-center text-zinc-500 font-bold uppercase">МИН</div>
        <div className="w-8" />
      </div>
      <div className="space-y-1">
        {exerciseData.sets.map((set: any) => (
          <SetRow key={set.id} set={set} onUpdate={onUpdateSet} onDelete={onDeleteSet} onComplete={onCompleteSet} onToggleEdit={onToggleEdit} />
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

const HomeScreen = ({ groups, onSearch, onSelectGroup, onAllExercises, onHistory, searchQuery }: any) => {
  return (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-6">
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <Input placeholder="Найти..." value={searchQuery || ''} onChange={(e: React.ChangeEvent<HTMLInputElement>) => onSearch(e.target.value)} className="pl-12 bg-zinc-900 w-full" />
      </div>
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

const ExercisesListScreen = ({ exercises, title, onBack, onSelectExercise, onAddExercise, onEditExercise, searchQuery, onSearch, allExercises }: any) => {
  const [infoModalExId, setInfoModalExId] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  
  // Получаем актуальные данные упражнения из allExercises
  const infoModalEx = infoModalExId ? allExercises.find((ex: Exercise) => ex.id === infoModalExId) || null : null;
  
  // Отладка: логируем данные упражнения
  useEffect(() => {
    if (infoModalEx) {
      console.log('Exercise data in modal:', {
        id: infoModalEx.id,
        name: infoModalEx.name,
        imageUrl: infoModalEx.imageUrl,
        imageUrl2: infoModalEx.imageUrl2,
        hasImageUrl2: !!infoModalEx.imageUrl2,
        imageUrl2Length: infoModalEx.imageUrl2?.length || 0,
        imageUrl2Trimmed: infoModalEx.imageUrl2?.trim() || ''
      });
    }
  }, [infoModalEx]);
  
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
      <div className="sticky top-0 z-30 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800 p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 flex-1 min-w-0">
            <button onClick={onBack} className="p-2 -ml-2 text-zinc-400 active:text-white"><ChevronLeft className="w-6 h-6" /></button>
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
        </div>
        <button onClick={onAddExercise} className="p-2 text-blue-500 hover:bg-zinc-800 rounded-full active:scale-90"><Plus className="w-7 h-7" /></button>
      </div>
      <div className="p-4 space-y-2 pb-24">
        {exercises.map((ex: Exercise) => (
          <ExerciseCard key={ex.id} ex={ex} onSelectExercise={onSelectExercise} onInfoClick={(ex: Exercise) => setInfoModalExId(ex.id)} />
        ))}
      </div>
      <Modal isOpen={!!infoModalEx} onClose={() => setInfoModalExId(null)} title={infoModalEx?.name} headerAction={<button onClick={() => { if (infoModalEx) { onEditExercise(infoModalEx); setInfoModalExId(null); } }} className="p-2 bg-zinc-800 rounded-full text-zinc-400 hover:text-blue-400"><Pencil className="w-5 h-5" /></button>}>
        {infoModalEx && (
          <div className="space-y-4">
             <div className="aspect-square bg-zinc-800 rounded-2xl overflow-hidden">
               {infoModalEx.imageUrl ? (
                 <img src={infoModalEx.imageUrl} className="w-full h-full object-cover" alt="Основное фото" onError={() => console.error('Error loading main image:', infoModalEx.imageUrl)} />
               ) : (
                 <div className="w-full h-full flex items-center justify-center text-zinc-500">Нет фото</div>
               )}
             </div>
             {infoModalEx.imageUrl2 && infoModalEx.imageUrl2.trim() !== '' ? (
               <div className="aspect-square bg-zinc-800 rounded-2xl overflow-hidden">
                 <img src={infoModalEx.imageUrl2} className="w-full h-full object-cover" alt="Дополнительное фото" onError={() => console.error('Error loading second image:', infoModalEx.imageUrl2)} />
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

const WorkoutScreen = ({ initialExercise, allExercises, onBack, incrementOrder, haptic, notify }: any) => {
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
    // Не загружаем, если данные уже есть в стейте (например, восстановлены)
    setSessionData(prev => {
        // Если уже есть полные данные упражнения, не трогаем
        if (prev[exId] && prev[exId].exercise) {
             return prev; 
        }
        return prev; 
    });
    
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
                        initialSets = currentExercise.sets.map((s: any) => ({
                            id: crypto.randomUUID(), 
                            weight: s.weight.toString(), 
                            reps: s.reps.toString(), 
                            rest: s.rest.toString(), 
                            completed: false, 
                            prevWeight: s.weight
                        }));
                    }
                } else if (firstGroup.sets) {
                    // Обычные подходы (не в суперсете)
                    initialSets = firstGroup.sets.map((s: any) => ({
                        id: crypto.randomUUID(), 
                        weight: s.weight.toString(), 
                        reps: s.reps.toString(), 
                        rest: s.rest.toString(), 
                        completed: false, 
                        prevWeight: s.weight
                    }));
                }
                
                // Если не нашли подходы, создаем пустой сет
                if (initialSets.length === 0) {
                    initialSets = [{ id: crypto.randomUUID(), weight: '', reps: '', rest: '', completed: false, prevWeight: 0 }];
                }
            } else {
                // Если даты нет, создаем пустой сет
                initialSets = [{ id: crypto.randomUUID(), weight: '', reps: '', rest: '', completed: false, prevWeight: 0 }];
            }
        } else {
            initialSets = [{ id: crypto.randomUUID(), weight: '', reps: '', rest: '', completed: false, prevWeight: 0 }];
        }
        return { ...prev, [exId]: { exercise: allExercises.find((e: Exercise) => e.id === exId)!, note: note || '', history, sets: initialSets } };
    });
  };

  useEffect(() => { activeExercises.forEach(id => loadExerciseData(id)); }, [activeExercises]);

  const updateSetDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (updateSetDebounceRef.current) clearTimeout(updateSetDebounceRef.current); }, []);

  const handleCompleteSet = async (exId: string, setId: string) => {
    const set = sessionData[exId].sets.find(s => s.id === setId);
    if (!set || set.completed) return;
    if (!set.weight || !set.reps) { notify('error'); return; }
    
    haptic('medium');
    const order = incrementOrder();
    // Optimistic - сохраняем order и setGroupId для возможности редактирования
    setSessionData(prev => ({ ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.map(s => s.id === setId ? { ...s, completed: true, order, setGroupId: localGroupId } : s) } }));
    // Сбрасываем таймер и сразу запускаем заново (кнопка останется "Стоп")
    timer.resetAndStart();

    try {
        await api.saveSet({
            exercise_id: exId,
            weight: parseFloat(set.weight),
            reps: parseInt(set.reps),
            rest: parseFloat(set.rest) || 0,
            note: sessionData[exId].note,
            set_group_id: localGroupId,
            order
        });
        notify('success');
    } catch (e) {
        notify('error');
    }
  };

  const sessionDataRef = useRef(sessionData);
  useEffect(() => { sessionDataRef.current = sessionData; }, [sessionData]);

  const handleUpdateSet = (exId: string, setId: string, field: string, val: string) => {
    setSessionData(prev => {
      const next = { ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.map(s => s.id === setId ? { ...s, [field]: val } : s) } };
      return next;
    });

    // Проверяем нужно ли отправлять обновление
    setTimeout(() => {
      const currentData = sessionDataRef.current;
      const set = currentData[exId]?.sets.find(s => s.id === setId);
      
      if (set?.completed && set.isEditing && set.order != null && set.setGroupId) {
        if (updateSetDebounceRef.current) clearTimeout(updateSetDebounceRef.current);
        
        updateSetDebounceRef.current = setTimeout(async () => {
          updateSetDebounceRef.current = null;
          // Получаем самые свежие данные
          const latestData = sessionDataRef.current;
          const latestSet = latestData[exId]?.sets.find(s => s.id === setId);
          if (!latestSet || !latestSet.setGroupId) return;

          console.log('Sending update:', { exId, setId, weight: latestSet.weight, reps: latestSet.reps, rest: latestSet.rest, order: latestSet.order, setGroupId: latestSet.setGroupId });
          
          try {
            const result = await api.updateSet({
              exercise_id: exId,
              set_group_id: latestSet.setGroupId,
              order: latestSet.order,
              weight: parseFloat(latestSet.weight) || 0,
              reps: parseInt(latestSet.reps) || 0,
              rest: parseFloat(latestSet.rest) || 0
            });
            console.log('Update result:', result);
            
            if (result?.status === 'success') {
              // После успешного сохранения - карандаш становится серым
              setSessionData(s => ({
                ...s,
                [exId]: {
                  ...s[exId],
                  sets: s[exId].sets.map(st => st.id === setId ? { ...st, isEditing: false } : st)
                }
              }));
            }
          } catch (e) {
            console.error('Failed to update set:', e);
          }
        }, 2000); // 2 секунды чтобы Google Sheets успел обновиться
      }
    }, 0);
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
        const newSet = { id: crypto.randomUUID(), weight: lastSet?.weight || '', reps: lastSet?.reps || '', rest: lastSet?.rest || '', completed: false, prevWeight: 0 };
        return { ...prev, [exId]: { ...prev[exId], sets: [...currentSets, newSet] } };
    });
  };

  const handleDeleteSet = (exId: string, setId: string) => {
      setSessionData(prev => {
          if (!prev[exId]) return prev;
          const filteredSets = prev[exId].sets.filter(s => s.id !== setId);
          // Если удалили все подходы, добавляем один пустой
          const finalSets = filteredSets.length === 0 
              ? [{ id: crypto.randomUUID(), weight: '', reps: '', rest: '', completed: false, prevWeight: 0 }]
              : filteredSets;
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
            return <WorkoutCard key={exId} exerciseData={data} onAddSet={() => handleAddSet(exId)} onUpdateSet={(sid: string, f: string, v: string) => handleUpdateSet(exId, sid, f, v)} onDeleteSet={(sid: string) => handleDeleteSet(exId, sid)} onCompleteSet={(sid: string) => handleCompleteSet(exId, sid)} onToggleEdit={(sid: string) => handleToggleEdit(exId, sid)} onNoteChange={(val: string) => setSessionData(p => ({...p, [exId]: {...p[exId], note: val}}))} onAddSuperset={() => setIsAddModalOpen(true)} />;
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
      <div className="fixed bottom-6 left-6 z-20"><button onClick={handleFinish} className="w-12 h-12 rounded-full bg-zinc-800 text-zinc-400 flex items-center justify-center border border-zinc-700 shadow-lg hover:text-white"><ArrowLeft className="w-6 h-6" /></button></div>
    </div>
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
            <div className="sticky top-0 z-30 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800 p-4 flex items-center gap-4">
                <button onClick={onBack} className="p-2 -ml-2 text-zinc-400 active:text-white"><ChevronLeft className="w-6 h-6" /></button>
                <h1 className="text-xl font-bold">История</h1>
            </div>
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
                                            const isSupersetEnd = isSuperset && nextSupersetId !== ex.supersetId;
                                            
                                            // Отладочная информация (можно убрать после тестирования)
                                            if (isSuperset) {
                                                console.log(`Exercise "${ex.name}": supersetId=${ex.supersetId}, prev=${prevSupersetId}, next=${nextSupersetId}, start=${isSupersetStart}, middle=${isSupersetMiddle}, end=${isSupersetEnd}`);
                                            }
                                            
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
                                                                    <div 
                                                                        key={j} 
                                                                        className={`p-3 ${setBorderClass} flex items-center justify-between`}
                                                                    >
                                                                        <div>
                                                                            <div className="text-lg font-medium text-zinc-200">
                                                                                {weight} <span className="text-sm text-zinc-500">кг</span> × {reps} <span className="text-sm text-zinc-500">повторений</span>
                                                                            </div>
                                                                        </div>
                                                                        <div className="text-zinc-500 font-mono text-sm bg-zinc-900/50 px-2 py-1 rounded">
                                                                            отдых {rest}м
                                                                        </div>
                                                                    </div>
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

const EditExerciseModal = ({ isOpen, onClose, exercise, groups, onSave }: any) => {
    const STORAGE_KEY = 'gym_edit_exercise_draft';
    
    const [name, setName] = useState('');
    const [group, setGroup] = useState('');
    const [description, setDescription] = useState('');
    const [image, setImage] = useState('');
    const [image2, setImage2] = useState('');
    const fileRef = useRef<HTMLInputElement>(null);
    const fileRef2 = useRef<HTMLInputElement>(null);
    
    // Сохраняем состояние в localStorage при каждом изменении
    useEffect(() => {
        if (exercise && isOpen) {
            const draft = {
                exerciseId: exercise.id,
                name,
                group,
                description,
                image,
                image2
            };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
        }
    }, [name, group, description, image, image2, exercise, isOpen]);
    
    // Восстанавливаем состояние из localStorage или из exercise
    useEffect(() => { 
        if(exercise && isOpen) {
            // Пытаемся восстановить из localStorage
            const saved = localStorage.getItem(STORAGE_KEY);
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
                        return;
                    }
                } catch (e) {
                    console.error('Error restoring draft:', e);
                }
            }
            // Если нет сохраненного или это другой exercise, используем данные из exercise
            setName(exercise.name); 
            setGroup(exercise.muscleGroup); 
            setDescription(exercise.description || '');
            setImage(exercise.imageUrl || ''); 
            setImage2(exercise.imageUrl2 || ''); 
        }
    }, [exercise, isOpen]);
    
    // Очищаем сохраненное состояние при закрытии модального окна
    useEffect(() => {
        if (!isOpen) {
            localStorage.removeItem(STORAGE_KEY);
        }
    }, [isOpen]);
    
    // Сохраняем состояние при сворачивании приложения (visibilitychange)
    useEffect(() => {
        if (!isOpen || !exercise) return;
        
        const handleVisibilityChange = () => {
            if (document.hidden) {
                // Приложение свернуто - сохраняем состояние
                const draft = { exerciseId: exercise.id, name, group, description, image, image2 };
                localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
                console.log('App hidden - saved draft to localStorage');
            } else {
                // Приложение снова видимо - восстанавливаем состояние
                const saved = localStorage.getItem(STORAGE_KEY);
                if (saved) {
                    try {
                        const draft = JSON.parse(saved);
                        if (draft.exerciseId === exercise.id) {
                            setName(draft.name || exercise.name);
                            setGroup(draft.group || exercise.muscleGroup);
                            setDescription(draft.description || exercise.description || '');
                            setImage(draft.image || exercise.imageUrl || '');
                            setImage2(draft.image2 || exercise.imageUrl2 || '');
                            console.log('App visible - restored draft from localStorage');
                        }
                    } catch (e) {
                        console.error('Error restoring draft on visibility change:', e);
                    }
                }
            }
        };
        
        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => document.removeEventListener('visibilitychange', handleVisibilityChange);
    }, [isOpen, exercise, name, group, description, image, image2]);
    
    const [uploadingImage1, setUploadingImage1] = useState(false);
    const [uploadingImage2, setUploadingImage2] = useState(false);

    const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setUploadingImage1(true);
            try {
                // Показываем превью локально
                const r = new FileReader();
                r.onloadend = () => setImage(r.result as string);
                r.readAsDataURL(file);
                
                // Загружаем на Cloudinary
                console.log('Uploading image 1 to Cloudinary...');
                const result = await api.uploadImage(file);
                console.log('Upload result:', result);
                if (result && result.url) {
                    setImage(result.url);
                    console.log('Image 1 uploaded successfully, URL:', result.url);
                } else {
                    console.error('Failed to upload image 1: no URL in result');
                }
            } catch (error) {
                console.error('Error uploading image 1:', error);
            } finally {
                setUploadingImage1(false);
            }
        }
    };

    const handleFile2 = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setUploadingImage2(true);
            try {
                // Показываем превью локально
                const r = new FileReader();
                r.onloadend = () => setImage2(r.result as string);
                r.readAsDataURL(file);
                
                // Загружаем на Cloudinary
                console.log('Uploading image 2 to Cloudinary...');
                const result = await api.uploadImage(file);
                console.log('Upload result:', result);
                if (result && result.url) {
                    setImage2(result.url);
                    console.log('Image 2 uploaded successfully, URL:', result.url);
                } else {
                    console.error('Failed to upload image 2: no URL in result');
                }
            } catch (error) {
                console.error('Error uploading image 2:', error);
            } finally {
                setUploadingImage2(false);
            }
        }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Редактировать">
            <div className="space-y-6">
                <div>
                    <label className="text-sm text-zinc-400 mb-2 block">Основное фото</label>
                    <div onClick={() => {
                        // Сохраняем состояние перед открытием файлового диалога
                        if (exercise) {
                            const draft = { exerciseId: exercise.id, name, group, description, image, image2 };
                            localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
                        }
                        fileRef.current?.click();
                    }} className="w-full h-48 bg-zinc-800 rounded-2xl overflow-hidden relative flex items-center justify-center cursor-pointer border border-zinc-700 border-dashed">
                        {image ? <img src={image} className="w-full h-full object-cover" /> : <div className="flex flex-col items-center text-zinc-500"><Camera className="w-8 h-8 mb-2" /><span className="text-sm">Фото</span></div>}
                    </div>
                    <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
                </div>
                <div>
                    <label className="text-sm text-zinc-400 mb-2 block">Дополнительное фото</label>
                    <div onClick={() => {
                        // Сохраняем состояние перед открытием файлового диалога
                        if (exercise) {
                            const draft = { exerciseId: exercise.id, name, group, description, image, image2 };
                            localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
                        }
                        fileRef2.current?.click();
                    }} className="w-full h-48 bg-zinc-800 rounded-2xl overflow-hidden relative flex items-center justify-center cursor-pointer border border-zinc-700 border-dashed">
                        {image2 ? <img src={image2} className="w-full h-full object-cover" /> : <div className="flex flex-col items-center text-zinc-500"><Camera className="w-8 h-8 mb-2" /><span className="text-sm">Фото 2</span></div>}
                    </div>
                    <input ref={fileRef2} type="file" accept="image/*" className="hidden" onChange={handleFile2} />
                </div>
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
                <Button 
                    onClick={() => { 
                        console.log('Saving exercise with images:', { 
                            id: exercise.id, 
                            imageUrl: image, 
                            imageUrl2: image2,
                            imageUrlIsCloudinary: image?.startsWith('http'),
                            imageUrl2IsCloudinary: image2?.startsWith('http')
                        });
                        // Очищаем сохраненное состояние после успешного сохранения
                        localStorage.removeItem(STORAGE_KEY);
                        onSave(exercise.id, { name, muscleGroup: group, description, imageUrl: image, imageUrl2: image2 }); 
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
  const [exerciseToEdit, setExerciseToEdit] = useState<Exercise | null>(null);
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
                    console.log('Restoring previous workout session...');
                    setCurrentExercise(ex);
                    setScreen('workout');
                }
            } else {
                // Если данные устарели или пусты, очищаем
                localStorage.removeItem(WORKOUT_STORAGE_KEY);
            }
        } catch (e) {
            console.error('Failed to restore session', e);
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

  // Порядок отображения групп мышц
  const groupOrder = ['Спина', 'Ноги', 'Грудь', 'Плечи', 'Трицепс', 'Бицепс', 'Пресс', 'Кардио'];
  
  // Мемоизированная функция сортировки групп
  const sortGroups = useMemo(() => {
    return (groupsList: string[]): string[] => {
      const sorted: string[] = [];
      const remaining = [...groupsList];
      
      // Сначала добавляем группы в указанном порядке
      groupOrder.forEach(groupName => {
        const index = remaining.indexOf(groupName);
        if (index !== -1) {
          sorted.push(groupName);
          remaining.splice(index, 1);
        }
      });
      
      // Затем добавляем оставшиеся группы (если есть новые, не указанные в порядке)
      sorted.push(...remaining);
      
      return sorted;
    };
  }, []);

  useEffect(() => { 
    api.getInit().then(d => { 
      setGroups(sortGroups(d.groups)); 
      setAllExercises(d.exercises); 
    }); 
  }, [sortGroups]);

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
      console.log('handleUpdate called with:', { id, updates });
      console.log('imageUrl:', updates.imageUrl);
      console.log('imageUrl2:', updates.imageUrl2);
      
      // Обновляем локально для мгновенного отображения
      setAllExercises(p => p.map(ex => ex.id === id ? { ...ex, ...updates } : ex));
      // Сохраняем на сервере
      const result = await api.updateExercise(id, updates);
      console.log('Update result:', result);
      if (result) {
          // Перезагружаем данные с сервера для синхронизации
          const freshData = await api.getInit();
          if (freshData && freshData.exercises) {
              const updatedEx = freshData.exercises.find((ex: Exercise) => ex.id === id);
              console.log('Reloaded exercise data:', updatedEx);
              setAllExercises(freshData.exercises);
          }
          notify('success');
      } else {
          console.error('Update failed');
          notify('error');
      }
  };

  return (
    <div className="bg-zinc-950 min-h-screen text-zinc-50 font-sans selection:bg-blue-500/30 pt-24">
      {screen === 'home' && <HomeScreen groups={groups} onSearch={(q: string) => { setSearchQuery(q); if(q) setScreen('exercises'); }} onSelectGroup={(g: string) => { setSelectedGroup(g); setScreen('exercises'); }} onAllExercises={() => { setSelectedGroup(null); setScreen('exercises'); }} onHistory={() => setScreen('history')} searchQuery={searchQuery} />}
      {screen === 'history' && <HistoryScreen onBack={() => setScreen('home')} />}
      {screen === 'exercises' && <ExercisesListScreen exercises={filteredExercises} allExercises={allExercises} title={selectedGroup || (searchQuery ? `Поиск: ${searchQuery}` : 'Все упражнения')} searchQuery={searchQuery} onSearch={(q: string) => setSearchQuery(q)} onBack={() => { setSearchQuery(''); setSelectedGroup(null); setScreen('home'); }} onSelectExercise={(ex: Exercise) => { haptic('light'); setCurrentExercise(ex); setScreen('workout'); }} onAddExercise={() => setIsCreateModalOpen(true)} onEditExercise={(ex: Exercise) => setExerciseToEdit(ex)} />}
      {screen === 'workout' && currentExercise && <WorkoutScreen initialExercise={currentExercise} allExercises={allExercises} incrementOrder={incrementOrder} haptic={haptic} notify={notify} onBack={() => setScreen('exercises')} />}
      
      <Modal isOpen={isCreateModalOpen} onClose={() => setIsCreateModalOpen(false)} title="Новое упражнение">
         <div className="space-y-4">
             <div><label className="text-sm text-zinc-400 mb-1 block">Название</label><Input value={newName} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewName(e.target.value)} placeholder="Например: Отжимания" /></div>
             <div><label className="text-sm text-zinc-400 mb-1 block">Группа</label><div className="flex flex-wrap gap-2">{groups.map(g => <button key={g} onClick={() => setNewGroup(g)} className={`px-3 py-2 rounded-xl text-sm border ${newGroup === g ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-800 border-zinc-700 text-zinc-400'}`}>{g}</button>)}</div></div>
             <Button onClick={handleCreate} className="w-full h-12 mt-4">Создать</Button>
         </div>
      </Modal>
      {exerciseToEdit && <EditExerciseModal isOpen={!!exerciseToEdit} onClose={() => setExerciseToEdit(null)} exercise={exerciseToEdit} groups={groups} onSave={handleUpdate} />}
    </div>
  );
};

export default App;