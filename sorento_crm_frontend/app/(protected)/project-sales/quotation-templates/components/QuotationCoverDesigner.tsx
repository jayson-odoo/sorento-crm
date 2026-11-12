'use client';

import * as React from 'react';
import type { Editor } from '@tiptap/react';
import { ArrowDown, ArrowUp, GripVertical, Plus, X } from 'lucide-react';
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
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { CoverPagePreview } from '@/components/quotation/CoverPagePreview';
import { cn } from '@/lib/utils';
import {
  COVER_MAX_COLUMNS,
  COVER_MAX_LABEL,
  COVER_MAX_SECTIONS,
  COVER_SECTION_STYLES,
  type CoverDesign,
  type CoverDesignRow,
  type CoverDesignSection,
  type CoverSectionStyle,
  type CoverSource,
} from '@/lib/quotation-cover';
import {
  useCoverDefaultDesign,
  useCoverDesignPreview,
  useCoverSources,
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
  const fieldId = React.useId();
  const labelId = `${fieldId}-label`;

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
        <Label id={labelId} htmlFor={fieldId}>
          {label}
        </Label>
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
        id={fieldId}
        aria-labelledby={labelId}
        value={value}
        onChange={onChange}
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
  // The default design and the source fields are the server's, so the designer, the preview and
  // the PDF read one list.
  const defaults = useCoverDefaultDesign();
  const sources = useCoverSources();
  const failed = defaults.isError ? defaults.error : sources.error;
  if (!defaults.data || !sources.data) {
    return (
      <Dialog open onOpenChange={(next) => !next && onDone()}>
        <DialogContent className="w-full max-w-5xl">
          <DialogHeader>
            <DialogTitle>
              {template ? `Edit ${template.name}` : 'Add a cover page design'}
            </DialogTitle>
          </DialogHeader>
          <DialogBody>
            {failed ? (
              <p className="text-sm text-muted-foreground">{failed.message}</p>
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </DialogBody>
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <CoverDesignerForm
      template={template}
      onDone={onDone}
      defaults={defaults.data}
      sources={sources.data}
    />
  );
}

interface RowState extends CoverDesignRow {
  id: string;
}

interface SectionState extends Omit<CoverDesignSection, 'rows'> {
  id: string;
  rows: RowState[];
}

let nextId = 0;
const newId = () => `cover-${(nextId += 1)}`;

function withIds(design: CoverDesign): SectionState[] {
  return design.sections.map((section) => ({
    ...section,
    id: newId(),
    rows: section.rows.map((row) => ({ ...row, id: newId() })),
  }));
}

function withoutIds(sections: SectionState[]): CoverDesignSection[] {
  return sections.map(({ id: _id, rows, ...section }) => ({
    ...section,
    rows: rows.map(({ id: _rowId, ...row }) => row),
  }));
}

const COLUMN_OPTIONS = Array.from({ length: COVER_MAX_COLUMNS }, (_, i) => ({
  value: String(i + 1),
  label: i === 0 ? '1 column' : `${i + 1} columns`,
}));

const STYLE_OPTIONS = COVER_SECTION_STYLES.map((style) => ({
  value: style.value,
  label: style.label,
}));

/** One section: style, band label, column count, then its rows (drag, tick, source, column,
 * printed label, remove) and an Add a row picker. */
function SectionEditor({
  section,
  index,
  count,
  sources,
  onChange,
  onMove,
  onRemove,
}: {
  section: SectionState;
  index: number;
  count: number;
  sources: CoverSource[];
  onChange: (next: SectionState) => void;
  onMove: (offset: -1 | 1) => void;
  onRemove: () => void;
}) {
  const byKey = React.useMemo(
    () => Object.fromEntries(sources.map((source) => [source.key, source])),
    [sources],
  );
  const sourceOptions = React.useMemo(
    () =>
      sources.map((source) => ({
        value: source.key,
        label: source.caption,
        group: source.group,
      })),
    [sources],
  );
  const name = section.label.trim() || `Section ${index + 1}`;
  const columnOptions = COLUMN_OPTIONS.slice(0, section.columns);

  function patchRow(id: string, patch: Partial<RowState>) {
    onChange({
      ...section,
      rows: section.rows.map((row) =>
        row.id === id ? { ...row, ...patch } : row,
      ),
    });
  }

  function changeSource(row: RowState, source: string) {
    const before = byKey[row.source]?.default_label ?? '';
    // A label still at the old field's default follows the new field; a typed one stays.
    const label =
      !row.label.trim() || row.label === before
        ? (byKey[source]?.default_label ?? row.label)
        : row.label;
    patchRow(row.id, { source, label });
  }

  function setColumns(value: string) {
    const columns = Number(value) || 1;
    onChange({
      ...section,
      columns,
      // A row in a column that no longer exists moves to the last one.
      rows: section.rows.map((row) =>
        row.column >= columns ? { ...row, column: columns - 1 } : row,
      ),
    });
  }

  function addRow(source: string) {
    if (!source) return;
    onChange({
      ...section,
      rows: [
        ...section.rows,
        {
          id: newId(),
          source,
          label: byKey[source]?.default_label ?? '',
          shown: true,
          column: 0,
        },
      ],
    });
  }

  return (
    <div
      role="group"
      aria-label={name}
      className="min-w-0 rounded-md border border-border"
    >
      <div className="grid min-w-0 gap-2 border-b border-border bg-muted/40 p-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)_8rem_auto]">
        <SearchableSelect
          value={section.style}
          options={STYLE_OPTIONS}
          onChange={(value) =>
            value && onChange({ ...section, style: value as CoverSectionStyle })
          }
          aria-label={`Style of ${name}`}
          size="sm"
        />
        <Input
          value={section.label}
          maxLength={COVER_MAX_LABEL}
          placeholder="Band label"
          aria-label={`Band label of ${name}`}
          className="h-8 min-w-0"
          onChange={(event) =>
            onChange({ ...section, label: event.target.value })
          }
        />
        <SearchableSelect
          value={String(section.columns)}
          options={COLUMN_OPTIONS}
          onChange={(value) => value && setColumns(value)}
          aria-label={`Columns of ${name}`}
          size="sm"
        />
        <div className="flex items-center justify-end gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            mode="icon"
            aria-label={`Move ${name} up`}
            title="Move up"
            disabled={index === 0}
            onClick={() => onMove(-1)}
          >
            <ArrowUp className="size-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            mode="icon"
            aria-label={`Move ${name} down`}
            title="Move down"
            disabled={index === count - 1}
            onClick={() => onMove(1)}
          >
            <ArrowDown className="size-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            mode="icon"
            aria-label={`Remove ${name}`}
            title="Remove section"
            disabled={count === 1}
            onClick={onRemove}
          >
            <X className="size-4" />
          </Button>
        </div>
      </div>

      <Sortable
        value={section.rows}
        onValueChange={(next) =>
          onChange({ ...section, rows: next as RowState[] })
        }
        getItemValue={(row) => row.id}
        strategy="vertical"
        className="flex flex-col"
      >
        {/* The rows must be Sortable's DIRECT children: its drag overlay clones the direct
            child whose value is being dragged. */}
        {section.rows.map((row) => {
          const caption = byKey[row.source]?.caption ?? row.source;
          return (
            <SortableItem key={row.id} value={row.id} asChild>
              <div
                role="group"
                aria-label={caption}
                className={cn(
                  'grid min-w-0 items-center gap-2 border-b border-border bg-background px-2 py-1.5',
                  section.columns > 1
                    ? 'grid-cols-[auto_auto_minmax(0,1fr)_auto] sm:grid-cols-[auto_auto_minmax(0,1fr)_7rem_minmax(0,1fr)_auto]'
                    : 'grid-cols-[auto_auto_minmax(0,1fr)_auto] sm:grid-cols-[auto_auto_minmax(0,1fr)_minmax(0,1fr)_auto]',
                )}
              >
                <SortableItemHandle asChild>
                  <button
                    type="button"
                    aria-label={`Drag ${caption} to reorder`}
                    className="shrink-0 touch-none"
                  >
                    <GripVertical className="size-4 text-muted-foreground" />
                  </button>
                </SortableItemHandle>
                <Checkbox
                  checked={row.shown}
                  aria-label={`Show ${caption}`}
                  onCheckedChange={(checked) =>
                    patchRow(row.id, { shown: checked === true })
                  }
                />
                <SearchableSelect
                  value={row.source}
                  options={sourceOptions}
                  onChange={(value) => value && changeSource(row, value)}
                  aria-label={`Source field for ${caption}`}
                  size="sm"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  mode="icon"
                  aria-label={`Remove ${caption}`}
                  title="Remove row"
                  className="sm:order-last"
                  onClick={() =>
                    onChange({
                      ...section,
                      rows: section.rows.filter((item) => item.id !== row.id),
                    })
                  }
                >
                  <X className="size-4" />
                </Button>
                {section.columns > 1 && (
                  <div className="col-span-2 col-start-3 min-w-0 sm:col-span-1 sm:col-start-auto">
                    <SearchableSelect
                      value={String(row.column + 1)}
                      options={columnOptions.map((option) => ({
                        value: option.value,
                        label: `Column ${option.value}`,
                      }))}
                      onChange={(value) =>
                        value && patchRow(row.id, { column: Number(value) - 1 })
                      }
                      aria-label={`Column for ${caption}`}
                      size="sm"
                    />
                  </div>
                )}
                <Input
                  value={row.label}
                  maxLength={COVER_MAX_LABEL}
                  aria-label={`Printed label for ${caption}`}
                  placeholder="No label"
                  className="col-span-2 col-start-3 h-8 min-w-0 sm:col-span-1 sm:col-start-auto"
                  onChange={(event) =>
                    patchRow(row.id, { label: event.target.value })
                  }
                />
              </div>
            </SortableItem>
          );
        })}
      </Sortable>

      <div className="p-2">
        <SearchableSelect
          value=""
          options={sourceOptions}
          onChange={addRow}
          placeholder="Add a row: pick a field"
          aria-label={`Add a row to ${name}`}
          size="sm"
        />
      </div>
    </div>
  );
}

function CoverDesignerForm({
  template,
  onDone,
  defaults,
  sources,
}: {
  template: QuotationTemplate | null;
  onDone: () => void;
  defaults: CoverDesign;
  sources: CoverSource[];
}) {
  const { create, update } = useQuotationTemplateMutations('cover_page');
  const initial = template?.design ?? defaults;
  const [name, setName] = React.useState(template?.name ?? '');
  const [title, setTitle] = React.useState(initial.title);
  const [showLetterhead, setShowLetterhead] = React.useState(
    initial.show_letterhead,
  );
  const [sections, setSections] = React.useState<SectionState[]>(() =>
    withIds(initial),
  );
  const [intro, setIntro] = React.useState(template?.body_html ?? '');
  const [closing, setClosing] = React.useState(initial.closing_html);
  const pending = create.isPending || update.isPending;

  const design: CoverDesign = {
    show_letterhead: showLetterhead,
    title,
    sections: withoutIds(sections),
    closing_html: closing,
  };
  const preview = useCoverDesignPreview(design, intro);

  function patchSection(id: string, next: SectionState) {
    setSections((previous) =>
      previous.map((section) => (section.id === id ? next : section)),
    );
  }

  function moveSection(index: number, offset: -1 | 1) {
    setSections((previous) => {
      const next = [...previous];
      const [moved] = next.splice(index, 1);
      next.splice(index + offset, 0, moved);
      return next;
    });
  }

  function addSection() {
    setSections((previous) => [
      ...previous,
      { id: newId(), style: 'fields', label: '', columns: 1, rows: [] },
    ]);
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
      <DialogContent className="max-h-[92dvh] w-full max-w-6xl overflow-hidden">
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
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
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

                <TextWithFields
                  label="Intro text"
                  value={intro}
                  onChange={setIntro}
                />

                <div className="space-y-3">
                  {sections.map((section, index) => (
                    <SectionEditor
                      key={section.id}
                      section={section}
                      index={index}
                      count={sections.length}
                      sources={sources}
                      onChange={(next) => patchSection(section.id, next)}
                      onMove={(offset) => moveSection(index, offset)}
                      onRemove={() =>
                        setSections((previous) =>
                          previous.filter((item) => item.id !== section.id),
                        )
                      }
                    />
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={sections.length >= COVER_MAX_SECTIONS}
                    onClick={addSection}
                  >
                    <Plus className="size-4" />
                    Add a section
                  </Button>
                </div>

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
