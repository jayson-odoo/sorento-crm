'use client';

import { useEffect, useRef, useState } from 'react';
import { ArrowUpDown, MoreHorizontal } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { DeferredCountdown } from '@/components/common/DeferredActionButton';

const REMOVE_WINDOW_SECONDS = 5;

export interface WordsDataGridProps {
  /** e.g. "Other names for this specification" - the field label sits ABOVE this. */
  words: string[];
  mode: 'view' | 'edit';
  onAdd: (word: string) => void;
  onRename: (oldWord: string, newWord: string) => void;
  onRemove: (word: string) => void;
  emptyMessage?: string;
  addPlaceholder?: string;
}

/**
 * Every list of words is a data grid (D13, owner ruling 27 Sep 2026: "this should
 * be tabulated with data grid"). One row per word, sortable, edited in place,
 * `+ Add a word` at the foot, a deferred 5s remove per row - the same shape D13
 * asks be reused everywhere a spec screen lists words (Other names for this
 * specification here; the Choices and words grid uses the same idea for a comma
 * list of words per choice, which is a plain cell rather than a nested grid).
 */
export function WordsDataGrid({
  words,
  mode,
  onAdd,
  onRename,
  onRemove,
  emptyMessage = 'No words yet.',
  addPlaceholder = 'a word',
}: WordsDataGridProps) {
  const [sortDesc, setSortDesc] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newWord, setNewWord] = useState('');
  const [removals, setRemovals] = useState<Record<string, { commitAt: number; timer: ReturnType<typeof setTimeout> }>>(
    {},
  );
  const wordsRef = useRef(words);
  wordsRef.current = words;
  const onRemoveRef = useRef(onRemove);
  onRemoveRef.current = onRemove;

  useEffect(() => {
    return () => {
      Object.values(removals).forEach((r) => clearTimeout(r.timer));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sorted = [...words].sort((a, b) => (sortDesc ? b.localeCompare(a) : a.localeCompare(b)));

  const startRemoval = (word: string) => {
    const commitAt = Date.now() + REMOVE_WINDOW_SECONDS * 1000;
    const timer = setTimeout(() => {
      onRemoveRef.current(word);
      setRemovals((current) => {
        const next = { ...current };
        delete next[word];
        return next;
      });
    }, REMOVE_WINDOW_SECONDS * 1000);
    setRemovals((current) => ({ ...current, [word]: { commitAt, timer } }));
  };

  const cancelRemoval = (word: string) => {
    setRemovals((current) => {
      const removal = current[word];
      if (removal) clearTimeout(removal.timer);
      const next = { ...current };
      delete next[word];
      return next;
    });
  };

  const commitAdd = () => {
    const trimmed = newWord.trim();
    if (trimmed) onAdd(trimmed);
    setNewWord('');
    setAdding(false);
  };

  return (
    <div className="overflow-hidden rounded-md border">
      <div className="overflow-x-auto">
      <table className="w-full table-fixed text-sm">
        <colgroup>
          <col style={{ width: '80%' }} />
          <col style={{ width: '20%' }} />
        </colgroup>
        <thead>
          <tr className="border-b bg-muted/40">
            <th className="p-2 text-left font-medium">
              <button
                type="button"
                aria-label="Sort by word"
                className="inline-flex items-center gap-1 hover:underline"
                onClick={() => setSortDesc((v) => !v)}
              >
                Word <ArrowUpDown className="size-3" aria-hidden />
              </button>
            </th>
            <th className="p-2" aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && !adding && (
            <tr>
              <td colSpan={2} className="p-3 text-center text-muted-foreground">
                {emptyMessage}
              </td>
            </tr>
          )}
          {sorted.map((word) => {
            const removal = removals[word];
            if (removal) {
              return (
                <tr key={word} className="border-b last:border-0">
                  <td className="p-2" colSpan={2}>
                    <DeferredCountdown
                      pending={{
                        id: word,
                        action_key: 'spec_word.remove',
                        entity_type: 'spec_word',
                        entity_id: word,
                        commit_at: new Date(removal.commitAt).toISOString(),
                        window_seconds: REMOVE_WINDOW_SECONDS,
                      }}
                      verb="Removing"
                      subject={word}
                      onCancel={() => cancelRemoval(word)}
                    />
                  </td>
                </tr>
              );
            }
            return (
              <tr key={word} className="border-b last:border-0">
                <td className="p-2">
                  {mode === 'edit' && editing === word ? (
                    <Input
                      autoFocus
                      defaultValue={word}
                      className="h-8"
                      onBlur={(e) => {
                        const next = e.target.value.trim();
                        if (next && next !== word) onRename(word, next);
                        setEditing(null);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') e.currentTarget.blur();
                        if (e.key === 'Escape') setEditing(null);
                      }}
                    />
                  ) : (
                    <button
                      type="button"
                      disabled={mode !== 'edit'}
                      onClick={() => mode === 'edit' && setEditing(word)}
                      className={`truncate text-left ${mode === 'edit' ? 'hover:underline' : ''}`}
                    >
                      {word}
                    </button>
                  )}
                </td>
                <td className="p-2 text-right">
                  {mode === 'edit' && (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          aria-label={`${word} actions`}
                          className="size-7 text-muted-foreground"
                        >
                          <MoreHorizontal className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing(word)}>Edit</DropdownMenuItem>
                        <DropdownMenuItem variant="destructive" onClick={() => startRemoval(word)}>
                          Remove
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  )}
                </td>
              </tr>
            );
          })}
          {mode === 'edit' && (
            <tr>
              <td colSpan={2} className="p-2">
                {adding ? (
                  <Input
                    autoFocus
                    value={newWord}
                    placeholder={addPlaceholder}
                    className="h-8"
                    onChange={(e) => setNewWord(e.target.value)}
                    onBlur={commitAdd}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') commitAdd();
                      if (e.key === 'Escape') {
                        setNewWord('');
                        setAdding(false);
                      }
                    }}
                  />
                ) : (
                  <button
                    type="button"
                    className="text-primary hover:underline"
                    onClick={() => setAdding(true)}
                  >
                    + Add a word
                  </button>
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}

export default WordsDataGrid;
