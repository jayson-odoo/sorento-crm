'use client';

/**
 * Staff new / edit sample request (SR-CORE), restructured by SAMPLE-REQUEST-V2 (owner 11 Nov):
 * four guided sections like the price tag request (Customer & project / Ship to / Items /
 * Delivery), ship to = a party of the project (the proposal's party picker), the contact person
 * from that party's people (the registration contacts popup), and one main button, Preview, whose
 * popup submits. Every exit returns to where the person started (`?from=`, owner 16:30).
 */

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { Loader2, Plus } from 'lucide-react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { DatePicker } from '@/components/ui/date-picker';
import { toIsoDate } from '@/components/ui/date-range-picker';
import { FormSection } from '@/components/common/FormSection';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SampleRequestLines } from '@/components/common/SampleRequestLines';
import { SampleRequestFooterFields } from '@/components/common/SampleRequestFooterFields';
import {
  SampleRequestPrefillNote,
  SampleRequestQuotationPicker,
} from '@/components/common/SampleRequestQuotationSource';
import { useSampleRequestPrefill } from '@/hooks/useSampleRequestPrefill';
import { useHasPermission } from '@/hooks/usePermissions';
import { AsyncCombobox } from '@/app/(auth)/portal/components/AsyncCombobox';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import {
  SampleRequestError,
  type SampleRequestDetail,
  type SampleRequestWrite,
} from '@/types/sampleRequest';
import {
  DELIVERY_MODE_LABELS,
  GOODS_FROM_LABELS,
} from '@/types/sampleRequest';
import {
  EMPTY_FORM,
  blankLine,
  goodsFromTicks,
  productSource,
  staffPayloadFromState,
  stateFromDetail,
  numberErrors,
  validateStaff,
  withShipToContacts,
  withShipToParty,
  type FormState,
} from '@/lib/sample-request-form';
import { lookupCustomersForRequest } from '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService';
import type { CustomerLookupItem } from '@/app/(protected)/procurement-management/purchase-requests/types/purchaseRequest.types';
import { searchProjectsForLink } from '@/app/(protected)/complaint-management/complaints/services/complaintService';
import * as portalSampleRequest from '@/app/(auth)/portal/lib/sample-request-service';
import PortalSampleRequestForm from '@/app/(auth)/portal/components/SampleRequestForm';
import { clientService, useSubmissionClient } from '@/app/(auth)/portal/lib/submission-client';
import { MyRequestClientProvider } from '@/components/common/MyRequestPortalForm';
import { useRequestScope } from '@/hooks/useRequestScope';
import { useProject, usePartyContacts, usePartyRoleLabel } from '../../_shared/hooks/useProjects';
import { useReviewOriginHref } from '../../_shared/hooks/useReviewOrigin';
import { projectFromOrigin } from './SampleRequestPageHeader';
import { projectCodeLabel } from '../../_shared/lib/projectCode';
import { ProjectPartyPicker } from '../../_shared/components/ProjectPartyPicker';
import { PartyContactsDialog } from '../../_shared/components/PartyContactsDialog';
import type { PartyContact } from '../../_shared/types/project.types';
import {
  useSampleRequestMutations,
  useSampleRequestQuery,
  useSampleRequestSwitches,
} from '../hooks/useSampleRequests';
import {
  getSampleRequestQuotationPrefill,
  searchSampleRequestProducts,
} from '../services/sampleRequestService';

const BASE_PATH = '/project-sales/sample-requests';

function Field({
  label,
  htmlFor,
  className,
  error,
  children,
}: {
  label: string;
  htmlFor?: string;
  className?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className={`min-w-0 space-y-1.5 ${className ?? ''}`}>
      {htmlFor ? <Label htmlFor={htmlFor}>{label}</Label> : <p className="text-sm font-medium">{label}</p>}
      {children}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}

const ReadValue = ({ children }: { children: ReactNode }) => (
  <p className="min-h-9 break-words rounded-md border border-dashed px-3 py-2 text-sm">
    {children || '-'}
  </p>
);

interface SampleRequestFormProps {
  /** Edit mode: the draft to change. */
  requestId?: string;
  /** New mode: a project to start from (the project tab's Create). */
  projectId?: string;
}

/**
 * Every server call the form makes, so one form serves two callers (SAMPLE-REQUEST-V2 slice 2,
 * owner Q1 a): staff through the CRM routes (the default), and a salesperson limited to their own
 * sample requests through My Requests (`useOwnSampleRequestApi`), whose rows stay theirs, their
 * customers their own debtors and their projects their own. The party and contact pickers use the
 * CRM's own party routes in both cases (they answer by the caller's grants and project scope).
 */
export interface SampleRequestFormApi {
  getRequest: (id: string) => Promise<SampleRequestDetail>;
  create: (body: SampleRequestWrite) => Promise<SampleRequestDetail>;
  update: (id: string, body: SampleRequestWrite) => Promise<SampleRequestDetail>;
  submit: (id: string) => Promise<SampleRequestDetail>;
  lookupCustomers: (q: string) => Promise<CustomerLookupItem[]>;
  searchProjects: (q: string) => Promise<{ value: string; label: string }[]>;
  searchProducts: typeof searchSampleRequestProducts;
  getPrefill: typeof getSampleRequestQuotationPrefill;
}

/** The My Requests calls, from the portal's own service over the CRM session (`MyRequestClientProvider`). */
function useOwnSampleRequestApi(): SampleRequestFormApi {
  const client = useSubmissionClient();
  return useMemo(() => {
    const svc = clientService(client, 'sampleRequest', portalSampleRequest);
    return {
      getRequest: svc.getSampleRequest,
      create: svc.createSampleRequest,
      update: svc.updateSampleRequest,
      submit: svc.submitSampleRequest,
      lookupCustomers: async (q) =>
        (await svc.lookupSampleRequestCustomers(q)).map((c) => ({
          customer_id: c.customer_id,
          customer_code: c.customer_code,
          debtor_name: c.debtor_name,
          debtor_type: null,
          sales_type: null,
        })),
      // The CRM project search, which the own-scope guard answers with this salesperson's own
      // projects only: the portal lookup is company-wide, and My Requests refuses any other
      // project on save (security review B1, slice 2).
      searchProjects: (q) => searchProjectsForLink(q, 1),
      searchProducts: svc.searchSampleRequestProducts as typeof searchSampleRequestProducts,
      getPrefill: svc.getSampleRequestQuotationPrefill as typeof getSampleRequestQuotationPrefill,
    };
  }, [client]);
}

/** The query a salesperson's own request is read with (dropped after every save, review S2). */
const OWN_REQUEST_KEY = ['my-request', 'sample_request'] as const;

function OwnSampleRequestForm(props: SampleRequestFormProps) {
  const api = useOwnSampleRequestApi();
  if (props.requestId) return <OwnSampleRequestOpen requestId={props.requestId} api={api} />;
  return <StaffSampleRequestForm {...props} api={api} />;
}

/**
 * A salesperson's own request, opened from its row or its edit link: a draft is the guided form
 * (the same as New, owner standing rule "Edit opens the same form as Create"); anything submitted
 * is the read-only view with its PDF and Cancel (review B1 / N1, slice 2).
 */
function OwnSampleRequestOpen({ requestId, api }: { requestId: string; api: SampleRequestFormApi }) {
  const own = useQuery({
    queryKey: [...OWN_REQUEST_KEY, requestId],
    queryFn: () => api.getRequest(requestId),
    refetchOnMount: 'always',
    staleTime: 0,
  });
  if (own.isError) return <LoadFailed onRetry={() => void own.refetch()} />;
  if (!own.data) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-4">
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (own.data.status !== 'draft') return <PortalSampleRequestForm requestId={requestId} />;
  return <StaffSampleRequestForm requestId={requestId} api={api} />;
}

/** Nothing hangs (owner standing rule): a request that cannot be loaded says so, with Try again. */
function LoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="mx-auto w-full max-w-4xl rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center text-sm">
      <p>This sample request could not be loaded.</p>
      <Button type="button" variant="outline" size="sm" className="mt-3" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

/** The detail page of a salesperson limited to their own sample requests (same rule as above). */
export function OwnSampleRequestDetail({ requestId }: { requestId: string }) {
  return (
    <MyRequestClientProvider>
      <OwnSampleRequestForm requestId={requestId} />
    </MyRequestClientProvider>
  );
}

/**
 * One form for everyone (SAMPLE-REQUEST-V2 slice 2, owner Q1 a: one experience from registration
 * on). A salesperson limited to their own sample requests writes through My Requests, so their
 * rows stay theirs (PORTAL-P4-REQUESTS R3); everyone else through the CRM routes.
 */
export default function SampleRequestForm(props: SampleRequestFormProps) {
  const { limited } = useRequestScope('sample_request');
  if (limited) {
    return (
      <MyRequestClientProvider>
        <OwnSampleRequestForm {...props} />
      </MyRequestClientProvider>
    );
  }
  return <StaffSampleRequestForm {...props} />;
}

function StaffSampleRequestForm({
  requestId,
  projectId,
  api,
}: SampleRequestFormProps & { api?: SampleRequestFormApi }) {
  const router = useRouter();
  const origin = useReviewOriginHref();
  const { create, update, submit } = useSampleRequestMutations();
  const staffExisting = useSampleRequestQuery(api ? null : (requestId ?? null));
  const ownExisting = useQuery({
    queryKey: [...OWN_REQUEST_KEY, requestId],
    queryFn: () => (api as SampleRequestFormApi).getRequest(requestId as string),
    enabled: Boolean(api && requestId),
    refetchOnMount: 'always',
    staleTime: 0,
  });
  const existing = api ? ownExisting : staffExisting;
  const [apiBusy, setApiBusy] = useState(false);
  const { data: switches } = useSampleRequestSwitches();
  const canEditParties = useHasPermission('projects.parties.edit');
  const roleLabel = usePartyRoleLabel();
  const [state, setState] = useState<FormState>({ ...EMPTY_FORM, lines: [blankLine()] });
  const [hydrated, setHydrated] = useState(!requestId);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [serverMessage, setServerMessage] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [contactsOpen, setContactsOpen] = useState(false);
  const [open, setOpen] = useState({ customer: true, shipTo: true, items: true, delivery: true });

  const set = useCallback(
    <K extends keyof FormState>(key: K, value: FormState[K]) =>
      setState((prev) => ({ ...prev, [key]: value })),
    [],
  );
  const patch = useCallback(
    (next: Partial<FormState>) => setState((prev) => ({ ...prev, ...next })),
    [],
  );
  const project = useProject(state.project_id || undefined);
  const siteAddress = project.data?.address ?? null;
  const contacts = usePartyContacts(state.ship_to_party_id || null);

  // A request from a quotation offers only that quotation's products (SFQ-27).
  const sourceDoc = state.quotation_document_id;
  const sourceIssue = state.quotation_issue_id;
  const searchProductsForRequest = useCallback(
    (q: string) => {
      const source = productSource(sourceDoc, sourceIssue);
      const search = api?.searchProducts ?? searchSampleRequestProducts;
      return source ? search(q, source) : search(q);
    },
    [sourceDoc, sourceIssue, api],
  );
  // A NEW request starts from its project's quotation (SAMPLE-FROM-QUOTE, owner Q6 a); a draft
  // never refills.
  const prefill = useSampleRequestPrefill({
    enabled: !requestId,
    projectId: state.project_id,
    state,
    patch,
    fetchPrefill: api?.getPrefill ?? getSampleRequestQuotationPrefill,
  });

  useEffect(() => {
    // Fill the form from a FRESH read only: a cached copy from before the last save would otherwise
    // be shown and then saved back (review S2). The cache itself is never dropped mid-submit (R2-B1).
    if (requestId && existing.data && !hydrated && !existing.isFetching) {
      const loaded = stateFromDetail(existing.data);
      setState(loaded.lines.length ? loaded : { ...loaded, lines: [blankLine()] });
      setHydrated(true);
    }
  }, [requestId, existing.data, existing.isFetching, hydrated]);

  // A project passed in the URL starts the request on that project, its buyer prefilled.
  const startProject = useProject(!requestId ? projectId : undefined);
  useEffect(() => {
    const p = startProject.data;
    if (!p || requestId) return;
    setState((prev) =>
      prev.project_id
        ? prev
        : {
            ...prev,
            project_id: p.id,
            project_label: `${projectCodeLabel(p)} - ${p.title}`,
            // The project's buyer is its originating lead's customer; none when registered directly.
            ...(p.customer_id && !prev.customer_id
              ? { customer_id: p.customer_id, customer_label: p.customer_name ?? '' }
              : {}),
          },
    );
  }, [startProject.data, requestId]);

  /** Where every exit goes: the page the person came from, else the list (owner, 11 Nov 16:30). */
  const leave = (fallback: string) => router.push(origin ?? fallback);

  const explain = (e: unknown) => {
    const message = e instanceof Error ? e.message : 'Failed to save the sample request';
    if (e instanceof SampleRequestError && e.field) {
      setErrors((prev) => ({ ...prev, [e.field as string]: message }));
    }
    setServerMessage(message);
  };

  const saving = apiBusy || create.isPending || update.isPending || submit.isPending;

  const save = async () => {
    const body = staffPayloadFromState(state);
    if (api) return requestId ? api.update(requestId, body) : api.create(body);
    return requestId
      ? update.mutateAsync({ id: requestId, data: body })
      : create.mutateAsync(body);
  };
  const submitSaved = (id: string) => (api ? api.submit(id) : submit.mutateAsync(id));
  /** The My Requests path has no mutation hook: hold the buttons while it runs. */
  const busy = async <T,>(fn: () => Promise<T>): Promise<T> => {
    setApiBusy(true);
    try {
      return await fn();
    } finally {
      setApiBusy(false);
    }
  };


  const handleSaveDraft = async () => {
    setServerMessage(null);
    const numberProblems = numberErrors(state);
    setErrors(numberProblems);
    if (Object.keys(numberProblems).length > 0) return;
    try {
      await busy(save);
      toast.success('Draft saved');
      leave(BASE_PATH);
    } catch (e) {
      explain(e);
    }
  };

  const handlePreview = () => {
    setServerMessage(null);
    const found = validateStaff(state, { requireProject: switches?.requireProject });
    setErrors(found);
    if (Object.keys(found).length > 0) {
      // Open the sections holding a problem so the message is in view.
      setOpen((o) => ({
        customer: o.customer || Boolean(found.customer_id || found.project_id),
        shipTo:
          o.shipTo || Boolean(found.ship_to_party_id || found.ship_to_role || found.ship_to_address),
        items: o.items || Boolean(found.lines || found.board_label),
        delivery:
          o.delivery || Boolean(found.delivery_date || found.delivery_mode || found.loan_value),
      }));
      return;
    }
    setPreviewOpen(true);
  };

  const handleSubmit = async () => {
    setServerMessage(null);
    try {
      const saved = await busy(save);
      const done = await busy(() => submitSaved(saved.id));
      toast.success(`Sample request ${done?.request_no ?? saved.request_no} submitted`);
      setPreviewOpen(false);
      leave(BASE_PATH);
    } catch (e) {
      // A refused submit closes the popup so the form shows the problem.
      setPreviewOpen(false);
      explain(e);
    }
  };

  async function applyContacts(ids: string[]) {
    // A contact added inside the popup may not be in the cached list yet: read it fresh then.
    let list: PartyContact[] = contacts.data ?? [];
    if (ids.some((id) => !list.some((c) => c.id === id))) {
      list = (await contacts.refetch()).data ?? list;
    }
    const rows = ids
      .map((id) => list.find((c) => c.id === id))
      .filter((c): c is PartyContact => Boolean(c));
    setState((prev) => withShipToContacts(prev, rows));
  }

  if (requestId && existing.isError) {
    return <LoadFailed onRetry={() => void existing.refetch()} />;
  }
  if (requestId && (existing.isLoading || !hydrated)) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-4">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  const record = existing.data;
  const requireProject = Boolean(switches?.requireProject);
  // The project is fixed text when the form was opened from that project (its tab's Create, or
  // Edit of a request opened from its tab): Edit matches Create (standing rule, crew pass 11 Nov).
  const projectFixed =
    Boolean(state.project_id) &&
    ((Boolean(projectId) && !requestId) || projectFromOrigin(origin) === state.project_id);
  const projectText = state.project_id ? state.project_label : state.project_title;
  const customerText = state.customer_id ? state.customer_label : '';
  const roleText = state.ship_to_role ? roleLabel(state.ship_to_role) : '';
  const pickedLines = state.lines.filter((l) => l.product_id);
  const contactText = [state.site_contact_name, state.site_contact_phone].filter(Boolean).join(', ');
  const shipToText = state.ship_to_name
    ? `${state.ship_to_name}${roleText ? ` (${roleText})` : ''}`
    : '';
  const deliveryText = [
    state.delivery_date ? formatDateInMalaysia(state.delivery_date) : '',
    state.delivery_mode ? DELIVERY_MODE_LABELS[state.delivery_mode] : '',
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="mx-auto w-full max-w-4xl space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`${STATUS_PILL_BASE} ${statusPillClass('draft')}`}>
          {record?.status_label ?? 'Draft'}
        </span>
      </div>

      <FormSection
        title="Customer & project"
        summary={[customerText, projectText].filter(Boolean).join(' · ')}
        open={open.customer}
        onOpenChange={(v) => setOpen((o) => ({ ...o, customer: v }))}
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label="Customer *"
            htmlFor="sr-customer"
            className="sm:col-span-2"
            error={errors.customer_id}
          >
            <AsyncCombobox<CustomerLookupItem>
              id="sr-customer"
              value={customerText}
              onChange={(_v, item) => {
                // A debtor only (owner, 11 Nov: "customer stay mandatory and source from debtor").
                if (item && item.customer_id) {
                  patch({
                    customer_id: item.customer_id,
                    customer_label: item.debtor_name,
                    customer_name: '',
                  });
                } else {
                  patch({ customer_id: '', customer_label: '', customer_name: '' });
                }
              }}
              fetchOptions={api?.lookupCustomers ?? lookupCustomersForRequest}
              optionValue={(o) => o.debtor_name}
              optionLabel={(o) => o.debtor_name}
              optionMeta={(o) => o.customer_code}
              placeholder="Search a debtor"
            />
          </Field>
          {projectFixed ? (
            <Field label="Project">
              <ReadValue>{state.project_label}</ReadValue>
            </Field>
          ) : (
            <Field
              label={requireProject ? 'Project *' : 'Registered project'}
              htmlFor="sr-project"
              error={errors.project_id}
            >
              <SearchableSelect
                id="sr-project"
                value={state.project_id}
                onChange={(v) => {
                  if (!v) {
                    setState((prev) =>
                      withShipToParty({ ...prev, project_id: '', project_label: '' }, null),
                    );
                  }
                }}
                onOptionChange={(opt) =>
                  opt &&
                  setState((prev) =>
                    withShipToParty(
                      { ...prev, project_id: opt.value, project_label: opt.label },
                      null,
                    ),
                  )
                }
                selectedOption={
                  state.project_id
                    ? { value: state.project_id, label: state.project_label }
                    : undefined
                }
                fetchOptions={(query, pageIndex) =>
                  api
                    ? pageIndex === 0
                      ? api.searchProjects(query)
                      : Promise.resolve([])
                    : searchProjectsForLink(query, pageIndex + 1)
                }
                paginated={!api}
                pageSize={25}
                clearable
                truncateTriggerLabel
                placeholder="Search a project by code or title"
                emptyMessage="No project matches that."
              />
            </Field>
          )}
          {!state.project_id && !requireProject && (
            <Field label="Project title" htmlFor="sr-project-title">
              <Input
                id="sr-project-title"
                value={state.project_title}
                onChange={(e) => set('project_title', e.target.value)}
              />
            </Field>
          )}
          <Field label="Requested by">
            <ReadValue>
              {[
                record?.salesperson_name ?? 'You',
                formatDateInMalaysia(record?.request_date ?? new Date()),
              ]
                .filter(Boolean)
                .join(' · ')}
            </ReadValue>
          </Field>
        </div>
      </FormSection>

      <FormSection
        title="Ship to"
        summary={[shipToText, state.site_contact_name].filter(Boolean).join(' · ')}
        open={open.shipTo}
        onOpenChange={(v) => setOpen((o) => ({ ...o, shipTo: v }))}
      >
        <div className="grid grid-cols-1 gap-4">
          <ProjectPartyPicker
            projectId={state.project_id || null}
            id="sr-ship-to"
            roleSelectId="sr-ship-to-role"
            label="Ship to *"
            partyId={state.ship_to_party_id}
            role={state.ship_to_role}
            fallbackName={state.ship_to_name}
            error={errors.ship_to_party_id ?? errors.ship_to_role}
            onPick={(party, role, onProject) =>
              setState((prev) =>
                withShipToParty(
                  prev,
                  party
                    ? {
                        id: party.id,
                        name: party.name,
                        // A names-only search leaves the address unknown: the server fills it.
                        address: party.detailed ? party.address : null,
                        role,
                        siteAddress: party.detailed ? siteAddress : null,
                        needsRole: Boolean(prev.project_id) && !onProject,
                        addressUnknown: !party.detailed,
                      }
                    : null,
                ),
              )
            }
            onRoleChange={(role) => patch({ ship_to_role: role ?? '' })}
          />
          {state.ship_to_typed_before && !state.ship_to_party_id && (
            <p className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
              Typed before: {state.ship_to_typed_before}
            </p>
          )}
          <Field label="Shipping address *" htmlFor="sr-address" error={errors.ship_to_address}>
            <Textarea
              id="sr-address"
              rows={3}
              value={state.ship_to_address}
              onChange={(e) => set('ship_to_address', e.target.value)}
            />
          </Field>
          <Field label="Contact person">
            <div className="flex min-h-9 items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm">
              <span className="min-w-0 truncate" title={contactText}>
                {contactText || <span className="text-muted-foreground">No contact picked</span>}
              </span>
              {state.ship_to_party_id && (
                <Button
                  type="button"
                  variant="link"
                  size="sm"
                  className="h-auto shrink-0 p-0"
                  onClick={() => setContactsOpen(true)}
                >
                  Choose contact
                </Button>
              )}
            </div>
          </Field>
        </div>
      </FormSection>

      <FormSection
        title="Items"
        summary={
          pickedLines.length
            ? `${pickedLines.length} ${pickedLines.length === 1 ? 'item' : 'items'}`
            : ''
        }
        open={open.items}
        onOpenChange={(v) => setOpen((o) => ({ ...o, items: v }))}
      >
        {prefill.documents.length > 1 && (
          <div className="mb-3">
            <SampleRequestQuotationPicker
              documents={prefill.documents}
              value={prefill.documentId ?? ''}
              onPick={prefill.pickDocument}
            />
          </div>
        )}
        <SampleRequestLines
          value={state}
          onChange={patch}
          search={searchProductsForRequest}
          listWhenEmpty={Boolean(sourceDoc)}
          captions={{ no: 'No.', item: 'Item Code', qty: 'Qty' }}
          errors={errors}
        />
        {prefill.note && (
          <div className="mt-3">
            <SampleRequestPrefillNote note={prefill.note} />
          </div>
        )}
        <div className="mt-3">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => patch({ lines: [...state.lines, blankLine()] })}
          >
            <Plus className="size-4" />
            Add row
          </Button>
        </div>
      </FormSection>

      <FormSection
        title="Delivery"
        summary={deliveryText}
        open={open.delivery}
        onOpenChange={(v) => setOpen((o) => ({ ...o, delivery: v }))}
      >
        <div className="space-y-4">
          <Field
            label="Request delivery date *"
            htmlFor="sr-delivery-date"
            error={errors.delivery_date}
          >
            <div className="sm:max-w-xs">
              <DatePicker
                id="sr-delivery-date"
                ariaLabel="Request delivery date"
                value={state.delivery_date ? new Date(`${state.delivery_date}T00:00:00`) : undefined}
                onChange={(d) => set('delivery_date', toIsoDate(d) ?? '')}
              />
            </div>
          </Field>
          <SampleRequestFooterFields state={state} set={set} errors={errors} />
        </div>
      </FormSection>

      {serverMessage && (
        <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {serverMessage}
        </p>
      )}

      <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-end">
        <Button type="button" variant="outline" onClick={handleSaveDraft} disabled={saving}>
          {saving && !previewOpen && <Loader2 className="mr-1 size-4 animate-spin" />}
          Save as draft
        </Button>
        <Button type="button" onClick={handlePreview} disabled={saving}>
          Preview
        </Button>
      </div>

      {contactsOpen && state.ship_to_party_id && (
        <PartyContactsDialog
          parties={[{ partyId: state.ship_to_party_id, name: state.ship_to_name }]}
          picks={{ [state.ship_to_party_id]: state.ship_to_contact_ids }}
          canEdit={canEditParties}
          onSave={(next) => void applyContacts(next[state.ship_to_party_id] ?? [])}
          onClose={() => setContactsOpen(false)}
        />
      )}

      <Dialog open={previewOpen} onOpenChange={(v) => !saving && setPreviewOpen(v)}>
        <DialogContent className="sm:max-w-2xl" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>Preview sample request</DialogTitle>
          </DialogHeader>
          <DialogBody>
            <dl className="grid grid-cols-1 gap-x-4 gap-y-2 text-sm sm:grid-cols-[150px_1fr]">
              <dt className="text-muted-foreground">Customer</dt>
              <dd className="break-words">{customerText || '-'}</dd>
              <dt className="text-muted-foreground">Project</dt>
              <dd className="break-words">{projectText || '-'}</dd>
              <dt className="text-muted-foreground">Ship to</dt>
              <dd className="break-words">
                {shipToText || '-'}
                {state.ship_to_address && (
                  <span className="block whitespace-pre-line text-muted-foreground">
                    {state.ship_to_address}
                  </span>
                )}
              </dd>
              <dt className="text-muted-foreground">Contact</dt>
              <dd className="break-words">{contactText || '-'}</dd>
              <dt className="text-muted-foreground">Deliver by</dt>
              <dd>{deliveryText || '-'}</dd>
              <dt className="text-muted-foreground">Loan</dt>
              <dd>
                {state.loan_value} {state.loan_unit === 'days' ? 'days' : 'months'},{' '}
                {GOODS_FROM_LABELS[goodsFromTicks(state.goods_demo, state.goods_new)]}
              </dd>
              <dt className="text-muted-foreground">Items</dt>
              <dd className="min-w-0">
                <ul className="space-y-0.5">
                  {pickedLines.map((l) => (
                    <li key={l.key} className="truncate" title={l.label}>
                      {l.qty} x {l.label}
                      {l.remark ? ` (${l.remark})` : ''}
                    </li>
                  ))}
                  {state.board_mounting && <li>Board: {state.board_label}</li>}
                </ul>
              </dd>
            </dl>
          </DialogBody>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setPreviewOpen(false)}
              disabled={saving}
            >
              Back to edit
            </Button>
            <Button type="button" onClick={handleSubmit} disabled={saving}>
              {saving && <Loader2 className="mr-1 size-4 animate-spin" />}
              Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
