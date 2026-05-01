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
  PortalAttachment,
  PortalSubmissionDetail,
  PortalSubmissionKind,
  PortalUnauthorizedError,
  SUBMISSION_LABELS,
  fetchSubmission,
  saveDraft,
  submitDraft,
} from '../lib/portal-client';
import { AttachmentDropzone } from './AttachmentDropzone';

type ProductLine = {
  item_code?: string;
  quantity?: string;
  unit_price?: string;
  total?: string;
  remark?: string;
};

interface FieldDef {
  name: string;
  label: string;
  type?: 'text' | 'textarea' | 'date';
  placeholder?: string;
}

const FIELDS: Record<PortalSubmissionKind, FieldDef[]> = {
  complaint: [
    { name: 'customer_name', label: 'Customer name' },
    { name: 'contact_person', label: 'Contact person' },
    { name: 'contact_number', label: 'Contact number' },
    { name: 'customer_address', label: 'Customer address', type: 'textarea' },
    { name: 'delivery_order_number', label: 'Delivery order number' },
    { name: 'complaint_date', label: 'Complaint date', type: 'date' },
    { name: 'product_code', label: 'Product code' },
    { name: 'product_type', label: 'Product type' },
    { name: 'within_warranty', label: 'Within warranty' },
    { name: 'defects_discovered', label: 'Defects discovered' },
    { name: 'complaint_type', label: 'Complaint type' },
    { name: 'defect_description', label: 'Defect description', type: 'textarea' },
    { name: 'salesperson', label: 'Salesperson' },
    { name: 'project_title', label: 'Project title' },
  ],
  stock_inquiry: [
    { name: 'product_code', label: 'Product code' },
    { name: 'item_description', label: 'Item description', type: 'textarea' },
    { name: 'quantity', label: 'Quantity' },
    { name: 'delivery_date', label: 'Required delivery date' },
    { name: 'project_customer', label: 'Project customer' },
    { name: 'project_name', label: 'Project name' },
    { name: 'salesperson', label: 'Salesperson' },
    { name: 'remark', label: 'Remark', type: 'textarea' },
  ],
  purchase_request: [
    { name: 'customer_name', label: 'Customer name' },
    { name: 'project_title', label: 'Project title' },
    { name: 'purpose', label: 'Purpose', type: 'textarea' },
    { name: 'request_date', label: 'Request date', type: 'date' },
    { name: 'expected_delivery_date', label: 'Expected delivery date', type: 'date' },
    { name: 'expected_po_date', label: 'Expected PO date', type: 'date' },
    { name: 'requested_by', label: 'Requested by' },
    { name: 'external_reference', label: 'External reference' },
  ],
  sponsorship_form: [
    { name: 'customer_name', label: 'Customer name' },
    { name: 'project_title', label: 'Project title' },
    { name: 'sponsor_subject', label: 'Sponsor subject' },
    { name: 'purpose', label: 'Purpose', type: 'textarea' },
    { name: 'delivery_address', label: 'Delivery address', type: 'textarea' },
    { name: 'total_project_value', label: 'Total project value' },
    { name: 'request_date', label: 'Request date', type: 'date' },
    { name: 'expected_delivery_date', label: 'Expected delivery date', type: 'date' },
    { name: 'requested_by', label: 'Requested by' },
  ],
};

const HAS_LINES: PortalSubmissionKind[] = ['purchase_request', 'sponsorship_form'];

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
  const [detail, setDetail] = useState<PortalSubmissionDetail | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [products, setProducts] = useState<ProductLine[]>([]);
  const [attachments, setAttachments] = useState<PortalAttachment[]>([]);
  const [error, setError] = useState<string | null>(null);

  const fieldDefs = FIELDS[kind];
  const showLines = HAS_LINES.includes(kind);
  const isEditable = useMemo(
    () => !detail || detail.is_draft || detail.status === 'rejected',
    [detail]
  );

  useEffect(() => {
    if (!submissionId) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchSubmission(kind, submissionId);
        if (cancelled) return;
        setDetail(data);
        const next: Record<string, string> = {};
        for (const f of fieldDefs) {
          const v = (data as Record<string, unknown>)[f.name];
          next[f.name] = v == null ? '' : String(v);
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
  }, [fieldDefs, kind, router, showLines, submissionId]);

  const cleanedFields = useMemo(() => {
    const out: Record<string, unknown> = {};
    for (const f of fieldDefs) {
      const value = (fields[f.name] ?? '').trim();
      if (value) out[f.name] = value;
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
      const saved = await saveDraft(kind, cleanedFields, cleanedProducts, submissionId);
      toast.success('Draft saved.');
      if (!submissionId) {
        router.replace(`/portal/${kind}/${saved.id}`);
      } else {
        setDetail(saved);
      }
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
          {fieldDefs.map((f) => (
            <FieldInput
              key={f.name}
              field={f}
              value={fields[f.name] ?? ''}
              onChange={(v) => setFields((prev) => ({ ...prev, [f.name]: v }))}
              disabled={!isEditable}
            />
          ))}
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
                    <Input
                      value={line.item_code ?? ''}
                      onChange={(e) =>
                        setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, item_code: e.target.value } : p)))
                      }
                      disabled={!isEditable}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Quantity</Label>
                    <Input
                      value={line.quantity ?? ''}
                      onChange={(e) =>
                        setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, quantity: e.target.value } : p)))
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
                            setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, unit_price: e.target.value } : p)))
                          }
                          disabled={!isEditable}
                        />
                      </div>
                      <div className="space-y-1.5">
                        <Label>Total</Label>
                        <Input
                          value={line.total ?? ''}
                          onChange={(e) =>
                            setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, total: e.target.value } : p)))
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
                      setProducts((prev) => prev.map((p, i) => (i === index ? { ...p, remark: e.target.value } : p)))
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
                    onClick={() => setProducts((prev) => prev.filter((_, i) => i !== index))}
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
        <Button variant="outline" onClick={handleSaveDraft} disabled={!isEditable || saving || submitting}>
          {saving ? 'Saving...' : 'Save as draft'}
        </Button>
        <Button onClick={() => setConfirmOpen(true)} disabled={!isEditable || saving || submitting}>
          {submitting ? 'Submitting...' : 'Submit'}
        </Button>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Submit this {SUBMISSION_LABELS[kind].toLowerCase()}?</AlertDialogTitle>
            <AlertDialogDescription>
              Once submitted, your team will be notified. You can no longer edit unless it is rejected.
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
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={field.name}>{field.label}</Label>
      {field.type === 'textarea' ? (
        <Textarea
          id={field.name}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          disabled={disabled}
        />
      ) : (
        <Input
          id={field.name}
          type={field.type === 'date' ? 'date' : 'text'}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
        />
      )}
    </div>
  );
}
