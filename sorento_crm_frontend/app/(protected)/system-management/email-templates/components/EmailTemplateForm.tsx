'use client';

import { useEffect, useMemo, useState } from 'react';
import type { Editor } from '@tiptap/react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { useCreateEmailTemplate, useTemplateVariableCatalog } from '../hooks/useEmailTemplates';
import type { EmailTemplate } from '../types/emailTemplate.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved?: (created: EmailTemplate) => void;
}

/**
 * Create-only (S8): editing a template now happens in place on its own
 * detail page (view/edit are the same layout there), so this dialog no
 * longer takes a `template` prop to edit. Block-level authoring (order,
 * per-block settings) also lives on the detail page after creation.
 */
export default function EmailTemplateForm({ open, onOpenChange, onSaved }: Props) {
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [subject, setSubject] = useState('');
  const [preheader, setPreheader] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [bodyText, setBodyText] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [bodyEditor, setBodyEditor] = useState<Editor | null>(null);

  const variables = useTemplateVariableCatalog();
  const createMut = useCreateEmailTemplate();
  const saving = createMut.isPending;

  useEffect(() => {
    if (!open) return;
    setCode('');
    setName('');
    setDescription('');
    setSubject('');
    setPreheader('');
    setBodyHtml('');
    setBodyText('');
    setIsActive(true);
  }, [open]);

  const variableList = useMemo(() => variables.data?.variables ?? [], [variables.data]);

  function insertVariable(key: string) {
    const token = `{{ ${key} }}`;
    if (bodyEditor) {
      bodyEditor.chain().focus().insertContent(token).run();
      return;
    }
    setBodyHtml((prev) => `${prev}${token}`);
  }

  async function onSubmit() {
    if (!code.trim() || !name.trim() || !subject.trim() || !bodyHtml.trim()) {
      toast.error('Code, name, subject and body are required');
      return;
    }
    const payload = {
      code: code.trim(),
      name: name.trim(),
      description: description.trim() || null,
      subject: subject.trim(),
      preheader: preheader.trim() || null,
      body_html: bodyHtml,
      body_text: bodyText.trim() ? bodyText : null,
      is_active: isActive,
    };
    try {
      const created = await createMut.mutateAsync(payload);
      toast.success('Email template created');
      onSaved?.(created);
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message || 'Save failed');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>New email template</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="md:col-span-2 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="et-code">Code</Label>
                <Input
                  id="et-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  placeholder="promo-expiry-reminder"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="et-name">Name</Label>
                <Input
                  id="et-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Promotion expiry reminder"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="et-description">Description</Label>
              <Input
                id="et-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What this template is for"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="et-subject">Subject (Jinja2)</Label>
              <Input
                id="et-subject"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Promo {{ promotion.code }} expires on {{ promotion.end_date }}"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="et-preheader">Preheader</Label>
              <Input
                id="et-preheader"
                value={preheader}
                onChange={(e) => setPreheader(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label>Body</Label>
              <RichTextEditor
                value={bodyHtml}
                onChange={setBodyHtml}
                onEditorReady={setBodyEditor}
                minHeight={260}
                placeholder="Compose the email - use the Variables panel to insert {{ promotion.code }} etc."
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="et-body-text">Body plain text (optional - auto-derived from HTML if empty)</Label>
              <Textarea
                id="et-body-text"
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                rows={4}
                className="font-mono text-sm"
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch id="et-active" checked={isActive} onCheckedChange={setIsActive} />
              <Label htmlFor="et-active">Active</Label>
            </div>
          </div>

          <div className="space-y-2 rounded-md border p-3">
            <p className="text-sm font-medium">Variables</p>
            <p className="text-xs text-muted-foreground">
              Click to insert a Jinja2 placeholder at your cursor position.
            </p>
            <div className="flex flex-col gap-1 max-h-[400px] overflow-y-auto">
              {variableList.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  className="text-left text-xs hover:bg-muted rounded px-2 py-1 font-mono"
                  onClick={() => insertVariable(v.key)}
                  title={v.label}
                >
                  {`{{ ${v.key} }}`}
                </button>
              ))}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={saving}>
            {saving ? 'Saving…' : 'Create template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
