'use client';

import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
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
import { useUpsertTextGlossary } from '../hooks/useTextGlossary';
import type { TextGlossaryEntry } from '../types/textGlossary.types';

/**
 * Add / edit one word (R2, AC-E4). One write path behind both: a PUT upserts on
 * `source_text`, so editing an existing row locks that field - changing it would mint a
 * different glossary entry rather than correct this one. Locale is not shown (R9);
 * every row this dialog writes is `en`.
 */
export function TextGlossaryFormDialog({
  open,
  onOpenChange,
  entry,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  /** Present = editing that row's translation. Absent = Add. */
  entry?: TextGlossaryEntry | null;
}) {
  const upsert = useUpsertTextGlossary();
  const [sourceText, setSourceText] = useState('');
  const [translation, setTranslation] = useState('');

  useEffect(() => {
    if (open) {
      setSourceText(entry?.source_text ?? '');
      setTranslation(entry?.translation ?? '');
    }
  }, [open, entry]);

  const canSave = sourceText.trim().length > 0 && translation.trim().length > 0;

  const submit = async () => {
    if (!canSave) return;
    try {
      await upsert.mutateAsync({ source_text: sourceText.trim(), translation: translation.trim() });
      onOpenChange(false);
    } catch {
      // The mutation hook already toasts the message.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{entry ? 'Edit translation' : 'Add glossary entry'}</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div>
            <Label htmlFor="text-glossary-source" className="mb-1 block text-xs">
              Source text
            </Label>
            <Input
              id="text-glossary-source"
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="e.g. 连体马桶"
              disabled={!!entry}
            />
          </div>
          <div>
            <Label htmlFor="text-glossary-translation" className="mb-1 block text-xs">
              English
            </Label>
            <Input
              id="text-glossary-translation"
              value={translation}
              onChange={(e) => setTranslation(e.target.value)}
              placeholder="e.g. One-piece toilet"
            />
          </div>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={!canSave || upsert.isPending}>
            {upsert.isPending ? <LoaderCircle className="size-4 animate-spin" /> : null}
            {entry ? 'Save' : 'Add entry'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default TextGlossaryFormDialog;
