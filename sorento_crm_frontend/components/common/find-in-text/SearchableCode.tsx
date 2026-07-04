'use client';

import { Fragment, useEffect, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils';
import { FindBar, isFindChord } from './FindBar';
import { useFindController } from './useFindController';

/**
 * Read-only monospace text panel with a built-in find widget (Cmd/Ctrl+F when
 * focused). Matches are highlighted inline; the active match is emphasised and
 * scrolled into view. Used for the trace inspector's input/output JSON.
 */
export function SearchableCode({
  text,
  className,
  ariaLabel,
  'data-testid': dataTestId,
}: {
  text: string;
  className?: string;
  ariaLabel?: string;
  'data-testid'?: string;
}) {
  const find = useFindController(text);
  const { open, matches, activeIndex, openFind, close } = find;
  const activeRef = useRef<HTMLElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView?.({ block: 'center', behavior: 'smooth' });
  }, [activeIndex, matches.length]);

  const segments = useMemo(() => {
    if (matches.length === 0) return [{ text, match: -1 }];
    const out: { text: string; match: number }[] = [];
    let cursor = 0;
    matches.forEach((m, i) => {
      if (m.start > cursor) out.push({ text: text.slice(cursor, m.start), match: -1 });
      out.push({ text: text.slice(m.start, m.end), match: i });
      cursor = m.end;
    });
    if (cursor < text.length) out.push({ text: text.slice(cursor), match: -1 });
    return out;
  }, [text, matches]);

  return (
    <div
      className="relative"
      tabIndex={0}
      role="textbox"
      aria-readonly="true"
      aria-label={ariaLabel}
      data-testid={dataTestId}
      onKeyDown={(e) => {
        if (isFindChord(e)) {
          e.preventDefault();
          openFind();
        } else if (e.key === 'Escape' && open) {
          e.preventDefault();
          close();
        }
      }}
    >
      <FindBar controller={find} />
      <pre
        className={cn(
          'max-h-[420px] overflow-auto rounded-md border bg-muted/30 p-3 text-xs whitespace-pre-wrap break-words outline-none',
          className,
        )}
      >
        {segments.map((seg, i) =>
          seg.match === -1 ? (
            <Fragment key={i}>{seg.text}</Fragment>
          ) : (
            <mark
              key={i}
              ref={seg.match === activeIndex ? activeRef : undefined}
              className={cn(
                'rounded-sm',
                seg.match === activeIndex
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-warning/40 text-foreground',
              )}
            >
              {seg.text}
            </mark>
          ),
        )}
      </pre>
    </div>
  );
}
