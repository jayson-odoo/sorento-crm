'use client';

import { useEffect, useState } from 'react';

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
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

import {
  SNIPPET_VARIABLES,
  type MessageSnippet,
  type MessageSnippetFormData,
} from '../types/messageSnippet.types';

interface MessageSnippetFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Null = create. */
  snippet: MessageSnippet | null;
  onSubmit: (data: MessageSnippetFormData) => Promise<unknown>;
  isSubmitting: boolean;
}

const EMPTY: MessageSnippetFormData = {
  name: '',
  shortcut: '',
  body: '',
  is_active: true,
};

export default function MessageSnippetFormDialog({
  open,
  onOpenChange,
  snippet,
  onSubmit,
  isSubmitting,
}: MessageSnippetFormDialogProps) {
  const [form, setForm] = useState<MessageSnippetFormData>(EMPTY);
  const [errors, setErrors] = useState<{ name?: string; body?: string }>({});

  useEffect(() => {
    if (!open) return;
    setErrors({});
    setForm(
      snippet
        ? {
            name: snippet.name,
            shortcut: snippet.shortcut ?? '',
            body: snippet.body,
            is_active: snippet.is_active,
          }
        : EMPTY,
    );
  }, [open, snippet]);

  const submit = async () => {
    const next: { name?: string; body?: string } = {};
    if (!form.name.trim()) next.name = 'Give the snippet a name.';
    if (!form.body.trim()) next.body = 'A snippet needs some text.';
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    await onSubmit({
      name: form.name.trim(),
      shortcut: (form.shortcut || '').trim() || null,
      body: form.body,
      is_active: form.is_active,
    });
  };

  /** Drop a variable into the body at the caret (or at the end). */
  const insertToken = (token: string) => {
    setForm((prev) => ({
      ...prev,
      body: prev.body ? `${prev.body}${prev.body.endsWith(' ') ? '' : ' '}${token}` : token,
    }));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{snippet ? 'Edit snippet' : 'Add snippet'}</DialogTitle>
        </DialogHeader>

        <DialogBody className="space-y-4">
          <div>
            <Label className="mb-1 block" htmlFor="snippet-name">
              Name
            </Label>
            <Input
              id="snippet-name"
              value={form.name}
              placeholder="Stock check"
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
            />
            {errors.name && <p className="mt-1 text-xs text-destructive">{errors.name}</p>}
          </div>

          <div>
            <Label className="mb-1 block" htmlFor="snippet-shortcut">
              Shortcut
            </Label>
            <Input
              id="snippet-shortcut"
              value={form.shortcut ?? ''}
              placeholder="stock"
              onChange={(e) => setForm((p) => ({ ...p, shortcut: e.target.value }))}
            />
          </div>

          <div>
            <Label className="mb-1 block" htmlFor="snippet-body">
              Message
            </Label>
            <Textarea
              id="snippet-body"
              value={form.body}
              rows={6}
              placeholder="Hi $contact_name, we are checking stock and will come back to you shortly."
              onChange={(e) => setForm((p) => ({ ...p, body: e.target.value }))}
              className="resize-none"
            />
            {errors.body && <p className="mt-1 text-xs text-destructive">{errors.body}</p>}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {SNIPPET_VARIABLES.map((variable) => (
                <Button
                  key={variable.token}
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-7 font-mono text-xs"
                  title={variable.description}
                  onClick={() => insertToken(variable.token)}
                >
                  {variable.token}
                </Button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Switch
              id="snippet-active"
              checked={form.is_active}
              onCheckedChange={(checked) => setForm((p) => ({ ...p, is_active: checked }))}
            />
            <Label htmlFor="snippet-active">Available in the composer</Label>
          </div>
        </DialogBody>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button onClick={() => void submit()} disabled={isSubmitting}>
            {isSubmitting ? 'Saving…' : snippet ? 'Save changes' : 'Create snippet'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
