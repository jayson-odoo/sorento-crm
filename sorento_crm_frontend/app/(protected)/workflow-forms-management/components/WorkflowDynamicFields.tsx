'use client';

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
import { Plus, Trash2 } from 'lucide-react';
import type { WorkflowFormSchema, WorkflowHeaderField } from '../types/workflowForms.types';

function renderField(
  f: WorkflowHeaderField,
  value: unknown,
  onChange: (v: unknown) => void,
  disabled: boolean,
) {
  const common = { disabled, placeholder: f.placeholder };
  switch (f.type) {
    case 'textarea':
      return (
        <Textarea
          {...common}
          rows={3}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case 'number':
      return (
        <Input
          {...common}
          type="number"
          value={value === undefined || value === null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        />
      );
    case 'checkbox':
      return (
        <Checkbox
          disabled={disabled}
          checked={Boolean(value)}
          onCheckedChange={(c) => onChange(c === true)}
        />
      );
    case 'select':
    case 'radio':
      return (
        <Select
          disabled={disabled}
          value={typeof value === 'string' ? value : ''}
          onValueChange={onChange}
        >
          <SelectTrigger>
            <SelectValue placeholder="Select…" />
          </SelectTrigger>
          <SelectContent>
            {(f.options ?? []).map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    case 'multi_select': {
      const arr = Array.isArray(value) ? (value as string[]) : [];
      const toggle = (v: string, on: boolean) => {
        if (on) onChange(Array.from(new Set([...arr, v])));
        else onChange(arr.filter((x) => x !== v));
      };
      return (
        <div className="flex flex-col gap-2 border rounded-md p-2">
          {(f.options ?? []).map((o) => (
            <div key={o.value} className="flex items-center gap-2">
              <Checkbox
                disabled={disabled}
                checked={arr.includes(o.value)}
                onCheckedChange={(c) => toggle(o.value, c === true)}
              />
              <span className="text-sm">{o.label}</span>
            </div>
          ))}
        </div>
      );
    }
    case 'date_range': {
      const dr =
        value && typeof value === 'object' && !Array.isArray(value)
          ? (value as { start?: string; end?: string })
          : {};
      const start = typeof dr.start === 'string' ? dr.start : '';
      const end = typeof dr.end === 'string' ? dr.end : '';
      return (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-4">
          <div className="space-y-1 flex-1 min-w-0">
            <Label className="text-xs text-muted-foreground">Start date</Label>
            <Input
              type="date"
              disabled={disabled}
              value={start}
              onChange={(e) => onChange({ start: e.target.value, end })}
            />
          </div>
          <div className="space-y-1 flex-1 min-w-0">
            <Label className="text-xs text-muted-foreground">End date</Label>
            <Input
              type="date"
              disabled={disabled}
              value={end}
              min={start || undefined}
              onChange={(e) => onChange({ start, end: e.target.value })}
            />
          </div>
        </div>
      );
    }
    default:
      return (
        <Input
          {...common}
          type={f.type === 'email' ? 'email' : f.type === 'date' ? 'date' : 'text'}
          value={typeof value === 'string' || typeof value === 'number' ? String(value ?? '') : ''}
          onChange={(e) => onChange(e.target.value)}
        />
      );
  }
}

function headerFieldLists(schema: WorkflowFormSchema): { title: string; fields: WorkflowHeaderField[] }[] {
  if (schema.header_sections?.length) {
    return schema.header_sections.map((s) => ({ title: s.title, fields: s.fields }));
  }
  return [{ title: '', fields: schema.header_fields ?? [] }];
}

export function WorkflowHeaderFieldsForm({
  schema,
  data,
  onChange,
  disabled,
}: {
  schema: WorkflowFormSchema;
  data: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  disabled?: boolean;
}) {
  const groups = headerFieldLists(schema);

  return (
    <div className="space-y-8">
      {groups.map((g, gi) => (
        <div key={`hdr-sec-${gi}`} className="space-y-4">
          {g.title ? (
            <h3 className="text-sm font-semibold text-foreground border-b pb-2">{g.title}</h3>
          ) : null}
          {g.fields.map((f, i) => (
            <div key={`hdr-${f.id}-${i}`} className="space-y-1">
              <Label className="flex flex-col gap-0.5 items-start">
                <span>
                  {f.label}
                  {f.required ? ' *' : ''}
                </span>
                {f.help_text ? (
                  <span className="text-xs font-normal text-muted-foreground whitespace-pre-wrap">{f.help_text}</span>
                ) : null}
              </Label>
              {renderField(f, data[f.id], (v) => onChange({ ...data, [f.id]: v }), !!disabled)}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function WorkflowLineGroupsEditor({
  schema,
  lines,
  onChange,
  disabled,
}: {
  schema: WorkflowFormSchema;
  lines: { line_group_id: string; sort_order: number; row_data: Record<string, unknown> }[];
  onChange: (next: typeof lines) => void;
  disabled?: boolean;
}) {
  const addRow = (groupId: string) => {
    const row = { line_group_id: groupId, sort_order: lines.filter((l) => l.line_group_id === groupId).length, row_data: {} };
    onChange([...lines, row]);
  };

  const updateRow = (idx: number, row_data: Record<string, unknown>) => {
    const next = [...lines];
    next[idx] = { ...next[idx], row_data };
    onChange(next);
  };

  const removeRow = (idx: number) => {
    onChange(lines.filter((_, i) => i !== idx));
  };

  return (
    <div className="space-y-6">
      {schema.line_groups.map((g, gi) => {
        const rowIndexes = lines
          .map((l, i) => (l.line_group_id === g.id ? i : -1))
          .filter((i) => i >= 0);
        return (
          <div key={`lg-${gi}`} className="border rounded-md p-4 space-y-3">
            <div className="flex justify-between items-center">
              <h4 className="font-medium">{g.name}</h4>
              {!disabled ? (
                <Button type="button" size="sm" variant="outline" onClick={() => addRow(g.id)}>
                  <Plus className="size-4 mr-1" />
                  Add row
                </Button>
              ) : null}
            </div>
            {rowIndexes.length === 0 ? (
              <p className="text-sm text-muted-foreground">No rows.</p>
            ) : (
              rowIndexes.map((idx) => (
                <div key={idx} className="border rounded p-3 space-y-3 relative">
                  {!disabled ? (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="absolute top-2 right-2"
                      onClick={() => removeRow(idx)}
                    >
                      <Trash2 className="size-4 text-destructive" />
                    </Button>
                  ) : null}
                  <div className="grid gap-3 md:grid-cols-2 pe-8">
                    {g.fields.map((f, fi) => (
                      <div key={`lg-${gi}-f-${fi}`} className="space-y-1">
                        <Label className="text-xs">
                          {f.label}
                          {f.required ? ' *' : ''}
                        </Label>
                        {renderField(
                          f,
                          lines[idx].row_data[f.id],
                          (v) => updateRow(idx, { ...lines[idx].row_data, [f.id]: v }),
                          !!disabled,
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        );
      })}
    </div>
  );
}
