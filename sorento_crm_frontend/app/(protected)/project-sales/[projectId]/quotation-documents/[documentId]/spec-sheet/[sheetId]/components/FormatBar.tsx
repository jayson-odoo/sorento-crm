'use client';

import * as React from 'react';
import { AlignCenter, AlignLeft, AlignRight, Bold, Italic } from 'lucide-react';

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
 * The designer's text formatting (font, size, bold, italic, align) in the reader's toolbar, for
 * the selected text layer. Each control changes the layer through the same handle the Inspector
 * uses, so "Every page" applies to these too.
 */
export function FormatBar({
  layer,
  onProps,
}: {
  /** The selected layer. Anything but text draws the same bar, hidden, so the toolbar keeps its size. */
  layer: TagLayer | null;
  onProps: (id: string, changes: Partial<TagLayerProps>) => void;
}) {
  const library = useKitLibrary();
  const active = layer?.props.kind === 'text' ? layer : null;
  const text =
    active && active.props.kind === 'text' ? active.props : defaultTextProps();
  const set = (changes: Partial<TagLayerProps>) => {
    if (active) onProps(active.id, changes);
  };
  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-1',
        !active && 'invisible',
      )}
      role="group"
      aria-label="Text formatting"
      aria-hidden={!active || undefined}
      inert={!active || undefined}
    >
      <div className="w-28">
        <SearchableSelect
          size="sm"
          value={text.fontFamily}
          onChange={(value: string) => value && set({ fontFamily: value })}
          options={library.fontOptions}
          aria-label="Font"
        />
      </div>
      <NumberInput
        min={1}
        max={400}
        aria-label="Font size"
        className="h-7 w-16 text-xs"
        value={text.fontSize}
        onValueChange={(size) => {
          if (size !== null && Number.isFinite(size) && size > 0)
            set({ fontSize: size });
        }}
      />
      <Button
        type="button"
        size="icon"
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
          variant={text.align === align ? 'primary' : 'outline'}
          aria-label={`Align ${align}`}
          aria-pressed={text.align === align}
          onClick={() => set({ align })}
        >
          <Icon className="size-4" />
        </Button>
      ))}
    </div>
  );
}
