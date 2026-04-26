'use client';

import { forwardRef, useEffect, useImperativeHandle, useState } from 'react';
import { cn } from '@/lib/utils';

export type MentionItem = { id: string; label: string };

export type MentionListProps = {
  items: MentionItem[];
  command: (item: MentionItem) => void;
};

/** Dropdown for TipTap @ mention suggestion (keyboard nav via ref). */
export const MentionList = forwardRef<{ onKeyDown: (props: { event: KeyboardEvent }) => boolean }, MentionListProps>(
  ({ items, command }, ref) => {
    const [selected, setSelected] = useState(0);

    useEffect(() => {
      setSelected(0);
    }, [items]);

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }) => {
        if (event.key === 'ArrowDown') {
          event.preventDefault();
          setSelected((i) => (items.length ? (i + 1) % items.length : 0));
          return true;
        }
        if (event.key === 'ArrowUp') {
          event.preventDefault();
          setSelected((i) => (items.length ? (i - 1 + items.length) % items.length : 0));
          return true;
        }
        if (event.key === 'Enter' && items.length) {
          event.preventDefault();
          const it = items[selected];
          if (it) command(it);
          return true;
        }
        return false;
      },
    }));

    if (!items.length) {
      return (
        <div
          data-mention-composer-dropdown
          className="bg-popover text-muted-foreground rounded-lg border px-3 py-2 text-sm shadow-md"
        >
          No matches
        </div>
      );
    }

    return (
      <div
        data-mention-composer-dropdown
        className="bg-popover max-h-[220px] min-w-[200px] overflow-auto rounded-lg border py-1 shadow-md"
      >
        {items.map((item, idx) => (
          <button
            key={item.id}
            type="button"
            className={cn(
              'hover:bg-accent block w-full px-3 py-1.5 text-left text-sm',
              idx === selected && 'bg-accent',
            )}
            onClick={() => command(item)}
          >
            {item.label}
          </button>
        ))}
      </div>
    );
  },
);

MentionList.displayName = 'MentionList';
