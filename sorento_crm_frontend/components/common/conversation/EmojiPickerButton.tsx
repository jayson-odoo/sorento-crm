'use client';

/**
 * Emoji picker for the conversation composer (UAC AC-L5).
 *
 * Uses `emoji-picker-react`, which was ALREADY a dependency of this app, rather
 * than hand-rolling a grid: it brings search, categories and skin tones for
 * free, and adding nothing to package.json is the cheapest possible answer.
 *
 * Two deliberate settings:
 * - `next/dynamic` with `ssr: false`, so the module is never imported on the
 *   server. The picker reads `window` at module scope; a client component is
 *   still prerendered by `next build`, and this is what keeps that build green.
 * - native emoji style, so no sprite sheets are fetched from a CDN at all. A
 *   composer that needs the network to show a smiley is a composer that shows
 *   empty squares on a bad connection.
 *
 * Insertion is the CALLER's job (`onSelect`): only the composer knows where the
 * caret is.
 */

import { useState } from 'react';
import dynamic from 'next/dynamic';
import { Smile } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

const EmojiPicker = dynamic(() => import('emoji-picker-react'), {
  ssr: false,
  loading: () => <div className="h-[350px] w-[300px] animate-pulse rounded-md bg-muted" />,
});

interface EmojiPickerButtonProps {
  onSelect: (emoji: string) => void;
  disabled?: boolean;
}

export default function EmojiPickerButton({ onSelect, disabled = false }: EmojiPickerButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          aria-label="Insert emoji"
          data-testid="emoji-picker-trigger"
        >
          <Smile className="size-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto border-none p-0" align="start" side="top">
        <EmojiPicker
          // 'native' is EmojiStyle.NATIVE. Cast rather than importing the enum:
          // a value import would pull the whole picker into the server bundle
          // and undo the ssr:false above.
          emojiStyle={'native' as never}
          lazyLoadEmojis
          skinTonesDisabled
          width={300}
          height={350}
          previewConfig={{ showPreview: false }}
          onEmojiClick={(data: { emoji: string }) => {
            onSelect(data.emoji);
            setOpen(false);
          }}
        />
      </PopoverContent>
    </Popover>
  );
}
