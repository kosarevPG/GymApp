import { ChevronLeft } from 'lucide-react';

interface ScreenHeaderProps {
  title: string;
  onBack: () => void;
  children?: React.ReactNode;
  rightAction?: React.ReactNode;
}

export function ScreenHeader({ title, onBack, children, rightAction }: ScreenHeaderProps) {
  return (
    <div className="sticky top-0 z-30 bg-zinc-950/80 backdrop-blur-md border-b border-zinc-800 p-4 flex items-center justify-between gap-4">
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <button onClick={onBack} className="p-2 -ml-2 text-zinc-400 active:text-white">
          <ChevronLeft className="w-6 h-6" />
        </button>
        {children ?? <h1 className="text-xl font-bold truncate">{title}</h1>}
      </div>
      {rightAction}
    </div>
  );
}
