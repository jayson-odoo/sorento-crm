'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ChevronLeft, ChevronRight, Plus, Sparkles, Trash2 } from 'lucide-react';
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
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import {
  DebtorLookupItem,
  DOLookupItem,
  PortalAttachment,
  PortalContact,
  PortalSubmissionDetail,
  PortalSubmissionKind,
  PortalSubmissionNeighbours,
  PortalOwnerMismatchError,
  PortalUnauthorizedError,
  ProductLookupItem,
  SUBMISSION_LABELS,
  deleteDraftSubmission,
  fetchMe,
  fetchRequestorOptions,
  fetchSubmission,
  fetchSubmissionNeighbours,
  lookupDebtors,
  lookupDeliveryOrders,
  lookupProducts,
  lookupSet,
  saveDraft,
  statusLabel,
  submitDraft,
  uploadAttachment,
} from '../lib/portal-client';
import { portalDetailPath, portalHomePath, portalVerifyPath } from '../lib/portal-paths';
import { cleanLineItems } from '../lib/line-items';
import { AIExtractDialog, AIExtractApplyPayload } from './AIExtractDialog';
import { AttachmentDropzone } from './AttachmentDropzone';
import { AsyncCombobox } from './AsyncCombobox';
import { DOFilterMultiSelect } from './DOFilterMultiSelect';
import { LookupSelect } from './LookupSelect';
import { MultiPillInput } from './MultiPillInput';
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

type ComplaintLine = {
  product_code: string;
  product_type: string;
  quantity: string;
};

type WidgetKind =
  | 'text'
  | 'textarea'
  | 'date'
  | 'number'
  | 'lookup-select'
  | 'product-async'
  | 'debtor-async'
  | 'do-multi-filter'
  | 'pill-product'
  | 'pill-text'
  | 'product-quantities'
  | 'contact-select';

interface FieldDef {
  name: string;
  label: string;
  widget?: WidgetKind;
  setKey?: string;
  defaultFromContact?: 'fullname' | 'first_name' | 'contact_id';
  defaultToday?: boolean;
  placeholder?: string;
  required?: boolean;
  /** Render this field only when the predicate (given the current field values)
   *  returns true. Used e.g. for the sponsor-subject "Others" companion input. */
  showWhen?: (fields: Record<string, string | string[]>) => boolean;
  /**
   * `contact-select` only: name of the legacy free-text sibling column
   * (e.g. `requested_by`, `salesperson`) carrying the display label for the
   * saved contact id. Used to build `selectedOption` so a saved-but-now-
   * ineligible contact still renders its name instead of a blank / UUID.
   */
  legacyLabelField?: string;
}

const FIELDS: Record<PortalSubmissionKind, FieldDef[]> = {
  stock_inquiry: [
    { name: 'product_code', label: 'Product code', widget: 'product-async' },
    { name: 'item_description', label: 'Item description', widget: 'textarea' },
    { name: 'quantity', label: 'Quantity', widget: 'number' },
    { name: 'delivery_date', label: 'Required delivery date', widget: 'date' },
    { name: 'project_customer', label: 'Project customer', widget: 'debtor-async' },
    { name: 'project_name', label: 'Project name' },
    {
      name: 'salesperson_contact_id',
      label: 'Salesperson',
      widget: 'contact-select',
      legacyLabelField: 'salesperson',
      defaultFromContact: 'contact_id',
      required: true,
    },
    { name: 'remark', label: 'Remark', widget: 'textarea' },
    { name: 'additional_remark', label: 'Additional remark', widget: 'textarea' },
  ],
  complaint: [
    {
      name: 'delivery_order_number',
      label: 'Delivery order number(s)',
      widget: 'do-multi-filter',
      required: true,
    },
    {
      name: 'customer_name',
      label: 'Customer name',
      widget: 'debtor-async',
      required: true,
    },
    { name: 'contact_person', label: 'Contact person', required: true },
    { name: 'contact_number', label: 'Contact number', required: true },
    { name: 'customer_address', label: 'Delivery address', widget: 'textarea' },
    {
      name: 'customer_type',
      label: 'Customer type',
      widget: 'lookup-select',
      setKey: 'complaints_customer_type',
      required: true,
    },
    {
      name: 'complaint_date',
      label: 'Complaint date',
      widget: 'date',
      defaultToday: true,
      required: true,
    },
    {
      name: 'within_warranty',
      label: 'Within warranty',
      widget: 'lookup-select',
      setKey: 'complaints_within_warranty',
      required: true,
    },
    {
      name: 'defects_discovered',
      label: 'Defects discovered',
      widget: 'lookup-select',
      setKey: 'complaints_defects_discovered',
      required: true,
    },
    {
      name: 'complaint_type',
      label: 'Complaint type',
      widget: 'lookup-select',
      setKey: 'complaints_complaint_type',
      required: true,
    },
    {
      name: 'defect_description',
      label: 'Defect description',
      widget: 'textarea',
      required: true,
    },
    {
      name: 'salesperson',
      label: 'Salesperson',
      defaultFromContact: 'fullname',
      required: true,
    },
    { name: 'project_title', label: 'Project title' },
  ],
  purchase_request: [
    { name: 'customer_name', label: 'Customer name', widget: 'debtor-async' },
    { name: 'project_title', label: 'Project title' },
    { name: 'purpose', label: 'Purpose', widget: 'textarea' },
    {
      name: 'sales_type',
      label: 'Sales type',
      widget: 'lookup-select',
      setKey: 'procurement_sales_type',
    },
    {
      name: 'expected_delivery_date',
      label: 'Expected delivery date',
      widget: 'date',
    },
    { name: 'expected_po_date', label: 'Expected PO date', widget: 'date' },
    {
      name: 'requested_by_contact_id',
      label: 'Requested by',
      widget: 'contact-select',
      legacyLabelField: 'requested_by',
      defaultFromContact: 'contact_id',
      required: true,
    },
    { name: 'external_reference', label: 'External reference' },
  ],
  // Field order mirrors the system document view (PurchaseRequestDocumentEditCard /
  // detail): Customer → Delivery Address → Project Title → Total Project Value →
  // Sponsor Subject → Date of Delivery → Request date → Requested by.
  sponsorship_form: [
    { name: 'customer_name', label: 'Customer name', widget: 'debtor-async' },
    { name: 'delivery_address', label: 'Delivery address', widget: 'textarea' },
    { name: 'project_title', label: 'Project title' },
    { name: 'total_project_value', label: 'Total project value', widget: 'number', placeholder: 'e.g. 1234.00' },
    {
      name: 'sponsor_subject',
      label: 'Sponsor subject',
      widget: 'lookup-select',
      setKey: 'procurement_sponsor_subject',
    },
    {
      name: 'sponsor_subject_other',
      label: 'Please specify',
      placeholder: 'Specify the sponsor subject',
      showWhen: (f) => (typeof f.sponsor_subject === 'string' ? f.sponsor_subject : '') === 'others',
    },
    {
      name: 'expected_delivery_date',
      label: 'Expected delivery date',
      widget: 'date',
    },
    {
      name: 'requested_by_contact_id',
      label: 'Requested by',
      widget: 'contact-select',
      legacyLabelField: 'requested_by',
      defaultFromContact: 'contact_id',
      required: true,
    },
  ],
};

const HAS_LINES: PortalSubmissionKind[] = ['purchase_request', 'sponsorship_form'];

function fieldSpansFullWidth(f: FieldDef): boolean {
  return (
    f.widget === 'textarea' ||
    f.widget === 'do-multi-filter' ||
    f.widget === 'product-quantities'
  );
}

interface Props {
  kind: PortalSubmissionKind;
  submissionId?: string;
  /** Active contact slug from the deep-link URL. Threaded into the verify
   *  redirect so a second device (with no stored slug) still lands on the
   *  slug-mode verify card - which resolves "this {kind} belongs to {name}"
   *  and the OTP flow - instead of the legacy "message us" dead end. */
  slug?: string;
}

export function SubmissionForm({ kind, submissionId, slug }: Props) {
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
  const [complaintLines, setComplaintLines] = useState<ComplaintLine[]>([]);
  const [attachments, setAttachments] = useState<PortalAttachment[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [contact, setContact] = useState<PortalContact | null>(null);
  const [invalidFields, setInvalidFields] = useState<Set<string>>(new Set());
  const [staffPreviewOpen, setStaffPreviewOpen] = useState(false);
  const [neighbours, setNeighbours] = useState<PortalSubmissionNeighbours | null>(null);

  const fieldDefs = FIELDS[kind];
  const showLines = HAS_LINES.includes(kind);
  const isEditable = useMemo(
    () =>
      !detail ||
      detail.is_draft ||
      detail.status === 'rejected' ||
      detail.status === 'responded',
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
    const contactId = contact?.contact_id ?? '';
    if (!name) return { first_name: '', fullname: '', contactId };
    const parts = name.split(/\s+/);
    const [first, ...rest] = parts;
    void rest;
    return { first_name: first ?? '', fullname: name, contactId };
  }, [contact]);

  // Portal record navigation (edge chevrons + arrow keys). Same-kind, newest
  // first, token-scoped to the contact's own submissions - internal detail
  // pages keep their own separate top-right counter (untouched by this).
  useEffect(() => {
    if (!submissionId) {
      setNeighbours(null);
      return;
    }
    let cancelled = false;
    fetchSubmissionNeighbours(kind, submissionId)
      .then((n) => {
        if (!cancelled) setNeighbours(n);
      })
      .catch(() => {
        if (!cancelled) setNeighbours(null);
      });
    return () => {
      cancelled = true;
    };
  }, [kind, submissionId]);

  useEffect(() => {
    if (!neighbours) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      const isEditable = (el: Element | null) =>
        !!el &&
        (el.tagName === 'INPUT' ||
          el.tagName === 'TEXTAREA' ||
          el.tagName === 'SELECT' ||
          (el as HTMLElement).isContentEditable);
      if (isEditable(e.target as Element | null) || isEditable(document.activeElement)) return;
      if (document.querySelector('[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]')) {
        return;
      }
      if (e.key === 'ArrowLeft' && neighbours.prev_id) {
        router.push(portalDetailPath(kind, neighbours.prev_id, slug));
      } else if (e.key === 'ArrowRight' && neighbours.next_id) {
        router.push(portalDetailPath(kind, neighbours.next_id, slug));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [neighbours, kind, slug, router]);

  useEffect(() => {
    if (!submissionId) {
      let cancelledNew = false;
      const next: Record<string, string | string[]> = {};
      const lookupFields: FieldDef[] = [];
      for (const f of fieldDefs) {
        if (f.widget === 'do-multi-filter') {
          next[f.name] = [];
          continue;
        }
        if (f.defaultFromContact === 'fullname') {
          next[f.name] = defaultsFromContact.fullname;
        } else if (f.defaultFromContact === 'first_name') {
          next[f.name] = defaultsFromContact.first_name;
        } else if (f.defaultFromContact === 'contact_id') {
          next[f.name] = defaultsFromContact.contactId;
        } else if (f.defaultToday) {
          next[f.name] = new Date().toISOString().slice(0, 10);
        } else {
          next[f.name] = '';
        }
        if (f.widget === 'lookup-select' && f.setKey) lookupFields.push(f);
      }
      // Seed each lookup field's binding default (Default (new forms) in the lookup
      // admin) so the portal pre-selects it just like the system form. Must happen
      // HERE, not in the widget: this init does a full setFields replace that would
      // otherwise wipe a widget-applied value.
      void (async () => {
        await Promise.all(
          lookupFields.map((f) =>
            lookupSet(f.setKey as string)
              .then((r) => {
                if (r.defaultValue && !next[f.name]) next[f.name] = r.defaultValue;
              })
              .catch(() => {}),
          ),
        );
        if (!cancelledNew) {
          setFields(next);
          setComplaintLines([]);
          setLoading(false);
        }
      })();
      return () => {
        cancelledNew = true;
      };
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
        if (kind === 'complaint') {
          const pls =
            (data as {
              product_lines?: { product_code?: string | null; product_type?: string | null; quantity?: string | null }[];
            }).product_lines ?? [];
          setComplaintLines(
            pls
              .filter((l) => (l.product_code ?? '').trim())
              .map((l) => ({
                product_code: (l.product_code ?? '').trim(),
                product_type: (l.product_type ?? '').trim(),
                quantity: (l.quantity ?? '').trim(),
              })),
          );
        }
        setAttachments((data.attachments as PortalAttachment[]) ?? []);
      } catch (e) {
        if (e instanceof PortalUnauthorizedError) {
          router.replace(portalVerifyPath({ slug, reason: 'expired', type: kind, id: submissionId }));
          return;
        }
        // Logged in as a different contact than the form's owner - send them to
        // the owner's confirm-identity card (deep-link slug), keep their token.
        if (e instanceof PortalOwnerMismatchError) {
          router.replace(portalVerifyPath({ slug, reason: 'expired', type: kind, id: submissionId }));
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
    // Sponsorship: the "Others" detail only applies when the subject is 'others'.
    // Drop a stale value so switching back to Showroom/Mockup doesn't persist it.
    if (kind === 'sponsorship_form' && out.sponsor_subject !== 'others') {
      delete out.sponsor_subject_other;
    }
    // Complaint: structured per-product lines are the source of truth. Backend
    // re-derives the legacy product_code / product_type / quantity CSV columns.
    if (kind === 'complaint') {
      const lines = complaintLines
        .map((l) => ({
          product_code: (l.product_code || '').trim(),
          product_type: (l.product_type || '').trim() || undefined,
          quantity: (l.quantity || '').trim() || undefined,
        }))
        .filter((l) => l.product_code);
      if (lines.length > 0) out['product_lines'] = lines;
    }
    return out;
  }, [fieldDefs, fields, kind, complaintLines]);

  const cleanedProducts = useMemo(() => {
    if (!showLines) return undefined;
    return cleanLineItems(products);
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
      router.replace(portalHomePath({ type: kind }));
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace(portalVerifyPath({ reason: 'expired' }));
        return;
      }
      toast.error(e instanceof Error ? e.message : 'Failed to save.');
    } finally {
      setSaving(false);
    }
  };

  const handleSubmit = async () => {
    const missing: { name: string; label: string }[] = [];
    for (const f of fieldDefs) {
      if (!f.required) continue;
      const v = fields[f.name];
      const empty = Array.isArray(v)
        ? v.length === 0
        : !(typeof v === 'string' && v.trim().length > 0);
      if (empty) missing.push({ name: f.name, label: f.label });
    }
    if (
      kind === 'complaint' &&
      complaintLines.filter((l) => (l.product_code || '').trim()).length === 0
    ) {
      missing.push({ name: 'product_lines', label: 'At least one product' });
    }
    if (missing.length > 0) {
      setInvalidFields(new Set(missing.map((m) => m.name)));
      toast.error(
        `Missing ${missing.length} required field${missing.length === 1 ? '' : 's'}: ${missing
          .map((m) => m.label)
          .join(', ')}`,
      );
      setConfirmOpen(false);
      setTimeout(() => {
        const node = document.querySelector(
          `[data-field-name="${missing[0].name}"]`,
        ) as HTMLElement | null;
        node?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      }, 50);
      return;
    }
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
      router.replace(portalHomePath({ type: kind }));
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace(portalVerifyPath({ reason: 'expired' }));
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
      router.replace(portalHomePath({ type: kind }));
    } catch (e) {
      if (e instanceof PortalUnauthorizedError) {
        router.replace(portalVerifyPath({ reason: 'expired' }));
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

  useEffect(() => {
    setInvalidFields((prev) => {
      if (prev.size === 0) return prev;
      let changed = false;
      const next = new Set(prev);
      prev.forEach((name) => {
        const v = fields[name];
        const empty = Array.isArray(v)
          ? v.length === 0
          : !(typeof v === 'string' && v.trim().length > 0);
        if (!empty) {
          next.delete(name);
          changed = true;
        }
      });
      return changed ? next : prev;
    });
  }, [fields]);

  const handleAIExtractApply = async (payload: AIExtractApplyPayload) => {
    // AI extract is an explicit user action ("Confirm and prefill"), so we
    // overwrite the affected fields rather than skipping non-empty ones.
    // After the override, we enrich from a DO lookup: if the DO numbers exist
    // in the system we backfill customer / product / product_type from the
    // resolved DO rows. AI-provided values always take priority over the
    // DO-derived ones.
    const aiValues = payload.values;
    const widgetByName: Record<string, WidgetKind | undefined> = {};
    for (const f of fieldDefs) widgetByName[f.name] = f.widget;
    setFields((prev) => {
      const next = { ...prev };
      for (const [name, value] of Object.entries(aiValues)) {
        const isMultiArray = widgetByName[name] === 'do-multi-filter';
        if (Array.isArray(value) && !isMultiArray) {
          next[name] = value.map((v) => String(v).trim()).filter(Boolean).join(', ');
        } else {
          next[name] = value;
        }
      }
      return next;
    });
    if (payload.alsoAttach && payload.files.length > 0) {
      setPendingFiles((prev) => [...prev, ...payload.files]);
    }

    if (HAS_LINES.includes(kind) && payload.productLines && payload.productLines.length > 0) {
      const numToString = (n: number | null | undefined): string | undefined =>
        n === null || n === undefined ? undefined : String(n);
      const aiLines: ProductLine[] = payload.productLines.map((p) => ({
        item_code: p.product_code ?? undefined,
        quantity: numToString(p.quantity),
        unit_price: numToString(p.unit_price),
        total: numToString(p.total),
        remark: p.notes ?? undefined,
      }));
      setProducts((prev) => {
        const isPrevEmpty =
          prev.length === 0 ||
          (prev.length === 1 &&
            !prev[0].item_code &&
            !prev[0].quantity &&
            !prev[0].unit_price &&
            !prev[0].total &&
            !prev[0].remark);
        return isPrevEmpty ? aiLines : [...prev, ...aiLines];
      });
    }

    if (kind !== 'complaint') return;

    // Complaint AI product lines → complaintLines. Map code+qty, then enrich
    // product_type from the master category (preserving qty).
    let aiSuppliedLines = false;
    if (payload.productLines && payload.productLines.length > 0) {
      const aiLines: ComplaintLine[] = payload.productLines
        .map((p) => ({
          product_code: (p.product_code ?? '').trim(),
          product_type: '',
          quantity: p.quantity === null || p.quantity === undefined ? '' : String(p.quantity),
        }))
        .filter((l) => l.product_code);
      if (aiLines.length > 0) {
        aiSuppliedLines = true;
        setComplaintLines(aiLines);
        buildComplaintLinesFromCodes(
          aiLines.map((l) => l.product_code),
          aiLines,
        )
          .then(setComplaintLines)
          .catch(() => {});
      }
    }

    const aiDOsRaw = aiValues.delivery_order_number;
    if (!aiDOsRaw) return;
    const doNumbers = (
      Array.isArray(aiDOsRaw)
        ? aiDOsRaw
        : String(aiDOsRaw)
            .split(/[,\n]/)
            .map((s) => s.trim())
            .filter(Boolean)
    )
      .map((s) => String(s).trim())
      .filter(Boolean);
    if (doNumbers.length === 0) return;

    // Best-effort lookup. Each DO not in the system simply contributes nothing
    // to the enrichment - the field still keeps the AI-provided pill.
    const items: DOLookupItem[] = [];
    for (const dn of doNumbers) {
      try {
        const matches = await lookupDeliveryOrders(dn, 5);
        const exact = matches.find((m) => m.order_number === dn);
        if (exact) items.push(exact);
      } catch {
        // ignore - DO not resolvable, treat as free-text only.
      }
    }
    if (items.length === 0) return;

    const aiCustomer =
      typeof aiValues.customer_name === 'string'
        ? aiValues.customer_name.trim()
        : '';
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
    // AI customer wins; only fill from DO debtor when AI did not provide.
    if (!aiCustomer && customerNames.length > 0) {
      setFields((prev) => ({ ...prev, customer_name: customerNames.join(', ') }));
    }
    // Only derive product lines from the DO when AI didn't already supply them.
    if (!aiSuppliedLines && productCodes.length > 0) {
      const built = await buildComplaintLinesFromCodes(productCodes, complaintLines);
      setComplaintLines(built);
    }
  };

  // Build complaint line rows from a set of product codes, deriving each row's
  // product_type from the product master category. Preserves quantities already
  // entered for a code; new codes start with empty quantity.
  const buildComplaintLinesFromCodes = async (
    productCodes: string[],
    prevLines: ComplaintLine[],
  ): Promise<ComplaintLine[]> => {
    const prevByCode = new Map(prevLines.map((l) => [l.product_code, l]));
    const out: ComplaintLine[] = [];
    for (const code of productCodes) {
      const existing = prevByCode.get(code);
      let productType = existing?.product_type ?? '';
      if (!productType) {
        try {
          const matches = await lookupProducts(code, 5);
          const exact = matches.find((m) => m.product_code === code);
          productType = (exact?.category_code ?? exact?.category_name ?? '').trim();
        } catch {
          // best-effort - leave blank, user can fill
        }
      }
      out.push({ product_code: code, product_type: productType, quantity: existing?.quantity ?? '' });
    }
    return out;
  };

  // Complaint product selection is handled per-row inside the lines table; the
  // section prop is kept for signature compatibility with the other sections.
  const handleProductItemSelected = () => {};

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
    setFields((prev) => ({ ...prev, customer_name: customerNames.join(', ') }));
    if (productCodes.length > 0) {
      const built = await buildComplaintLinesFromCodes(productCodes, complaintLines);
      setComplaintLines(built);
    }
  };

  const handleDOProductsConfirmed = async ({
    items,
    productCodes,
  }: {
    items: DOLookupItem[];
    productCodes: string[];
  }) => {
    if (kind !== 'complaint') return;
    const customerNames = Array.from(
      new Set(
        items
          .map((i) => (i.debtor_name ?? i.customer_name ?? '').trim())
          .filter(Boolean),
      ),
    );
    setFields((prev) => ({ ...prev, customer_name: customerNames.join(', ') }));
    if (productCodes.length > 0) {
      const built = await buildComplaintLinesFromCodes(productCodes, complaintLines);
      setComplaintLines(built);
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

  // Purchasing / technical response shown at top for salesperson once responded. Hidden when empty.
  const responseInfo = (() => {
    if (kind === 'stock_inquiry') {
      const v = ((detail?.purchasing_response as string | null | undefined) ?? '').trim();
      return v ? { label: 'Comment / reply by purchasing', value: v, team: 'purchasing' } : null;
    }
    if (kind === 'complaint') {
      let v = ((detail?.technical_team_response as string | null | undefined) ?? '').trim();
      // Strip legacy composed customer message so only technician wording shows (matches CRM).
      if (v.startsWith('There has been an update regarding your complaint')) {
        const idx = v.lastIndexOf(': ');
        if (idx !== -1) v = v.slice(idx + 2).trim();
      }
      return v ? { label: 'Technical team response', value: v, team: 'technical team' } : null;
    }
    return null;
  })();

  // Staff (purchasing / technical) response attachments - surfaced at the top
  // of the reply banner, scoped away from the contact's own uploads below.
  // Count is derived from the loaded attachments, never typed.
  const staffAttachments = attachments.filter((a) => a.uploader_kind === 'user');
  const staffPreviewItems: AttachmentPreviewItem[] = staffAttachments.map((a) => ({
    id: a.link_id,
    name: a.filename || 'Attachment',
    url: a.url ?? '',
    sizeBytes: a.size,
  }));

  // "Requested by" / "Salesperson" contact-select: pre-select the saved id and
  // resolve a NAME to show (never a UUID) - the legacy free-text sibling
  // column carries the point-in-time label, falling back to the submitting
  // contact's own name for a brand-new form.
  const resolveContactOption = (field: FieldDef): SearchableSelectOption | undefined => {
    if (field.widget !== 'contact-select') return undefined;
    const id = typeof fields[field.name] === 'string' ? (fields[field.name] as string) : '';
    if (!id) return undefined;
    const legacyLabel = field.legacyLabelField
      ? ((detail as Record<string, unknown> | null)?.[field.legacyLabelField] as string | undefined)
      : undefined;
    const label = (legacyLabel ?? '').trim() || defaultsFromContact.fullname || 'You';
    return { value: id, label };
  };

  return (
    <div className="min-h-screen max-w-7xl mx-auto px-4 py-6 space-y-4">
      <div className="flex items-center justify-between">
        <Button variant="ghost" size="sm" asChild>
          <Link href={portalHomePath({ type: kind })}>
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Link>
        </Button>
        <div className="flex items-center gap-3">
          {isEditable && (
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
            <span className="text-sm text-muted-foreground">
              {detail.reference}
              {neighbours && (
                <span className="ml-2 text-xs text-muted-foreground/70">
                  {neighbours.position} / {neighbours.total}
                </span>
              )}
            </span>
          )}
          {!detail?.reference && neighbours && (
            <span className="text-xs text-muted-foreground/70">
              {neighbours.position} / {neighbours.total}
            </span>
          )}
        </div>
      </div>

      {!isEditable && (
        <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
          This submission is not editable.
        </div>
      )}
      {detail?.rejection_reason && (
        <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <p className="font-medium">Rejection reason</p>
          <p>{detail.rejection_reason}</p>
        </div>
      )}

      {responseInfo && (
        <div className="rounded-md border border-emerald-500/40 bg-emerald-500/5 p-3 text-sm">
          <p className="font-medium text-emerald-700 dark:text-emerald-400">{responseInfo.label}</p>
          <p className="mt-1 whitespace-pre-wrap text-foreground">{responseInfo.value}</p>
          {staffAttachments.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-xs text-emerald-700/80 dark:text-emerald-400/80">
                {staffAttachments.length} attachment{staffAttachments.length === 1 ? '' : 's'} from{' '}
                {responseInfo.team}
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setStaffPreviewOpen(true)}
              >
                View attachment{staffAttachments.length === 1 ? '' : 's'} ({staffAttachments.length})
              </Button>
            </div>
          )}
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
          resolveContactOption={resolveContactOption}
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
          onDOProductsConfirmed={handleDOProductsConfirmed}
          invalidFields={invalidFields}
          complaintLines={complaintLines}
          setComplaintLines={setComplaintLines}
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
          resolveContactOption={resolveContactOption}
        />
      )}

      {showLines && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Items</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="w-10 px-2 py-2 text-left">#</th>
                    <th className="min-w-[180px] px-2 py-2 text-left">Item code</th>
                    <th className="w-28 px-2 py-2 text-left">Quantity</th>
                    {kind === 'sponsorship_form' && (
                      <>
                        <th className="w-32 px-2 py-2 text-left">Unit price</th>
                        <th className="w-32 px-2 py-2 text-left">Total</th>
                      </>
                    )}
                    <th className="min-w-[200px] px-2 py-2 text-left">Remark</th>
                    <th className="w-12 px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((line, index) => {
                    const qtyNum = Number(line.quantity);
                    const priceNum = Number(line.unit_price);
                    const computedTotal =
                      Number.isFinite(qtyNum) && Number.isFinite(priceNum)
                        ? (qtyNum * priceNum).toFixed(2)
                        : '';
                    return (
                      <tr key={index} className="border-t border-border align-top">
                        <td className="px-2 py-2 text-muted-foreground">{index + 1}</td>
                        <td className="px-2 py-2">
                          <AsyncCombobox<ProductLookupItem>
                            value={line.item_code ?? ''}
                            onChange={(v) =>
                              setProducts((prev) =>
                                prev.map((p, i) =>
                                  i === index ? { ...p, item_code: v } : p,
                                ),
                              )
                            }
                            fetchOptions={(q) => lookupProducts(q)}
                            optionValue={(o) => o.product_code}
                            optionLabel={(o) => o.product_code}
                            optionMeta={(o) => o.product_name ?? ''}
                            disabled={!isEditable}
                          />
                        </td>
                        <td className="px-2 py-2">
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
                        </td>
                        {kind === 'sponsorship_form' && (
                          <>
                            <td className="px-2 py-2">
                              <Input
                                type="number"
                                inputMode="decimal"
                                min="0"
                                step="0.01"
                                value={line.unit_price ?? ''}
                                onChange={(e) =>
                                  setProducts((prev) =>
                                    prev.map((p, i) =>
                                      i === index
                                        ? { ...p, unit_price: e.target.value }
                                        : p,
                                    ),
                                  )
                                }
                                disabled={!isEditable}
                              />
                            </td>
                            <td className="px-2 py-2">
                              <Input
                                type="number"
                                inputMode="decimal"
                                min="0"
                                step="0.01"
                                value={line.total ?? computedTotal}
                                onChange={(e) =>
                                  setProducts((prev) =>
                                    prev.map((p, i) =>
                                      i === index ? { ...p, total: e.target.value } : p,
                                    ),
                                  )
                                }
                                placeholder={
                                  computedTotal && !line.total ? computedTotal : ''
                                }
                                disabled={!isEditable}
                              />
                            </td>
                          </>
                        )}
                        <td className="px-2 py-2">
                          <Textarea
                            value={line.remark ?? ''}
                            onChange={(e) =>
                              setProducts((prev) =>
                                prev.map((p, i) =>
                                  i === index ? { ...p, remark: e.target.value } : p,
                                ),
                              )
                            }
                            rows={1}
                            disabled={!isEditable}
                          />
                        </td>
                        <td className="px-2 py-2 text-right">
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            disabled={!isEditable}
                            onClick={() =>
                              setProducts((prev) => prev.filter((_, i) => i !== index))
                            }
                            title="Remove"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                  {kind === 'sponsorship_form' && products.length > 0 && (
                    <tr className="border-t-2 border-border bg-muted/20 font-medium">
                      <td className="px-2 py-2 text-right" colSpan={4}>
                        Grand total
                      </td>
                      <td className="px-2 py-2">
                        {(() => {
                          const sum = products.reduce((acc, p) => {
                            const t = Number(p.total);
                            if (Number.isFinite(t)) return acc + t;
                            const q = Number(p.quantity);
                            const u = Number(p.unit_price);
                            if (Number.isFinite(q) && Number.isFinite(u))
                              return acc + q * u;
                            return acc;
                          }, 0);
                          return sum.toFixed(2);
                        })()}
                      </td>
                      <td className="px-2 py-2" colSpan={2}></td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
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
          onClick={() => router.replace(portalHomePath({ type: kind }))}
          disabled={saving || submitting || deleting}
        >
          Cancel
        </Button>
        {detail?.status !== 'rejected' && detail?.status !== 'responded' && (
          <Button
            variant="outline"
            onClick={handleSaveDraft}
            disabled={!isEditable || saving || submitting}
          >
            {saving ? 'Saving...' : 'Save as draft'}
          </Button>
        )}
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
              is returned to you for changes.
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

      <AttachmentPreviewModal
        open={staffPreviewOpen}
        onOpenChange={setStaffPreviewOpen}
        items={staffPreviewItems}
      />

      {neighbours?.prev_id && (
        <button
          type="button"
          onClick={() => router.push(portalDetailPath(kind, neighbours.prev_id as string, slug))}
          aria-label="Previous submission"
          className="fixed left-1 top-1/2 z-30 flex size-8 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-background/80 opacity-60 shadow-sm backdrop-blur transition hover:opacity-100 sm:left-3 sm:size-10"
        >
          <ChevronLeft className="h-4 w-4 sm:h-5 sm:w-5" />
        </button>
      )}
      {neighbours?.next_id && (
        <button
          type="button"
          onClick={() => router.push(portalDetailPath(kind, neighbours.next_id as string, slug))}
          aria-label="Next submission"
          className="fixed right-1 top-1/2 z-30 flex size-8 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-background/80 opacity-60 shadow-sm backdrop-blur transition hover:opacity-100 sm:right-3 sm:size-10"
        >
          <ChevronRight className="h-4 w-4 sm:h-5 sm:w-5" />
        </button>
      )}
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
  onDOProductsConfirmed?: (payload: {
    items: DOLookupItem[];
    productCodes: string[];
  }) => void;
  invalidFields?: Set<string>;
  complaintLines?: ComplaintLine[];
  setComplaintLines?: Dispatch<SetStateAction<ComplaintLine[]>>;
  /** `contact-select` fields only - resolves the picker's pre-selected option
   *  (id + human-readable name) so a saved-but-ineligible contact still shows
   *  its name instead of a blank or a UUID. */
  resolveContactOption?: (field: FieldDef) => SearchableSelectOption | undefined;
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
  resolveContactOption,
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
            field={fieldByName.salesperson_contact_id}
            value={fields.salesperson_contact_id ?? ''}
            onChange={(v) => setFieldValue('salesperson_contact_id', v)}
            disabled={!isEditable}
            contactOption={resolveContactOption?.(fieldByName.salesperson_contact_id)}
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

/** Per-product lines table for complaints: searchable product code (auto-derives
 * product type from the master category), quantity, add/remove - mirrors the
 * purchase-request / sponsorship Items table. */
function ComplaintLinesTable({
  lines,
  setLines,
  disabled,
  invalid,
}: {
  lines: ComplaintLine[];
  setLines: Dispatch<SetStateAction<ComplaintLine[]>>;
  disabled?: boolean;
  invalid?: boolean;
}) {
  const updateRow = (index: number, patch: Partial<ComplaintLine>) =>
    setLines((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  const addRow = () =>
    setLines((prev) => [...prev, { product_code: '', product_type: '', quantity: '' }]);
  const removeRow = (index: number) =>
    setLines((prev) => prev.filter((_, i) => i !== index));

  return (
    <div className="space-y-2" data-field-name="product_lines">
      <Label className="min-w-0">
        Products<span className="ml-0.5 text-destructive">*</span>
      </Label>
      <div
        className={`overflow-x-auto rounded-md border ${invalid ? 'border-destructive' : 'border-border'}`}
      >
        <table className="w-full text-sm">
          <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="w-10 px-2 py-2 text-left">#</th>
              <th className="min-w-[200px] px-2 py-2 text-left">Product code</th>
              <th className="min-w-[140px] px-2 py-2 text-left">Product type</th>
              <th className="w-24 px-2 py-2 text-left">Qty</th>
              <th className="w-10 px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {lines.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">
                  No products yet. Click “Add product”.
                </td>
              </tr>
            )}
            {lines.map((line, index) => (
              <tr key={index} className="border-t border-border align-top">
                <td className="px-2 py-2 text-muted-foreground">{index + 1}</td>
                <td className="px-2 py-2">
                  <AsyncCombobox<ProductLookupItem>
                    value={line.product_code}
                    onChange={(v, item) => {
                      const derived = item
                        ? (item.category_code ?? item.category_name ?? '').trim()
                        : '';
                      updateRow(index, {
                        product_code: v,
                        ...(derived ? { product_type: derived } : {}),
                      });
                    }}
                    fetchOptions={(q) => lookupProducts(q)}
                    optionValue={(o) => o.product_code}
                    optionLabel={(o) => o.product_code}
                    optionMeta={(o) => o.product_name ?? ''}
                    disabled={disabled}
                  />
                </td>
                <td className="px-2 py-2">
                  <Input
                    value={line.product_type}
                    onChange={(e) => updateRow(index, { product_type: e.target.value })}
                    placeholder="Type"
                    disabled={disabled}
                  />
                </td>
                <td className="px-2 py-2">
                  <Input
                    type="number"
                    inputMode="numeric"
                    min="0"
                    value={line.quantity}
                    onChange={(e) => updateRow(index, { quantity: e.target.value })}
                    placeholder="Qty"
                    disabled={disabled}
                    // min-width on the input (not the <th>, which table
                    // auto-layout ignores) keeps room for ≥4 digits on mobile.
                    className="min-w-[72px]"
                  />
                </td>
                <td className="px-2 py-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRow(index)}
                    disabled={disabled}
                    aria-label="Remove product"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!disabled && (
        <Button type="button" variant="outline" size="sm" onClick={addRow}>
          <Plus className="h-4 w-4 mr-1" />
          Add product
        </Button>
      )}
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
  onDOProductsConfirmed,
  invalidFields,
  complaintLines,
  setComplaintLines,
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
              className={`min-w-0 ${fieldSpansFullWidth(f) ? 'md:col-span-2' : ''}`}
            >
              <FieldInput
                field={f}
                value={fields[f.name] ?? ''}
                onChange={(v) => setFieldValue(f.name, v)}
                onItemSelect={(item) => onProductItemSelected(f.name, item)}
                onDOItemsChange={onDOItemsChanged}
                onDOProductsConfirmed={onDOProductsConfirmed}
                invalid={invalidFields?.has(f.name)}
                disabled={!isEditable}
              />
            </div>
          ))}
          {complaintLines && setComplaintLines && (
            <div className="md:col-span-2">
              <ComplaintLinesTable
                lines={complaintLines}
                setLines={setComplaintLines}
                disabled={!isEditable}
                invalid={invalidFields?.has('product_lines')}
              />
            </div>
          )}
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
  resolveContactOption,
}: SectionProps & { kind: PortalSubmissionKind }) {
  const heading =
    kind === 'sponsorship_form' ? 'Project Sales Sponsorship Form' : 'Purchase Request';
  return (
    <div className="w-full">
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
            {fieldDefs
              .filter((f) => (f.showWhen ? f.showWhen(fields) : true))
              .map((f) => (
                <div
                  key={f.name}
                  className={`min-w-0 ${fieldSpansFullWidth(f) ? 'sm:col-span-2' : ''}`}
                >
                  <FieldInput
                    field={f}
                    value={fields[f.name] ?? ''}
                    onChange={(v) => setFieldValue(f.name, v)}
                    onItemSelect={(item) => onProductItemSelected(f.name, item)}
                    disabled={!isEditable}
                    contactOption={resolveContactOption?.(f)}
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
  onDOProductsConfirmed,
  invalid,
  disabled,
  contactOption,
}: {
  field: FieldDef;
  value: string | string[];
  onChange: (v: string | string[]) => void;
  onItemSelect?: (item: ProductLookupItem) => void;
  onDOItemsChange?: (items: DOLookupItem[]) => void;
  onDOProductsConfirmed?: (payload: {
    items: DOLookupItem[];
    productCodes: string[];
  }) => void;
  invalid?: boolean;
  disabled?: boolean;
  contactOption?: SearchableSelectOption;
}) {
  return (
    <div className="space-y-1.5 min-w-0" data-field-name={field.name}>
      <Label htmlFor={field.name} className="min-w-0">
        {field.label}
        {field.required && <span className="ml-0.5 text-destructive">*</span>}
      </Label>
      <div
        className={
          invalid
            ? '[&_input]:border-destructive [&_textarea]:border-destructive [&_[role=combobox]]:border-destructive [&_.pill-shell]:border-destructive'
            : ''
        }
      >
        <FieldControl
          field={field}
          value={value}
          onChange={onChange}
          onItemSelect={onItemSelect}
          onDOItemsChange={onDOItemsChange}
          onDOProductsConfirmed={onDOProductsConfirmed}
          disabled={disabled}
          contactOption={contactOption}
        />
      </div>
      {invalid && (
        <p className="text-xs text-destructive">{field.label} is required.</p>
      )}
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
  onItemSelect,
  onDOItemsChange,
  onDOProductsConfirmed,
  disabled,
  contactOption,
}: {
  field: FieldDef;
  value: string | string[];
  onChange: (v: string | string[]) => void;
  onItemSelect?: (item: ProductLookupItem) => void;
  onDOItemsChange?: (items: DOLookupItem[]) => void;
  onDOProductsConfirmed?: (payload: {
    items: DOLookupItem[];
    productCodes: string[];
  }) => void;
  contactOption?: SearchableSelectOption;
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
          min={0}
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
          multiline
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
          onProductsConfirmed={onDOProductsConfirmed}
          disabled={disabled}
        />
      );
    case 'pill-product':
      return (
        <MultiPillInput
          id={field.name}
          value={stringValue}
          onChange={(csv) => onChange(csv)}
          placeholder={field.placeholder ?? 'Type code, press Enter'}
          disabled={disabled}
          fetchOptions={async (q) => {
            const items = await lookupProducts(q);
            return items.map((p) => ({
              value: p.product_code,
              label: p.product_code,
              meta: p.product_name ?? '',
              data: p,
            }));
          }}
          onItemSelect={(_v, opt) => {
            if (!onItemSelect) return;
            const data = opt.data as ProductLookupItem | undefined;
            if (data) onItemSelect(data);
          }}
        />
      );
    case 'pill-text':
      return (
        <MultiPillInput
          id={field.name}
          value={stringValue}
          onChange={(csv) => onChange(csv)}
          placeholder={field.placeholder ?? 'Type and press Enter'}
          disabled={disabled}
        />
      );
    case 'contact-select':
      return (
        <SearchableSelect
          id={field.name}
          value={stringValue}
          onChange={(v) => onChange(v)}
          fetchOptions={async (q) => {
            const { items } = await fetchRequestorOptions(q);
            return items.map((o) => ({ value: o.id, label: o.name }));
          }}
          selectedOption={contactOption}
          placeholder={field.placeholder ?? 'Select...'}
          emptyMessage="No one matches yet."
          disabled={disabled}
        />
      );
    case 'text':
    default:
      // Render plain text fields as a wrapping Textarea so long values are
      // visible without horizontal scrolling. Auto-grows to fit content.
      return (
        <AutoGrowTextarea
          id={field.name}
          value={stringValue}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
          disabled={disabled}
        />
      );
  }
}

function AutoGrowTextarea({
  id,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  id?: string;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);
  return (
    <Textarea
      ref={ref}
      id={id}
      rows={1}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      disabled={disabled}
      className="resize-none overflow-hidden"
    />
  );
}
