'use client';

import { Input } from '@/components/ui/input';
import type { AnyBlockPatch, HeadingBlock } from '../../types/emailTemplate.types';
import { AlignSelect } from './AlignSelect';

export function HeadingSettings({
  block,
  onChange,
}: {
  block: HeadingBlock;
  onChange: (patch: AnyBlockPatch) => void;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_160px]">
      <Input
        aria-label="Heading text"
        value={block.text}
        onChange={(e) => onChange({ text: e.target.value })}
        placeholder="Reset your password"
      />
      <AlignSelect value={block.align} onChange={(align) => onChange({ align })} />
    </div>
  );
}

export default HeadingSettings;
