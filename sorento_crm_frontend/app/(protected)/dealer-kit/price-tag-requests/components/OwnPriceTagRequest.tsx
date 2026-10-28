'use client';

/**
 * A salesperson's own price tag request on the Dealer Kit request page (PORTAL-P4-REQUESTS S7,
 * card v1.2 Q8). The same record header and Request / Lines tabs as the staff page; New
 * (`/new`, `?from=` duplicates) and Edit (`?edit=1`, `&revise=1` for a revision) are this layout
 * with the fields as inputs in place. Every read and write runs the portal's own routes through
 * My Requests, so the drafts, submit, proof review, collection and revision rules are the
 * portal's. Marketing's tools (claim, designer, void, export, line prices) are not here.
 */

import { useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle2, FileText, HandCoins, ListOrdered, MessageSquare, Paperclip, Save, Send, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import BackToList from '@/components/common/BackToList';
import { PageHeader } from '@/components/common/PageHeader';
import { MyRequestActions } from '@/components/common/MyRequestActions';
import { OwnAttachmentDelete, OwnAttachmentUpload } from '@/components/common/OwnRequestAttachmentActions';
import { PrintBySelect } from '@/components/dealer-kit/PrintBySelect';
import { priceTagStatusLabel, priceTagStatusPillClass } from '@/lib/price-tag-status';
import { formatDate, formatDateTimeInMalaysia } from '@/lib/helpers';
import { printByLabel, type PrintBy } from '@/lib/dealer-kit/print-collection';
import { codeWithName } from '@/lib/product-display';
import { useMyPriceTagDebtors, useMyPriceTagMutations, useMyPriceTagRequest } from '@/hooks/useMyRequests';
import {
  searchMyPriceTagItems,
  type MyPriceTagLineWrite,
  type MyPriceTagRequestDetail,
  type MyPriceTagWrite,
} from '@/services/myRequestsService';

const LIST_PATH = '/dealer-kit/price-tag-requests';
const STATUS_PILL_BASE = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold';

type Tab = 'request' | 'lines' | 'attachments';

/** A line being edited: what is written back, plus what a reader sees for it. */
type EditLine = MyPriceTagLineWrite & { key: string; label: string };

interface Draft {
  debtor_code: string;
  debtor_name: string;
  needed_by_date: string;
  notes: string;
  print_by: PrintBy | null;
  lines: EditLine[];
}

const EMPTY: Draft = { debtor_code: '', debtor_name: '', needed_by_date: '', notes: '', print_by: null, lines: [] };

function draftFrom(row: MyPriceTagRequestDetail | undefined): Draft {
  if (!row) return EMPTY;
  return {
    debtor_code: row.debtor_code ?? '',
    debtor_name: row.debtor_name ?? '',
    needed_by_date: row.needed_by_date ?? '',
    notes: row.notes ?? '',
    print_by: (row.print_by as PrintBy | null) ?? null,
    lines: (row.lines ?? []).map((line, i) => ({
      key: line.id || `line-${i}`,
      label: codeWithName(line.code, line.name) || line.name || line.code || 'Item',
      line_type: line.line_type,
      product_id: line.product_id ?? null,
      product_set_id: line.product_set_id ?? null,
      quantity: line.quantity || 1,
      remarks: line.remarks ?? null,
    })),
  };
}

function body(draft: Draft): MyPriceTagWrite {
  return {
    debtor_code: draft.debtor_code || null,
    debtor_name: draft.debtor_name || null,
    needed_by_date: draft.needed_by_date || null,
    notes: draft.notes || null,
    print_by: draft.print_by,
    lines: draft.lines.map(({ line_type, product_id, product_set_id, quantity, remarks }) => ({
      line_type,
      product_id,
      product_set_id,
      quantity,
      remarks,
    })),
  };
}

export default function OwnPriceTagRequest({ requestId }: { requestId?: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const creating = !requestId;
  const revising = !creating && search?.get('revise') === '1';
  const editing = creating || search?.get('edit') === '1' || revising;
  const fromId = creating ? search?.get('from') : null;

  const { data: row, isLoading } = useMyPriceTagRequest(requestId ?? fromId);
  const debtors = useMyPriceTagDebtors(editing);
  const m = useMyPriceTagMutations();

  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [tab, setTab] = useState<Tab>('request');
  const [reason, setReason] = useState('');
  const [changesOpen, setChangesOpen] = useState(false);
  const [changeNote, setChangeNote] = useState('');

  useEffect(() => {
    if (editing) setDraft(draftFrom(row));
  }, [editing, row]);

  const busy =
    m.create.isPending ||
    m.update.isPending ||
    m.submit.isPending ||
    m.remove.isPending ||
    m.approve.isPending ||
    m.requestChanges.isPending ||
    m.collect.isPending ||
    m.revise.isPending;

  const debtorOptions: SearchableSelectOption[] = useMemo(
    () =>
      (debtors.data ?? []).map((d) => {
        const code = d.customer_code ?? d.debtor_code ?? '';
        const name = d.customer_name ?? d.debtor_name ?? code;
        return { value: code, label: code ? `${code} - ${name}` : name, searchText: `${code} ${name}` };
      }),
    [debtors.data],
  );

  const set = (patch: Partial<Draft>) => setDraft((prev) => ({ ...prev, ...patch }));
  const view = (id: string) => router.push(`${LIST_PATH}/${encodeURIComponent(id)}`);

  /** Save the draft (create or update) and answer its id. */
  const save = async (): Promise<string> => {
    if (creating) return (await m.create.mutateAsync(body(draft))).id;
    await m.update.mutateAsync({ id: requestId as string, data: body(draft) });
    return requestId as string;
  };

  const saveAsDraft = async () => {
    try {
      const id = await save();
      if (creating) router.replace(`${LIST_PATH}/${encodeURIComponent(id)}`);
      else view(id);
    } catch {
      // The hook already said why.
    }
  };

  const saveAndSubmit = async () => {
    try {
      const id = await save();
      await m.submit.mutateAsync(id);
      if (creating) router.replace(`${LIST_PATH}/${encodeURIComponent(id)}`);
      else view(id);
    } catch {
      // The hook already said why.
    }
  };

  const sendRevision = async () => {
    if (!requestId || !row) return;
    const { lines, ...fields } = body(draft);
    try {
      await m.revise.mutateAsync({
        id: requestId,
        input: { reason, expectedRevisionNo: row.revision_no ?? 0, fields, products: lines ?? [] },
      });
      view(requestId);
    } catch {
      // The hook already said why.
    }
  };

  const title = creating ? 'New Price Tag Request' : (row?.doc_number ?? 'Price Tag Request');
  const header = (
    <PageHeader title={title} actions={<BackToList listPath={LIST_PATH} label="Back to price tag requests" />} />
  );

  if (isLoading && (requestId || fromId)) {
    return (
      <div className="space-y-4">
        {header}
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (requestId && !row) {
    return (
      <div className="space-y-4">
        {header}
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">Price tag request not found</div>
        </Card>
      </div>
    );
  }

  const isDraft = creating || Boolean(row?.portal_draft_at);
  const status = creating ? 'draft' : isDraft ? 'draft' : (row?.status ?? '');
  const revisable = !isDraft && Boolean(row?.revision?.allowed);

  const editActions = (
    <div className="flex flex-wrap items-center gap-2">
      {revising ? (
        <Button variant="primary" size="sm" onClick={() => void sendRevision()} disabled={busy || !reason.trim()}>
          <Send className="size-4" />
          Send revision
        </Button>
      ) : (
        <>
          <Button variant="outline" size="sm" onClick={() => void saveAsDraft()} disabled={busy}>
            <Save className="size-4" />
            Save as draft
          </Button>
          <Button variant="primary" size="sm" onClick={() => void saveAndSubmit()} disabled={busy}>
            <Send className="size-4" />
            Submit
          </Button>
        </>
      )}
    </div>
  );

  const viewActions = row ? (
    <div className="flex flex-wrap items-center gap-2">
      {row.status === 'proof_ready' && !isDraft && (
        <>
          <Button variant="outline" size="sm" onClick={() => setChangesOpen(true)} disabled={busy}>
            <MessageSquare className="size-4" />
            Request changes
          </Button>
          <Button variant="primary" size="sm" onClick={() => m.approve.mutate(row.id)} disabled={busy}>
            <CheckCircle2 className="size-4" />
            Approve proof
          </Button>
        </>
      )}
      {row.status === 'ready_for_collection' && !isDraft && (
        <Button variant="primary" size="sm" onClick={() => m.collect.mutate(row.id)} disabled={busy}>
          <HandCoins className="size-4" />
          Mark collected
        </Button>
      )}
      <MyRequestActions
        status={isDraft ? 'draft' : 'submitted'}
        revisable={revisable}
        busy={busy}
        onEdit={() => router.push(`${LIST_PATH}/${encodeURIComponent(row.id)}?edit=1`)}
        onRevise={() => router.push(`${LIST_PATH}/${encodeURIComponent(row.id)}?edit=1&revise=1`)}
        onDuplicate={() => router.push(`${LIST_PATH}/new?from=${encodeURIComponent(row.id)}`)}
        onDelete={() => m.remove.mutate(row.id, { onSuccess: () => router.push(LIST_PATH) })}
        onSubmit={() => m.submit.mutate(row.id)}
      />
    </div>
  ) : null;

  const lines = editing ? draft.lines : draftFrom(row).lines;
  const attachments = row?.attachments ?? [];
  const refreshKeys = [['my-request', 'price_tag_request']];

  return (
    <div className="space-y-4">
      {header}

      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0 space-y-1">
              <div className="flex min-w-0 flex-wrap items-center gap-3">
                <CardTitle className="text-lg">{creating ? 'New request' : row?.doc_number}</CardTitle>
                {status && (
                  <span className={`${STATUS_PILL_BASE} ${priceTagStatusPillClass(status)}`}>
                    {priceTagStatusLabel(status)}
                  </span>
                )}
              </div>
              {row && !creating && (
                <p className="text-sm text-muted-foreground">
                  Created: {formatDateTimeInMalaysia(row.created_at)}
                  {' · '}
                  Assigned to: {row.assigned_to_name ?? 'Unclaimed'}
                  {' · '}
                  Printing: {printByLabel(row.print_by)}
                </p>
              )}
            </div>
            {editing ? editActions : viewActions}
          </div>
        </CardHeader>
      </Card>

      <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start">
          <TabsTrigger value="request">
            <FileText />
            <span>Request</span>
          </TabsTrigger>
          <TabsTrigger value="lines">
            <ListOrdered />
            <span>Lines</span>
          </TabsTrigger>
          {!creating && (
            <TabsTrigger value="attachments">
              <Paperclip />
              <span>Sales Order</span>
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="request" className="mt-0 space-y-4 focus-visible:outline-none">
          <Card>
            <CardContent className="px-4 py-4">
              {revising && (
                <div className="mb-4">
                  <Label htmlFor="pt-revise-reason">Reason for the revision</Label>
                  <Textarea
                    id="pt-revise-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    className="mt-1"
                  />
                </div>
              )}
              <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
                <div>
                  <span className="block text-muted-foreground">Customer</span>
                  {editing ? (
                    <SearchableSelect
                      value={draft.debtor_code}
                      onChange={(code) => {
                        const hit = (debtors.data ?? []).find(
                          (d) => (d.customer_code ?? d.debtor_code ?? '') === code,
                        );
                        set({
                          debtor_code: code,
                          debtor_name: hit?.customer_name ?? hit?.debtor_name ?? '',
                        });
                      }}
                      options={debtorOptions}
                      selectedOption={
                        draft.debtor_code
                          ? { value: draft.debtor_code, label: `${draft.debtor_code} - ${draft.debtor_name}` }
                          : undefined
                      }
                      placeholder="Select customer"
                      clearable
                      triggerClassName="mt-1"
                    />
                  ) : (
                    <>
                      <p className="font-medium">{row?.debtor_name ?? '-'}</p>
                      {row?.debtor_code && <p className="text-xs text-muted-foreground">{row.debtor_code}</p>}
                    </>
                  )}
                </div>
                <div>
                  <span className="block text-muted-foreground">Need by</span>
                  {editing ? (
                    <Input
                      type="date"
                      aria-label="Need by"
                      value={draft.needed_by_date}
                      onChange={(e) => set({ needed_by_date: e.target.value })}
                      className="mt-1"
                    />
                  ) : (
                    <p className="font-medium">{row?.needed_by_date ? formatDate(new Date(row.needed_by_date)) : '-'}</p>
                  )}
                </div>
                <div>
                  <span className="block text-muted-foreground">Printing</span>
                  {editing ? (
                    <PrintBySelect value={draft.print_by} onChange={(next) => set({ print_by: next })} />
                  ) : (
                    <p className="font-medium">{printByLabel(row?.print_by)}</p>
                  )}
                </div>
              </div>
              <div className="mt-4">
                <span className="block text-sm text-muted-foreground">Notes</span>
                {editing ? (
                  <Textarea
                    aria-label="Notes"
                    value={draft.notes}
                    onChange={(e) => set({ notes: e.target.value })}
                    className="mt-1"
                  />
                ) : (
                  <p className="mt-1 text-sm">{row?.notes || <span className="text-muted-foreground">No notes</span>}</p>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="lines" className="mt-0 space-y-4 focus-visible:outline-none">
          <Card>
            <CardHeader className="px-4 py-3">
              <CardTitle className="text-base">Lines ({lines.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 px-4 pb-4">
              {lines.length === 0 && (
                <div className="py-6 text-center">
                  <div className="text-sm font-semibold">No lines yet</div>
                  <p className="text-sm text-muted-foreground">Add the products to print tags for.</p>
                </div>
              )}
              {lines.map((line, index) => (
                <div key={line.key} className="flex flex-wrap items-center gap-3 border-b pb-3 last:border-b-0">
                  <span className="min-w-0 flex-1 truncate text-sm font-medium" title={line.label}>
                    {line.label}
                  </span>
                  {editing ? (
                    <>
                      <Input
                        type="number"
                        min={1}
                        aria-label={`Quantity for ${line.label}`}
                        value={line.quantity}
                        onChange={(e) => {
                          const quantity = Math.max(1, Number(e.target.value) || 1);
                          set({ lines: draft.lines.map((l, i) => (i === index ? { ...l, quantity } : l)) });
                        }}
                        className="w-24"
                      />
                      <Button
                        mode="icon"
                        variant="ghost"
                        aria-label={`Remove ${line.label}`}
                        title={`Remove ${line.label}`}
                        onClick={() => set({ lines: draft.lines.filter((_, i) => i !== index) })}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </>
                  ) : (
                    <span className="text-sm text-muted-foreground">Qty {line.quantity}</span>
                  )}
                </div>
              ))}
              {editing && (
                <SearchableSelect
                  value=""
                  onChange={() => undefined}
                  fetchOptions={async (q) =>
                    (await searchMyPriceTagItems(q)).map((item) => ({
                      value: `${item.kind}:${item.id}`,
                      label: codeWithName(item.code, item.name) || item.name,
                      code: item.code,
                    }))
                  }
                  onOptionChange={(option) => {
                    if (!option) return;
                    const [kind, id] = option.value.split(':');
                    const lineType = kind === 'product_set' ? 'product_set' : 'product';
                    set({
                      lines: [
                        ...draft.lines,
                        {
                          key: `new-${Date.now()}`,
                          label: option.label,
                          line_type: lineType,
                          product_id: lineType === 'product' ? id : null,
                          product_set_id: lineType === 'product_set' ? id : null,
                          quantity: 1,
                          remarks: null,
                        },
                      ],
                    });
                  }}
                  placeholder="Add a product or set"
                />
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {!creating && row && (
          <TabsContent value="attachments" className="mt-0 space-y-4 focus-visible:outline-none">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between px-4 py-3">
                <CardTitle className="text-base">Sales Order ({attachments.length})</CardTitle>
                <OwnAttachmentUpload kind="price_tag_request" requestId={row.id} refreshKeys={refreshKeys} />
              </CardHeader>
              <CardContent className="space-y-2 px-4 pb-4">
                {attachments.length === 0 ? (
                  <div className="py-6 text-center">
                    <div className="text-sm font-semibold">No files yet</div>
                    <p className="text-sm text-muted-foreground">The sales order goes here.</p>
                  </div>
                ) : (
                  attachments.map((att) => (
                    <div key={att.link_id} className="flex items-center justify-between gap-3">
                      <span className="truncate text-sm" title={att.filename ?? undefined}>
                        {att.filename || 'Attachment'}
                      </span>
                      {att.can_unlink && <OwnAttachmentDelete linkId={att.link_id} refreshKeys={refreshKeys} />}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      <Dialog open={changesOpen} onOpenChange={setChangesOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request changes</DialogTitle>
            <DialogDescription>What should marketing change on the design?</DialogDescription>
          </DialogHeader>
          <Textarea aria-label="Changes" value={changeNote} onChange={(e) => setChangeNote(e.target.value)} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setChangesOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={busy || !changeNote.trim() || !row}
              onClick={() =>
                row &&
                m.requestChanges.mutate(
                  { id: row.id, note: changeNote.trim() },
                  {
                    onSuccess: () => {
                      setChangesOpen(false);
                      setChangeNote('');
                    },
                  },
                )
              }
            >
              Send
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
