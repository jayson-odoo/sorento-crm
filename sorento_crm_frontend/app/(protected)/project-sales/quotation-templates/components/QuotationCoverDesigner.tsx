'use client';

import * as React from 'react';
import type { Editor } from '@tiptap/react';
import { GripVertical, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
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
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { RichTextEditor } from '@/components/ui/rich-text-editor';
import {
  Sortable,
  SortableItem,
  SortableItemHandle,
} from '@/components/ui/sortable';
import { Switch } from '@/components/ui/switch';
import { CoverPagePreview } from '@/components/quotation/CoverPagePreview';
import {
  COVER_MAX_LABEL,
  COVER_ROW_LABELS,
  defaultCoverDesign,
  type CoverDesign,
  type CoverDesignRow,
} from '@/lib/quotation-cover';
import {
  useCoverDesignPreview,
  useQuotationMergeFields,
  useQuotationTemplateMutations,
} from '../../_shared/hooks/useQuotationTemplates';
import type { QuotationTemplate } from '../../_shared/services/quotationTemplateService';

/** One rich-text field with an Insert field list of the backend's merge fields. */
function TextWithFields({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (html: string) => void;
}) {
  const fields = useQuotationMergeFields();
  const [editor, setEditor] = React.useState<Editor | null>(null);
  const [open, setOpen] = React.useState(false);

  function insert(placeholder: string) {
    setOpen(false);
    if (editor) {
      editor.chain().focus().insertContent(placeholder).run();
      return;
    }
    onChange(`${value}${placeholder}`);
  }

  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label>{label}</Label>
        <Popover open={open} onOpenChange={setOpen}>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
            >
              <Plus className="size-3.5" />
              Insert field
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align="end"
            className="max-h-64 w-64 overflow-y-auto p-1"
          >
            {(fields.data ?? []).map((field) => (
              <button
                key={field.token}
                type="button"
                className="block w-full min-w-0 truncate rounded px-2 py-1.5 text-left text-sm hover:bg-muted"
                title={field.placeholder}
                onClick={() => insert(field.placeholder)}
              >
                {field.label}
              </button>
            ))}
          </PopoverContent>
        </Popover>
      </div>
      <RichTextEditor
        value={value}
        onChange={onChange}
        placeholder={label}
        minHeight={120}
        onEditorReady={setEditor}
      />
    </div>
  );
}

/**
 * Create or edit one cover page design. The form sits beside a live preview of page 1 filled with
 * sample values, the same card the sign link and the quotation's Cover letter tab draw.
 */
export function QuotationCoverDesigner({
  template,
  onDone,
}: {
  template: QuotationTemplate | null;
  onDone: () => void;
}) {
  const { create, update } = useQuotationTemplateMutations('cover_page');
  const initial = template?.design ?? defaultCoverDesign();
  const [name, setName] = React.useState(template?.name ?? '');
  const [title, setTitle] = React.useState(initial.title);
  const [showLetterhead, setShowLetterhead] = React.useState(
    initial.show_letterhead,
  );
  const [rows, setRows] = React.useState<CoverDesignRow[]>(initial.rows);
  const [intro, setIntro] = React.useState(template?.body_html ?? '');
  const [closing, setClosing] = React.useState(initial.closing_html);
  const pending = create.isPending || update.isPending;

  const design: CoverDesign = {
    show_letterhead: showLetterhead,
    title,
    rows,
    closing_html: closing,
  };
  const preview = useCoverDesignPreview(design, intro);

  function patchRow(key: string, patch: Partial<CoverDesignRow>) {
    setRows((previous) =>
      previous.map((row) => (row.key === key ? { ...row, ...patch } : row)),
    );
  }

  async function save() {
    const body = { name: name.trim(), body_html: intro, design };
    try {
      if (template) {
        await update.mutateAsync({ id: template.id, body });
      } else {
        await create.mutateAsync(body);
      }
      onDone();
    } catch {
      // the mutation already toasted the refusal; keep the dialog open
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92dvh] w-full max-w-5xl overflow-hidden">
        <DialogHeader>
          <DialogTitle>
            {template ? `Edit ${template.name}` : 'Add a cover page design'}
          </DialogTitle>
        </DialogHeader>

        <form
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <DialogBody className="max-h-[68dvh] overflow-y-auto">
            <div className="grid gap-6 lg:grid-cols-2">
              <div className="min-w-0 space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="min-w-0 space-y-1.5">
                    <Label htmlFor="cover-design-name">Name</Label>
                    <Input
                      id="cover-design-name"
                      value={name}
                      maxLength={150}
                      onChange={(event) => setName(event.target.value)}
                    />
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <Label htmlFor="cover-design-title">Title</Label>
                    <Input
                      id="cover-design-title"
                      value={title}
                      maxLength={COVER_MAX_LABEL}
                      onChange={(event) => setTitle(event.target.value)}
                    />
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <Switch
                    id="cover-design-letterhead"
                    checked={showLetterhead}
                    onCheckedChange={setShowLetterhead}
                  />
                  <Label htmlFor="cover-design-letterhead">
                    Show company letterhead
                  </Label>
                </div>

                <Sortable
                  value={rows}
                  onValueChange={(next) => setRows(next as CoverDesignRow[])}
                  getItemValue={(row) => row.key}
                  strategy="vertical"
                  className="flex flex-col gap-2"
                >
                  {/* The rows must be Sortable's DIRECT children: its drag overlay clones the
                      direct child whose value is being dragged, and a wrapper div leaves an
                      empty zero-size overlay that no row ever collides with. */}
                  {rows.map((row) => {
                    const base = COVER_ROW_LABELS[row.key] ?? row.key;
                    return (
                      <SortableItem key={row.key} value={row.key} asChild>
                        <div
                          role="group"
                          aria-label={base}
                          className="flex items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5"
                        >
                          <SortableItemHandle asChild>
                            <button
                              type="button"
                              aria-label={`Drag ${base} to reorder`}
                              className="shrink-0 touch-none"
                            >
                              <GripVertical className="size-4 text-muted-foreground" />
                            </button>
                          </SortableItemHandle>
                          <Checkbox
                            checked={row.shown}
                            aria-label={`Show ${base}`}
                            onCheckedChange={(checked) =>
                              patchRow(row.key, { shown: checked === true })
                            }
                          />
                          <Input
                            value={row.label}
                            maxLength={COVER_MAX_LABEL}
                            aria-label={`Printed label for ${base}`}
                            className="h-8 min-w-0 flex-1"
                            onChange={(event) =>
                              patchRow(row.key, { label: event.target.value })
                            }
                          />
                        </div>
                      </SortableItem>
                    );
                  })}
                </Sortable>

                <TextWithFields
                  label="Intro text"
                  value={intro}
                  onChange={setIntro}
                />
                <TextWithFields
                  label="Closing text"
                  value={closing}
                  onChange={setClosing}
                />
              </div>

              <div className="min-w-0 lg:sticky lg:top-0 lg:self-start">
                <CoverPagePreview
                  cover={preview.data}
                  isLoading={preview.isLoading}
                />
              </div>
            </div>
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || pending}>
              {template ? 'Save changes' : 'Add design'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
