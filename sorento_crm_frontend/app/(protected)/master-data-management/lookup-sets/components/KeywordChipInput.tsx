'use client';
import { useState } from 'react';
import { X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import type { LookupKeyword } from '../types/lookup.types';

export default function KeywordChipInput({
  value, onChange,
}: { value: LookupKeyword[]; onChange: (v: LookupKeyword[]) => void }) {
  const [draft, setDraft] = useState('');
  return (
    <div className="border rounded-md px-2 py-1.5 flex flex-wrap gap-1.5">
      {value.map((k, i) => (
        <span key={`${k.keyword}-${i}`} className="inline-flex items-center gap-1 bg-muted text-sm rounded-full px-2 py-0.5">
          {k.keyword}
          <button
            aria-label={`Remove ${k.keyword}`}
            type="button"
            onClick={() => onChange(value.filter((_, j) => j !== i))}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <Input
        className="border-0 shadow-none flex-1 min-w-32"
        placeholder="Add keyword and press Enter"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && draft.trim()) {
            e.preventDefault();
            onChange([...value, { keyword: draft.trim(), locale: null }]);
            setDraft('');
          }
        }}
      />
    </div>
  );
}
