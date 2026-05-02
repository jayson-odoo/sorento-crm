'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Plus, Sparkles, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  DebtorLookupItem,
  DOLookupItem,
  PortalAttachment,
  PortalContact,
  PortalSubmissionDetail,
  PortalSubmissionKind,
  PortalUnauthorizedError,
  ProductLookupItem,
  SUBMISSION_LABELS,
  deleteDraftSubmission,
  fetchMe,
  fetchSubmission,
  lookupDebtors,
  lookupProducts,
  saveDraft,
  statusLabel,
  submitDraft,
  uploadAttachment,
} from '../lib/portal-client';
import { AIExtractDialog, AIExtractApplyPayload } from './AIExtractDialog';
import { AttachmentDropzone } from './AttachmentDropzone';
import { AsyncCombobox } from './AsyncCombobox';
import { DOFilterMultiSelect } from './DOFilterMultiSelect';
import { LookupSelect } from './LookupSelect';
import {
  InquiryFormTableRow,
  ProductInquiryFormLayout,
} from '@/app/(protected)/procurement-management/stock-inquiries/components/ProductInquiryFormLayout';

type ProductLine = {
  item_code?: string;
  quantity?: string;
  unit_price?: string;
  total?: string;
  remark?: string;
};

type WidgetKind =
  | 'text'
  | 'textarea'
  | 'date'
  | 'number'
  | 'lookup-select'
  | 'product-async'
  | 'debtor-async'
  | 'do-multi-filter';

interface FieldDef {
  name: string;
  label: string;
  widget?: WidgetKind;
  setKey?: string;
  defaultFromContact?: 'fullname' | 'first_name';
  defaultToday?: boolean;
  placeholder?: string;
}

const FIELDS: Record<PortalSubmissionKind, FieldDef[]> = {
  stock_inquiry: [
    { name: 'product_code', label: 'Product code', widget: 'product-async' },
    { name: 'item_description', label: 'Item description', widget: 'textarea' },
    { name: 'quantity', label: 'Quantity', widget: 'number' },
    { name: 'delivery_date', label: 'Required delivery date', widget: 'date' },
    { name: 'project_customer', label: 'Project customer', widget: 'debtor-async' },
    { name: 'project_name', label: 'Project name' },
    { name: 'salesperson', label: 'Salesperson', defaultFromContact: 'fullname' },
    { name: 'remark', label: 'Remark', widget: 'textarea' },
    { name: 'additional_remark', label: 'Additional remark', widget: 'textarea' },
  ],
  complaint: [
    {
      name: 'delivery_order_number',
      label: 'Delivery order number(s)',
      widget: 'do-multi-filter',
    },
    { name: 'customer_name', label: 'Customer name', widget: 'debtor-async' },
    { name: 'contact_person', label: 'Contact person' },
    { name: 'contact_number', label: 'Contact number' },
    { name: 'customer_address', label: 'Customer address', widget: 'textarea' },
    {
      name: 'customer_type',
      label: 'Customer type',
      widget: 'lookup-select',
      setKey: 'complaints_customer_type',
    },
    {
      name: 'complaint_date',
      label: 'Complaint date',
      widget: 'date',
      defaultToday: true,
    },
    { name: 'product_code', label: 'Product code', widget: 'product-async' },
    { name: 'product_type', label: 'Product type' },
    {
      name: 'within_warranty',
      label: 'Within warranty',
      widget: 'lookup-select',
      setKey: 'complaints_within_warranty',
    },
    {
      name: 'defects_discovered',
      label: 'Defects discovered',
      widget: 'lookup-select',
      setKey: 'complaints_defects_discovered',
    },
    {
      name: 'complaint_type',
      label: 'Complaint type',
      widget: 'lookup-select',
      setKey: 'complaints_complaint_type',
    },
    {
      name: 'defect_description',
      label: 'Defect description',
      widget: 'textarea',
    },
    {
      name: 'salesperson',
      label: 'Salesperson',
      defaultFromContact: 'fullname',
    },
    { name: 'project_title', label: 'Project title' },
  ],
  purchase_request: [
    { name: 'customer_name', label: 'Customer name' },
    { name: 'project_title', label: 'Project title' },
    { name: 'purpose', label: 'Purpose', widget: 'textarea' },
    { name: 'request_date', label: 'Request date', widget: 'date' },
    {
      name: 'expected_delivery_date',
      label: 'Expected delivery date',
      widget: 'date',
    },
    { name: 'expected_po_date', label: 'Expected PO date', widget: 'date' },
    { name: 'requested_by', label: 'Requested by' },
    { name: 'external_reference', label: 'External reference' },
  ],
  sponsorship_form: [
    { name: 'customer_name', label: 'Customer name' },
    { name: 'project_title', label: 'Project title' },
    { name: 'sponsor_subject', label: 'Sponsor subject' },
    { name: 'purpose', label: 'Purpose', widget: 'textarea' },
    { name: 'delivery_address', label: 'Delivery address', widget: 'textarea' },
    { name: 'total_project_value', label: 'Total project value' },
    { name: 'request_date', label: 'Request date', widget: 'date' },
    {
      name: 'expected_delivery_date',
      label: 'Expected delivery date',
      widget: 'date',
    },
    { name: 'requested_by', label: 'Requested by' },
  ],
};

const HAS_LINES: PortalSubmissionKind[] = ['purchase_request', 'sponsorship_form'];

function fieldSpansFullWidth(f: FieldDef): boolean {
  return f.widget === 'textarea' || f.widget === 'do-multi-filter';
}

interface Props {
  kind: PortalSubmissionKind;
  submissionId?: string;
}

export function SubmissionForm({ kind, submissionId }: Props) {
  const router = useRouter();
  const [loading, setLoading] = useState(Boolean(submissionId));
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [aiExtractOpen, setAiExtractOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [detail, setDetail] = useState<PortalSubmissionDetail | null>(null);
  const [fields, setFields] = useState<Record<string, string | string[]>>({});
  const [products, setProducts] = useState<ProductLine[]>([]);
  const [attachments, setAttachments] = useState<PortalAttachment[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState<PortalContact | null>(null);

  const fieldDefs = FIELDS[kind];
  const showLines = HAS_LINES.includes(kind);
  const isEditable = useMemo(
    () => !detail || detail.is_draft || detail.status === 'rejected',
    [detail],
  );

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((c) => {
        if (!cancelled) setContact(c);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  const defaultsFromContact = useMemo(() => {
    const name = contact?.name?.trim() ?? '';
    if (!name) return { first_name: '', fullname: '' };
    const parts = name.split(/\s+/);
    const [first, ...rest] = parts;
    void rest;
    return { first_name: first ?? '', fullname: name };
  }, [contact]);

  useEffect(() => {
    if (!submissionId) {
      const next: Record<string, string | string[]> = {};
      for (const f of fieldDefs) {
        if (f.widget === 'do-multi-filter') {
          next[f.name] = [];
          continue;
        }
        if (f.defaultFromContact === 'fullname') {
          next[f.name] = defaultsFromContact.fullname;
        } else if (f.defaultFromContact === 'first_name') {
          next[f.name] = defaultsFromContact.first_name;
        } else if (f.defaultToday) {
          next[f.name] = new Date().toISOString().slice(0, 10);
        } else {
          next[f.name] = '';
        }
      }
      setFields(next);
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchSubmission(kind, submissionId);
        if (cancelled) return;
        setDetail(data);
        const next: Record<string, string | string[]> = {};
        for (const f of fieldDefs) {
          const v = (data as Record<string, unknown>)[f.name];
          if (f.widget === 'do-multi-filter') {
            if (Array.isArray(v)) {
              next[f.name] = v.map((x) => String(x).trim()).filter(Boolean);
            } else if (v == null || v === '') {
              next[f.name] = [];
            } else {
              next[f.name] = String(v)
                .split(/[,\n]/)
                .map((x) => x.trim())
                .filter(Boolean);
            }
          } else {
            next[f.name] = v == null ? '' : String(v);
          }
        }
        setFields(next);
        if (showLines) {
          const lines = (data as { products?: ProductLine[] }).products ?? [];
          setProducts(lines.map((l) => ({ ...l })));
        }
        setAttachments((data.attachments as PortalAttachment[]) ?? []);
      } catch (e) {
        if (e instanceof PortalUnauthorizedError) {
          router.replace('/portal/verify?reason=expired');
          return;
        }
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fieldDefs, kind, router, showLines, submissionId, defaultsFromContact]);

  const cleanedFields = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const f of fieldDefs) {
      const raw = fields[f.name];
      if (f.widget === 'do-multi-filter') {
        const arr = Array.isArray(raw) ? raw : [];
        const cleaned = arr.map((x) => String(x).trim()).filter(Boolean);
        if (cleaned.length > 0) {
          out[f.name] = cleaned.join(', ');
        }
      } else {
        const value = (typeof raw === 'string' ? raw : '').trim();
        if (value) out[f.name] = value;
      }
    }
    return out;
  }, [fieldDefs, fields]);

  const cleanedProducts = useMemo(() => {
    if (!showLines) return undefined;
    return products
      .map((p) => ({
        item_code: (p.item_code ?? '').trim() || null,
        quantity: (p.quantity ?? '').trim() || null,
        unit_price: (p.unit_price ?? '').trim() || null,
        total: (p.total ?? '').trim() || null,
        remark: (p.remark ?? '').trim() || null,
      }))
      .filter((p) => p.item_code || p.quantity || p.remark);
  }, [products, showLines]);

  const flushPendingFiles = async (id: string) => {
    if (pendingFiles.length === 0) return;
    const uploaded: PortalAttachment[] = [];
    const remaining: File[] = [];
    const errors: string[] = [];
    for (const file of pendingFiles) {
      try {
        const att = await uploadAttachment(kind, id, file);
        uploaded.push(att);
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'unknown error';
        errors.push(`${file.name}: ${msg}`);
        remaining.push(file);
      }
    }
    if (uploaded.length > 0) setAttachments((prev) => [...prev, ...uploaded]);
    setPendingFiles(remaining);
    if (errors.length > 0) {
      throw new Error(
        `${errors.length} attachment${errors.length > 1 ? 's' : ''} failed: ${errors.join('; ')}`,
      );
    }
  };

  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      const saved = await saveDraft(kind, cleanedFields, cleanedProducts, submissionId);
      await flushPendingFiles(saved.id);
      toast.success('Draft saved.');
      router.replace('/portal');
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace('/portal/verify?reason=expired');
        return;
      }
      toast.error(e instanceof Error ? e.message : 'Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      let id = submissionId;
      if (!id) {
        const saved = await saveDraft(kind, cleanedFields, cleanedProducts);
        id = saved.id;
      }
      await flushPendingFiles(id);
      await submitDraft(kind, id, cleanedFields, cleanedProducts);
      toast.success('Submitted.');
      router.replace('/portal');
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace('/portal/verify?reason=expired');
        return;
      }
      toast.error(e instanceof Error ? e.message : 'Failed to submit.');
    } finally {
      setSubmitting(false);
      setConfirmOpen(false);
    }
  };

  const handleDelete = async () => {
    if (!submissionId) return;
    setDeleting(true);
    try {
      await deleteDraftSubmission(kind, submissionId);
      toast.success('Draft deleted.');
      router.replace('/portal');
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace('/portal/verify?reason=expired');
        return;
      }
      toast.error(e instanceof Error ? e.message : 'Failed to delete draft.');
    } finally {
      setDeleting(false);
      setConfirmDeleteOpen(false);
    }
  };

  const setFieldValue = (name: string, value: string | string[]) => {
    setFields((prev) => ({ ...prev, [name]: value }));
  };

  const handleAIExtractApply = (payload: AIExtractApplyPayload) => {
    let applied = 0;
    setFields((prev) => {
      const next = { ...prev };
      for (const [name, value] of Object.entries(payload.values)) {
        const existing = prev[name];
        const isEmpty = Array.isArray(existing)
          ? existing.length === 0
          : !((existing ?? '') as string).trim();
        if (!isEmpty) continue;
        next[name] = value;
        applied += 1;
      }
      return next;
    });
    if (payload.alsoAttach && payload.files.length > 0) {
      setPendingFiles((prev) => [...prev, ...payload.files]);
    }
    if (applied === 0) {
      toast.message('No empty fields to fill — your existing entries were kept.');
    }
  };

  // For complaint kind: when product is picked from search results, derive
  // product_type from the product's category (code preferred, name fallback).
  const handleProductItemSelected = (fieldName: string, item: ProductLookupItem) => {
    if (kind !== 'complaint') return;
    if (fieldName !== 'product_code') return;
    const derived = (item.category_code ?? item.category_name ?? '').trim();
    if (!derived) return;
    setFields((prev) => ({ ...prev, product_type: derived }));
  };

  // For complaint kind: when DO multi-select changes, auto-populate customer
  // name / product code / product type from the chosen DOs. Multiple distinct
  // values join with ", ". Product type is derived per code via category code.
  const handleDOItemsChanged = async (items: DOLookupItem[]) => {
    if (kind !== 'complaint') return;
    if (items.length === 0) return;
    const customerNames = Array.from(
      new Set(
        items
          .map((i) => (i.debtor_name ?? i.customer_name ?? '').trim())
          .filter(Boolean),
      ),
    );
    const productCodes = Array.from(
      new Set(
        items
          .flatMap((i) => i.products ?? [])
          .map((p) => (p ?? '').trim())
          .filter(Boolean),
      ),
    );
    setFields((prev) => ({
      ...prev,
      customer_name: customerNames.join(', '),
      product_code: productCodes.join(', '),
    }));
    if (productCodes.length > 0) {
      try {
        const cats = new Set<string>();
        for (const code of productCodes) {
          const matches = await lookupProducts(code, 5);
          const exact = matches.find((m) => m.product_code === code);
          const c = (exact?.category_code ?? exact?.category_name ?? '').trim();
          if (c) cats.add(c);
        }
        if (cats.size > 0) {
          setFields((prev) => ({ ...prev, product_type: Array.from(cats).join(', ') }));
        }
      } catch {
        // Best-effort — leave product_type as-is on lookup failure.
      }
    }
  };

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading...</div>;
  }

  const statusBadge = detail?.is_draft
    ? { label: 'Draft', variant: 'warning' as const }
    : detail?.status
      ? {
          label: statusLabel(detail.status),
          variant:
            detail.status === 'rejected'
              ? ('destructive' as const)
              : detail.status === 'approved' || detail.status === 'responded'
                ? ('success' as const)
                : ('secondary' as const),
        }
      : null;

  return (
    <div className="min-h-screen max-w-3xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/portal">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
        </Button>
        <div className="flex items-center gap-3">
          {kind === 'complaint' && isEditable && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setAiExtractOpen(true)}
              data-testid="ai-extract-trigger"
            >
              <Sparkles className="h-4 w-4 mr-2 text-primary" />
              AI Extract
            </Button>
          )}
          {detail?.reference && (
            <span className="text-sm text-muted-foreground">{detail.reference}</span>
          )}
        </div>
      </div>

      {!isEditable && (
        <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          This submission is not editable. Status:{' '}
          <span className="font-medium text-foreground">{statusLabel(detail?.status ?? '')}</span>
          .
        </div>
      )}
      {detail?.rejection_reason && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <p className="font-medium">Rejection reason</p>
          <p>{detail.rejection_reason}</p>
        </div>
      )}

      {kind === 'stock_inquiry' ? (
        <StockInquiryFormSection
          submissionId={submissionId}
          detail={detail}
          fieldDefs={fieldDefs}
          fields={fields}
          setFieldValue={setFieldValue}
          isEditable={isEditable}
          statusBadge={statusBadge}
          onProductItemSelected={handleProductItemSelected}
        />
      ) : kind === 'complaint' ? (
        <ComplaintFormSection
          submissionId={submissionId}
          detail={detail}
          fieldDefs={fieldDefs}
          fields={fields}
          setFieldValue={setFieldValue}
          isEditable={isEditable}
          statusBadge={statusBadge}
          onProductItemSelected={handleProductItemSelected}
          onDOItemsChanged={handleDOItemsChanged}
        />
      ) : (
        <PurchaseRequestFormSection
          kind={kind}
          submissionId={submissionId}
          detail={detail}
          fieldDefs={fieldDefs}
          fields={fields}
          setFieldValue={setFieldValue}
          isEditable={isEditable}
          statusBadge={statusBadge}
          onProductItemSelected={handleProductItemSelected}
        />
      )}

      {showLines && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Items</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {products.map((line, index) => (
              <div key={index} className="rounded-md border border-border p-3 space-y-2">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <div className="space-y-1.5">
                    <Label>Item code</Label>
                    <AsyncCombobox<ProductLookupItem>
                      value={line.item_code ?? ''}
                      onChange={(v) =>
                        setProducts((prev) =>
                          prev.map((p, i) => (i === index ? { ...p, item_code: v } : p)),
                        )
                      }
                      fetchOptions={(q) => lookupProducts(q)}
                      optionValue={(o) => o.product_code}
                      optionLabel={(o) => o.product_code}
                      optionMeta={(o) => o.product_name ?? ''}
                      disabled={!isEditable}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Quantity</Label>
                    <Input
                      type="number"
                      inputMode="numeric"
                      min="0"
                      value={line.quantity ?? ''}
                      onChange={(e) =>
                        setProducts((prev) =>
                          prev.map((p, i) =>
                            i === index ? { ...p, quantity: e.target.value } : p,
                          ),
                        )
                      }
                      disabled={!isEditable}
                    />
                  </div>
                  {kind === 'sponsorship_form' && (
                    <>
                      <div className="space-y-1.5">
                        <Label>Unit price</Label>
                        <Input
                          type="number"
                          inputMode="decimal"
                          min="0"
                          step="0.01"
                          value={line.unit_price ?? ''}
                          onChange={(e) =>
                            setProducts((prev) =>
                              prev.map((p, i) =>
                                i === index ? { ...p, unit_price: e.target.value } : p,
                              ),
                            )
                          }
                          disabled={!isEditable}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Total</Label>
                        <Input
                          type="number"
                          inputMode="decimal"
                          min="0"
                          step="0.01"
                          value={line.total ?? ''}
                          onChange={(e) =>
                            setProducts((prev) =>
                              prev.map((p, i) =>
                                i === index ? { ...p, total: e.target.value } : p,
                              ),
                            )
                          }
                          disabled={!isEditable}
                        />
                      </div>
                    </>
                  )}
                </div>
                <div className="space-y-1.5">
                  <Label>Remark</Label>
                  <Textarea
                    value={line.remark ?? ''}
                    onChange={(e) =>
                      setProducts((prev) =>
                        prev.map((p, i) =>
                          i === index ? { ...p, remark: e.target.value } : p,
                        ),
                      )
                    }
                    rows={2}
                    disabled={!isEditable}
                  />
                </div>
                <div className="flex justify-end">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!isEditable}
                    onClick={() =>
                      setProducts((prev) => prev.filter((_, i) => i !== index))
                    }
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Remove
                  </Button>
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!isEditable}
              onClick={() => setProducts((prev) => [...prev, {}])}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add item
            </Button>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Attachments</CardTitle>
        </CardHeader>
        <CardContent>
          <AttachmentDropzone
            kind={kind}
            submissionId={submissionId ?? null}
            attachments={attachments}
            onChange={setAttachments}
            disabled={!isEditable}
            pendingFiles={pendingFiles}
            onPendingFilesChange={setPendingFiles}
          />
        </CardContent>
      </Card>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex flex-wrap gap-2 justify-end pt-2">
        {submissionId && detail?.is_draft && (
          <Button
            variant="outline"
            className="text-destructive border-destructive/50 hover:bg-destructive/10 mr-auto"
            onClick={() => setConfirmDeleteOpen(true)}
            disabled={saving || submitting || deleting}
          >
            <Trash2 className="size-4 mr-1" />
            {deleting ? 'Deleting...' : 'Delete draft'}
          </Button>
        )}
        <Button
          variant="ghost"
          onClick={() => router.replace('/portal')}
          disabled={saving || submitting || deleting}
        >
          Cancel
        </Button>
        <Button
          variant="outline"
          onClick={handleSaveDraft}
          disabled={!isEditable || saving || submitting}
        >
          {saving ? 'Saving...' : 'Save as draft'}
        </Button>
        <Button
          onClick={() => setConfirmOpen(true)}
          disabled={!isEditable || saving || submitting}
        >
          {submitting ? 'Submitting...' : 'Submit'}
        </Button>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Submit this {SUBMISSION_LABELS[kind].toLowerCase()}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Once submitted, your team will be notified. You can no longer edit unless it
              is rejected.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleSubmit} disabled={submitting}>
              Submit
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AIExtractDialog
        open={aiExtractOpen}
        onOpenChange={setAiExtractOpen}
        kind={kind}
        fieldDefs={fieldDefs}
        onApply={handleAIExtractApply}
      />

      <AlertDialog open={confirmDeleteOpen} onOpenChange={setConfirmDeleteOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this draft?</AlertDialogTitle>
            <AlertDialogDescription>
              This action cannot be undone. The draft will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

interface SectionProps {
  submissionId?: string;
  detail: PortalSubmissionDetail | null;
  fieldDefs: FieldDef[];
  fields: Record<string, string | string[]>;
  setFieldValue: (name: string, value: string | string[]) => void;
  isEditable: boolean;
  statusBadge: { label: string; variant: 'warning' | 'destructive' | 'success' | 'secondary' } | null;
  onProductItemSelected: (fieldName: string, item: ProductLookupItem) => void;
  onDOItemsChanged?: (items: DOLookupItem[]) => void;
}

function StockInquiryFormSection({
  submissionId,
  detail,
  fieldDefs,
  fields,
  setFieldValue,
  isEditable,
  statusBadge,
  onProductItemSelected,
}: SectionProps) {
  const fieldByName = useMemo(() => {
    const out: Record<string, FieldDef> = {};
    for (const f of fieldDefs) out[f.name] = f;
    return out;
  }, [fieldDefs]);

  const dateValue = detail?.created_at
    ? new Date(detail.created_at).toLocaleDateString(undefined, { dateStyle: 'short' })
    : new Date().toLocaleDateString(undefined, { dateStyle: 'short' });
  const inquiryNumber =
    (detail?.document_number as string | undefined) ||
    (detail?.inquiry_number as string | undefined) ||
    (submissionId ? '—' : 'auto-generated on submit');

  return (
    <div className="space-y-3">
      {statusBadge && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">Status:</span>
          <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
        </div>
      )}
      <ProductInquiryFormLayout>
        <InquiryFormTableRow label="Date">
          <span className="text-sm">{dateValue}</span>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Stock inquiry number">
          <span className="text-sm">{inquiryNumber}</span>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Sales person">
          <FieldControl
            field={fieldByName.salesperson}
            value={fields.salesperson ?? ''}
            onChange={(v) => setFieldValue('salesperson', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Product code">
          <FieldControl
            field={fieldByName.product_code}
            value={fields.product_code ?? ''}
            onChange={(v) => setFieldValue('product_code', v)}
            onItemSelect={(item) => onProductItemSelected('product_code', item)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Item description" labelClassName="items-start pt-3">
          <FieldControl
            field={fieldByName.item_description}
            value={fields.item_description ?? ''}
            onChange={(v) => setFieldValue('item_description', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Project customer">
          <FieldControl
            field={fieldByName.project_customer}
            value={fields.project_customer ?? ''}
            onChange={(v) => setFieldValue('project_customer', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Project name">
          <FieldControl
            field={fieldByName.project_name}
            value={fields.project_name ?? ''}
            onChange={(v) => setFieldValue('project_name', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Qty">
          <FieldControl
            field={fieldByName.quantity}
            value={fields.quantity ?? ''}
            onChange={(v) => setFieldValue('quantity', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Delivery date">
          <FieldControl
            field={fieldByName.delivery_date}
            value={fields.delivery_date ?? ''}
            onChange={(v) => setFieldValue('delivery_date', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Remark" labelClassName="items-start pt-3">
          <FieldControl
            field={fieldByName.remark}
            value={fields.remark ?? ''}
            onChange={(v) => setFieldValue('remark', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Additional remark" labelClassName="items-start pt-3">
          <FieldControl
            field={fieldByName.additional_remark}
            value={fields.additional_remark ?? ''}
            onChange={(v) => setFieldValue('additional_remark', v)}
            disabled={!isEditable}
          />
        </InquiryFormTableRow>
      </ProductInquiryFormLayout>
    </div>
  );
}

function ComplaintFormSection({
  fieldDefs,
  fields,
  setFieldValue,
  isEditable,
  statusBadge,
  onProductItemSelected,
  onDOItemsChanged,
}: SectionProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2">
        <CardTitle>Complaint Information</CardTitle>
        {statusBadge && <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>}
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {fieldDefs.map((f) => (
            <div
              key={f.name}
              className={fieldSpansFullWidth(f) ? 'md:col-span-2' : undefined}
            >
              <FieldInput
                field={f}
                value={fields[f.name] ?? ''}
                onChange={(v) => setFieldValue(f.name, v)}
                onItemSelect={(item) => onProductItemSelected(f.name, item)}
                onDOItemsChange={onDOItemsChanged}
                disabled={!isEditable}
              />
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function PurchaseRequestFormSection({
  kind,
  fieldDefs,
  fields,
  setFieldValue,
  isEditable,
  statusBadge,
  onProductItemSelected,
}: SectionProps & { kind: PortalSubmissionKind }) {
  const heading =
    kind === 'sponsorship_form' ? 'Project Sales Sponsorship Form' : 'Purchase Request';
  return (
    <div className="lg:col-span-2 max-w-5xl mx-auto w-full">
      <Card className="border-2 shadow-sm">
        <CardContent className="pt-6 pb-8 px-5 sm:px-10">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex flex-wrap gap-2">
              <Badge variant="secondary">{SUBMISSION_LABELS[kind]}</Badge>
              {statusBadge && (
                <Badge variant={statusBadge.variant}>{statusBadge.label}</Badge>
              )}
            </div>
          </div>
          <h2 className="text-center text-xl font-semibold tracking-tight border-b border-border pb-4 mb-6">
            {heading}
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-10 gap-y-5">
            {fieldDefs.map((f) => (
              <div
                key={f.name}
                className={fieldSpansFullWidth(f) ? 'sm:col-span-2' : undefined}
              >
                <FieldInput
                  field={f}
                  value={fields[f.name] ?? ''}
                  onChange={(v) => setFieldValue(f.name, v)}
                  onItemSelect={(item) => onProductItemSelected(f.name, item)}
                  disabled={!isEditable}
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function FieldInput({
  field,
  value,
  onChange,
  onItemSelect,
  onDOItemsChange,
  disabled,
}: {
  field: FieldDef;
  value: string | string[];
  onChange: (v: string | string[]) => void;
  onItemSelect?: (item: ProductLookupItem) => void;
  onDOItemsChange?: (items: DOLookupItem[]) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={field.name}>{field.label}</Label>
      <FieldControl
        field={field}
        value={value}
        onChange={onChange}
        onItemSelect={onItemSelect}
        onDOItemsChange={onDOItemsChange}
        disabled={disabled}
      />
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
  onItemSelect,
  onDOItemsChange,
  disabled,
}: {
  field: FieldDef;
  value: string | string[];
  onChange: (v: string | string[]) => void;
  onItemSelect?: (item: ProductLookupItem) => void;
  onDOItemsChange?: (items: DOLookupItem[]) => void;
  disabled?: boolean;
}) {
  const widget: WidgetKind = field.widget ?? 'text';
  const stringValue = typeof value === 'string' ? value : '';
  const arrayValue = Array.isArray(value) ? value : [];

  switch (widget) {
    case 'textarea':
      return (
        <Textarea
          id={field.name}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          disabled={disabled}
        />
      );
    case 'date':
      return (
        <Input
          id={field.name}
          type="date"
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
        />
      );
    case 'number':
      return (
        <Input
          id={field.name}
          type="number"
          inputMode="numeric"
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
        />
      );
    case 'lookup-select':
      return (
        <LookupSelect
          id={field.name}
          setKey={field.setKey ?? ''}
          value={stringValue}
          onChange={(v) => onChange(v)}
          placeholder={field.placeholder ?? 'Select...'}
          disabled={disabled}
        />
      );
    case 'product-async':
      return (
        <AsyncCombobox<ProductLookupItem>
          id={field.name}
          value={stringValue}
          onChange={(v, item) => {
            onChange(v);
            if (item && onItemSelect) onItemSelect(item);
          }}
          fetchOptions={(q) => lookupProducts(q)}
          optionValue={(o) => o.product_code}
          optionLabel={(o) => o.product_code}
          optionMeta={(o) => o.product_name ?? ''}
          placeholder={field.placeholder ?? 'Search products...'}
          disabled={disabled}
        />
      );
    case 'debtor-async':
      return (
        <AsyncCombobox<DebtorLookupItem>
          id={field.name}
          value={stringValue}
          onChange={(v) => onChange(v)}
          fetchOptions={(q) => lookupDebtors(q)}
          optionValue={(o) => o.debtor_name}
          optionLabel={(o) => o.debtor_name}
          placeholder={field.placeholder ?? 'Search debtors...'}
          disabled={disabled}
        />
      );
    case 'do-multi-filter':
      return (
        <DOFilterMultiSelect
          id={field.name}
          value={arrayValue}
          onChange={(vs, items) => {
            onChange(vs);
            if (items && onDOItemsChange) onDOItemsChange(items);
          }}
          disabled={disabled}
        />
      );
    case 'text':
    default:
      return (
        <Input
          id={field.name}
          type="text"
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
        />
      );
  }
}
