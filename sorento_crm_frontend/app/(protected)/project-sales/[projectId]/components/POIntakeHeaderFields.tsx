'use client';

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { formatDateInMalaysia } from '@/lib/helpers';
import type { POVersionHeader } from '../../_shared/types/poIntake.types';

/**
 * What the extraction read off the top of the document (AC-D2), editable before it binds
 * (AC-D3).
 *
 * Saved as one block rather than per field: a person correcting a misread PO number usually
 * corrects the date beside it in the same breath, and a save per blur would fire five
 * writes for one correction.
 */
export function POIntakeHeaderFields({
  header,
  readOnly,
  saving,
  onSave,
}: {
  header: POVersionHeader;
  readOnly: boolean;
  saving: boolean;
  onSave: (body: Partial<POVersionHeader>) => Promise<void>;
}) {
  const [draft, setDraft] = React.useState<POVersionHeader>(header);

  // The server's copy wins whenever it changes underneath (a poll finishing, a card applied).
  React.useEffect(() => {
    setDraft(header);
  }, [header]);

  const dirty = FIELDS.some(
    (field) => normalise(draft[field]) !== normalise(header[field]),
  );

  const set = (field: keyof POVersionHeader, value: string) =>
    setDraft((current) => ({
      ...current,
      [field]:
        field === 'term_days' ? (value === '' ? null : Number(value)) : value || null,
    }));

  if (readOnly) {
    return (
      <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
        {READ_ONLY_ROWS.map(({ label, value }) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd
              className="truncate text-sm font-medium"
              title={value(header) ?? undefined}
            >
              {value(header) ?? 'Not on the document'}
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return (
    <form
      className="space-y-4"
      onSubmit={async (event) => {
        event.preventDefault();
        await onSave({
          po_number: draft.po_number,
          po_date: draft.po_date,
          term_days: draft.term_days,
          sales_person: draft.sales_person,
          customer_order_ref: draft.customer_order_ref,
          admin_ref: draft.admin_ref,
          remark: draft.remark,
        });
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field id="po-header-number" label="PO number">
          <Input
            id="po-header-number"
            value={draft.po_number ?? ''}
            onChange={(event) => set('po_number', event.target.value)}
            placeholder="Not read"
          />
        </Field>
        <Field id="po-header-date" label="PO date">
          <Input
            id="po-header-date"
            type="date"
            value={draft.po_date ?? ''}
            onChange={(event) => set('po_date', event.target.value)}
          />
        </Field>
        <Field id="po-header-term" label="Term (days)">
          <Input
            id="po-header-term"
            type="number"
            min="0"
            value={draft.term_days ?? ''}
            onChange={(event) => set('term_days', event.target.value)}
            placeholder="Not read"
          />
        </Field>
        <Field id="po-header-sales" label="Salesperson">
          <Input
            id="po-header-sales"
            value={draft.sales_person ?? ''}
            onChange={(event) => set('sales_person', event.target.value)}
            placeholder="Not read"
          />
        </Field>
        <Field id="po-header-ref" label="Their order reference">
          <Input
            id="po-header-ref"
            value={draft.customer_order_ref ?? ''}
            onChange={(event) => set('customer_order_ref', event.target.value)}
            placeholder="Not read"
          />
        </Field>
        <Field id="po-header-admin" label="Filing reference">
          <Input
            id="po-header-admin"
            value={draft.admin_ref ?? ''}
            onChange={(event) => set('admin_ref', event.target.value)}
            placeholder="Not read"
          />
        </Field>
      </div>

      <Field id="po-header-remark" label="Remark">
        <Textarea
          id="po-header-remark"
          rows={2}
          value={draft.remark ?? ''}
          onChange={(event) => set('remark', event.target.value)}
          placeholder="Not read"
        />
      </Field>

      <div className="flex flex-wrap items-center justify-end gap-2">
        {dirty && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setDraft(header)}
          >
            Undo changes
          </Button>
        )}
        <Button type="submit" size="sm" disabled={!dirty || saving}>
          {saving ? 'Saving…' : 'Save header'}
        </Button>
      </div>
    </form>
  );
}

const FIELDS: Array<keyof POVersionHeader> = [
  'po_number',
  'po_date',
  'term_days',
  'sales_person',
  'customer_order_ref',
  'admin_ref',
  'remark',
];

const READ_ONLY_ROWS: Array<{
  label: string;
  value: (header: POVersionHeader) => string | null;
}> = [
  { label: 'PO number', value: (h) => h.po_number },
  {
    label: 'PO date',
    value: (h) => (h.po_date ? formatDateInMalaysia(h.po_date) : null),
  },
  {
    label: 'Term (days)',
    value: (h) => (h.term_days == null ? null : String(h.term_days)),
  },
  { label: 'Salesperson', value: (h) => h.sales_person },
  { label: 'Their order reference', value: (h) => h.customer_order_ref },
  { label: 'Filing reference', value: (h) => h.admin_ref },
  { label: 'Remark', value: (h) => h.remark },
];

function normalise(value: string | number | null): string {
  return value === null || value === undefined ? '' : String(value);
}

function Field({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}
