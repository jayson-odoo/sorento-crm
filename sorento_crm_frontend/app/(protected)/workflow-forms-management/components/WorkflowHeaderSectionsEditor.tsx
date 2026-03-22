'use client';

import { useMemo } from 'react';
import { GripVertical, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Kanban,
  KanbanBoard,
  KanbanColumn,
  KanbanColumnContent,
  KanbanColumnHandle,
  KanbanItem,
  KanbanItemHandle,
  useKanbanContext,
} from '@/components/ui/kanban';
import { verticalListSortingStrategy } from '@dnd-kit/sortable';
import type { WorkflowFieldType, WorkflowHeaderField, WorkflowHeaderSection } from '../types/workflowForms.types';
import { FIELD_TYPES, fieldUsesChoices } from './workflow-field-constants';
import { WorkflowFieldChoicesEditor } from './workflow-field-choices-editor';

function KanbanSectionsBody({
  sections,
  onSectionTitleChange,
  onAddField,
  onRemoveSection,
  onPatchField,
  onRemoveField,
}: {
  sections: WorkflowHeaderSection[];
  onSectionTitleChange: (sectionId: string, title: string) => void;
  onAddField: (sectionId: string) => void;
  onRemoveSection: (sectionId: string) => void;
  onPatchField: (sectionId: string, fieldId: string, patch: Partial<WorkflowHeaderField>) => void;
  onRemoveField: (sectionId: string, fieldId: string) => void;
}) {
  const { columnIds, columns } = useKanbanContext<WorkflowHeaderField>();

  return (
    <>
      {columnIds.map((sectionId) => {
        const sec = sections.find((s) => s.id === sectionId);
        const title = sec?.title ?? 'Section';
        const fields = columns[sectionId] ?? [];

        return (
          <KanbanColumn key={sectionId} value={sectionId} className="rounded-lg border bg-card p-3 gap-3">
            <div className="flex flex-wrap items-center gap-2 border-b border-border pb-2">
              <KanbanColumnHandle asChild>
                <button
                  type="button"
                  className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                  aria-label="Drag section"
                >
                  <GripVertical className="size-4" />
                </button>
              </KanbanColumnHandle>
              <Label className="text-xs shrink-0">Section</Label>
              <Input
                value={title}
                onChange={(e) => onSectionTitleChange(sectionId, e.target.value)}
                className="flex-1 min-w-[140px] max-w-md font-medium"
                placeholder="Section title"
              />
              <Button type="button" size="sm" variant="outline" onClick={() => onAddField(sectionId)}>
                <Plus className="size-4 mr-1" />
                Add field
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                className="text-destructive hover:text-destructive"
                onClick={() => onRemoveSection(sectionId)}
                aria-label="Remove section"
              >
                <Trash2 className="size-4" />
              </Button>
            </div>

            <KanbanColumnContent value={sectionId} className="gap-3">
              {fields.length === 0 ? (
                <p className="text-sm text-muted-foreground py-2">No fields in this section. Add a field or drag one here.</p>
              ) : (
                fields.map((f) => (
                  <KanbanItem key={f.id} value={f.id}>
                    <div className="grid gap-2 md:grid-cols-6 border rounded-md p-3 bg-background">
                      <div className="md:col-span-6 flex items-center gap-2 pb-1 border-b border-border/60 -mt-1 mb-1">
                        <KanbanItemHandle asChild>
                          <button
                            type="button"
                            className="rounded p-1 text-muted-foreground hover:bg-muted"
                            aria-label="Drag field"
                          >
                            <GripVertical className="size-4" />
                          </button>
                        </KanbanItemHandle>
                        <span className="text-xs text-muted-foreground">Drag to reorder or move to another section</span>
                      </div>
                      <div className="md:col-span-2 space-y-1">
                        <Label className="text-xs">Id</Label>
                        <Input
                          value={f.id}
                          onChange={(e) => onPatchField(sectionId, f.id, { id: e.target.value })}
                        />
                      </div>
                      <div className="md:col-span-2 space-y-1">
                        <Label className="text-xs">Label</Label>
                        <Input
                          value={f.label}
                          onChange={(e) => onPatchField(sectionId, f.id, { label: e.target.value })}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">Type</Label>
                        <Select
                          value={f.type}
                          onValueChange={(v) => {
                            const t = v as WorkflowFieldType;
                            const patch: Partial<WorkflowHeaderField> = { type: t };
                            if (fieldUsesChoices(t)) {
                              if (!f.options?.length) {
                                patch.options = [{ value: 'choice_1', label: 'Choice 1' }];
                              }
                            } else {
                              patch.options = undefined;
                            }
                            onPatchField(sectionId, f.id, patch);
                          }}
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {FIELD_TYPES.map((t) => (
                              <SelectItem key={t} value={t}>
                                {t}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex items-end gap-2 justify-between">
                        <div className="flex items-center gap-2">
                          <Checkbox
                            id={`req-${sectionId}-${f.id}`}
                            checked={!!f.required}
                            onCheckedChange={(c) => onPatchField(sectionId, f.id, { required: c === true })}
                          />
                          <Label htmlFor={`req-${sectionId}-${f.id}`} className="text-xs">
                            Required
                          </Label>
                        </div>
                        <Button
                          type="button"
                          size="icon"
                          variant="ghost"
                          onClick={() => onRemoveField(sectionId, f.id)}
                        >
                          <Trash2 className="size-4 text-destructive" />
                        </Button>
                      </div>
                      <div className="md:col-span-6 space-y-1">
                        <Label className="text-xs">Remarks / help text</Label>
                        <Textarea
                          value={f.help_text ?? ''}
                          onChange={(e) =>
                            onPatchField(sectionId, f.id, {
                              help_text: e.target.value || undefined,
                            })
                          }
                          rows={2}
                          placeholder="Optional guidance shown under the label when users fill the form"
                          className="resize-y min-h-[52px] text-sm"
                        />
                      </div>
                      {fieldUsesChoices(f.type) ? (
                        <WorkflowFieldChoicesEditor
                          options={f.options ?? []}
                          onChange={(next) => onPatchField(sectionId, f.id, { options: next })}
                        />
                      ) : null}
                    </div>
                  </KanbanItem>
                ))
              )}
            </KanbanColumnContent>
          </KanbanColumn>
        );
      })}
    </>
  );
}

export function WorkflowHeaderSectionsEditor({
  sections,
  onChange,
  onAddSection,
}: {
  sections: WorkflowHeaderSection[];
  onChange: (next: WorkflowHeaderSection[]) => void;
  onAddSection: () => void;
}) {
  const columns = useMemo(
    () => Object.fromEntries(sections.map((s) => [s.id, s.fields])) as Record<string, WorkflowHeaderField[]>,
    [sections],
  );

  const handleKanbanChange = (next: Record<string, WorkflowHeaderField[]>) => {
    const order = Object.keys(next);
    onChange(
      order.map((id) => {
        const prev = sections.find((s) => s.id === id);
        return {
          id,
          title: prev?.title ?? 'Section',
          fields: next[id] ?? [],
        };
      }),
    );
  };

  const onSectionTitleChange = (sectionId: string, title: string) => {
    onChange(sections.map((s) => (s.id === sectionId ? { ...s, title } : s)));
  };

  const onAddField = (sectionId: string) => {
    const id = `f_${crypto.randomUUID().slice(0, 8)}`;
    const f: WorkflowHeaderField = { id, type: 'text', label: 'New field', required: false };
    onChange(
      sections.map((s) => (s.id === sectionId ? { ...s, fields: [...s.fields, f] } : s)),
    );
  };

  const onRemoveField = (sectionId: string, fieldId: string) => {
    onChange(
      sections.map((s) =>
        s.id === sectionId ? { ...s, fields: s.fields.filter((f) => f.id !== fieldId) } : s,
      ),
    );
  };

  const onPatchField = (sectionId: string, fieldId: string, patch: Partial<WorkflowHeaderField>) => {
    onChange(
      sections.map((sec) =>
        sec.id !== sectionId
          ? sec
          : {
              ...sec,
              fields: sec.fields.map((f) => (f.id !== fieldId ? f : { ...f, ...patch })),
            },
      ),
    );
  };

  const onRemoveSection = (sectionId: string) => {
    if (sections.length <= 1) {
      toast.error('At least one section is required.');
      return;
    }
    const idx = sections.findIndex((s) => s.id === sectionId);
    const victim = sections[idx];
    const rest = sections.filter((_, i) => i !== idx);
    const targetIdx = idx === 0 ? 0 : idx - 1;
    const mergedFields = [...(rest[targetIdx]?.fields ?? []), ...victim.fields];
    onChange(
      rest.map((s, i) => (i === targetIdx ? { ...s, fields: mergedFields } : s)),
    );
  };

  return (
    <Kanban value={columns} onValueChange={handleKanbanChange} getItemValue={(f) => f.id}>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
        <p className="text-sm text-muted-foreground">
          Drag sections or fields by the grip handle. Drop fields onto another section to move them.
        </p>
        <Button type="button" size="sm" variant="outline" onClick={onAddSection}>
          <Plus className="size-4 mr-1" />
          Add section
        </Button>
      </div>
      <KanbanBoard className="!flex !flex-col gap-6 w-full" strategy={verticalListSortingStrategy}>
        <KanbanSectionsBody
          sections={sections}
          onSectionTitleChange={onSectionTitleChange}
          onAddField={onAddField}
          onRemoveSection={onRemoveSection}
          onPatchField={onPatchField}
          onRemoveField={onRemoveField}
        />
      </KanbanBoard>
    </Kanban>
  );
}
