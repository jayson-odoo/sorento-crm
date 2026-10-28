'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter, useSearchParams } from 'next/navigation';
import { LoaderCircleIcon, Save, Send } from 'lucide-react';
import { format } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormField, FormItem, FormMessage } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useMyRequestSubmission,
  useReviseMyRequest,
  useSaveMyRequestDraft,
  useSubmitMyRequest,
} from '@/hooks/useMyRequests';
import { fetchRequestorOptions, type MyRequestDetail } from '@/services/myRequestsService';
import { RequestorContactSelect } from '@/app/(protected)/master-data-management/shared/components/RequestorContactSelect';
import { ProductInquiryFormLayout, InquiryFormTableRow } from './ProductInquiryFormLayout';
import StockInquiryFieldRows from './StockInquiryFieldRows';
import { StockInquirySchema, type StockInquirySchemaType } from '../forms/stock-inquiry-schema';
import { submitVerb } from '@/lib/submission-status';

const KIND = 'stock_inquiry' as const;
const LIST = '/procurement-management/stock-inquiries';

/** The inquiry's own fields as the portal takes them; the purchasing response is staff-only. */
const FIELDS = [
  'salesperson_contact_id',
  'product_code',
  'item_description',
  'project_customer',
  'project_name',
  'quantity',
  'delivery_date',
  'remark',
  'additional_remark',
] as const;

function toValues(row: MyRequestDetail | undefined): StockInquirySchemaType {
  const values: Record<string, string | null> = {};
  for (const key of FIELDS) {
    const v = row?.[key];
    values[key] = v == null || v === '' ? null : String(v);
  }
  return values as StockInquirySchemaType;
}

function toFields(values: StockInquirySchemaType): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  for (const key of FIELDS) {
    const v = values[key];
    if (v != null && v !== '') fields[key] = v;
  }
  return fields;
}

/**
 * A salesperson's own Stock Inquiry (PORTAL-P4-REQUESTS P4-24): the staff form's fields without
 * the purchasing response, written through My Requests so the portal's rules apply. A draft saves
 * and submits; a rejected row submits again; `?revise=1` sends a revision when the server allows
 * it (the requestor stays as submitted); `?from=<id>` starts a new draft from one of theirs.
 */
export default function MyStockInquiryForm({ inquiryId }: { inquiryId?: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const fromId = inquiryId ? null : searchParams?.get('from') || null;
  const revising = Boolean(inquiryId) && searchParams?.get('revise') === '1';
  const { data: row, isLoading } = useMyRequestSubmission(KIND, inquiryId ?? fromId);
  const save = useSaveMyRequestDraft(KIND);
  const submit = useSubmitMyRequest(KIND);
  const revise = useReviseMyRequest(KIND);
  const [savedId, setSavedId] = useState<string | undefined>(inquiryId);
  const [reason, setReason] = useState('');

  const form = useForm<StockInquirySchemaType>({
    resolver: zodResolver(StockInquirySchema),
    defaultValues: toValues(undefined),
    mode: 'onTouched',
  });

  const [initialized, setInitialized] = useState(false);
  useEffect(() => {
    if (row && !initialized) {
      form.reset(toValues(row));
      setInitialized(true);
    }
  }, [row, initialized, form]);

  const status = inquiryId ? String(row?.status ?? '') : 'draft';
  const canRevise = revising && row?.revision?.allowed === true;
  const editable = !inquiryId || row?.is_editable === true;
  const canSaveDraft = !inquiryId || status === 'draft';
  const busy = save.isPending || submit.isPending || revise.isPending;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const fields = () => toFields(form.getValues());
  const openRecord = (id: unknown) => router.push(`${LIST}/${String(id)}`);

  const onSaveDraft = async () => {
    try {
      const saved = await save.mutateAsync({ fields: fields(), id: savedId });
      setSavedId(String(saved.id));
      openRecord(saved.id);
    } catch {
      // toast from the mutation
    }
  };

  const onSubmit = async () => {
    try {
      const done = await submit.mutateAsync({ fields: fields(), id: savedId });
      openRecord(done.id ?? savedId);
    } catch {
      // toast from the mutation
    }
  };

  const onSendRevision = async () => {
    if (!inquiryId) return;
    try {
      await revise.mutateAsync({
        id: inquiryId,
        input: {
          reason: reason.trim(),
          expectedRevisionNo: Number(row?.revision?.used ?? row?.revision_no ?? 0),
          fields: fields(),
        },
      });
      openRecord(inquiryId);
    } catch {
      // toast from the mutation
    }
  };

  const created = typeof row?.created_at === 'string' && inquiryId ? new Date(row.created_at) : new Date();
  const number = inquiryId ? (row?.document_number as string | undefined) : undefined;

  return (
    <Form {...form}>
      <form onSubmit={(e) => e.preventDefault()} className="space-y-6">
        <ProductInquiryFormLayout>
          <InquiryFormTableRow label="Date">
            <p className="text-sm font-medium tabular-nums py-1">{format(created, 'dd/MM/yy')}</p>
          </InquiryFormTableRow>
          <InquiryFormTableRow label="Stock inquiry number">
            <p className="text-sm font-medium tabular-nums py-1">
              {number || <span className="text-muted-foreground font-normal">Assigned when you submit</span>}
            </p>
          </InquiryFormTableRow>
          <StockInquiryFieldRows
            form={form}
            readOnly={!editable && !canRevise}
            salesperson={
              <FormField
                control={form.control}
                name="salesperson_contact_id"
                render={({ field }) => (
                  <FormItem className="space-y-1">
                    <FormControl>
                      <RequestorContactSelect
                        value={field.value}
                        onChange={field.onChange}
                        savedContactId={row?.salesperson_contact_id as string | undefined}
                        savedContactName={row?.salesperson_contact_name as string | undefined}
                        placeholder="Select sales person"
                        // A revision keeps the requestor it was submitted with.
                        disabled={revising || (!editable && !canRevise)}
                        loadOptions={async (q) => (await fetchRequestorOptions(q)).items}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            }
          />
          {canRevise && (
            <InquiryFormTableRow label="Reason for revision" labelClassName="items-start pt-3">
              <div className="space-y-1 py-1">
                <Label htmlFor="revision_reason" className="sr-only">
                  Reason for revision
                </Label>
                <Textarea
                  id="revision_reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  rows={3}
                  className="min-h-[4.5rem] resize-y"
                />
              </div>
            </InquiryFormTableRow>
          )}
        </ProductInquiryFormLayout>

        <div className="flex flex-wrap justify-end gap-3">
          <Button type="button" variant="outline" onClick={() => router.back()} disabled={busy}>
            Cancel
          </Button>
          {canRevise ? (
            <Button type="button" onClick={onSendRevision} disabled={busy || !reason.trim()}>
              <Send className="size-4" />
              {revise.isPending ? 'Sending...' : 'Send revision'}
            </Button>
          ) : (
            editable && (
              <>
                {canSaveDraft && (
                  <Button type="button" variant="outline" onClick={onSaveDraft} disabled={busy}>
                    <Save className="size-4" />
                    Save as draft
                  </Button>
                )}
                <Button type="button" onClick={onSubmit} disabled={busy}>
                  <Send className="size-4" />
                  {submit.isPending ? 'Submitting...' : submitVerb(status)}
                </Button>
              </>
            )
          )}
        </div>
      </form>
    </Form>
  );
}
