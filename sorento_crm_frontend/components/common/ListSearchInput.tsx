'use client';

import {
  useLayoutEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type KeyboardEvent,
} from 'react';
import { LoaderCircle, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { addSearchChips, MAX_SEARCH_CHIPS, splitPastedSearch } from '@/lib/searchChips';
import { cn } from '@/lib/utils';

export interface ListSearchInputProps {
  /** Only where a visible `<Label htmlFor>` names the box. */
  id?: string;
  /** Kept for the boxes an existing spec already drives by test id. */
  'data-testid'?: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  /** From `useDebouncedSearch`. The leading icon spins while the box is ahead of the query. */
  isSettling?: boolean;
  /** Called on Enter, for a list that wants to skip the wait. */
  onSubmit?: () => void;
  className?: string;
  /**
   * Extra classes on the `<Input>` itself, additive to the shared
   * `ps-9 pe-9 w-full` (M6-06). For the one caller whose search box is the
   * page's primary control rather than a toolbar filter (the portal landing
   * page) and needs a size the shared 13px default under-serves.
   */
  inputClassName?: string;
  'aria-label'?: string;
  /** `search` gives the box the searchbox role; omitted keeps the plain text input. */
  type?: 'search';
  /**
   * A one-line hint on the box itself, for the single thing about THIS search a
   * reader would otherwise get wrong (the fulfilment board: a product match
   * lists the whole order). A hint, not a paragraph teaching the feature.
   */
  title?: string;
  /** Search chips (SEARCH-CHIPS). Chips mode is on when `onChipsChange` is passed. */
  chips?: string[];
  onChipsChange?: (next: string[]) => void;
}

/**
 * The search box every list draws, drawn once (S7-02).
 *
 * The block itself (relative wrapper, leading magnifier, trailing clear) was
 * copied into two dozen list toolbars; what none of the copies had was the
 * settling indicator, and that is the point of putting it here. While
 * `isSettling` the magnifier becomes a spinner IN PLACE: it occupies the same
 * 16px, so the field does not reflow on every keystroke, and the reader gets the
 * one thing the old box withheld - that the rows behind it are about to change.
 *
 * Never disabled while a query is in flight. Each keystroke changes the query
 * key, so the list is pending for most of the typing, and disabling the field on
 * that flip makes the browser blur it and drop the rest of the word.
 */
export function ListSearchInput(props: ListSearchInputProps) {
  if (props.onChipsChange) {
    return <ChipsSearchInput {...props} onChipsChange={props.onChipsChange} />;
  }
  return <PlainSearchInput {...props} />;
}

function PlainSearchInput({
  id,
  'data-testid': testId,
  value,
  onChange,
  placeholder = 'Search...',
  isSettling = false,
  onSubmit,
  className,
  inputClassName,
  'aria-label': ariaLabel,
  type,
  title,
}: ListSearchInputProps) {
  return (
    <div className={cn('relative', className ?? 'w-full md:w-64')}>
      {isSettling ? (
        <LoaderCircle
          className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2 animate-spin"
          aria-hidden
        />
      ) : (
        <Search
          className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2"
          aria-hidden
        />
      )}
      <Input
        id={id}
        type={type}
        data-testid={testId}
        placeholder={placeholder}
        aria-label={ariaLabel ?? placeholder}
        title={title}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onSubmit) {
            e.preventDefault();
            onSubmit();
          }
        }}
        className={cn('ps-9 pe-9 w-full', inputClassName)}
      />
      {/* Announced politely so a screen reader is told the wait, not shown a spinner. */}
      <span className="sr-only" role="status" aria-live="polite">
        {isSettling ? 'Searching' : ''}
      </span>
      {value && (
        <Button
          mode="icon"
          variant="dim"
          type="button"
          aria-label="Clear search"
          title="Clear search"
          className="absolute end-1.5 top-1/2 -translate-y-1/2 h-6 w-6"
          onClick={() => onChange('')}
        >
          <X />
        </Button>
      )}
    </div>
  );
}

/** Width the typed text keeps beside the chips on the folded line. */
const MIN_TEXT_WIDTH = 56;
/** Width kept for the "+N" chip before it has been measured. */
const MORE_CHIP_WIDTH = 36;
const CHIP_GAP = 4;

/**
 * Chips mode: each Enter or comma makes a chip; paste splits (`splitPastedSearch`). Folded,
 * the chips sit on one line and the rest collapse into "+N"; focused, the box opens downward
 * over the rows and shows every chip, without moving the toolbar.
 */
function ChipsSearchInput({
  id,
  'data-testid': testId,
  value,
  onChange,
  placeholder = 'Search...',
  isSettling = false,
  onSubmit,
  className,
  inputClassName,
  'aria-label': ariaLabel,
  type,
  title,
  chips = [],
  onChipsChange,
}: ListSearchInputProps & { onChipsChange: (next: string[]) => void }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const chipRefs = useRef<Array<HTMLSpanElement | null>>([]);
  const moreRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [capped, setCapped] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [fit, setFit] = useState(chips.length);
  const [boxWidth, setBoxWidth] = useState(0);

  useLayoutEffect(() => {
    const box = boxRef.current;
    if (!box || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => setBoxWidth(box.clientWidth));
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  // How many chips fit on the folded line, leaving room for "+N" and the text.
  useLayoutEffect(() => {
    const box = boxRef.current;
    if (open || !box || box.clientWidth === 0) {
      setFit(chips.length);
      return;
    }
    const style = window.getComputedStyle(box);
    const room =
      box.clientWidth -
      (parseFloat(style.paddingLeft) || 0) -
      (parseFloat(style.paddingRight) || 0) -
      MIN_TEXT_WIDTH;
    const more = (moreRef.current?.offsetWidth || MORE_CHIP_WIDTH) + CHIP_GAP;
    let used = 0;
    let count = 0;
    for (let i = 0; i < chips.length; i += 1) {
      const width = (chipRefs.current[i]?.offsetWidth ?? 0) + CHIP_GAP;
      const tail = i < chips.length - 1 ? more : 0;
      if (used + width + tail > room) break;
      used += width;
      count += 1;
    }
    setFit(count);
  }, [chips, open, boxWidth]);

  const hidden = open ? 0 : chips.length - fit;

  const setChips = (next: string[], nextCapped = false) => {
    setCapped(nextCapped);
    setActive(null);
    onChipsChange(next);
  };

  const add = (incoming: string[]) => {
    const out = addSearchChips(chips, incoming, MAX_SEARCH_CHIPS);
    if (out.chips.length !== chips.length || out.capped) setChips(out.chips, out.capped);
  };

  const remove = (index: number) => {
    setChips(chips.filter((_, i) => i !== index));
    inputRef.current?.focus();
  };

  const clearAll = () => {
    setChips([]);
    onChange('');
    inputRef.current?.focus();
  };

  const handleChange = (next: string) => {
    if (!next.includes(',')) {
      onChange(next);
      return;
    }
    const pieces = next.split(',');
    const rest = pieces.pop() ?? '';
    add(pieces);
    onChange(rest);
  };

  const handlePaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const pasted = e.clipboardData.getData('text');
    if (!pasted) return;
    e.preventDefault();
    const input = e.currentTarget;
    const start = input.selectionStart ?? value.length;
    const end = input.selectionEnd ?? value.length;
    add(splitPastedSearch(value.slice(0, start) + pasted + value.slice(end)));
    onChange('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      add([value]);
      onChange('');
      onSubmit?.();
      return;
    }
    if (e.key === 'Escape') {
      inputRef.current?.blur();
      return;
    }
    if (value !== '' || chips.length === 0) return;
    if (e.key === 'Backspace') {
      e.preventDefault();
      remove(active ?? chips.length - 1);
    } else if (e.key === 'Delete' && active !== null) {
      e.preventDefault();
      remove(active);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      setActive((i) => (i === null ? chips.length - 1 : Math.max(0, i - 1)));
    } else if (e.key === 'ArrowRight' && active !== null) {
      e.preventDefault();
      setActive((i) => (i === null || i >= chips.length - 1 ? null : i + 1));
    }
  };

  const showClear = value !== '' || chips.length > 0;

  return (
    <div
      ref={rootRef}
      role="presentation"
      className={cn('relative h-8.5', className ?? 'w-full md:w-64')}
      onFocus={() => setOpen(true)}
      onBlur={(e) => {
        if (!rootRef.current?.contains(e.relatedTarget as Node | null)) {
          setOpen(false);
          setActive(null);
        }
      }}
    >
      <div
        ref={boxRef}
        role="presentation"
        onMouseDown={(e) => {
          if (e.target !== inputRef.current) {
            e.preventDefault();
            inputRef.current?.focus();
          }
        }}
        className={cn(
          'absolute inset-x-0 top-0 flex items-center gap-1 rounded-md border border-input bg-background ps-9 pe-9 text-[0.8125rem] shadow-xs shadow-black/5 transition-[color,box-shadow]',
          open
            ? 'z-20 min-h-8.5 flex-wrap border-ring py-1 ring-[3px] ring-ring/30 shadow-lg'
            : 'h-8.5 flex-nowrap overflow-hidden',
        )}
      >
        {isSettling ? (
          <LoaderCircle
            className="size-4 text-muted-foreground absolute start-3 top-[8px] animate-spin"
            aria-hidden
          />
        ) : (
          <Search className="size-4 text-muted-foreground absolute start-3 top-[8px]" aria-hidden />
        )}
        {chips.map((chip, index) => (
          <span
            key={chip}
            ref={(el) => {
              chipRefs.current[index] = el;
            }}
            title={chip}
            style={{ order: index < chips.length - hidden ? 0 : 2 }}
            className={cn(
              'inline-flex max-w-full shrink-0 items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs',
              !open && 'max-w-36',
              index >= chips.length - hidden && 'invisible',
              active === index && 'outline-2 outline-ring',
            )}
          >
            <span className="truncate">{chip}</span>
            <button
              type="button"
              tabIndex={-1}
              aria-label={`Remove ${chip}`}
              className="opacity-60 hover:opacity-100"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => remove(index)}
            >
              <X className="size-3" />
            </button>
          </span>
        ))}
        {hidden > 0 && (
          <span
            ref={moreRef}
            style={{ order: 1 }}
            title={chips.slice(chips.length - hidden).join(', ')}
            className="inline-flex shrink-0 items-center rounded bg-accent px-1.5 py-0.5 text-xs font-medium"
          >
            +{hidden}
          </span>
        )}
        <input
          ref={inputRef}
          id={id}
          type={type}
          data-testid={testId}
          placeholder={chips.length ? (open ? 'Add another...' : '') : placeholder}
          aria-label={ariaLabel ?? placeholder}
          title={title}
          value={value}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          style={{ order: 3 }}
          className={cn(
            'h-6 min-w-14 flex-1 bg-transparent text-foreground outline-none placeholder:text-muted-foreground/80 pointer-coarse:text-base',
            inputClassName,
          )}
        />
        {showClear && (
          <Button
            mode="icon"
            variant="dim"
            type="button"
            aria-label="Clear search"
            title="Clear search"
            className="absolute end-1.5 top-[4px] h-6 w-6"
            onMouseDown={(e) => e.preventDefault()}
            onClick={clearAll}
          >
            <X />
          </Button>
        )}
        {open && chips.length > 0 && (
          <div
            style={{ order: 4 }}
            className="flex basis-full items-center justify-between border-t border-border pt-1 text-xs text-muted-foreground"
          >
            <span>
              {chips.length} values{capped ? `, first ${MAX_SEARCH_CHIPS} kept` : ''}
            </span>
            <button
              type="button"
              className="font-medium text-foreground hover:underline"
              onMouseDown={(e) => e.preventDefault()}
              onClick={clearAll}
            >
              Clear
            </button>
          </div>
        )}
      </div>
      <span className="sr-only" role="status" aria-live="polite">
        {isSettling ? 'Searching' : ''}
      </span>
    </div>
  );
}
