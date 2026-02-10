interface SetDisplayRowProps {
  weight: number | string;
  reps: number | string;
  rest: number | string;
  className?: string;
}

export function SetDisplayRow({ weight, reps, rest, className = '' }: SetDisplayRowProps) {
  return (
    <div className={`flex items-center justify-between ${className}`}>
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
}
