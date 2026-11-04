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

/**
 * The designer's text formatting (font, size, bold, italic, align) in the reader's toolbar, for
 * the selected text layer. Each control changes the layer through the same handle the Inspector
 * uses, so "Every page" applies to these too.
 */
export function FormatBar({
  layer,
  onProps,
}: {
  layer: TagLayer;
  onProps: (id: string, changes: Partial<TagLayerProps>) => void;
}) {
  const library = useKitLibrary();
  if (layer.props.kind !== 'text') return null;
  const text = layer.props;
  const set = (changes: Partial<TagLayerProps>) => onProps(layer.id, changes);
  return (
    <div
      className="flex flex-wrap items-center gap-1"
      role="group"
      aria-label="Text formatting"
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
