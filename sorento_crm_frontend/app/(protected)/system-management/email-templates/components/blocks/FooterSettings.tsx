'use client';

import { Textarea } from '@/components/ui/textarea';
import type { AnyBlockPatch, FooterBlock } from '../../types/emailTemplate.types';

export function FooterSettings({
  block,
  onChange,
}: {
  block: FooterBlock;
  onChange: (patch: AnyBlockPatch) => void;
}) {
  return (
    <Textarea
      aria-label="Footer note"
      value={block.note ?? ''}
      onChange={(e) => onChange({ note: e.target.value || null })}
      rows={2}
      placeholder="Optional - replaces the theme's default 'why you received this' line for this mail"
    />
  );
}

export default FooterSettings;
