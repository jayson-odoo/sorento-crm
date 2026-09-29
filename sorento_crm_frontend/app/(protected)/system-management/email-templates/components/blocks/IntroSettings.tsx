'use client';

import { Textarea } from '@/components/ui/textarea';
import type { AnyBlockPatch, IntroBlock } from '../../types/emailTemplate.types';
import { AlignSelect } from './AlignSelect';

export function IntroSettings({
  block,
  onChange,
}: {
  block: IntroBlock;
  onChange: (patch: AnyBlockPatch) => void;
}) {
  return (
    <div className="space-y-2">
      <Textarea
        aria-label="Intro text"
        value={block.text}
        onChange={(e) => onChange({ text: e.target.value })}
        rows={3}
        placeholder={'Hi {{ recipient.name }},\n\nA blank line starts a new paragraph.'}
      />
      <AlignSelect value={block.align} onChange={(align) => onChange({ align })} />
    </div>
  );
}

export default IntroSettings;
