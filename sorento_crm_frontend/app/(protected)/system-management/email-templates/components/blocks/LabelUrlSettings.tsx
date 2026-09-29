'use client';

import { Input } from '@/components/ui/input';
import type { AnyBlockPatch, ButtonBlock, LinkBlock } from '../../types/emailTemplate.types';

/** The button and link blocks share the same shape - label + URL - so one
 * settings body serves both (AC-EM043). */
export function LabelUrlSettings({
  block,
  onChange,
  urlPlaceholder = '{{ reset_link }}',
}: {
  block: ButtonBlock | LinkBlock;
  onChange: (patch: AnyBlockPatch) => void;
  urlPlaceholder?: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <Input
        aria-label="Label"
        value={block.label}
        onChange={(e) => onChange({ label: e.target.value })}
        placeholder="Reset password"
      />
      <Input
        aria-label="URL"
        value={block.url}
        onChange={(e) => onChange({ url: e.target.value })}
        placeholder={urlPlaceholder}
      />
    </div>
  );
}

export default LabelUrlSettings;
