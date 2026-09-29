'use client';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { BlockAlign } from '../../types/emailTemplate.types';

const ALIGN_OPTIONS = [
  { value: 'left', label: 'Left' },
  { value: 'center', label: 'Center' },
];

export function AlignSelect({
  value,
  onChange,
  label = 'Alignment',
}: {
  value: BlockAlign;
  onChange: (value: BlockAlign) => void;
  label?: string;
}) {
  return (
    <div className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <SearchableSelect
        aria-label={label}
        value={value}
        onChange={(v) => onChange(v as BlockAlign)}
        options={ALIGN_OPTIONS}
      />
    </div>
  );
}

export default AlignSelect;
