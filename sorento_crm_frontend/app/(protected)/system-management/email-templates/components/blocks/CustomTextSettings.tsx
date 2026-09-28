'use client';

import { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import type { AnyBlockPatch, CustomTextBlock } from '../../types/emailTemplate.types';

/**
 * Custom text edits with the existing Tiptap editor by default; the HTML
 * toggle swaps to a raw textarea because StarterKit has no Table extension
 * and the OI templates' pipe tables need to round-trip through it unchanged
 * (AC-EM045, D5).
 */
export function CustomTextSettings({
  block,
  onChange,
}: {
  block: CustomTextBlock;
  onChange: (patch: AnyBlockPatch) => void;
}) {
  // Tables and Jinja tags do not survive the rich-text editor (StarterKit has no Table
  // extension), so a block that carries them opens in HTML mode.
  const [htmlMode, setHtmlMode] = useState(() => /<table|\{%/i.test(block.html ?? ''));

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-end gap-2">
        <Switch id={`custom-text-html-${block.id}`} checked={htmlMode} onCheckedChange={setHtmlMode} />
        <Label htmlFor={`custom-text-html-${block.id}`} className="text-xs">
          HTML
        </Label>
      </div>
      {htmlMode ? (
        <Textarea
          aria-label="HTML source"
          value={block.html}
          onChange={(e) => onChange({ html: e.target.value })}
          rows={8}
          className="font-mono text-sm"
        />
      ) : (
        <RichTextEditor value={block.html} onChange={(html) => onChange({ html })} minHeight={160} />
      )}
    </div>
  );
}

export default CustomTextSettings;
