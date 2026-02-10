import { Camera } from 'lucide-react';

interface ImageUploadSlotProps {
  value: string;
  onChange: (url: string) => void;
  onUpload: (file: File) => Promise<string | null>;
  uploading: boolean;
  label: string;
  inputId: string;
  onBeforeOpen?: () => void;
}

export function ImageUploadSlot({ value, onChange, onUpload, uploading, label, inputId, onBeforeOpen }: ImageUploadSlotProps) {
  const handleChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const result = await onUpload(file);
    if (result) onChange(result);
    e.target.value = '';
  };

  return (
    <div>
      <label className="text-sm text-zinc-400 mb-2 block">{label}</label>
      <div
        onClick={() => {
          onBeforeOpen?.();
          (document.getElementById(inputId) as HTMLInputElement)?.click();
        }}
        className="w-full h-48 bg-zinc-800 rounded-2xl overflow-hidden relative flex items-center justify-center cursor-pointer border border-zinc-700 border-dashed"
      >
        {uploading ? (
          <div className="text-zinc-500">Загрузка...</div>
        ) : value ? (
          <img src={value} className="w-full h-full object-cover" alt={label} />
        ) : (
          <div className="flex flex-col items-center text-zinc-500">
            <Camera className="w-8 h-8 mb-2" />
            <span className="text-sm">Фото</span>
          </div>
        )}
      </div>
      <input
        id={inputId}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
        disabled={uploading}
      />
    </div>
  );
}
