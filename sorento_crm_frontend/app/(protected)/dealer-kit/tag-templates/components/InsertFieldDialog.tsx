'use client';

/**
 * Put a `{{merge field}}` into a text layer's content (D59).
 *
 * The content is edited HERE rather than in the Inspector's textarea while a
 * list sits beside it, for one reason: a field has to land where the cursor is.
 * A designer writing "800 x 500 mm in stainless steel" is inserting into the
 * middle of a sentence, and a dialog that could only append would be a list of
 * tokens to copy by hand.
 *
 * The preview line under the list is the other half. A token that will resolve
 * to nothing looks exactly like one that will resolve fine, right up until
 * somebody prints the tag, so the dialog renders the content against whatever
 * the layer is actually previewing with and says so plainly when that is
 * nothing.
 */

import { useEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import type { MergeField, MergeFieldGroup, SpecKeyOption } from '@/lib/dealer-kit/merge-fields';
import { mergeFieldCatalog, renderMergeFields } from '@/lib/dealer-kit/merge-fields';
import type { TagBindingData } from '@/lib/dealer-kit/tag-template-types';

const GROUP_ORDER: MergeFieldGroup[] = ['Product', 'Specs', 'Set', 'Line'];

interface InsertFieldDialogProps {
  open: boolean;
  /** The layer's content as it stands. */
  value: string;
  /** What this layer draws against right now: its preview, its binding, or the line. */
  data: TagBindingData | null;
  /** The spec vocabulary, so a new key appears with no code change (D58). */
  specKeys: SpecKeyOption[];
  onCancel: () => void;
  onDone: (content: string) => void;
}

export function InsertFieldDialog({
  open,
  value,
  data,
  specKeys,
  onCancel,
  onDone,
}: InsertFieldDialogProps) {
  const [content, setContent] = useState(value);
  const [query, setQuery] = useState('');
  const contentRef = useRef<HTMLTextAreaElement>(null);
  /** Where the caret was, so a click on the list does not lose it to the button. */
  const caret = useRef<[number, number]>([value.length, value.length]);

  // Re-seeded on every open rather than kept in step, so the dialog never
  // opens on content the layer no longer has.
  useEffect(() => {
    if (!open) return;
    setContent(value);
    setQuery('');
    caret.current = [value.length, value.length];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const catalog = useMemo(() => mergeFieldCatalog(specKeys), [specKeys]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return catalog;
    return catalog.filter(
      (field) =>
        field.label.toLowerCase().includes(needle) ||
        field.path.toLowerCase().includes(needle),
    );
  }, [catalog, query]);

  const grouped = useMemo(() => {
    return GROUP_ORDER.map((group) => ({
      group,
      fields: matches.filter((field) => field.group === group),
    })).filter((section) => section.fields.length > 0);
  }, [matches]);

  const rememberCaret = () => {
    const box = contentRef.current;
    if (!box) return;
    caret.current = [box.selectionStart ?? 0, box.selectionEnd ?? 0];
  };

  const insert = (field: MergeField) => {
    const [start, end] = caret.current;
    const next = content.slice(0, start) + field.token + content.slice(end);
    const after = start + field.token.length;
    caret.current = [after, after];
    setContent(next);
    // Put the caret back after the inserted token so a second insert lands
    // where the designer is looking, not back at the start.
    requestAnimationFrame(() => {
      const box = contentRef.current;
      if (!box) return;
      box.focus();
      box.setSelectionRange(after, after);
    });
  };

  const preview = data ? renderMergeFields(content, data, 'print') : null;

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Insert field</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <Label htmlFor="merge-field-content" className="text-xs text-muted-foreground">
              Content
            </Label>
            <textarea
              id="merge-field-content"
              ref={contentRef}
              className="min-h-[72px] w-full rounded-md border bg-background px-2 py-1 text-xs"
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                rememberCaret();
              }}
              onSelect={rememberCaret}
              onKeyUp={rememberCaret}
              onClick={rememberCaret}
            />
          </div>

          <Input
            placeholder="Search fields..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 text-xs"
          />

          <ScrollArea className="h-56 rounded-md border">
            <div className="flex flex-col p-1">
              {grouped.map((section) => (
                <div key={section.group}>
                  <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {section.group}
                  </div>
                  {section.fields.map((field) => (
                    <button
                      key={field.path}
                      type="button"
                      className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left text-xs hover:bg-accent"
                      onClick={() => insert(field)}
                    >
                      <span className="truncate" title={field.label}>
                        {field.label}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
                        {field.token}
                      </span>
                    </button>
                  ))}
                </div>
              ))}
              {grouped.length === 0 && (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                  No field matches that.
                </p>
              )}
            </div>
          </ScrollArea>

          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">Preview:</span>
            <span className="whitespace-pre-wrap rounded-md bg-muted px-2 py-1 text-xs">
              {preview ?? '(preview a product to see values)'}
            </span>
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button onClick={() => onDone(content)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
