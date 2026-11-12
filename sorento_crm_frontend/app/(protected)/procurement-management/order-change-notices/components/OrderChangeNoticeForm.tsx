'use client';

/**
 * Raise / edit an Order Change Notice (OCN-ORDER-CHANGE-NOTICE G3), drawn in the sample request
 * document shell: one bordered card, the kind badge and status pill, the centred title, the
 * two-column field grid, the line items, and Cancel / Save as draft / Submit. The detail page
 * shows the same fields in the same order.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Loader2, Plus } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { DocField, ReadValue } from '@/components/common/DocField';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  OrderChangeNoticeLines,
  blankOcnLine,
  type OcnDraftLine,
} from '@/components/common/OrderChangeNoticeLines';
import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { cn } from '@/lib/utils';
import { getUserLookup } from '@/services/userSelectService';
import { lookupCustomersForRequest } from '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService';
import type { CustomerLookupItem } from '@/app/(protected)/procurement-management/purchase-requests/types/purchaseRequest.types';
import { searchProjectsForLink } from '@/app/(protected)/complaint-management/complaints/services/complaintService';
import {
  ocnStatusPillKey,
  ocnStatusWord,
  type OcnDetail,
  type OcnWrite,
} from '@/types/orderChangeNotice';
import {
  useChangeTypesQuery,
  useOrderChangeNoticeMutations,
  useOrderChangeNoticeQuery,
} from '../hooks/useOrderChangeNotices';
import {
  OrderChangeNoticeError,
  searchOrderChangeNoticeProducts,
} from '../services/orderChangeNoticeService';
import { OCN_BASE_PATH } from './OrderChangeNoticesList';

interface FormState {
  change_type_id: string;
  customer_id: string;
  customer_name: string;
  customer_po_no: string;
  so_no_text: string;
  project_id: string;
  project_label: string;
  sales_in_charge_user_id: string;
  cs_in_charge_user_id: string;
  description: string;
  lines: OcnDraftLine[];
}

const EMPTY: FormState = {
  change_type_id: '',
  customer_id: '',
  customer_name: '',
  customer_po_no: '',
  so_no_text: '',
  project_id: '',
  project_label: '',
  sales_in_charge_user_id: '',
  cs_in_charge_user_id: '',
  description: '',
  lines: [],
};

const NUMBER_RE = /^\d+(\.\d+)?$/;

function stateFromDetail(d: OcnDetail): FormState {
  return {
    change_type_id: d.change_type_id ?? '',
    customer_id: d.customer_id ?? '',
    customer_name: d.customer_name ?? '',
    customer_po_no: d.customer_po_no ?? '',
    so_no_text: d.so_no_text ?? '',
    project_id: d.project_id ?? '',
    project_label: d.project_title ?? '',
    sales_in_charge_user_id: d.sales_in_charge_user_id ?? '',
    cs_in_charge_user_id: d.cs_in_charge_user_id ?? '',
    description: d.description ?? '',
    lines: (d.lines ?? []).map((l) => ({
      ...blankOcnLine(),
      product_id: l.product_id,
      label: [l.product_code, l.product_name].filter(Boolean).join(' '),
      qty_before: l.qty_before ?? '',
      qty_after: l.qty_after ?? '',
      date_before: l.date_before ?? null,
      date_after: l.date_after ?? null,
      delivered_qty: l.delivered_qty ?? '',
      remark: l.remark ?? '',
    })),
  };
}

const blankToNull = (v: string) => (v.trim() ? v.trim() : null);

/** The backend body. A line with no product yet is not sent (a draft may hold an empty row). */
function payloadFromState(s: FormState): OcnWrite {
  return {
    change_type_id: s.change_type_id || null,
    customer_id: s.customer_id || null,
    customer_name: blankToNull(s.customer_name),
    customer_po_no: blankToNull(s.customer_po_no),
    so_no_text: blankToNull(s.so_no_text),
    project_id: s.project_id || null,
    sales_in_charge_user_id: s.sales_in_charge_user_id || null,
    cs_in_charge_user_id: s.cs_in_charge_user_id || null,
    description: blankToNull(s.description),
    lines: s.lines
      .filter((l) => l.product_id)
      .map((l) => ({
        product_id: l.product_id,
        qty_before: blankToNull(l.qty_before),
        qty_after: blankToNull(l.qty_after),
        date_before: l.date_before || null,
        date_after: l.date_after || null,
        delivered_qty: blankToNull(l.delivered_qty),
        remark: blankToNull(l.remark),
      })),
  };
}

/** A typed quantity must be a plain number; an empty box is fine. */
function numberErrors(s: FormState): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of s.lines) {
    for (const field of ['qty_before', 'qty_after', 'delivered_qty'] as const) {
      const v = line[field].trim();
      if (v && !NUMBER_RE.test(v)) out[`${field}_${line.key}`] = 'Enter a number, 0 or more.';
    }
  }
  return out;
}

function submitErrors(s: FormState): Record<string, string> {
  const out = numberErrors(s);
  if (!s.customer_name.trim() && !s.customer_id) out.customer = 'Enter the customer name.';
  if (!s.customer_po_no.trim()) out.customer_po_no = 'Enter the customer PO no.';
  if (!s.change_type_id) out.change_type_id = 'Choose the type of change.';
  if (s.lines.length === 0) out.lines = 'Add at least one line item.';
  s.lines.forEach((line, index) => {
    if (!line.product_id) out[`product_${line.key}`] = `Line ${index + 1}: choose a product.`;
  });
  if (!out.lines && s.lines.some((l) => !l.product_id)) {
    out.lines = 'Every line needs a product from the catalogue.';
  }
  return out;
}

/** Where a server refusal that names a field is shown. */
const SERVER_FIELD: Record<string, string> = {
  customer_name: 'customer',
  customer_id: 'customer',
  change_type_id: 'change_type_id',
  project_id: 'project_id',
  lines: 'lines',
  customer_po_no: 'customer_po_no',
};

interface OrderChangeNoticeFormProps {
  /** Edit mode: the notice to change. */
  ocnId?: string;
  /** New mode: a project to start from. */
  projectId?: string;
}

export default function OrderChangeNoticeForm({ ocnId, projectId }: OrderChangeNoticeFormProps) {
  const router = useRouter();
  const { create, update, submit } = useOrderChangeNoticeMutations();
  const existing = useOrderChangeNoticeQuery(ocnId ?? null);
  const { data: changeTypes = [] } = useChangeTypesQuery();
  const { data: users = [] } = useQuery({
    queryKey: ['user-lookup'],
    queryFn: () => getUserLookup(),
    staleTime: 5 * 60_000,
  });
  const [state, setState] = useState<FormState>(() => ({
    ...EMPTY,
    project_id: projectId ?? '',
    lines: [blankOcnLine()],
  }));
  const [hydrated, setHydrated] = useState(!ocnId);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverMessage, setServerMessage] = useState<string | null>(null);

  const patch = useCallback(
    (next: Partial<FormState>) => setState((prev) => ({ ...prev, ...next })),
    [],
  );

  useEffect(() => {
    if (ocnId && existing.data && !hydrated) {
      const loaded = stateFromDetail(existing.data);
      setState(loaded.lines.length ? loaded : { ...loaded, lines: [blankOcnLine()] });
      setHydrated(true);
    }
  }, [ocnId, existing.data, hydrated]);

  const userOptions = useMemo(
    () => users.map((u) => ({ value: u.id, label: u.name?.trim() || 'Unnamed user' })),
    [users],
  );
  const pickedType = changeTypes.find((t) => t.id === state.change_type_id);
  const record = existing.data;
  const detailPath = (id: string) => `${OCN_BASE_PATH}/${id}`;
  const saving = create.isPending || update.isPending || submit.isPending;

  const explain = (e: unknown) => {
    const message = e instanceof Error ? e.message : 'Failed to save the order change notice';
    const field = e instanceof OrderChangeNoticeError && e.field ? SERVER_FIELD[e.field] : undefined;
    if (field) setErrors((prev) => ({ ...prev, [field]: message }));
    setServerMessage(message);
  };

  const save = () => {
    const body = payloadFromState(state);
    return ocnId ? update.mutateAsync({ id: ocnId, body }) : create.mutateAsync(body);
  };

  const handleSaveDraft = async () => {
    setServerMessage(null);
    const found = numberErrors(state);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    try {
      const saved = await save();
      toast.success('Draft saved');
      router.push(detailPath(saved.id));
    } catch (e) {
      explain(e);
    }
  };

  const handleSubmit = async () => {
    setServerMessage(null);
    const found = submitErrors(state);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    try {
      const saved = await save();
      await submit.mutateAsync({ id: saved.id, revisionNo: saved.revision_no ?? 0 });
      router.push(detailPath(saved.id));
    } catch (e) {
      explain(e);
    }
  };

  if (ocnId && existing.isError) {
    return (
      <div className="mx-auto w-full max-w-5xl rounded-md border p-6 text-center">
        <p className="text-sm font-medium">Could not load this order change notice.</p>
        <div className="mt-4 flex justify-center gap-2">
          <Button variant="outline" onClick={() => router.push(OCN_BASE_PATH)}>
            Back to the list
          </Button>
          <Button onClick={() => void existing.refetch()}>Reload</Button>
        </div>
      </div>
    );
  }

  if (ocnId && (existing.isLoading || !hydrated)) {
    return (
      <div className="mx-auto w-full max-w-5xl space-y-4">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Card className="border-2 shadow-sm">
        <CardContent className="px-5 pb-8 pt-6 sm:px-10">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">Order Change Notice</Badge>
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(record ? ocnStatusPillKey(record) : 'draft')}`}
            >
              {record ? ocnStatusWord(record) : 'Draft'}
            </span>
          </div>
          <h2 className="mb-6 border-b border-border pb-4 text-center text-xl font-semibold tracking-tight">
            Order Change Notice
          </h2>

          <div className="grid grid-cols-1 gap-x-10 gap-y-5 sm:grid-cols-2">
            <DocField label="Sales Person">
              <ReadValue>{record?.created_by_name ?? 'You'}</ReadValue>
            </DocField>
            <DocField label="Date">
              {/* Spaced so the day reads as its own word next to its label. */}
              <ReadValue> {formatDateInMalaysia(record?.ocn_date ?? new Date()) || '-'} </ReadValue>
            </DocField>

            <DocField label="Customer Name *" htmlFor="ocn-customer" className="sm:col-span-2" error={errors.customer}>
              <AsyncCombobox<CustomerLookupItem>
                id="ocn-customer"
                value={state.customer_name}
                onChange={(v, item) => {
                  if (item && item.customer_id) {
                    patch({ customer_id: item.customer_id, customer_name: item.debtor_name });
                  } else {
                    patch({ customer_id: '', customer_name: v });
                  }
                }}
                fetchOptions={lookupCustomersForRequest}
                optionValue={(o) => o.debtor_name}
                optionLabel={(o) => o.debtor_name}
                optionMeta={(o) => o.customer_code}
                placeholder="Customer name"
              />
            </DocField>

            <DocField label="Customer PO No. *" htmlFor="ocn-po" error={errors.customer_po_no}>
              <Input
                id="ocn-po"
                value={state.customer_po_no}
                onChange={(e) => patch({ customer_po_no: e.target.value })}
              />
            </DocField>
            <DocField label="SO No." htmlFor="ocn-so">
              <Input
                id="ocn-so"
                value={state.so_no_text}
                onChange={(e) => patch({ so_no_text: e.target.value })}
              />
            </DocField>

            <DocField
              label="Registered project (optional)"
              htmlFor="ocn-project"
              className="sm:col-span-2"
              error={errors.project_id}
            >
              <SearchableSelect
                id="ocn-project"
                value={state.project_id}
                onChange={(v) => {
                  if (!v) patch({ project_id: '', project_label: '' });
                }}
                onOptionChange={(opt) =>
                  opt && patch({ project_id: opt.value, project_label: String(opt.label) })
                }
                selectedOption={
                  state.project_id
                    ? { value: state.project_id, label: state.project_label || 'Project' }
                    : undefined
                }
                fetchOptions={(query, pageIndex) => searchProjectsForLink(query, pageIndex + 1)}
                paginated
                pageSize={25}
                clearable
                truncateTriggerLabel
                placeholder="Search a project by code or title"
                emptyMessage="No project matches that."
              />
            </DocField>

            <DocField label="C.S. Incharge" htmlFor="ocn-cs">
              <SearchableSelect
                id="ocn-cs"
                value={state.cs_in_charge_user_id}
                onChange={(v) => patch({ cs_in_charge_user_id: v })}
                options={userOptions}
                clearable
                placeholder="Choose a person"
              />
            </DocField>
            <DocField label="Sales Incharge" htmlFor="ocn-sales">
              <SearchableSelect
                id="ocn-sales"
                value={state.sales_in_charge_user_id}
                onChange={(v) => patch({ sales_in_charge_user_id: v })}
                options={userOptions}
                clearable
                placeholder="Choose a person"
              />
            </DocField>

            <DocField label="Type of change *" className="sm:col-span-2" error={errors.change_type_id}>
              <div className="flex flex-wrap gap-2" role="group" aria-label="Type of change">
                {changeTypes.map((t) => {
                  const on = t.id === state.change_type_id;
                  return (
                    <button
                      key={t.id}
                      type="button"
                      aria-pressed={on}
                      onClick={() => patch({ change_type_id: t.id })}
                      className={cn(
                        'rounded-md border px-3 py-1.5 text-sm transition-colors',
                        on
                          ? 'border-primary bg-primary/10 font-medium text-primary'
                          : 'border-border hover:bg-muted',
                      )}
                    >
                      {t.name}
                    </button>
                  );
                })}
              </div>
              {pickedType && (
                <div className="mt-3 rounded-md border bg-muted/30 px-3 py-2 text-sm">
                  <p>
                    <span className="text-muted-foreground">Risk: </span>
                    <span className="font-medium">{pickedType.risk_level}</span>
                  </p>
                  {pickedType.guide_text && (
                    <p className="mt-1 text-muted-foreground">{pickedType.guide_text}</p>
                  )}
                </div>
              )}
            </DocField>

            <DocField label="Description" htmlFor="ocn-description" className="sm:col-span-2">
              <Textarea
                id="ocn-description"
                rows={3}
                value={state.description}
                onChange={(e) => patch({ description: e.target.value })}
              />
            </DocField>
          </div>

          <div className="mb-3 mt-8 flex items-center justify-between gap-3">
            <h3 className="text-base font-semibold">Line items</h3>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => patch({ lines: [...state.lines, blankOcnLine()] })}
            >
              <Plus className="size-4" />
              Add row
            </Button>
          </div>
          <OrderChangeNoticeLines
            lines={state.lines}
            onChange={(lines) => patch({ lines })}
            search={searchOrderChangeNoticeProducts}
            errors={errors}
          />

          {serverMessage && (
            <p className="mt-6 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {serverMessage}
            </p>
          )}

          <div className="mt-8 flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push(ocnId ? detailPath(ocnId) : OCN_BASE_PATH)}
            >
              Cancel
            </Button>
            <Button type="button" variant="outline" onClick={handleSaveDraft} disabled={saving}>
              {saving && <Loader2 className="mr-1 size-4 animate-spin" />}
              Save as draft
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={saving}>
              {saving && <Loader2 className="mr-1 size-4 animate-spin" />}
              Submit
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
