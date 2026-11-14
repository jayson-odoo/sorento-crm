'use client';

import * as React from 'react';
import { AlignCenter, AlignLeft, AlignRight, Bold, CaseUpper, Italic, Settings2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { NumberInput } from '@/components/ui/number-input';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useKitLibrary } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import type {
  TagLayer,
  TagLayerProps,
} from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';
import { cn } from '@/lib/utils';

/**
 * The designer's text formatting (font, size, bold, italic, align, ALL CAPS) in the reader's one
 * toolbar row (v3 AC-C1.4), for the selected text layer; nothing at all for any other selection.
 * Each control changes the layer through the same handle the Inspector uses, so "Every page"
 * applies to these too.
 */
export function FormatBar({
  layer,
  onProps,
  onManageFonts,
}: {
  /** The selected layer. Anything but text draws nothing (the toolbar row keeps its fixed height). */
  layer: TagLayer | null;
  onProps: (id: string, changes: Partial<TagLayerProps>) => void;
  /** v3 (AC-C6.1): open the reader's font dialog, beside the font list. Absent: no button. */
  onManageFonts?: () => void;
}) {
  const library = useKitLibrary();
  const active = layer?.props.kind === 'text' ? layer : null;
  const text =
    active && active.props.kind === 'text' ? active.props : defaultTextProps();
  const set = (changes: Partial<TagLayerProps>) => {
    if (active) onProps(active.id, changes);
  };
  if (!active) return null;
  return (
    <div
      className={cn('flex shrink-0 flex-nowrap items-center gap-1')}
      role="group"
      aria-label="Text formatting"
    >
      <div className="w-24">
        <SearchableSelect
          size="sm"
          value={text.fontFamily}
          onChange={(value: string) => value && set({ fontFamily: value })}
          options={library.fontOptions}
          aria-label="Font"
        />
      </div>
      {onManageFonts && (
        <Button
          type="button"
          size="icon"
          className="size-7"
          variant="ghost"
          aria-label="Manage fonts"
          title="Manage fonts"
          onClick={onManageFonts}
        >
          <Settings2 className="size-4" />
        </Button>
      )}
      <NumberInput
        min={1}
        max={400}
        aria-label="Font size"
        className="h-7 w-14 text-xs"
        value={text.fontSize}
        onValueChange={(size) => {
          if (size !== null && Number.isFinite(size) && size > 0)
            set({ fontSize: size });
        }}
      />
      <Button
        type="button"
        size="icon"
        className="size-7"
        variant={text.fontWeight >= 600 ? 'primary' : 'outline'}
        aria-label="Bold"
        aria-pressed={text.fontWeight >= 600}
        onClick={() => set({ fontWeight: text.fontWeight >= 600 ? 400 : 700 })}
      >
        <Bold className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon"
        className="size-7"
        variant={text.italic ? 'primary' : 'outline'}
        aria-label="Italic"
        aria-pressed={Boolean(text.italic)}
        onClick={() => set({ italic: !text.italic })}
      >
        <Italic className="size-4" />
      </Button>
      {(
        [
          ['left', AlignLeft],
          ['center', AlignCenter],
          ['right', AlignRight],
        ] as const
      ).map(([align, Icon]) => (
        <Button
          key={align}
          type="button"
          size="icon"
          className="size-7"
          variant={text.align === align ? 'primary' : 'outline'}
          aria-label={`Align ${align}`}
          aria-pressed={text.align === align}
          onClick={() => set({ align })}
        >
          <Icon className="size-4" />
        </Button>
      ))}
      <Button
        type="button"
        size="icon"
        className="size-7"
        variant={text.uppercase ? 'primary' : 'outline'}
        aria-label="ALL CAPS"
        aria-pressed={Boolean(text.uppercase)}
        onClick={() => set({ uppercase: !text.uppercase })}
      >
        <CaseUpper className="size-4" />
      </Button>
    </div>
  );
}
