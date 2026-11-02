'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, ArrowRight, Loader2, Sparkles } from 'lucide-react';
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
import { WizardSteps } from '@/components/common/WizardSteps';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { toast } from '@/lib/toast';
import { useLookupSetOptions } from '@/hooks/useLookupSetOptions';
import { getUserLookup } from '@/services/userSelectService';
import {
  CLASH_MIN_CHARS,
  useClashPreview,
  useFetchClashPreview,
  useFetchCustomerOptions,
  useFetchPartyOptions,
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
  PartyLink,
  PartyLinkRole,
  PartyType,
  Project,
  ProjectRegisterBody,
  ProjectUpdateBody,
} from '../types/project.types';
import { isProjectApproved } from '../lib/projectApproval';
import { isAwaitingDecision } from './ApprovalStatePill';
import { ProjectAIExtractDialog, type ProjectExtractFill } from './ProjectAIExtractDialog';
import { PartyContactsPicker } from './PartyContactsPicker';

/** The district lookup set of a state: `my_district_<state>` (migration psr3_0001). */
export function districtSetKey(state: string): string {
  return state ? `my_district_${state.toLowerCase().split(/\s+/).filter(Boolean).join('_')}` : '';
}

/** The party roles linked beyond the three single columns (owner 2 Nov ~21:40, Q5 b). */
const LINK_ROLES: { role: PartyLinkRole; label: string; many: boolean }[] = [
  { role: 'subcontractor', label: 'Subcontractors', many: true },
  { role: 'trading_house', label: 'Trading houses', many: true },
  { role: 'tender_party', label: 'Tender parties', many: true },
  { role: 'consultant', label: 'Consultant', many: false },
  { role: 'interior_designer', label: 'Interior designer', many: false },
];

type LinkPicks = Record<PartyLinkRole, PickOption[]>;

function linksFrom(project?: Project): LinkPicks {
  const picks = Object.fromEntries(LINK_ROLES.map((r) => [r.role, []])) as unknown as LinkPicks;
  for (const link of project?.party_links ?? []) {
    picks[link.role]?.push({ value: link.party_id, label: link.name ?? 'Party' });
  }
  return picks;
}

const WIZARD_STEPS = [
  { id: 'check', label: 'Check' },
  { id: 'details', label: 'Details' },
] as const;
type WizardStepId = (typeof WIZARD_STEPS)[number]['id'];

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
 * - A third section, "Customer and salesperson", open from the start.
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
  // A staff or approved project being edited follows the general rule (Save changes).
  const submitOnly =
    !canEditProjects &&
    canSubmitRegistration &&
    !(mode === 'edit' && project && isProjectApproved(project));

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
  const [leadSource, setLeadSource] = React.useState(project?.lead_source ?? '');
  const [linkPicks, setLinkPicks] = React.useState<LinkPicks>(() => linksFrom(project));
  // Register only: the picked contacts per party id. A party no longer picked drops its picks
  // (rule 7) because only the picked parties' lists are sent.
  const [contactPicks, setContactPicks] = React.useState<Record<string, string[]>>({});
  // Names of party options seen in a multi picker, so a newly ticked party keeps its label.
  const linkOptionCache = React.useRef<Record<string, PickOption>>({});
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
  // The blocking project the user is registering interest in (D4); non-null opens the dialog.
  const [interestTarget, setInterestTarget] = React.useState<ClashCandidate | null>(null);
  const [extractOpen, setExtractOpen] = React.useState(false);

  const fetchDeveloperOptions = useFetchPartyOptions('developer');
  const fetchArchitectOptions = useFetchPartyOptions('architect');
  const fetchContractorOptions = useFetchPartyOptions('main_contractor');
  const fetchSubcontractorOptions = useFetchPartyOptions('subcontractor');
  const fetchTradingHouseOptions = useFetchPartyOptions('trading_house');
  const fetchTenderPartyOptions = useFetchPartyOptions('tender_party');
  const fetchConsultantOptions = useFetchPartyOptions('consultant');
  const fetchInteriorDesignerOptions = useFetchPartyOptions('interior_designer');
  const fetchLinkOptions: Record<PartyLinkRole, (query: string) => Promise<PickOption[]>> = {
    subcontractor: fetchSubcontractorOptions,
    trading_house: fetchTradingHouseOptions,
    tender_party: fetchTenderPartyOptions,
    consultant: fetchConsultantOptions,
    interior_designer: fetchInteriorDesignerOptions,
  };
  const fetchCustomerOptions = useFetchCustomerOptions();
  // Both routes need projects.types.view: without it the type and template show as the
  // project's own text and nothing is requested.
  const canViewTypes = useHasPermission('projects.types.view');
  const types = useProjectTypes({ enabled: canViewTypes });
  const templates = useProjectTemplates(typeId || undefined, { enabled: canViewTypes });
  const states = useLookupSetOptions('my_state');
  const leadSources = useLookupSetOptions('project_lead_source');
  const districts = useLookupSetOptions(districtSetKey(state), { enabled: Boolean(state) });
  const users = useQuery({
    queryKey: ['user-lookup', 'project-owner'],
    queryFn: () => getUserLookup(),
  });

  // The title the user last checked; editing the field clears it, so a result never
  // sits under a title it was not asked about.
  const [checkedTitle, setCheckedTitle] = React.useState('');
  // Create mode is a two-step wizard: Check (title + developer), then Details. Edit mode is
  // the flat form.
  const [step, setStep] = React.useState<WizardStepId>('check');
  const wizard = mode === 'create';
  const [checkFailed, setCheckFailed] = React.useState(false);
  // The title counts as filled once the user leaves the field or checks it, so Details
  // does not open under them after the first letter.
  const [titleSettled, setTitleSettled] = React.useState(mode === 'edit');
  const clash = useClashPreview(checkedTitle, developerId || null);
  const fetchClash = useFetchClashPreview();

  const [sectionOpen, setSectionOpen] = React.useState({
    who: true,
    details: mode === 'edit',
    parties: true,
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

  function toggleSection(
    key: 'who' | 'details' | 'parties' | 'salesCustomer',
    next: boolean,
  ) {
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
  // Customer optional, lead source required to register or submit (PS-REGISTRATION-V3).
  const leadSourceMissing = (mode === 'create' || submitOnly) && !leadSource;
  const canSubmit =
    title.trim().length > 0 && !leadSourceMissing && !wouldBlock && !pending;
  const canSaveDraft = title.trim().length > 0 && !pending;
  // The top blocking candidate: the footer's one primary becomes Register as secondary lead (D2).
  const blocker =
    mode === 'create' && wouldBlock ? candidates.find((candidate) => candidate.blocks) : undefined;

  async function handleCheck() {
    const trimmed = title.trim();
    if (trimmed.length < CLASH_MIN_CHARS) return;
    setTitleSettled(true);
    setCheckFailed(false);
    setCheckedTitle(trimmed);
    try {
      await fetchClash(trimmed, developerId || null);
    } catch {
      // Say so and let the user press Check again (a swallowed failure read as "no clash").
      setCheckedTitle('');
      setCheckFailed(true);
    }
  }

  /** A new title or developer makes the last result stale: clear it, Check returns. */
  function clearCheck() {
    setCheckedTitle('');
    setCheckFailed(false);
  }

  function goToDetails() {
    setStep('details');
  }

  const checked = hasChecked && clash.isSuccess && !clash.isFetching;
  // A registration waiting for approval has no lock (its `candidates` carry blocks: false), but
  // its matches still read as a Clash line, as information.
  const blockingCandidate = (
    mode === 'edit' ? rawCandidates.filter((c) => c.project_id !== project!.id) : rawCandidates
  ).find((candidate) => candidate.blocks);
  /** The one result line of a Check, the same in create and edit. */
  const checkResult = checkFailed ? (
    <p className="text-sm text-destructive" role="alert">
      The check did not finish. Try again.
    </p>
  ) : checked ? (
    blockingCandidate ? (
      <p className="break-words text-sm text-destructive" aria-live="polite">
        Clash:{' '}
        <Link
          href={`/project-sales/${blockingCandidate.project_id}`}
          className="font-medium underline"
        >
          {blockingCandidate.project_code}
        </Link>{' '}
        {blockingCandidate.title}
      </p>
    ) : (
      <p className="text-sm text-muted-foreground" aria-live="polite">
        No clash
      </p>
    )
  ) : null;

  /** Step 1's forward action: Check, then Next, or the way out of a clash. */
  function forwardFromCheck() {
    if (blocker) {
      setInterestTarget(blocker);
      return;
    }
    if (checked) {
      goToDetails();
      return;
    }
    void handleCheck();
  }

  /** The parties picked on the form, each with its role, for the contacts pickers. */
  const pickedParties: { partyId: string; name: string }[] = [
    ...(developerId ? [{ partyId: developerId, name: developerOption?.label ?? 'Developer' }] : []),
    ...(architectId ? [{ partyId: architectId, name: architectOption?.label ?? 'Architect' }] : []),
    ...(mainContractorId
      ? [{ partyId: mainContractorId, name: contractorOption?.label ?? 'Main contractor' }]
      : []),
    ...LINK_ROLES.flatMap((r) => linkPicks[r.role].map((o) => ({ partyId: o.value, name: o.label }))),
  ].filter((p, i, all) => all.findIndex((q) => q.partyId === p.partyId) === i);

  function buildBody(): ProjectRegisterBody {
    const partyLinks: PartyLink[] = LINK_ROLES.flatMap((r) =>
      linkPicks[r.role].map((o) => ({ role: r.role, party_id: o.value })),
    );
    const contactIds = Array.from(
      new Set(pickedParties.flatMap((p) => contactPicks[p.partyId] ?? [])),
    );
    return {
      lead_source: leadSource || null,
      party_links: partyLinks,
      ...(mode === 'create' && contactIds.length ? { contact_ids: contactIds } : {}),
      title: title.trim(),
      developer_party_id: developerId || null,
      type_id: typeId || null,
      template_id: templateId || null,
      owner_user_id: ownerUserId || null,
      registered_company_name: registeredCompany.trim() || null,
      location: location.trim() || null,
      state: state || null,
      mukim: mukim || null,
      address: address.trim() || null,
      admin_ref: adminRef.trim() || null,
      architect_party_id: architectId || null,
      main_contractor_party_id: mainContractorId || null,
      estimated_sales_value: estimatedValue.trim() || null,
      launch_date: launchDate || null,
      expected_delivery_from: deliveryFrom || null,
      expected_delivery_to: deliveryTo || null,
      ...((mode === 'create' ? Boolean(customerId) : customerId !== (project?.customer_id ?? ''))
        ? { customer_id: customerId || null }
        : {}),
    };
  }

  /** Pre-fills the form from a confirmed AI extract; the typed title is never overwritten. */
  function applyExtract(fill: ProjectExtractFill) {
    if (fill.title && !title.trim()) setTitle(fill.title);
    clearCheck();
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
    if (canViewTypes && fill.project_type && fill.project_type.id !== typeId) {
      setTypeId(fill.project_type.id);
      setTemplateId('');
    }
    if (fill.state) setState(fill.state);
    if (fill.mukim) setMukim(fill.mukim);
    setTitleSettled(true);
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
    if (wizard && step === 'check') {
      forwardFromCheck();
      return;
    }
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
    // A refusal (403, ...) is toasted by the mutation hook;
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

  // Both routes need projects.types.view: without it the type and template show as the
  // project's own text and nothing is requested.
  const typeField = (
    <div className="space-y-1.5">
      <Label id="project-type-label" htmlFor="project-type">
        Project type
      </Label>
      {!canViewTypes ? (
        <p id="project-type" aria-labelledby="project-type-label" className="text-sm">
          {project?.type_name || '-'}
        </p>
      ) : (
        <SearchableSelect
          id="project-type"
          value={typeId}
          onChange={(next) => {
            // A new type must clear the template too, or a stale template from the previous
            // type is submitted and the project gets roles it should not offer. In the
            // handler, not an effect, so opening an edit form never wipes the project's own
            // template.
            setTypeId(next);
            if (next !== typeId) setTemplateId('');
          }}
          clearable
          loadError={types.error}
          onRetry={() => void types.refetch()}
          options={(types.data ?? []).map((type) => ({ value: type.id, label: type.name }))}
          placeholder="Select a type"
        />
      )}
    </div>
  );
  const templateField = (
    <div className="space-y-1.5">
      <Label id="project-template-label" htmlFor="project-template">
        To-do list template
      </Label>
      {!canViewTypes ? (
        <p id="project-template" aria-labelledby="project-template-label" className="text-sm">
          {project?.template_name || '-'}
        </p>
      ) : (
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
            description: template.has_forked_status_graph ? 'Has its own stage flow' : undefined,
          }))}
          placeholder="Select a to-do list template"
          emptyMessage="No to-do list templates for this type"
        />
      )}
    </div>
  );

  const titleInput = (
    <Textarea
      id="project-title"
      value={title}
      onChange={(event) => {
        setTitle(event.target.value);
        clearCheck();
        if (!event.target.value.trim()) setTitleSettled(false);
      }}
      onBlur={() => setTitleSettled(title.trim().length > 0)}
      placeholder="e.g. Setia Alam Phase 3B"
      autoComplete="off"
      rows={3}
      className="min-h-20 [field-sizing:content]"
      required
    />
  );

  function handleCancel() {
    router.push(mode === 'create' ? '/project-sales/pipeline' : `/project-sales/${project!.id}`);
  }

  return (
    <>
      <form onSubmit={handleSubmit} className="space-y-4">
        {wizard && (
          <WizardSteps
            steps={WIZARD_STEPS}
            currentId={step}
            className="mb-2 rounded-lg border border-border p-4"
          />
        )}

        {wizard && step === 'check' && (
          <div className="space-y-4 rounded-lg border border-border p-4">
            <div className="space-y-1.5">
              <Label htmlFor="project-title">
                Project title <span className="text-destructive">*</span>
              </Label>
              {titleInput}
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setExtractOpen(true)}
                >
                  <Sparkles className="size-4" aria-hidden />
                  AI extract
                </Button>
              </div>
            </div>
            <div className="space-y-1.5">
              <div className="space-y-1.5">
                <Label htmlFor="project-developer">Developer</Label>
                <SearchableSelect
                  id="project-developer"
                  value={developerId}
                  onChange={(next) => {
                    setDeveloperId(next);
                    clearCheck();
                  }}
                  onOptionChange={setDeveloperOption}
                  fetchOptions={fetchDeveloperOptions}
                  selectedOption={developerOption ?? undefined}
                  clearable
                  placeholder="Search developers"
                  emptyMessage="No developers found"
                  createOption={partyCreateOption(
                    'developer',
                    'developer',
                    (id, option) => {
                      setDeveloperId(id);
                      setDeveloperOption(option);
                      clearCheck();
                    },
                  )}
                />
                <TypedHint typed={typed?.developer_name} picked={developerId} />
              </div>
            </div>
            {checkResult}
          </div>
        )}

        {wizard && step === 'details' && blockingCandidate && checkResult}

        {(!wizard || step === 'details') && (
          <FormSection
            title="Who and what"
            summary={title.trim() || null}
            open={sectionOpen.who}
            onOpenChange={(next) => toggleSection('who', next)}
          >
            {!wizard && (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="project-title">
                    Project title <span className="text-destructive">*</span>
                  </Label>
                  {titleInput}
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
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setExtractOpen(true)}
                    >
                      <Sparkles className="size-4" aria-hidden />
                      AI extract
                    </Button>
                  </div>
                  {checkResult}
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <div className="space-y-1.5">
                      <Label htmlFor="project-developer">Developer</Label>
                      <SearchableSelect
                        id="project-developer"
                        value={developerId}
                        onChange={(next) => {
                          setDeveloperId(next);
                          clearCheck();
                        }}
                        onOptionChange={setDeveloperOption}
                        fetchOptions={fetchDeveloperOptions}
                        selectedOption={developerOption ?? undefined}
                        clearable
                        placeholder="Search developers"
                        emptyMessage="No developers found"
                        createOption={partyCreateOption(
                          'developer',
                          'developer',
                          (id, option) => {
                            setDeveloperId(id);
                            setDeveloperOption(option);
                            clearCheck();
                          },
                        )}
                      />
                      <TypedHint
                        typed={typed?.developer_name}
                        picked={developerId}
                      />
                    </div>
                  </div>
                  {typeField}
                </div>
              </>
            )}
            {wizard && (
              <div className="space-y-1.5">{typeField}</div>
            )}

            {typeId && templateField}
          </FormSection>
        )}

        {(!wizard || step === 'details') && (
          <FormSection
            title="Details"
            open={sectionOpen.details}
            onOpenChange={(next) => toggleSection('details', next)}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="project-registered-company">
                  Registered company / SPV
                </Label>
                <Input
                  id="project-registered-company"
                  value={registeredCompany}
                  onChange={(event) => setRegisteredCompany(event.target.value)}
                  placeholder="Optional"
                />
              </div>
              {!wizard && (
                <div className="space-y-1.5">
                  <Label htmlFor="project-location">Location</Label>
                  <Input
                    id="project-location"
                    value={location}
                    onChange={(event) => setLocation(event.target.value)}
                    placeholder="e.g. Setia Alam, Selangor"
                  />
                </div>
              )}
            </div>

            {/* State + Area say where it is; the free-text Location shows on edit only so older
                projects keep their text (PS-REGISTRATION-V3 rule 2). */}

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="project-state">State</Label>
                <SearchableSelect
                  id="project-state"
                  value={state}
                  onChange={(next) => {
                    setState(next);
                    // An area belongs to its state: a new state starts the area over.
                    if (next !== state) setMukim('');
                  }}
                  clearable
                  loadError={states.error}
                  onRetry={() => void states.refetch()}
                  options={[
                    // A stored value the lookup set no longer offers still shows as itself.
                    ...(state &&
                    !(states.data ?? []).some((o) => o.value === state)
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
                <Label htmlFor="project-mukim">Area</Label>
                <SearchableSelect
                  id="project-mukim"
                  value={mukim}
                  onChange={setMukim}
                  clearable
                  disabled={!state}
                  loadError={state ? districts.error : undefined}
                  onRetry={() => void districts.refetch()}
                  options={[
                    // An area typed before the list existed still shows as itself.
                    ...(mukim && !(districts.data ?? []).some((o) => o.value === mukim)
                      ? [{ value: mukim, label: mukim }]
                      : []),
                    ...(districts.data ?? []).map((option) => ({
                      value: option.value,
                      label: option.label,
                    })),
                  ]}
                  placeholder={state ? 'Select an area' : 'Pick a state first'}
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
                <Label htmlFor="project-value">
                  Estimated sales value (RM)
                </Label>
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
                <Label htmlFor="project-delivery-range">
                  Expected delivery
                </Label>
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

          </FormSection>
        )}

        {(!wizard || step === 'details') && (
          <FormSection
            title="Parties and contacts"
            open={sectionOpen.parties}
            onOpenChange={(next) => toggleSection('parties', next)}
          >
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
                  createOption={partyCreateOption(
                    'architect',
                    'architect',
                    (id, option) => {
                      setArchitectId(id);
                      setArchitectOption(option);
                    },
                  )}
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
                <TypedHint
                  typed={typed?.main_contractor_name}
                  picked={mainContractorId}
                />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {LINK_ROLES.map(({ role, label, many }) => {
                const picks = linkPicks[role];
                const setPicks = (next: PickOption[]) =>
                  setLinkPicks((prev) => ({ ...prev, [role]: next }));
                const id = `project-${role.replace('_', '-')}`;
                const noun = label.toLowerCase();
                return (
                  <div key={role} className="space-y-1.5">
                    <Label htmlFor={id}>{label}</Label>
                    {many ? (
                      <SearchableMultiSelect
                        id={id}
                        value={picks.map((o) => o.value)}
                        onChange={(ids) =>
                          setPicks(
                            ids.map(
                              (value) =>
                                picks.find((o) => o.value === value) ??
                                linkOptionCache.current[value] ?? { value, label: 'Party' },
                            ),
                          )
                        }
                        fetchOptions={async (query) => {
                          const rows = await fetchLinkOptions[role](query);
                          for (const row of rows) linkOptionCache.current[row.value] = row;
                          return rows;
                        }}
                        selectedOptions={picks}
                        clearable
                        placeholder={`Search ${label.toLowerCase()}`}
                        emptyMessage={`No ${label.toLowerCase()} found`}
                      />
                    ) : (
                      <SearchableSelect
                        id={id}
                        value={picks[0]?.value ?? ''}
                        onChange={(value) => {
                          if (!value) setPicks([]);
                        }}
                        onOptionChange={(option) => setPicks(option ? [option] : [])}
                        fetchOptions={fetchLinkOptions[role]}
                        selectedOption={picks[0]}
                        clearable
                        placeholder={`Search ${noun}s`}
                        emptyMessage={`No ${noun}s found`}
                        createOption={partyCreateOption(role, noun, (pid, option) =>
                          setPicks([{ ...option, value: pid }]),
                        )}
                      />
                    )}
                  </div>
                );
              })}
            </div>

            {mode === 'create' && pickedParties.length > 0 && (
              <div className="grid gap-4 sm:grid-cols-2">
                {pickedParties.map((party) => (
                  <PartyContactsPicker
                    key={party.partyId}
                    partyId={party.partyId}
                    partyName={party.name}
                    value={contactPicks[party.partyId] ?? []}
                    onChange={(ids) =>
                      setContactPicks((prev) => ({ ...prev, [party.partyId]: ids }))
                    }
                    canCreate={canCreateParty}
                  />
                ))}
              </div>
            )}
          </FormSection>
        )}

        {(!wizard || step === 'details') && (
          <FormSection
            title="Lead source, customer and salesperson"
            open={sectionOpen.salesCustomer}
            onOpenChange={(next) => toggleSection('salesCustomer', next)}
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="project-lead-source">
                  Lead source
                  {(mode === 'create' || submitOnly) && (
                    <span className="text-destructive"> *</span>
                  )}
                </Label>
                <SearchableSelect
                  id="project-lead-source"
                  value={leadSource}
                  onChange={setLeadSource}
                  clearable={mode === 'edit' && !submitOnly}
                  loadError={leadSources.error}
                  onRetry={() => void leadSources.refetch()}
                  options={[
                    ...(leadSource &&
                    !(leadSources.data ?? []).some((o) => o.value === leadSource)
                      ? [{ value: leadSource, label: leadSource }]
                      : []),
                    ...(leadSources.data ?? []).map((option) => ({
                      value: option.value,
                      label: option.label,
                    })),
                  ]}
                  placeholder="Where did this project come from?"
                />
              </div>
              <div className="space-y-1.5">
                  <Label htmlFor="project-customer">Customer</Label>
                  <SearchableSelect
                    id="project-customer"
                    value={customerId}
                    onChange={setCustomerId}
                    onOptionChange={setCustomerOption}
                    fetchOptions={fetchCustomerOptions}
                    selectedOption={customerOption ?? undefined}
                    clearable
                    placeholder="Search customers"
                    emptyMessage="No customers found"
                  />
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
        )}

        {wizard ? (
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-between">
            <Button
              type="button"
              variant="outline"
              disabled={step === 'check'}
              onClick={() => setStep('check')}
            >
              <ArrowLeft className="size-4" aria-hidden />
              Back
            </Button>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="button" variant="outline" onClick={handleCancel}>
                Cancel
              </Button>
              {step === 'check' ? (
                blocker ? (
                  <Button
                    type="button"
                    onClick={() => setInterestTarget(blocker)}
                  >
                    Register as secondary lead on {blocker.project_code}
                  </Button>
                ) : checked ? (
                  <Button type="button" onClick={goToDetails}>
                    Next
                    <ArrowRight className="size-4" aria-hidden />
                  </Button>
                ) : (
                  <Button
                    type="button"
                    disabled={!checkable || clash.isFetching}
                    onClick={() => void handleCheck()}
                  >
                    {clash.isFetching && hasChecked && (
                      <Loader2 className="size-4 animate-spin" aria-hidden />
                    )}
                    Check
                  </Button>
                )
              ) : (
                <>
                  {blocker ? (
                    <Button
                      type="button"
                      onClick={() => setInterestTarget(blocker)}
                    >
                      Register as secondary lead on {blocker.project_code}
                    </Button>
                  ) : submitOnly ? (
                    <>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={!canSaveDraft}
                        onClick={() => void save(false)}
                      >
                        Save draft
                      </Button>
                      <Button type="submit" disabled={!canSubmit}>
                        {pending && (
                          <Loader2
                            className="size-4 animate-spin"
                            aria-hidden
                          />
                        )}
                        Submit for approval
                      </Button>
                    </>
                  ) : (
                    <Button type="submit" disabled={!canSubmit}>
                      {pending && (
                        <Loader2 className="size-4 animate-spin" aria-hidden />
                      )}
                      Register project
                    </Button>
                  )}
                </>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={handleCancel}>
              Cancel
            </Button>
            {blocker ? (
              <Button type="button" onClick={() => setInterestTarget(blocker)}>
                Register as secondary lead on {blocker.project_code}
              </Button>
            ) : submitOnly ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  disabled={!canSaveDraft}
                  onClick={() => void save(false)}
                >
                  {mode === 'edit' && project?.approval_state !== 'draft'
                    ? 'Save changes'
                    : 'Save draft'}
                </Button>
                <Button type="submit" disabled={!canSubmit}>
                  {pending && (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  )}
                  Submit for approval
                </Button>
              </>
            ) : (
              <Button type="submit" disabled={!canSubmit}>
                {pending && (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                )}
                Save changes
              </Button>
            )}
          </div>
        )}
      </form>

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
          <DialogTitle>Register as secondary lead on {candidate.project_code}</DialogTitle>
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
              toast.success(`Registered as secondary lead on ${candidate.project_code}`);
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
              Register as secondary lead
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
