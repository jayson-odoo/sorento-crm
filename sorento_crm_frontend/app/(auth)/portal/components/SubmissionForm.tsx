'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, Plus, Trash2 } from 'lucide-react';
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
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  DOLookupItem,
  DebtorLookupItem,
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
  lookupDeliveryOrders,
  lookupProducts,
  saveDraft,
  submitDraft,
} from '../lib/portal-client';
import { AttachmentDropzone } from './AttachmentDropzone';
import { AsyncCombobox } from './AsyncCombobox';
import { AsyncMultiCombobox } from './AsyncMultiCombobox';
import { LookupSelect } from './LookupSelect';

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
  | 'do-multi-async';

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
  ],
  complaint: [
    { name: 'customer_name', label: 'Customer name' },
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
      name: 'delivery_order_number',
      label: 'Delivery order number(s)',
      widget: 'do-multi-async',
    },
    {
      name: 'complaint_date',
      label: 'Complaint date',
      widget: 'date',
      defaultToday: true,
    },
    { name: 'product_code', label: 'Product code', widget: 'product-async' },
    // TODO: auto-fill product_type from selected product.category_id once a
    // category-code lookup endpoint is exposed; admin can fill manually for now.
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

// Fields that benefit from a 2-column md grid layout (short text fields).
// Multi-line / async-multi widgets always span full width.
function fieldSpansFullWidth(f: FieldDef): boolean {
  return (
    f.widget === 'textarea' ||
    f.widget === 'do-multi-async'
  );
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
  const [deleting, setDeleting] = useState(false);
  const [detail, setDetail] = useState<PortalSubmissionDetail | null>(null);
  const [fields, setFields] = useState<Record<string, string | string[]>>({});
  const [products, setProducts] = useState<ProductLine[]>([]);
  const [attachments, setAttachments] = useState<PortalAttachment[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState<PortalContact | null>(null);

  const fieldDefs = FIELDS[kind];
  const showLines = HAS_LINES.includes(kind);
  const isEditable = useMemo(
    () => !detail || detail.is_draft || detail.status === 'rejected',
    [detail],
  );

  // Fetch portal contact once for default values (salesperson etc.)
  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((c) => {
        if (!cancelled) setContact(c);
      })
      .catch(() => {
        // Ignore — defaults will simply be blank if /me fails.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Helpers to derive default values from contact name.
  const defaultsFromContact = useMemo(() => {
    const name = contact?.name?.trim() ?? '';
    if (!name) return { first_name: '', fullname: '' };
    const parts = name.split(/\s+/);
    const [first, ...rest] = parts;
    void rest; // last name not currently used as a default
    return { first_name: first ?? '', fullname: name };
  }, [contact]);

  // Load existing submission OR initialize with default values.
  useEffect(() => {
    if (!submissionId) {
      // Fresh create: seed defaults.
      const next: Record<string, string | string[]> = {};
      for (const f of fieldDefs) {
        if (f.widget === 'do-multi-async') {
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
          if (f.widget === 'do-multi-async') {
            // Backend may return either an array or a comma/newline-joined string.
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
    // We intentionally re-seed defaults whenever the contact resolves on a
    // fresh-create path, so include defaultsFromContact in deps.
  }, [fieldDefs, kind, router, showLines, submissionId, defaultsFromContact]);

  const cleanedFields = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const f of fieldDefs) {
      const raw = fields[f.name];
      if (f.widget === 'do-multi-async') {
        const arr = Array.isArray(raw) ? raw : [];
        const cleaned = arr.map((x) => String(x).trim()).filter(Boolean);
        if (cleaned.length > 0) {
          // Send as a comma-separated string for legacy text storage; backends
          // that accept arrays will accept this as long as the field is text.
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

  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      await saveDraft(kind, cleanedFields, cleanedProducts, submissionId);
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

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="min-h-screen max-w-3xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/portal">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
        </Button>
        {detail?.reference && (
          <span className="text-sm text-muted-foreground">{detail.reference}</span>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            {submissionId ? 'Edit' : 'New'} {SUBMISSION_LABELS[kind]}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!isEditable && (
            <p className="text-sm text-muted-foreground">
              This submission is not editable. Status: {detail?.status}.
            </p>
          )}
          {detail?.rejection_reason && (
            <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
              <p className="font-medium">Rejection reason</p>
              <p>{detail.rejection_reason}</p>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {fieldDefs.map((f) => (
              <div
                key={f.name}
                className={fieldSpansFullWidth(f) ? 'md:col-span-2' : undefined}
              >
                <FieldInput
                  field={f}
                  value={fields[f.name] ?? ''}
                  onChange={(v) => setFields((prev) => ({ ...prev, [f.name]: v }))}
                  disabled={!isEditable}
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

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

function FieldInput({
  field,
  value,
  onChange,
  disabled,
}: {
  field: FieldDef;
  value: string | string[];
  onChange: (v: string | string[]) => void;
  disabled?: boolean;
}) {
  const widget: WidgetKind = field.widget ?? 'text';
  const stringValue = typeof value === 'string' ? value : '';
  const arrayValue = Array.isArray(value) ? value : [];

  let control: React.ReactNode;
  switch (widget) {
    case 'textarea':
      control = (
        <Textarea
          id={field.name}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          disabled={disabled}
        />
      );
      break;
    case 'date':
      control = (
        <Input
          id={field.name}
          type="date"
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
        />
      );
      break;
    case 'number':
      control = (
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
      break;
    case 'lookup-select':
      control = (
        <LookupSelect
          id={field.name}
          setKey={field.setKey ?? ''}
          value={stringValue}
          onChange={(v) => onChange(v)}
          placeholder={field.placeholder ?? 'Select...'}
          disabled={disabled}
        />
      );
      break;
    case 'product-async':
      control = (
        <AsyncCombobox<ProductLookupItem>
          id={field.name}
          value={stringValue}
          onChange={(v) => onChange(v)}
          fetchOptions={(q) => lookupProducts(q)}
          optionValue={(o) => o.product_code}
          optionLabel={(o) => o.product_code}
          optionMeta={(o) => o.product_name ?? ''}
          placeholder={field.placeholder ?? 'Search products...'}
          disabled={disabled}
        />
      );
      break;
    case 'debtor-async':
      control = (
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
      break;
    case 'do-multi-async':
      control = (
        <AsyncMultiCombobox<DOLookupItem>
          id={field.name}
          value={arrayValue}
          onChange={(vs) => onChange(vs)}
          fetchOptions={(q) => lookupDeliveryOrders(q)}
          optionValue={(o) => o.order_number}
          optionLabel={(o) => o.order_number}
          optionMeta={(o) =>
            [o.debtor_name, o.customer_name].filter(Boolean).join(' • ')
          }
          placeholder={field.placeholder ?? 'Search delivery orders...'}
          disabled={disabled}
        />
      );
      break;
    case 'text':
    default:
      control = (
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

  return (
    <div className="space-y-1.5">
      <Label htmlFor={field.name}>{field.label}</Label>
      {control}
    </div>
  );
}
