import React, { useState, useEffect, useRef, useMemo } from 'react';
import { 
  Search, ChevronRight, Plus, X, Info, Clock, 
  Check, Trash2, StickyNote, ChevronDown, Dumbbell, Calendar, 
  ChevronLeft, Settings, ArrowLeft, Link as LinkIcon, Camera, Pencil, Trophy,
  History as HistoryIcon, Activity
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

// --- CONFIG ---
// Используем переменную окружения или localhost для разработки
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'; 

// --- TYPES ---

type Screen = 'home' | 'exercises' | 'workout' | 'history';

interface Exercise {
  id: string;
  name: string;
  muscleGroup: string;
  description?: string;
  imageUrl?: string;
}

interface WorkoutSet {
  id: string;
  weight: string;
  reps: string;
  rest: string;
  completed: boolean;
  prevWeight?: number;
}

interface HistoryItem {
  date: string;
  weight: number;
  reps: number;
  rest: number;
  order?: number;
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
    exercises: { name: string; sets: any[] }[];
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
    }
  }, []);
  const haptic = (style: any) => tg?.HapticFeedback?.impactOccurred(style);
  const notify = (type: any) => tg?.HapticFeedback?.notificationOccurred(type);
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
  const formatTime = (ms: number) => {
    const totalSeconds = Math.floor(ms / 1000);
    const m = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
    const s = (totalSeconds % 60).toString().padStart(2, '0');
    const ms2 = Math.floor((ms % 1000) / 10).toString().padStart(2, '0');
    return `${m}:${s}.${ms2}`;
  };
  return { time, isRunning, start, pause, reset, formatTime };
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
        <motion.div initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", damping: 25, stiffness: 300 }} className="fixed bottom-0 left-0 right-0 bg-zinc-900 border-t border-zinc-800 rounded-t-3xl z-50 max-h-[90vh] flex flex-col">
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
  const groupedHistory = useMemo(() => {
    const groups: Record<string, HistoryItem[]> = {};
    history.forEach((item: HistoryItem) => {
      if (!groups[item.date]) groups[item.date] = [];
      groups[item.date].push(item);
    });
    // Сортируем подходы внутри каждой даты по ORDER (от старых к новым)
    Object.keys(groups).forEach(date => {
      groups[date].sort((a, b) => (a.order || 0) - (b.order || 0));
    });
    return groups;
  }, [history]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`История: ${exerciseName}`}>
      <div className="space-y-6">
        {Object.entries(groupedHistory).map(([date, items]) => (
          <div key={date}>
            <div className="flex items-center gap-2 mb-2 sticky top-0 bg-zinc-900 py-1 z-10">
               <Calendar className="w-4 h-4 text-zinc-500" /><span className="text-sm font-bold text-zinc-400 uppercase tracking-wider">{date}</span>
            </div>
            <div className="bg-zinc-800/30 border border-zinc-800 rounded-xl overflow-hidden">
              {items.map((item, idx) => (
                <div key={idx} className="p-3 border-b border-zinc-800 last:border-0 flex items-center justify-between">
                  <div>
                    <div className="text-lg font-medium text-zinc-200">{item.weight} <span className="text-sm text-zinc-500">кг</span> × {item.reps}</div>
                  </div>
                  <div className="text-zinc-500 font-mono text-sm bg-zinc-900/50 px-2 py-1 rounded">{item.rest}м</div>
                </div>
              ))}
            </div>
          </div>
        ))}
        {history.length === 0 && <div className="text-center text-zinc-500 py-10">История пуста</div>}
      </div>
    </Modal>
  );
};

const SetRow = ({ set, index, onUpdate, onDelete, onComplete }: any) => {
  const oneRM = set.weight && set.reps ? Math.round(parseFloat(set.weight) * (1 + parseInt(set.reps) / 30)) : 0;
  const delta = set.prevWeight ? (parseFloat(set.weight) - set.prevWeight) : 0;
  const deltaText = delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : '0';
  const deltaColor = delta > 0 ? 'text-green-500' : delta < 0 ? 'text-red-500' : 'text-zinc-500';

  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`grid grid-cols-[auto_1fr_1fr_1fr_auto] gap-2 items-start mb-3 ${set.completed ? 'opacity-50 pointer-events-none grayscale' : ''}`}>
      <button onClick={() => onComplete(set.id)} className={`w-12 h-12 rounded-xl border flex items-center justify-center transition-colors ${set.completed ? 'bg-green-500 border-green-500' : 'bg-zinc-900 border-zinc-700'}`}>
        {set.completed && <Check className="w-6 h-6 text-white" />}
      </button>
      <div className="flex flex-col gap-1">
        <input type="number" inputMode="decimal" placeholder="0" value={set.weight} onChange={e => onUpdate(set.id, 'weight', e.target.value)} className="w-full h-12 bg-zinc-800 rounded-xl text-center text-xl font-bold text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums" />
        {(oneRM > 0 || set.prevWeight) && (
          <div className="flex justify-between px-1 text-[10px]">
            {oneRM > 0 && <span className="text-zinc-500">1PM:{oneRM}</span>}
            {set.prevWeight !== undefined && <span className={`${deltaColor} font-medium`}>{deltaText}</span>}
          </div>
        )}
      </div>
      <input type="tel" inputMode="numeric" placeholder="0" value={set.reps} onChange={e => onUpdate(set.id, 'reps', e.target.value)} className="w-full h-12 bg-zinc-800 rounded-xl text-center text-xl font-bold text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums" />
      <input type="number" inputMode="decimal" placeholder="0" value={set.rest} onChange={e => onUpdate(set.id, 'rest', e.target.value)} className="w-full h-12 bg-zinc-800 rounded-xl text-center text-zinc-400 focus:text-zinc-100 focus:ring-1 focus:ring-blue-500 outline-none tabular-nums" />
      <button onClick={() => onDelete(set.id)} className="w-10 h-12 flex items-center justify-center text-zinc-600 hover:text-red-500"><Trash2 className="w-5 h-5" /></button>
    </motion.div>
  );
};

const WorkoutCard = ({ exerciseData, onAddSet, onUpdateSet, onDeleteSet, onCompleteSet, onNoteChange, onAddSuperset }: any) => {
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const personalRecord = useMemo(() => {
    if (!exerciseData.history.length) return 0;
    return Math.max(...exerciseData.history.map(h => h.weight));
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
        {exerciseData.sets.map((set: any, idx: number) => (
          <SetRow key={set.id} set={set} index={idx} onUpdate={onUpdateSet} onDelete={onDeleteSet} onComplete={onCompleteSet} />
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

const HomeScreen = ({ groups, onSearch, onSelectGroup, onAllExercises, onHistory }: any) => (
  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-4 space-y-6">
    <div className="flex items-center gap-2">
      <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-500" />
          <Input placeholder="Найти..." onChange={(e: any) => onSearch(e.target.value)} className="pl-12 bg-zinc-900 w-full" />
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

const ExercisesListScreen = ({ exercises, title, onBack, onSelectExercise, onAddExercise, onEditExercise, searchQuery, onSearch }: any) => {
  const [infoModalEx, setInfoModalEx] = useState<Exercise | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  
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
                  onChange={(e: any) => onSearch(e.target.value)} 
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
          <div key={ex.id} className="flex items-center p-2 rounded-2xl hover:bg-zinc-900 border border-transparent hover:border-zinc-800 transition-all">
            <div onClick={(e) => { e.stopPropagation(); setInfoModalEx(ex); }} className="w-14 h-14 rounded-xl bg-zinc-800 flex-shrink-0 overflow-hidden cursor-pointer active:scale-90 transition-transform relative group">
              {ex.imageUrl ? <img src={ex.imageUrl} className="w-full h-full object-cover" /> : <div className="w-full h-full flex items-center justify-center text-zinc-600"><Info /></div>}
              <div className="absolute inset-0 bg-black/30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"><Settings className="w-5 h-5 text-white" /></div>
            </div>
            <div onClick={() => onSelectExercise(ex)} className="flex-1 px-4 cursor-pointer">
              <div className="font-medium text-zinc-100 text-[17px]">{ex.name}</div>
              <div className="text-xs text-zinc-500">{ex.muscleGroup}</div>
            </div>
            <button onClick={() => onSelectExercise(ex)} className="p-2 text-zinc-600"><ChevronRight className="w-5 h-5" /></button>
          </div>
        ))}
      </div>
      <Modal isOpen={!!infoModalEx} onClose={() => setInfoModalEx(null)} title={infoModalEx?.name} headerAction={<button onClick={() => { if (infoModalEx) { onEditExercise(infoModalEx); setInfoModalEx(null); } }} className="p-2 bg-zinc-800 rounded-full text-zinc-400 hover:text-blue-400"><Pencil className="w-5 h-5" /></button>}>
        {infoModalEx && (
          <div className="space-y-4">
             <div className="aspect-video bg-zinc-800 rounded-2xl overflow-hidden">{infoModalEx.imageUrl && <img src={infoModalEx.imageUrl} className="w-full h-full object-cover" />}</div>
             <div className="text-zinc-400 leading-relaxed">{infoModalEx.description || 'Описание отсутствует.'}</div>
             <div className="pt-4"><div className="text-xs text-zinc-500 uppercase font-bold tracking-wider mb-2">Группа</div><div className="px-3 py-1 bg-zinc-800 rounded-lg inline-block text-zinc-300 text-sm">{infoModalEx.muscleGroup}</div></div>
          </div>
        )}
      </Modal>
    </motion.div>
  );
};

const WorkoutScreen = ({ initialExercise, allExercises, onBack, sessionId, incrementOrder, haptic, notify }: any) => {
  const timer = useTimer();
  const [activeExercises, setActiveExercises] = useState<string[]>([initialExercise.id]);
  const [sessionData, setSessionData] = useState<Record<string, ExerciseSessionData>>({});
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);

  const loadExerciseData = async (exId: string) => {
    if (sessionData[exId]) return;
    const { history, note } = await api.getHistory(exId);
    setSessionData(prev => {
        let initialSets: WorkoutSet[] = [];
        if (history.length > 0) {
            // Сортируем историю по ORDER (от старых к новым), если есть поле order
            const sortedHistory = [...history].sort((a, b) => {
                if (a.order !== undefined && b.order !== undefined) {
                    return a.order - b.order;
                }
                return 0;
            });
            
            // Берем последнюю дату (самую новую)
            const lastDate = sortedHistory[sortedHistory.length - 1]?.date || sortedHistory[0]?.date;
            
            // Фильтруем по последней дате и сортируем по ORDER
            const lastDateItems = sortedHistory
                .filter(h => h.date === lastDate)
                .sort((a, b) => (a.order || 0) - (b.order || 0));
            
            initialSets = lastDateItems.map(h => ({
                id: crypto.randomUUID(), 
                weight: h.weight.toString(), 
                reps: h.reps.toString(), 
                rest: h.rest.toString(), 
                completed: false, 
                prevWeight: h.weight
            }));
        } else {
            initialSets = [{ id: crypto.randomUUID(), weight: '', reps: '', rest: '', completed: false, prevWeight: 0 }];
        }
        return { ...prev, [exId]: { exercise: allExercises.find(e => e.id === exId)!, note: note || '', history, sets: initialSets } };
    });
  };

  useEffect(() => { activeExercises.forEach(id => loadExerciseData(id)); }, [activeExercises]);

  const handleCompleteSet = async (exId: string, setId: string) => {
    const set = sessionData[exId].sets.find(s => s.id === setId);
    if (!set || set.completed) return;
    if (!set.weight || !set.reps) { notify('error'); return; }
    
    haptic('medium');
    // Optimistic
    setSessionData(prev => ({ ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.map(s => s.id === setId ? { ...s, completed: true } : s) } }));
    // Сбрасываем таймер и сразу запускаем заново
    timer.reset();
    timer.start();

    try {
        const order = incrementOrder();
        await api.saveSet({
            exercise_id: exId,
            weight: parseFloat(set.weight),
            reps: parseInt(set.reps),
            rest: parseFloat(set.rest) || 0,
            note: sessionData[exId].note,
            set_group_id: sessionId,
            order
        });
        notify('success');
    } catch (e) {
        notify('error');
    }
  };

  const handleUpdateSet = (exId: string, setId: string, field: any, val: any) => {
    setSessionData(prev => ({ ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.map(s => s.id === setId ? { ...s, [field]: val } : s) } }));
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
      setSessionData(prev => ({ ...prev, [exId]: { ...prev[exId], sets: prev[exId].sets.filter(s => s.id !== setId) } }));
  };

  return (
    <div className="min-h-screen bg-zinc-950 pb-20">
      <TimerBlock timer={timer} onToggle={() => timer.isRunning ? timer.reset() : timer.start()} />
      <div className="px-4 space-y-4">
        {activeExercises.map(exId => {
            const data = sessionData[exId];
            if (!data) return <div key={exId} className="h-40 bg-zinc-900 rounded-2xl animate-pulse" />;
            return <WorkoutCard key={exId} exerciseData={data} onAddSet={() => handleAddSet(exId)} onUpdateSet={(sid, f, v) => handleUpdateSet(exId, sid, f, v)} onDeleteSet={(sid) => handleDeleteSet(exId, sid)} onCompleteSet={(sid) => handleCompleteSet(exId, sid)} onNoteChange={(val) => setSessionData(p => ({...p, [exId]: {...p[exId], note: val}}))} onAddSuperset={() => setIsAddModalOpen(true)} />;
        })}
      </div>
      <div className="px-4 mt-8 mb-20"><Button variant="primary" onClick={onBack} className="w-full h-14 text-lg font-semibold shadow-xl shadow-blue-900/20">Завершить упражнение</Button></div>
      <Modal isOpen={isAddModalOpen} onClose={() => setIsAddModalOpen(false)} title="Добавить в суперсет">
        <div className="space-y-2">{allExercises.map((ex: Exercise) => (<div key={ex.id} onClick={() => { if (!activeExercises.includes(ex.id)) setActiveExercises([...activeExercises, ex.id]); setIsAddModalOpen(false); }} className="flex items-center p-3 bg-zinc-800/50 rounded-xl border border-zinc-800 cursor-pointer"><div className="font-medium text-zinc-200">{ex.name}</div>{activeExercises.includes(ex.id) && <Check className="ml-auto text-green-500 w-5 h-5"/>}</div>))}</div>
      </Modal>
      <div className="fixed bottom-6 left-6 z-20"><button onClick={onBack} className="w-12 h-12 rounded-full bg-zinc-800 text-zinc-400 flex items-center justify-center border border-zinc-700 shadow-lg hover:text-white"><ArrowLeft className="w-6 h-6" /></button></div>
    </div>
  );
};

const HistoryScreen = ({ onBack }: any) => {
    const [history, setHistory] = useState<GlobalWorkoutSession[]>([]);
    const [expandedId, setExpandedId] = useState<string | null>(null);
    useEffect(() => { 
        api.getGlobalHistory().then(data => {
            console.log('History data received:', data);
            if (data && data.length > 0) {
                console.log('First session:', data[0]);
                if (data[0].exercises) {
                    console.log('First session exercises:', data[0].exercises);
                    if (data[0].exercises.length > 0) {
                        console.log('First exercise:', data[0].exercises[0]);
                        console.log('First exercise sets:', data[0].exercises[0].sets);
                    }
                }
            }
            setHistory(data);
        });
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
                                            console.log(`Exercise ${i}:`, ex.name, 'sets:', ex.sets);
                                            return (
                                                <div key={i} className="p-4 border-b border-zinc-800/50 last:border-0">
                                                    <div className="font-medium text-zinc-300 mb-2">{ex.name}</div>
                                                    {ex.sets && Array.isArray(ex.sets) && ex.sets.length > 0 ? (
                                                        <div className="space-y-1">
                                                            {ex.sets.map((s: any, j: number) => {
                                                                console.log(`Set ${j}:`, s);
                                                                const weight = typeof s.weight === 'number' ? s.weight : (s.weight ? parseFloat(String(s.weight)) : 0);
                                                                const reps = typeof s.reps === 'number' ? s.reps : (s.reps ? parseInt(String(s.reps)) : 0);
                                                                if (weight === 0 && reps === 0) {
                                                                    console.warn(`Set ${j} has zero values:`, s);
                                                                }
                                                                return (
                                                                    <div key={j} className="flex justify-between text-sm text-zinc-400 px-2 py-1 bg-zinc-800/30 rounded">
                                                                        <span>#{j+1} {weight}кг</span>
                                                                        <span>{reps}повт</span>
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    ) : (
                                                        <div className="text-xs text-zinc-500">
                                                            Нет подходов. 
                                                            <br />ex.sets type: {typeof ex.sets}, 
                                                            <br />isArray: {Array.isArray(ex.sets)}, 
                                                            <br />length: {ex.sets ? (Array.isArray(ex.sets) ? ex.sets.length : 'not array') : 'null'},
                                                            <br />value: {ex.sets ? JSON.stringify(ex.sets).substring(0, 100) : 'null'}
                                                        </div>
                                                    )}
                                                </div>
                                            );
                                        })
                                    ) : (
                                        <div className="p-4 text-center text-zinc-500 text-sm">Нет упражнений (exercises: {w.exercises ? JSON.stringify(w.exercises) : 'null'})</div>
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
    const [name, setName] = useState('');
    const [group, setGroup] = useState('');
    const [image, setImage] = useState('');
    const fileRef = useRef<any>(null);
    useEffect(() => { if(exercise) { setName(exercise.name); setGroup(exercise.muscleGroup); setImage(exercise.imageUrl || ''); } }, [exercise]);
    
    const handleFile = (e: any) => {
        const file = e.target.files?.[0];
        if (file) { const r = new FileReader(); r.onloadend = () => setImage(r.result as string); r.readAsDataURL(file); }
    };

    return (
        <Modal isOpen={isOpen} onClose={onClose} title="Редактировать">
            <div className="space-y-6">
                <div onClick={() => fileRef.current?.click()} className="w-full h-48 bg-zinc-800 rounded-2xl overflow-hidden relative flex items-center justify-center cursor-pointer border border-zinc-700 border-dashed">
                    {image ? <img src={image} className="w-full h-full object-cover" /> : <div className="flex flex-col items-center text-zinc-500"><Camera className="w-8 h-8 mb-2" /><span className="text-sm">Фото</span></div>}
                </div>
                <input ref={fileRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={handleFile} />
                <div><label className="text-sm text-zinc-400 mb-1 block">Название</label><Input value={name} onChange={(e:any) => setName(e.target.value)} /></div>
                <div>
                    <label className="text-sm text-zinc-400 mb-1 block">Группа</label>
                    <div className="flex flex-wrap gap-2">{groups.map((g: string) => <button key={g} onClick={() => setGroup(g)} className={`px-3 py-2 rounded-xl text-sm border ${group === g ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-800 border-zinc-700 text-zinc-400'}`}>{g}</button>)}</div>
                </div>
                <Button onClick={() => { onSave(exercise.id, { name, muscleGroup: group, imageUrl: image }); onClose(); }} className="w-full h-12">Сохранить</Button>
            </div>
        </Modal>
    );
};

// --- MAIN ---

const App = () => {
  const { tg, haptic, notify } = useTelegram();
  const { sessionId, incrementOrder } = useSession();
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

  useEffect(() => { api.getInit().then(d => { setGroups(d.groups); setAllExercises(d.exercises); }); }, []);

  const filteredExercises = useMemo(() => {
    let list = allExercises;
    if (selectedGroup) list = list.filter(ex => ex.muscleGroup === selectedGroup);
    if (searchQuery) list = list.filter(ex => ex.name.toLowerCase().includes(searchQuery.toLowerCase()));
    return list;
  }, [allExercises, selectedGroup, searchQuery]);

  const handleCreate = async () => {
      if (!newName || !newGroup) return;
      const newEx = await api.createExercise(newName, newGroup);
      if (newEx) { setAllExercises(p => [...p, newEx]); setIsCreateModalOpen(false); setNewName(''); notify('success'); }
  };

  const handleUpdate = async (id: string, updates: any) => {
      setAllExercises(p => p.map(ex => ex.id === id ? { ...ex, ...updates } : ex));
      await api.updateExercise(id, updates);
      notify('success');
  };

  return (
    <div className="bg-zinc-950 min-h-screen text-zinc-50 font-sans selection:bg-blue-500/30">
      {screen === 'home' && <HomeScreen groups={groups} onSearch={(q: string) => { setSearchQuery(q); if(q) setScreen('exercises'); }} onSelectGroup={(g: string) => { setSelectedGroup(g); setScreen('exercises'); }} onAllExercises={() => { setSelectedGroup(null); setScreen('exercises'); }} onHistory={() => setScreen('history')} />}
      {screen === 'history' && <HistoryScreen onBack={() => setScreen('home')} />}
      {screen === 'exercises' && <ExercisesListScreen exercises={filteredExercises} title={selectedGroup || (searchQuery ? `Поиск: ${searchQuery}` : 'Все упражнения')} searchQuery={searchQuery} onSearch={(q: string) => setSearchQuery(q)} onBack={() => { setSearchQuery(''); setSelectedGroup(null); setScreen('home'); }} onSelectExercise={(ex: Exercise) => { haptic('light'); setCurrentExercise(ex); setScreen('workout'); }} onAddExercise={() => setIsCreateModalOpen(true)} onEditExercise={(ex: Exercise) => setExerciseToEdit(ex)} />}
      {screen === 'workout' && currentExercise && <WorkoutScreen initialExercise={currentExercise} allExercises={allExercises} sessionId={sessionId} incrementOrder={incrementOrder} haptic={haptic} notify={notify} onBack={() => setScreen('exercises')} />}
      
      <Modal isOpen={isCreateModalOpen} onClose={() => setIsCreateModalOpen(false)} title="Новое упражнение">
         <div className="space-y-4">
             <div><label className="text-sm text-zinc-400 mb-1 block">Название</label><Input value={newName} onChange={(e:any) => setNewName(e.target.value)} placeholder="Например: Отжимания" /></div>
             <div><label className="text-sm text-zinc-400 mb-1 block">Группа</label><div className="flex flex-wrap gap-2">{groups.map(g => <button key={g} onClick={() => setNewGroup(g)} className={`px-3 py-2 rounded-xl text-sm border ${newGroup === g ? 'bg-blue-600 border-blue-600 text-white' : 'bg-zinc-800 border-zinc-700 text-zinc-400'}`}>{g}</button>)}</div></div>
             <Button onClick={handleCreate} className="w-full h-12 mt-4">Создать</Button>
         </div>
      </Modal>
      {exerciseToEdit && <EditExerciseModal isOpen={!!exerciseToEdit} onClose={() => setExerciseToEdit(null)} exercise={exerciseToEdit} groups={groups} onSave={handleUpdate} />}
    </div>
  );
};

export default App;