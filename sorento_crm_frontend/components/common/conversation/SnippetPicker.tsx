'use client';

/**
 * The composer's "/" snippet picker (UAC AC-L4).
 *
 * Presentational on purpose: the composer owns the "/" fragment, the keyboard
 * and the insertion, exactly as `InternalCommentComposer` owns its @mention
 * typeahead. This file owns only the list, so the two typeaheads look and
 * behave the same wherever they are mounted.
 *
 * What lands in the input is `resolved_body` - the backend already substituted
 * the ticket's context - so the preview a person reads here and the text the
 * contact receives cannot drift apart.
 */

import { Loader2 } from 'lucide-react';

import type { MessageSnippetOption } from '@/app/(protected)/sla-management/message-snippets/types/messageSnippet.types';

interface SnippetPickerProps {
  items: MessageSnippetOption[];
  isLoading: boolean;
  error?: string | null;
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
  onPick: (snippet: MessageSnippetOption) => void;
}

/** Client-side narrowing as the user keeps typing after the "/". */
export function filterSnippets(
  items: MessageSnippetOption[],
  query: string,
): MessageSnippetOption[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return items;
  return items.filter(
    (item) =>
      item.name.toLowerCase().includes(needle) ||
      (item.shortcut ?? '').toLowerCase().includes(needle),
  );
}

/**
 * The "/..." fragment being typed, or null.
 *
 * Only a "/" at the very START of the input opens the picker. A slash anywhere
 * else is ordinary text a person is writing (a date, a URL, "and/or"), and
 * opening a dropdown over it would fight the typist.
 */
export function activeSlashFragment(
  text: string,
  caret: number,
): { start: number; query: string } | null {
  if (!text.startsWith('/')) return null;
  if (caret < 1) return null;
  const query = text.slice(1, caret);
  if (/\s{2,}|\n/.test(query)) return null;
  if (query.length > 40) return null;
  return { start: 0, query };
}

export default function SnippetPicker({
  items,
  isLoading,
  error,
  activeIndex,
  onActiveIndexChange,
  onPick,
}: SnippetPickerProps) {
  return (
    <div
      data-testid="snippet-picker"
      role="listbox"
      aria-label="Snippets"
      className="absolute inset-x-0 bottom-full z-20 mb-1 max-h-56 overflow-y-auto rounded-md border bg-popover p-1 shadow-md"
    >
      {isLoading && items.length === 0 && (
        <div className="flex items-center gap-2 px-2 py-1.5 text-xs text-muted-foreground">
          <Loader2 className="size-3.5 animate-spin" />
          Loading snippets
        </div>
      )}

      {!isLoading && error && (
        <div className="px-2 py-1.5 text-xs text-destructive" data-testid="snippet-picker-error">
          {error}
        </div>
      )}

      {!isLoading && !error && items.length === 0 && (
        <div className="px-2 py-1.5 text-xs text-muted-foreground" data-testid="snippet-picker-empty">
          No snippets match.
        </div>
      )}

      {items.map((snippet, index) => (
        <button
          key={snippet.id}
          type="button"
          role="option"
          aria-selected={index === activeIndex}
          data-testid="snippet-option"
          // onMouseDown, not onClick: the textarea's blur would otherwise close
          // the picker before the click lands.
          onMouseDown={(event) => {
            event.preventDefault();
            onPick(snippet);
          }}
          onMouseEnter={() => onActiveIndexChange(index)}
          className={`block w-full rounded px-2 py-1.5 text-left hover:bg-accent ${
            index === activeIndex ? 'bg-accent' : ''
          }`}
        >
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-medium" title={snippet.name}>
              {snippet.name}
            </span>
            {snippet.shortcut && (
              <span className="shrink-0 font-mono text-2xs text-muted-foreground">
                /{snippet.shortcut}
              </span>
            )}
          </span>
          <span
            className="mt-0.5 block truncate text-xs text-muted-foreground"
            title={snippet.resolved_body}
          >
            {snippet.resolved_body}
          </span>
        </button>
      ))}
    </div>
  );
}
