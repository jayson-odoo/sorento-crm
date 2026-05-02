'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

export interface AsyncComboboxProps<T> {
  value: string;
  onChange: (value: string, item?: T) => void;
  fetchOptions: (q: string) => Promise<T[]>;
  optionValue: (o: T) => string;
  optionLabel: (o: T) => string;
  optionMeta?: (o: T) => string;
  placeholder?: string;
  disabled?: boolean;
  allowFreeText?: boolean;
  id?: string;
  /**
   * When true, renders the input as an auto-growing `<textarea>` so long
   * values wrap onto multiple lines instead of scrolling horizontally. The
   * search dropdown still works; pressing Enter while a result is highlighted
   * commits the selection (no newline inserted).
   */
  multiline?: boolean;
}

/**
 * Searchable single-select dropdown with free-text fallback.
 * - Debounced 300ms search-on-input.
 * - Keyboard: ArrowUp/ArrowDown/Enter/Escape.
 * - When `allowFreeText` (default true), blurring keeps the typed value
 *   as free-text if no option is selected.
 */
export function AsyncCombobox<T>({
  value,
  onChange,
  fetchOptions,
  optionValue,
  optionLabel,
  optionMeta,
  placeholder,
  disabled,
  allowFreeText = true,
  id,
  multiline,
}: AsyncComboboxProps<T>) {
  const [text, setText] = useState(value);
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<T[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastQueryRef = useRef<string>('');

  // Keep input in sync if parent changes value externally
  useEffect(() => {
    setText(value);
  }, [value]);

  const runFetch = useCallback(
    async (q: string) => {
      lastQueryRef.current = q;
      setLoading(true);
      try {
        const items = await fetchOptions(q);
        // Drop stale results
        if (lastQueryRef.current !== q) return;
        setOptions(items);
        setActiveIndex(items.length > 0 ? 0 : -1);
      } catch {
        if (lastQueryRef.current !== q) return;
        setOptions([]);
        setActiveIndex(-1);
      } finally {
        if (lastQueryRef.current === q) setLoading(false);
      }
    },
    [fetchOptions],
  );

  // Debounced fetch on text changes while open
  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      void runFetch(text);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [text, open, runFetch]);

  // Click-outside to close
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const commitSelection = (item: T) => {
    const v = optionValue(item);
    setText(v);
    setOpen(false);
    onChange(v, item);
  };

  const handleKeyDown = (
    e: React.KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((idx) => (options.length === 0 ? -1 : (idx + 1) % options.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      setActiveIndex((idx) =>
        options.length === 0 ? -1 : (idx - 1 + options.length) % options.length,
      );
    } else if (e.key === 'Enter') {
      // In multiline mode allow Enter to insert a newline UNLESS the user is
      // actively picking from the dropdown (activeIndex is highlighted).
      if (open && activeIndex >= 0 && activeIndex < options.length) {
        e.preventDefault();
        commitSelection(options[activeIndex]);
      } else if (!multiline && allowFreeText) {
        e.preventDefault();
        onChange(text);
        setOpen(false);
      }
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault();
        setOpen(false);
      }
    }
  };

  const handleBlur = () => {
    // Defer so option clicks fire first
    setTimeout(() => {
      if (!containerRef.current) return;
      if (containerRef.current.contains(document.activeElement)) return;
      setOpen(false);
      if (allowFreeText && text !== value) {
        onChange(text);
      }
    }, 150);
  };

  // Auto-grow the textarea to fit its content so wrapped values are fully
  // visible without scrolling.
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    if (!multiline) return;
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [text, multiline]);

  return (
    <div ref={containerRef} className="relative">
      {multiline ? (
        <Textarea
          ref={textareaRef}
          id={id}
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          rows={2}
          onChange={(e) => {
            setText(e.target.value);
            if (!open) setOpen(true);
          }}
          onFocus={() => {
            if (!open && !disabled) {
              setOpen(true);
              void runFetch(text);
            }
          }}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          autoComplete="off"
          className="resize-none overflow-hidden"
        />
      ) : (
        <Input
          id={id}
          type="text"
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(e) => {
            setText(e.target.value);
            if (!open) setOpen(true);
          }}
          onFocus={() => {
            if (!open && !disabled) {
              setOpen(true);
              void runFetch(text);
            }
          }}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          autoComplete="off"
        />
      )}
      {open && !disabled && (
        <div
          className="absolute z-50 mt-1 left-0 right-0 max-h-[200px] overflow-auto border rounded-md bg-background shadow"
          role="listbox"
        >
          {loading && (
            <div className="px-3 py-2 text-sm text-muted-foreground">Searching...</div>
          )}
          {!loading && options.length === 0 && (
            <div className="px-3 py-2 text-sm text-muted-foreground">No matches</div>
          )}
          {!loading &&
            options.map((opt, i) => {
              const v = optionValue(opt);
              const label = optionLabel(opt);
              const meta = optionMeta?.(opt);
              const isActive = i === activeIndex;
              return (
                <button
                  type="button"
                  key={`${v}-${i}`}
                  role="option"
                  aria-selected={isActive}
                  className={
                    'block w-full text-left px-3 py-2 text-sm transition ' +
                    (isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/60')
                  }
                  onMouseEnter={() => setActiveIndex(i)}
                  onMouseDown={(e) => {
                    // Prevent input blur before click handler runs
                    e.preventDefault();
                  }}
                  onClick={() => commitSelection(opt)}
                >
                  <div className="font-medium truncate">{label}</div>
                  {meta && (
                    <div className="text-xs text-muted-foreground truncate">{meta}</div>
                  )}
                </button>
              );
            })}
        </div>
      )}
    </div>
  );
}
