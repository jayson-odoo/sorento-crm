'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import { Loader2, Sparkles } from 'lucide-react';
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
import { NumberInput } from '@/components/ui/number-input';
import { numberFieldError } from '@/lib/number-field';
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { FormSection } from '@/components/common/FormSection';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { toast } from '@/lib/toast';
import { useLookupSetOptions } from '@/hooks/useLookupSetOptions';
import { getUserLookup } from '@/services/userSelectService';
import {
  CLASH_MIN_CHARS,
  useClashPreview,
  useFetchClashPreview,
  useFetchCustomerOptions,
  useFetchLeadOptions,
  useFetchPartyOptions,
  type LeadPick,
  usePartyMutations,
  useProjectTemplates,
  useProjectTypes,
  useRegisterProject,
  useSubmitProject,
  useTakeoverMutations,
  useUpdateProject,
} from '../hooks/useProjects';
import type {
  ClashCandidate,
  PartyType,
  Project,
  ProjectRegisterBody,
  ProjectUpdateBody,
} from '../types/project.types';
import { ClashWarningPanel } from '../../pipeline/components/ClashWarningPanel';
import { isAwaitingDecision } from './ApprovalStatePill';
import { LeadWizardDialog } from '../../leads/components/LeadWizardDialog';
import { ProjectAIExtractDialog, type ProjectExtractFill } from './ProjectAIExtractDialog';

type ProjectFormProps = { mode: 'create' } | { mode: 'edit'; project: Project };

const OWNER_MANAGE_PERMISSION = 'projects.projects.manage';
const PROJECT_EDIT_PERMISSION = 'projects.projects.edit';
const REGISTRATION_SUBMIT_PERMISSION = 'projects.registrations.submit';
const PARTY_EDIT_PERMISSION = 'projects.parties.edit';

/**
 * The form both `/project-sales/new` and `/project-sales/<id>/edit` render
 * (PLAN-project-form-28sep.md D1). One `<form>`, no dialog: the client asked for the
 * dialog gone and create and edit standardised on the same page.
 *
 * The Check button, the clash preview and the progressive "Details" section carry over
 * from the register dialog it replaces (PR #1336 round 2). Two things differ from that
 * dialog:
 *
 * - A third section, "Salesperson and customer", open from the start.
 * - Edit mode starts every section open, never wipes the project's own template on
 *   first render, and excludes the project itself from its own clash check.
 */
export function ProjectForm(props: ProjectFormProps) {
  const { mode } = props;
  const project = mode === 'edit' ? props.project : undefined;
  const router = useRouter();
  const { data: session } = useSession();
  const canManageOwner = useHasPermission(OWNER_MANAGE_PERMISSION);
  const canEditProjects = useHasPermission(PROJECT_EDIT_PERMISSION);
  const canSubmitRegistration = useHasPermission(REGISTRATION_SUBMIT_PERMISSION);
  const canCreateParty = useHasPermission(PARTY_EDIT_PERMISSION);
  // A salesperson with the submit slug but no edit rights saves a draft or submits for
  // approval instead of registering (PROJECT-REGISTER-V2 J1).
  const submitOnly = !canEditProjects && canSubmitRegistration;

  const register = useRegisterProject();
  const update = useUpdateProject(project?.id ?? '');
  const submitDraft = useSubmitProject(project?.id ?? '');
  const { create: createPartyMutation } = usePartyMutations();

  const [title, setTitle] = React.useState(project?.title ?? '');
  const [developerId, setDeveloperId] = React.useState(project?.developer_party_id ?? '');
  const [developerOption, setDeveloperOption] = React.useState<PickOption | null>(
    project?.developer_party_id
      ? { value: project.developer_party_id, label: project.developer_name ?? 'Developer' }
      : null,
  );
  const [typeId, setTypeId] = React.useState(project?.type_id ?? '');
  const [templateId, setTemplateId] = React.useState(project?.template_id ?? '');
  const [registeredCompany, setRegisteredCompany] = React.useState(
    project?.registered_company_name ?? '',
  );
  const [location, setLocation] = React.useState(project?.location ?? '');
  const [state, setState] = React.useState(project?.state ?? '');
  const [mukim, setMukim] = React.useState(project?.mukim ?? '');
  // What the salesperson typed on a portal registration, shown under a party picker until
  // somebody picks the party (PROJECT-REG-PORTAL R7).
  const typed = project?.registration ?? null;
  const [address, setAddress] = React.useState(project?.address ?? '');
  const [adminRef, setAdminRef] = React.useState(project?.admin_ref ?? '');
  const [architectId, setArchitectId] = React.useState(project?.architect_party_id ?? '');
  const [architectOption, setArchitectOption] = React.useState<PickOption | null>(
    project?.architect_party_id
      ? { value: project.architect_party_id, label: project.architect_name ?? 'Architect' }
      : null,
  );
  const [mainContractorId, setMainContractorId] = React.useState(
    project?.main_contractor_party_id ?? '',
  );
  const [contractorOption, setContractorOption] = React.useState<PickOption | null>(
    project?.main_contractor_party_id
      ? {
          value: project.main_contractor_party_id,
          label: project.main_contractor_name ?? 'Main contractor',
        }
      : null,
  );
  const [customerId, setCustomerId] = React.useState(project?.customer_id ?? '');
  const [customerOption, setCustomerOption] = React.useState<PickOption | null>(
    project?.customer_id
      ? { value: project.customer_id, label: project.customer_name ?? 'Customer' }
      : null,
  );
  const [estimatedValue, setEstimatedValue] = React.useState(project?.estimated_sales_value ?? '');
  const [launchDate, setLaunchDate] = React.useState(project?.launch_date ?? '');
  const [deliveryFrom, setDeliveryFrom] = React.useState(project?.expected_delivery_from ?? '');
  const [deliveryTo, setDeliveryTo] = React.useState(project?.expected_delivery_to ?? '');
  const [ownerUserId, setOwnerUserId] = React.useState(
    mode === 'create' ? (session?.user?.id ?? '') : (project?.owner_user_id ?? ''),
  );
  // The session can resolve after the first render; the default salesperson follows it
  // until somebody picks one.
  const sessionUserId = session?.user?.id;
  React.useEffect(() => {
    if (mode === 'create' && sessionUserId) {
      setOwnerUserId((current) => current || sessionUserId);
    }
  }, [mode, sessionUserId]);
  const [leadId, setLeadId] = React.useState(project?.lead_id ?? '');
  const [leadOption, setLeadOption] = React.useState<PickOption | null>(
    project?.lead_id ? { value: project.lead_id, label: project.lead_code ?? 'Linked lead' } : null,
  );
  // The lead governs the customer: when the lead has one it is shown read-only. An edit with a
  // stored lead shows the project's own customer without asking the lead again.
  const [leadHasCustomer, setLeadHasCustomer] = React.useState(
    mode === 'edit' && Boolean(project?.lead_id) && Boolean(project?.customer_id),
  );

  // The text typed into the Lead picker when nothing matched; non-null opens the lead wizard.
  const [creatingLeadTitle, setCreatingLeadTitle] = React.useState<string | null>(null);

  // The blocking project the user is registering interest in (D4); non-null opens the dialog.
  const [interestTarget, setInterestTarget] = React.useState<ClashCandidate | null>(null);
  const [extractOpen, setExtractOpen] = React.useState(false);

  const fetchDeveloperOptions = useFetchPartyOptions('developer');
  const fetchArchitectOptions = useFetchPartyOptions('architect');
  const fetchContractorOptions = useFetchPartyOptions('main_contractor');
  const fetchCustomerOptions = useFetchCustomerOptions();
  const types = useProjectTypes();
  const templates = useProjectTemplates(typeId || undefined);
  const states = useLookupSetOptions('my_state');
  const fetchLeadOptions = useFetchLeadOptions();
  const users = useQuery({
    queryKey: ['user-lookup', 'project-owner'],
    queryFn: () => getUserLookup(),
  });

  // The title the user last checked; editing the field clears it, so a result never
  // sits under a title it was not asked about.
  const [checkedTitle, setCheckedTitle] = React.useState('');
  // The title counts as filled once the user leaves the field or checks it, so Details
  // does not open under them after the first letter.
  const [titleSettled, setTitleSettled] = React.useState(mode === 'edit');
  const clash = useClashPreview(checkedTitle, developerId || null);
  const fetchClash = useFetchClashPreview();

  const [sectionOpen, setSectionOpen] = React.useState({
    who: true,
    details: mode === 'edit',
    salesCustomer: true,
  });
  // Edit mode never runs the auto-open below: every field already has a value, so
  // there is nothing "complete" to react to.
  const detailsSettledRef = React.useRef(mode === 'edit');

  const selectedType = types.data?.find((type) => type.id === typeId);
  // A property development infers its delivery window from the launch date plus a
  // configurable lag; anything else has to state the window, because a hotel
  // refurbishment has no launch date to count from.
  const derivesDelivery = selectedType?.derives_delivery_from_launch ?? false;

  function toggleSection(key: 'who' | 'details' | 'salesCustomer', next: boolean) {
    if (key === 'details') detailsSettledRef.current = true;
    setSectionOpen((prev) => ({ ...prev, [key]: next }));
  }

  // Template counts only when the chosen type offers one to pick, and only once that is
  // known: an unanswered template list must not open Details early.
  const templateNeeded = Boolean(typeId) && (templates.data?.length ?? 0) > 0;
  const whoComplete =
    Boolean(developerId) &&
    Boolean(typeId) &&
    templates.isSuccess &&
    titleSettled &&
    title.trim().length > 0 &&
    (!templateNeeded || Boolean(templateId));

  // Every Who and what field filled opens Details, once per form (the portal price tag
  // form's openSectionOnce).
  React.useEffect(() => {
    if (!whoComplete || detailsSettledRef.current) return;
    detailsSettledRef.current = true;
    setSectionOpen((prev) => (prev.details ? prev : { ...prev, details: true }));
  }, [whoComplete]);

  // The server re-runs the clash check on an edit only when the title or developer
  // changes; the form's guard follows it, so a project that already exists is never
  // blocked from saving an unrelated field.
  const identityChanged =
    mode === 'create' ||
    title.trim() !== (project?.title ?? '') ||
    (developerId || null) !== (project?.developer_party_id ?? null);
  const checkable = title.trim().length >= CLASH_MIN_CHARS;
  const hasChecked = checkedTitle.length > 0;
  const rawCandidates = clash.data?.candidates ?? [];
  // A portal registration still waiting for (or refused) approval sits outside the
  // registration lock (PROJECT-REG-PORTAL R3, owner ruling: duplicates never block). Its
  // matches are shown as information only; Approve's exact-duplicate 409 is the guard.
  const awaitingDecision = isAwaitingDecision(project?.approval_state);
  // In edit mode the project's own record is a "clash" against itself; it must never
  // block a save or show up in the panel.
  const candidates = (
    mode === 'edit' ? rawCandidates.filter((c) => c.project_id !== project!.id) : rawCandidates
  ).map((c) => (awaitingDecision ? { ...c, blocks: false } : c));
  const wouldBlock =
    identityChanged && hasChecked && candidates.some((candidate) => candidate.blocks);
  const pending = register.isPending || update.isPending || submitDraft.isPending;
  const [showErrors, setShowErrors] = React.useState(false);
  const valueError = numberFieldError(estimatedValue, { min: 0, optional: true });
  // A new project needs its Lead (LEAD-GOVERNS-REGISTER D1) and a Customer, which the lead
  // supplies unless it has none. Edit leaves both optional, so a project registered before the
  // rule saves. A salesperson's Submit for approval enforces them either way.
  const leadMissing = (mode === 'create' || submitOnly) && !leadId;
  const customerMissing = (mode === 'create' || submitOnly) && !customerId;
  const canSubmit =
    title.trim().length > 0 && !leadMissing && !customerMissing && !wouldBlock && !pending;
  const canSaveDraft = title.trim().length > 0 && !pending;
  // The top blocking candidate: the footer's one primary becomes Register interest (D2).
  const blocker =
    mode === 'create' && wouldBlock ? candidates.find((candidate) => candidate.blocks) : undefined;

  async function handleCheck() {
    const trimmed = title.trim();
    if (trimmed.length < CLASH_MIN_CHARS) return;
    setTitleSettled(true);
    setCheckedTitle(trimmed);
    await fetchClash(trimmed, developerId || null).catch(() => undefined);
  }

  function buildBody(): ProjectRegisterBody {
    return {
      title: title.trim(),
      developer_party_id: developerId || null,
      type_id: typeId || null,
      template_id: templateId || null,
      owner_user_id: ownerUserId || null,
      registered_company_name: registeredCompany.trim() || null,
      location: location.trim() || null,
      state: state || null,
      mukim: mukim.trim() || null,
      address: address.trim() || null,
      admin_ref: adminRef.trim() || null,
      architect_party_id: architectId || null,
      main_contractor_party_id: mainContractorId || null,
      estimated_sales_value: estimatedValue.trim() || null,
      launch_date: launchDate || null,
      expected_delivery_from: deliveryFrom || null,
      expected_delivery_to: deliveryTo || null,
      // A lead's own customer is sent back unchanged, which the server accepts.
      ...((mode === 'create' ? Boolean(customerId) : customerId !== (project?.customer_id ?? ''))
        ? { customer_id: customerId || null }
        : {}),
      lead_id: leadId || null,
    };
  }

  /** Pre-fills the form from a confirmed AI extract; the typed title is never overwritten. */
  function applyExtract(fill: ProjectExtractFill) {
    if (fill.title && !title.trim()) setTitle(fill.title);
    if (fill.developer) {
      setDeveloperId(fill.developer.id);
      setDeveloperOption({ value: fill.developer.id, label: fill.developer.name });
    }
    if (fill.architect) {
      setArchitectId(fill.architect.id);
      setArchitectOption({ value: fill.architect.id, label: fill.architect.name });
    }
    if (fill.main_contractor) {
      setMainContractorId(fill.main_contractor.id);
      setContractorOption({ value: fill.main_contractor.id, label: fill.main_contractor.name });
    }
    if (fill.project_type && fill.project_type.id !== typeId) {
      setTypeId(fill.project_type.id);
      setTemplateId('');
    }
    if (fill.state) setState(fill.state);
    if (fill.mukim) setMukim(fill.mukim);
    setTitleSettled(true);
  }

  /** Takes the customer and the assignee from the picked lead (LEAD-GOVERNS-REGISTER D2, D4). */
  function takeFromLead(
    lead: {
      customer_id?: string | null;
      customer_name?: string | null;
      owner_user_id?: string | null;
    } | null,
  ) {
    setLeadHasCustomer(Boolean(lead?.customer_id));
    if (lead?.customer_id) {
      setCustomerId(lead.customer_id);
      setCustomerOption({ value: lead.customer_id, label: lead.customer_name ?? 'Customer' });
    } else if (mode === 'create' || lead) {
      setCustomerId('');
      setCustomerOption(null);
    }
    if (lead?.owner_user_id && canManageOwner) setOwnerUserId(lead.owner_user_id);
  }

  /** Creates a party from the typed text and selects it (B2); holders of parties.edit only. */
  function partyCreateOption(
    partyType: PartyType,
    noun: string,
    pick: (id: string, option: PickOption) => void,
  ) {
    if (!canCreateParty) return undefined;
    return {
      label: (query: string) => (
        <span>
          Create {noun} &ldquo;{query}&rdquo;
        </span>
      ),
      onCreate: async (query: string) => {
        try {
          const party = await createPartyMutation.mutateAsync({
            name: query.trim(),
            party_type: partyType,
          });
          pick(party.id, { value: party.id, label: party.name });
        } catch {
          // toasted by the mutation; the picker stays as it was
        }
      },
    };
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    await save(submitOnly ? true : undefined);
  }

  /**
   * `intent` is only set for a salesperson without edit rights: false saves a draft (title
   * only, no duplicate check), true submits it for approval.
   */
  async function save(intent?: boolean) {
    const draft = intent === false;
    if (draft ? !canSaveDraft : !canSubmit) return;
    if (valueError) {
      setShowErrors(true);
      return;
    }
    // The one duplicate check on submit: the guard, whether or not Check was pressed.
    if (!draft && checkable && identityChanged && !awaitingDecision) {
      const trimmed = title.trim();
      setCheckedTitle(trimmed);
      // A failed check does not stop the user: the server refuses a blocked title
      // with a 409 of its own, which the register/update mutation toasts.
      const preview = await fetchClash(trimmed, developerId || null).catch(() => null);
      const previewCandidates = preview?.candidates ?? [];
      const filtered =
        mode === 'edit'
          ? previewCandidates.filter((c) => c.project_id !== project!.id)
          : previewCandidates;
      if (filtered.some((c) => c.blocks)) return;
    }
    // A refusal (409 lead_already_linked, 403, ...) is toasted by the mutation hook;
    // the user stays on the form with what they typed.
    try {
      if (mode === 'create') {
        const body: ProjectRegisterBody = buildBody();
        if (intent !== undefined) body.submit = intent;
        const created = await register.mutateAsync(body);
        router.push(`/project-sales/${created.id}`);
      } else {
        const body: ProjectUpdateBody = buildBody();
        await update.mutateAsync(body);
        if (intent === true) await submitDraft.mutateAsync();
        router.push(`/project-sales/${project!.id}`);
      }
    } catch {
      // handled by the hook's onError
    }
  }

  function handleCancel() {
    router.push(mode === 'create' ? '/project-sales/pipeline' : `/project-sales/${project!.id}`);
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="space-y-4">
        <FormSection
          title="Who and what"
          summary={title.trim() || null}
          open={sectionOpen.who}
          onOpenChange={(next) => toggleSection('who', next)}
        >
          <div className="space-y-1.5">
            <Label htmlFor="project-title">
              Project title <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="project-title"
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
                setCheckedTitle('');
                if (!event.target.value.trim()) setTitleSettled(false);
              }}
              onBlur={() => setTitleSettled(title.trim().length > 0)}
              placeholder="e.g. Setia Alam Phase 3B"
              autoComplete="off"
              rows={3}
              className="min-h-20 [field-sizing:content]"
              required
            />
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!checkable || clash.isFetching}
                onClick={() => void handleCheck()}
              >
                {clash.isFetching && hasChecked && (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                )}
                Check
              </Button>
              <Button type="button" variant="outline" onClick={() => setExtractOpen(true)}>
                <Sparkles className="size-4" aria-hidden />
                AI extract
              </Button>
            </div>
            {hasChecked && clash.isSuccess && !clash.isFetching && candidates.length === 0 && (
              <p className="text-xs text-muted-foreground" aria-live="polite">
                No existing project matches this title.
              </p>
            )}
          </div>

          {hasChecked && <ClashWarningPanel candidates={candidates} isLoading={clash.isFetching} />}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="project-developer">Developer</Label>
              <SearchableSelect
                id="project-developer"
                value={developerId}
                onChange={setDeveloperId}
                onOptionChange={setDeveloperOption}
                fetchOptions={fetchDeveloperOptions}
                selectedOption={developerOption ?? undefined}
                clearable
                placeholder="Search developers"
                emptyMessage="No developers found"
                createOption={partyCreateOption('developer', 'developer', (id, option) => {
                  setDeveloperId(id);
                  setDeveloperOption(option);
                })}
              />
              <TypedHint typed={typed?.developer_name} picked={developerId} />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="project-type">Project type</Label>
              <SearchableSelect
                id="project-type"
                value={typeId}
                onChange={(next) => {
                  // A new type must clear the template too, or a stale template from
                  // the previous type is submitted and the project gets roles it should
                  // not offer. In the handler, not an effect, so opening an edit form
                  // never wipes the project's own template.
                  setTypeId(next);
                  if (next !== typeId) setTemplateId('');
                }}
                clearable
                loadError={types.error}
                onRetry={() => void types.refetch()}
                options={(types.data ?? []).map((type) => ({
                  value: type.id,
                  label: type.name,
                }))}
                placeholder="Select a type"
              />
            </div>
          </div>

          {typeId && (
            <div className="space-y-1.5">
              <Label htmlFor="project-template">Template</Label>
              <SearchableSelect
                id="project-template"
                value={templateId}
                onChange={setTemplateId}
                clearable
                loadError={templates.error}
                onRetry={() => void templates.refetch()}
                options={(templates.data ?? []).map((template) => ({
                  value: template.id,
                  label: template.name,
                  description: template.has_forked_status_graph
                    ? 'Has its own stage flow'
                    : undefined,
                }))}
                placeholder="Select a template"
                emptyMessage="No templates for this type"
              />
            </div>
          )}

        </FormSection>

        <FormSection
          title="Details"
          open={sectionOpen.details}
          onOpenChange={(next) => toggleSection('details', next)}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="project-registered-company">Registered company / SPV</Label>
              <Input
                id="project-registered-company"
                value={registeredCompany}
                onChange={(event) => setRegisteredCompany(event.target.value)}
                placeholder="Optional"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-location">Location</Label>
              <Input
                id="project-location"
                value={location}
                onChange={(event) => setLocation(event.target.value)}
                placeholder="e.g. Setia Alam, Selangor"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="project-state">State</Label>
              <SearchableSelect
                id="project-state"
                value={state}
                onChange={setState}
                clearable
                loadError={states.error}
                onRetry={() => void states.refetch()}
                options={[
                  // A stored value the lookup set no longer offers still shows as itself.
                  ...(state && !(states.data ?? []).some((o) => o.value === state)
                    ? [{ value: state, label: state }]
                    : []),
                  ...(states.data ?? []).map((option) => ({
                    value: option.value,
                    label: option.label,
                  })),
                ]}
                placeholder="Select a state"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-mukim">Mukim</Label>
              <Input
                id="project-mukim"
                value={mukim}
                onChange={(event) => setMukim(event.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="project-address">Address</Label>
            <Textarea
              id="project-address"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
              rows={3}
              placeholder="Optional"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="project-admin-ref">Reference</Label>
              <Input
                id="project-admin-ref"
                value={adminRef}
                onChange={(event) => setAdminRef(event.target.value)}
                maxLength={64}
                placeholder="e.g. PS26-0143"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-value">Estimated sales value (RM)</Label>
              <NumberInput
                id="project-value"
                min="0"
                step="0.01"
                inputMode="decimal"
                value={estimatedValue}
                error={showErrors ? valueError : undefined}
                onChange={(event) => setEstimatedValue(event.target.value)}
                placeholder="0.00"
              />
            </div>
          </div>

          {derivesDelivery ? (
            <div className="space-y-1.5">
              <Label htmlFor="project-launch">Project launch date</Label>
              <Input
                id="project-launch"
                type="date"
                value={launchDate}
                onChange={(event) => setLaunchDate(event.target.value)}
              />
            </div>
          ) : (
            // One range, one control: two date fields let "to" land before "from"
            // and stop reading as a single fact once they wrap apart.
            <div className="space-y-1.5">
              <Label htmlFor="project-delivery-range">Expected delivery</Label>
              <DateRangePicker
                id="project-delivery-range"
                from={deliveryFrom || null}
                to={deliveryTo || null}
                onChange={({ from, to }) => {
                  setDeliveryFrom(from ?? '');
                  setDeliveryTo(to ?? '');
                }}
              />
            </div>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="project-architect">Architect</Label>
              <SearchableSelect
                id="project-architect"
                value={architectId}
                onChange={setArchitectId}
                onOptionChange={setArchitectOption}
                fetchOptions={fetchArchitectOptions}
                selectedOption={architectOption ?? undefined}
                clearable
                placeholder="Search architects"
                emptyMessage="No architects found"
                createOption={partyCreateOption('architect', 'architect', (id, option) => {
                  setArchitectId(id);
                  setArchitectOption(option);
                })}
              />
              <TypedHint typed={typed?.architect_name} picked={architectId} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-contractor">Main contractor</Label>
              <SearchableSelect
                id="project-contractor"
                value={mainContractorId}
                onChange={setMainContractorId}
                onOptionChange={setContractorOption}
                fetchOptions={fetchContractorOptions}
                selectedOption={contractorOption ?? undefined}
                clearable
                placeholder="Search main contractors"
                emptyMessage="No main contractors found"
                createOption={partyCreateOption(
                  'main_contractor',
                  'main contractor',
                  (id, option) => {
                    setMainContractorId(id);
                    setContractorOption(option);
                  },
                )}
              />
              <TypedHint typed={typed?.main_contractor_name} picked={mainContractorId} />
            </div>
          </div>

        </FormSection>

        <FormSection
          title="Lead, customer and salesperson"
          open={sectionOpen.salesCustomer}
          onOpenChange={(next) => toggleSection('salesCustomer', next)}
        >
          <div className="space-y-1.5">
            <Label htmlFor="project-lead">
              Lead{(mode === 'create' || submitOnly) && <span className="text-destructive"> *</span>}
            </Label>
            <SearchableSelect
              id="project-lead"
              value={leadId}
              onChange={setLeadId}
              onOptionChange={(option) => {
                setLeadOption(option);
                takeFromLead(option as LeadPick | null);
              }}
              fetchOptions={fetchLeadOptions}
              selectedOption={leadOption ?? undefined}
              clearable
              placeholder="Search leads by title or code"
              emptyMessage="No open leads match"
              // Ungated, like the Leads page's own Create lead: the server decides who may
              // create one (projects.projects.edit or projects.registrations.submit).
              createOption={{
                label: (query) => <span>Create lead &ldquo;{query}&rdquo;</span>,
                onCreate: setCreatingLeadTitle,
              }}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              {(leadId && leadHasCustomer) || (mode === 'create' && !leadId) ? (
                <>
                  <Label>Customer</Label>
                  <div className="flex min-h-9 items-center text-sm">
                    {customerId && customerOption ? (
                      <span className="truncate" title={customerOption.label}>
                        {customerOption.label}
                      </span>
                    ) : (
                      <span className="text-muted-foreground">-</span>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <Label htmlFor="project-customer">
                    Customer
                    {(mode === 'create' || submitOnly) && (
                      <span className="text-destructive"> *</span>
                    )}
                  </Label>
                  <SearchableSelect
                    id="project-customer"
                    value={customerId}
                    onChange={setCustomerId}
                    onOptionChange={setCustomerOption}
                    fetchOptions={fetchCustomerOptions}
                    selectedOption={customerOption ?? undefined}
                    clearable={mode === 'edit'}
                    placeholder="Search customers"
                    emptyMessage="No customers found"
                  />
                </>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-owner">Salesperson</Label>
              <SearchableSelect
                id="project-owner"
                value={ownerUserId}
                onChange={setOwnerUserId}
                disabled={!canManageOwner}
                loadError={users.error}
                onRetry={() => void users.refetch()}
                options={(users.data ?? []).map((user) => ({
                  value: user.id,
                  label: user.name || 'Unnamed user',
                }))}
                placeholder="Select a salesperson"
              />
            </div>
          </div>
        </FormSection>

        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button type="button" variant="outline" onClick={handleCancel}>
            Cancel
          </Button>
          {blocker ? (
            <Button type="button" onClick={() => setInterestTarget(blocker)}>
              Register interest in {blocker.project_code}
            </Button>
          ) : submitOnly ? (
            <>
              <Button
                type="button"
                variant="outline"
                disabled={!canSaveDraft}
                onClick={() => void save(false)}
              >
                {mode === 'edit' && project?.approval_state !== 'draft' ? 'Save changes' : 'Save draft'}
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
                Submit for approval
              </Button>
            </>
          ) : (
            <Button type="submit" disabled={!canSubmit}>
              {pending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              {mode === 'create' ? 'Register project' : 'Save changes'}
            </Button>
          )}
        </div>
      </form>

      {creatingLeadTitle !== null && (
        <LeadWizardDialog
          initialTitle={creatingLeadTitle}
          onDone={(created) => {
            setCreatingLeadTitle(null);
            if (!created) return;
            setLeadId(created.id);
            setLeadOption({
              value: created.id,
              label: created.title,
              description: created.lead_code,
            });
            takeFromLead(created);
          }}
        />
      )}

      {interestTarget && (
        <RegisterInterestDialog
          candidate={interestTarget}
          canViewProject={!submitOnly}
          onDone={() => setInterestTarget(null)}
        />
      )}

      <ProjectAIExtractDialog
        open={extractOpen}
        onOpenChange={setExtractOpen}
        titleText={title}
        canCreateParties={canCreateParty}
        onFill={applyExtract}
      />
    </>
  );
}

type PickOption = { value: string; label: string; description?: string };

/** The name a portal registration typed, while no party is picked for it. */
function TypedHint({ typed, picked }: { typed?: string | null; picked: string }) {
  if (picked || !typed?.trim()) return null;
  return <p className="text-xs text-muted-foreground">Typed: {typed.trim()}</p>;
}

/**
 * The way out of a hard block: register interest in the project that already holds this
 * development (PROJECT-REGISTER-V2 D4). It is the existing dispute request; a sales manager
 * decides. The note is mandatory because the manager has to decide on something.
 */
function RegisterInterestDialog({
  candidate,
  canViewProject,
  onDone,
}: {
  candidate: ClashCandidate;
  canViewProject: boolean;
  onDone: () => void;
}) {
  const router = useRouter();
  const [reason, setReason] = React.useState('');
  const { request } = useTakeoverMutations(candidate.project_id);

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92dvh] w-full max-w-lg overflow-hidden" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>Register interest in {candidate.project_code}</DialogTitle>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!reason.trim()) return;
            try {
              await request.mutateAsync({ kind: 'dispute', reason: reason.trim() });
            } catch {
              // toasted by the mutation; the dialog stays open with the note
              return;
            }
            onDone();
            // A salesperson who cannot open the project goes back to the list (D8).
            if (canViewProject) {
              router.push(`/project-sales/${candidate.project_id}`);
            } else {
              toast.success(`Interest registered in ${candidate.project_code}`);
              router.push('/project-sales/pipeline');
            }
          }}
        >
          <DialogBody className="max-h-[60dvh] space-y-3 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="takeover-reason">
                How and when did you find this project?{' '}
                <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="takeover-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                required
              />
            </div>
          </DialogBody>
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!reason.trim() || request.isPending}>
              {request.isPending && <Loader2 className="size-4 animate-spin" aria-hidden />}
              Register interest
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
