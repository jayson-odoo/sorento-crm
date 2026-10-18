'use client';

/**
 * Staff new / edit new product application (NEW-PRODUCT-APP): one document card, the way New
 * Sample Request and New Purchase Request draw theirs. The detail page shows the same fields in
 * the same order.
 */

import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  NewProductApplicationSheet,
  type SheetImageActions,
} from '@/components/common/NewProductApplicationSheet';
import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  EMPTY_FORM,
  blankLine,
  numberErrors,
  payloadFromState,
  stateFromDetail,
  stateFromPrefill,
  type FormState,
} from '@/lib/new-product-application-form';
import { lookupCustomersForRequest } from '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService';
import type { CustomerLookupItem } from '@/app/(protected)/procurement-management/purchase-requests/types/purchaseRequest.types';
import type { NewProductApplicationDetail } from '@/types/newProductApplication';
import {
  useNewProductApplicationLookups,
  useNewProductApplicationMutations,
  useNewProductApplicationPrefillQuery,
  useNewProductApplicationQuery,
} from '../hooks/useNewProductApplications';
import {
  copyNewProductApplicationLineImage,
  deleteNewProductApplicationLineImage,
  getStockInquiryAttachmentsForNpa,
  searchStockInquiryOptions,
  uploadNewProductApplicationLineImage,
} from '../services/newProductApplicationService';

const BASE_PATH = '/procurement-management/new-product-applications';

export default function NewProductApplicationForm({
  applicationId,
  stockInquiryId,
}: {
  /** Edit mode: the application to change. */
  applicationId?: string;
  /** New mode: a responded stock inquiry to copy the text from. */
  stockInquiryId?: string;
}) {
  const router = useRouter();
  const { create, update, submit } = useNewProductApplicationMutations();
  const existing = useNewProductApplicationQuery(applicationId ?? null);
  const prefill = useNewProductApplicationPrefillQuery(
    applicationId ? null : (stockInquiryId ?? null),
  );
  const lookups = useNewProductApplicationLookups();
  const [state, setState] = useState<FormState>({
    ...EMPTY_FORM,
    lines: [blankLine()],
  });
  const [hydrated, setHydrated] = useState(!applicationId && !stockInquiryId);
  const [errors, setErrors] = useState<Record<string, string>>({});
  // A Submit the server refuses leaves the draft saved; the next press updates it.
  const [savedId, setSavedId] = useState<string | null>(null);

  useEffect(() => {
    if (hydrated) return;
    if (applicationId && existing.data) {
      const loaded = stateFromDetail(existing.data);
      setState(
        loaded.lines.length ? loaded : { ...loaded, lines: [blankLine()] },
      );
      setHydrated(true);
    } else if (!applicationId && prefill.data) {
      setState(stateFromPrefill(prefill.data));
      setHydrated(true);
    } else if (!applicationId && prefill.isError) {
      // The inquiry could not be read: say why and keep the empty form usable.
      toast.error(
        prefill.error instanceof Error && prefill.error.message
          ? prefill.error.message
          : 'That stock inquiry could not be loaded.',
      );
      setHydrated(true);
    }
  }, [
    hydrated,
    applicationId,
    existing.data,
    prefill.data,
    prefill.isError,
    prefill.error,
  ]);

  const saving = create.isPending || update.isPending || submit.isPending;

  // The server answered with line ids and images: keep them on the draft so the next save
  // updates the same products instead of replacing them.
  const adopt = useCallback((saved?: Partial<NewProductApplicationDetail>) => {
    const lines = saved?.lines;
    if (!lines) return;
    setState((prev) => ({
      ...prev,
      lines: prev.lines.map((l, i) => {
        const match = l.id ? lines.find((x) => x.id === l.id) : lines[i];
        return match
          ? { ...l, id: match.id, images: match.images ?? l.images }
          : l;
      }),
    }));
  }, []);

  const save = async () => {
    const body = payloadFromState(state);
    const id = applicationId ?? savedId;
    if (id) {
      const updated = await update.mutateAsync({ id, data: body });
      await uploadStaged(id, updated);
      return updated;
    }
    const created = await create.mutateAsync(body);
    setSavedId(created.id);
    await uploadStaged(created.id, created);
    return created;
  };

  // Images picked before the application existed go up now, in product order.
  const uploadStaged = async (
    id: string,
    saved: Partial<NewProductApplicationDetail>,
  ) => {
    const lines = saved.lines ?? [];
    for (const [i, line] of state.lines.entries()) {
      const lineId = lines[i]?.id;
      if (!lineId) continue;
      for (const file of line.staged_images) {
        try {
          await uploadNewProductApplicationLineImage(id, lineId, file);
        } catch (e) {
          toast.error(
            e instanceof Error ? e.message : 'Failed to upload the image',
          );
        }
      }
    }
    // Removals staged during the edit are applied now that the save went through.
    for (const line of state.lines) {
      if (!line.id) continue;
      for (const linkId of line.removed_link_ids) {
        try {
          await deleteNewProductApplicationLineImage(id, line.id, linkId);
        } catch (e) {
          toast.error(
            e instanceof Error ? e.message : 'Failed to remove the image',
          );
        }
      }
    }
    adopt(saved);
    setState((prev) => ({
      ...prev,
      lines: prev.lines.map((l) => ({
        ...l,
        images: l.images.filter((i) => !l.removed_link_ids.includes(i.link_id)),
        staged_images: [],
        removed_link_ids: [],
      })),
    }));
  };

  const recordId = applicationId ?? savedId;
  const imageActions: SheetImageActions = {
    upload: async (line, file) => {
      if (!recordId || !line.id) return;
      try {
        adopt(await uploadNewProductApplicationLineImage(recordId, line.id, file));
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Failed to upload the image');
      }
    },
    copy: async (line, attachmentId) => {
      if (!recordId || !line.id) return;
      try {
        adopt(
          await copyNewProductApplicationLineImage(recordId, line.id, attachmentId),
        );
      } catch (e) {
        toast.error(e instanceof Error ? e.message : 'Failed to copy the image');
      }
    },
    listInquiry: () => getStockInquiryAttachmentsForNpa(state.stock_inquiry_id),
  };

  const checkNumbers = () => {
    const found = numberErrors(state);
    setErrors(found);
    return Object.keys(found).length === 0;
  };

  const handleSaveDraft = async () => {
    if (!checkNumbers()) return;
    try {
      const saved = await save();
      router.push(`${BASE_PATH}/${saved.id}`);
    } catch {
      // the mutation's own onError toast names the refusal
    }
  };

  // Save, then submit. The server's refusal names the line; the toast shows it and the
  // user stays here with the draft kept.
  const handleSubmit = async () => {
    if (!checkNumbers()) return;
    try {
      const saved = await save();
      await submit.mutateAsync(saved.id);
      router.push(`${BASE_PATH}/${saved.id}`);
    } catch {
      // the mutation's own onError toast names the refusal
    }
  };

  if ((applicationId && existing.isLoading) || !hydrated) {
    return (
      <div className="mx-auto w-full max-w-5xl space-y-4">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const record = existing.data;
  const cancelHref = applicationId
    ? `${BASE_PATH}/${applicationId}`
    : BASE_PATH;

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Card className="border-2 shadow-sm">
        <CardContent className="px-5 pb-8 pt-6 sm:px-10">
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">New Product Application</Badge>
            <span
              className={`${STATUS_PILL_BASE} ${statusPillClass(record?.status ?? 'draft')}`}
            >
              {record?.status_label ?? 'Draft'}
            </span>
          </div>
          <NewProductApplicationSheet
            value={state}
            onChange={setState}
            applicationNo={record?.application_no}
            createdAt={record?.created_at}
            salesPerson={record?.applicant_name ?? 'You'}
            brands={lookups.brands}
            errors={errors}
            imageActions={imageActions}
            stockInquiryField={
              <SearchableSelect
                aria-label="Stock inquiry"
                value={state.stock_inquiry_id}
                clearable
                placeholder="Search a stock inquiry"
                emptyMessage="No stock inquiry matches that."
                fetchOptions={(query) => searchStockInquiryOptions(query)}
                selectedOption={
                  state.stock_inquiry_id
                    ? {
                        value: state.stock_inquiry_id,
                        label: state.stock_inquiry_label,
                      }
                    : undefined
                }
                onChange={(v) => {
                  if (!v)
                    setState((prev) => ({
                      ...prev,
                      stock_inquiry_id: '',
                      stock_inquiry_label: '',
                    }));
                }}
                onOptionChange={(opt) =>
                  opt &&
                  setState((prev) => ({
                    ...prev,
                    stock_inquiry_id: opt.value,
                    stock_inquiry_label: opt.label,
                  }))
                }
              />
            }
            customerField={
              <>
                <AsyncCombobox<CustomerLookupItem>
                  ariaLabel="Customer"
                  value={state.customer_name}
                  onChange={(v, item) =>
                    setState((prev) => ({
                      ...prev,
                      customer_id: item?.customer_id ?? '',
                      customer_name: v,
                    }))
                  }
                  fetchOptions={lookupCustomersForRequest}
                  optionValue={(o) => o.debtor_name}
                  optionLabel={(o) => o.debtor_name}
                  optionMeta={(o) => o.customer_code}
                  placeholder="Customer name"
                />
                {!state.customer_id && state.customer_name.trim() && (
                  <Badge variant="secondary" className="mt-1.5">
                    No debtor code
                  </Badge>
                )}
              </>
            }
          />

          <div className="mt-8 flex flex-col gap-2 sm:flex-row sm:justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push(cancelHref)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handleSaveDraft}
              disabled={saving}
            >
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
