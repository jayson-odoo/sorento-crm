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
import {
  useCreateEmailTemplate,
  useTemplateVariableCatalog,
  useUpdateEmailTemplate,
} from '../hooks/useEmailTemplates';
import type { EmailTemplate } from '../types/emailTemplate.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template?: EmailTemplate | null;
  onSaved?: () => void;
}

export default function EmailTemplateForm({ open, onOpenChange, template, onSaved }: Props) {
  const isEdit = !!template;
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [subject, setSubject] = useState('');
  const [bodyHtml, setBodyHtml] = useState('');
  const [bodyText, setBodyText] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [bodyEditor, setBodyEditor] = useState<Editor | null>(null);

  const variables = useTemplateVariableCatalog();
  const createMut = useCreateEmailTemplate();
  const updateMut = useUpdateEmailTemplate(template?.id ?? '');
  const saving = createMut.isPending || updateMut.isPending;

  useEffect(() => {
    if (!open) return;
    if (template) {
      setCode(template.code);
      setName(template.name);
      setDescription(template.description ?? '');
      setSubject(template.subject);
      setBodyHtml(template.body_html);
      setBodyText(template.body_text ?? '');
      setIsActive(template.is_active);
    } else {
      setCode('');
      setName('');
      setDescription('');
      setSubject('');
      setBodyHtml('');
      setBodyText('');
      setIsActive(true);
    }
  }, [open, template]);

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
      body_html: bodyHtml,
      body_text: bodyText.trim() ? bodyText : null,
      is_active: isActive,
    };
    try {
      if (isEdit && template) {
        await updateMut.mutateAsync(payload);
        toast.success('Email template updated');
      } else {
        await createMut.mutateAsync(payload);
        toast.success('Email template created');
      }
      onSaved?.();
      onOpenChange(false);
    } catch (err) {
      toast.error((err as Error).message || 'Save failed');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit email template' : 'New email template'}</DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="md:col-span-2 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="et-code">Code</Label>
                <Input
                  id="et-code"
                  value={code}
                  disabled={isEdit}
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
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
