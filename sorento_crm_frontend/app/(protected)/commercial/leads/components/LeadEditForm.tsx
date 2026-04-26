'use client';

import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Camera, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { getCustomer, updateCustomer } from '@/app/(protected)/order-management/customers/services/customerService';
import { getUsersSelect } from '@/services/userSelectService';
import { useCommercialLead, useUpdateCommercialLead } from '../hooks/useCommercialLeads';
import { useLeadStagesList } from '../hooks/useLeadStages';
import { useLeadAssignmentSelect } from '../hooks/useLeadAssignmentSelect';
import { LeadMasterStackSelect } from './LeadMasterSelect';
import { SearchableSelect } from './SearchableSelect';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import AttachmentUploadDialog from '@/app/(protected)/resource-management/attachments/components/AttachmentUploadDialog';
import { listRespondWorkspaceSelect } from '../services/leadRespondContactsService';

const SALUTATION_NONE = '__none__';
const RESPOND_WORKSPACE_NONE = '__respond_workspace_none__';
const SALUTATIONS = ['Mr.', 'Ms.', 'Mrs.', 'Dr.'] as const;
const RATING_NONE = '__none__';
const RATINGS = ['Hot', 'Warm', 'Cold'] as const;

function field(q: Record<string, unknown>, key: string): string {
  const v = q[key];
  return v == null ? '' : String(v);
}

function boolField(q: Record<string, unknown>, key: string): boolean {
  const v = q[key];
  if (typeof v === 'boolean') return v;
  if (v === 'true' || v === true) return true;
  return false;
}

function initialsFromLead(first: string, last: string, company: string): string {
  const f = first.trim();
  const l = last.trim();
  if (f && l) return `${f[0]!}${l[0]!}`.toUpperCase();
  if (l.length >= 2) return l.slice(0, 2).toUpperCase();
  if (f.length >= 2) return f.slice(0, 2).toUpperCase();
  const c = company.trim();
  if (c.length >= 2) return c.slice(0, 2).toUpperCase();
  if (c.length === 1) return `${c[0]!}?`.toUpperCase();
  return '—';
}

/** Stage pill approximating Figma dev handoff (blue “New”, semantic elsewhere). */
function leadStageBadgeClass(stageCode: string | null | undefined): string {
  const c = (stageCode || '').toLowerCase();
  if (c.includes('won')) return 'bg-emerald-600 text-white';
  if (c.includes('lost') || c.includes('withdraw') || c.includes('no_award')) return 'bg-red-600 text-white';
  if (c.includes('proposal')) return 'bg-violet-600 text-white';
  if (c.includes('new')) return 'bg-[#2b7fff] text-white';
  if (c.includes('qualif')) return 'bg-amber-500 text-white';
  return 'bg-sky-600 text-white';
}

/** Label above control; optional red left accent for required fields (Figma edit). */
function StackField({
  label,
  htmlFor,
  missing,
  children,
}: {
  label: string;
  htmlFor?: string;
  missing?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={htmlFor} className="text-[#4a5565] text-sm font-medium leading-5">
        {label}
      </Label>
      <div
        className={cn(
          'min-w-0 overflow-hidden rounded-[4px] border border-[#d1d5dc] bg-background [&_[data-slot=select-trigger]]:h-[38px] [&_[data-slot=select-trigger]]:rounded-none [&_[data-slot=select-trigger]]:border-0 [&_[data-slot=select-trigger]]:shadow-none [&_input]:h-[38px] [&_input]:rounded-none [&_input]:border-0 [&_input]:shadow-none',
          missing && 'border-l-4 border-l-[#fb2c36]',
        )}
      >
        {children}
      </div>
    </div>
  );
}

/** Figma 11:1230 — edit header: gray strip, avatar + camera, title row, no primary actions here. */
function LeadEditPageHero(props: {
  leadCode: string;
  stageName: string;
  stageCode?: string | null;
  subtitle: string;
  avatarUrl: string | null;
  initials: string;
  onCameraClick: () => void;
}) {
  const { leadCode, stageName, stageCode, subtitle, avatarUrl, initials, onCameraClick } = props;

  return (
    <div className="border-b border-[#e5e7eb] bg-[#f9fafb]">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-start gap-4 px-6 py-6">
        <div className="relative shrink-0">
          <div className="border-border/60 relative size-[80px] overflow-hidden rounded-full border bg-[#ffe2e2] shadow-inner">
            {avatarUrl ? (
              <img src={avatarUrl} alt="" className="size-full object-cover" />
            ) : (
              <div className="text-primary flex size-full items-center justify-center text-xl font-semibold tracking-tight">
                {initials}
              </div>
            )}
          </div>
          <button
            type="button"
            className="absolute -bottom-0.5 -end-0.5 flex size-[26px] items-center justify-center rounded-full bg-[#1e2939] text-white shadow-md ring-2 ring-[#f9fafb] hover:bg-[#111827]"
            aria-label="Upload profile photo"
            onClick={onCameraClick}
          >
            <Camera className="size-3.5 opacity-95" aria-hidden />
          </button>
        </div>
        <div className="min-w-0 flex-1 space-y-1 pt-0.5">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h1 className="truncate text-[30px] font-semibold leading-9 tracking-tight text-[#0a0a0a]">
              Lead: {leadCode}
            </h1>
            {stageName ? (
              <span
                className={cn(
                  'inline-flex shrink-0 items-center rounded px-2 py-0.5 text-xs font-medium text-white',
                  leadStageBadgeClass(stageCode),
                )}
              >
                {stageName}
              </span>
            ) : null}
          </div>
          {subtitle ? <p className="truncate text-sm leading-5 text-[#4a5565]">{subtitle}</p> : null}
        </div>
      </div>
    </div>
  );
}

function EditFormFooter(props: {
  disabled: boolean;
  onCancel: () => void;
  onSaveAndNew: () => void;
  onSave: () => void;
}) {
  const { disabled, onCancel, onSaveAndNew, onSave } = props;
  return (
    <div className="flex flex-wrap items-center justify-end gap-3 pt-2">
      <Button
        type="button"
        variant="outline"
        className="h-[42px] rounded-md border-[#d1d5dc] px-5 text-base font-medium text-[#0a0a0a] shadow-none"
        onClick={onCancel}
      >
        Cancel
      </Button>
      <Button
        type="button"
        variant="outline"
        className="h-[42px] rounded-md border-[#d1d5dc] px-5 text-base font-medium text-[#0a0a0a] shadow-none"
        onClick={() => void onSaveAndNew()}
        disabled={disabled}
      >
        Save and new
      </Button>
      <Button
        type="button"
        disabled={disabled}
        className="h-[42px] min-w-[5.5rem] rounded-md bg-[#e7000b] px-6 text-base font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-60"
        onClick={() => void onSave()}
      >
        {disabled ? <Loader2 className="size-4 animate-spin" aria-hidden /> : 'Save'}
      </Button>
    </div>
  );
}

export default function LeadEditForm({ leadId }: { leadId: string }) {
  const router = useRouter();
  const qc = useQueryClient();
  const { data: lead, isLoading: leadLoading } = useCommercialLead(leadId);
  const { data: stages = [] } = useLeadStagesList();
  const updateLead = useUpdateCommercialLead(leadId);

  const { data: customer } = useQuery({
    queryKey: ['customer', lead?.customer_id],
    queryFn: () => getCustomer(lead!.customer_id),
    enabled: !!lead?.customer_id,
  });

  const { data: users = [] } = useQuery({
    queryKey: ['users-select', 'lead-edit'],
    queryFn: () => getUsersSelect({ status: 'ACTIVE' }),
    staleTime: 60_000,
  });

  const { data: respondWorkspaces = [] } = useQuery({
    queryKey: ['respond-workspaces-select'],
    queryFn: listRespondWorkspaceSelect,
    staleTime: 60_000,
  });

  const { data: leadStateOpts = [], isLoading: leadStatesLoading } = useLeadAssignmentSelect('lead_states');
  const { data: leadCountryOpts = [], isLoading: leadCountriesLoading } = useLeadAssignmentSelect('lead_countries');
  const { data: leadPropertyTypeOpts = [], isLoading: leadPropertyTypesLoading } =
    useLeadAssignmentSelect('lead_property_types');
  const { data: leadBudgetOpts = [], isLoading: leadBudgetsLoading } = useLeadAssignmentSelect('lead_budget_ranges');
  const { data: leadClosureOpts = [], isLoading: leadClosuresLoading } = useLeadAssignmentSelect(
    'lead_sales_closure_confidence',
  );
  const { data: leadSourceOpts = [], isLoading: leadSourcesLoading } = useLeadAssignmentSelect('lead_sources');
  const { data: leadIndustryOpts = [], isLoading: leadIndustriesLoading } = useLeadAssignmentSelect('lead_industries');

  const [title, setTitle] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [stageId, setStageId] = useState('');
  const [summary, setSummary] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [website, setWebsite] = useState('');
  const [source, setSource] = useState('');
  const [mainEmail, setMainEmail] = useState('');
  const [mainPhone, setMainPhone] = useState('');
  const [profileImageUrl, setProfileImageUrl] = useState('');
  const [salutation, setSalutation] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [mobile, setMobile] = useState('');
  const [industry, setIndustry] = useState('');
  const [annualRevenue, setAnnualRevenue] = useState('');
  const [emailOptOut, setEmailOptOut] = useState(false);
  const [fax, setFax] = useState('');
  const [noOfEmployees, setNoOfEmployees] = useState('');
  const [rating, setRating] = useState('');
  const [addr1, setAddr1] = useState('');
  const [addr2, setAddr2] = useState('');
  const [city, setCity] = useState('');
  const [postcode, setPostcode] = useState('');
  const [state, setState] = useState('');
  const [country, setCountry] = useState('');
  const [propertyType, setPropertyType] = useState('');
  const [propertyValue, setPropertyValue] = useState('');
  const [budgetRange, setBudgetRange] = useState('');
  const [closureConfidence, setClosureConfidence] = useState('');
  const [estStart, setEstStart] = useState('');
  const [estEnd, setEstEnd] = useState('');
  const [photoUploadOpen, setPhotoUploadOpen] = useState(false);
  const [respondWorkspaceId, setRespondWorkspaceId] = useState(RESPOND_WORKSPACE_NONE);

  const userSearchOptions = useMemo(
    () => users.map((u) => ({ value: u.id, label: String(u.name || u.email || u.id) })),
    [users],
  );
  const salutationSearchOptions = useMemo(
    () => [
      { value: SALUTATION_NONE, label: 'None' },
      ...SALUTATIONS.map((s) => ({ value: s, label: s })),
    ],
    [],
  );
  const stageSearchOptions = useMemo(() => stages.map((s) => ({ value: s.id, label: s.stage_name })), [stages]);
  const respondWorkspaceOptions = useMemo(
    () => [
      { value: RESPOND_WORKSPACE_NONE, label: 'None' },
      ...respondWorkspaces.map((w) => ({
        value: w.id,
        label: (w.name || '').trim() || w.space_id,
      })),
    ],
    [respondWorkspaces],
  );
  const ratingSearchOptions = useMemo(
    () => [
      { value: RATING_NONE, label: 'None' },
      ...RATINGS.map((r) => ({ value: r, label: r })),
    ],
    [],
  );

  useEffect(() => {
    if (!lead) return;
    setTitle(lead.title);
    setOwnerId(lead.owner_user_id ?? '');
    setStageId(lead.lead_stage_id);
    setSummary(lead.qualification_summary ?? '');
    const q = lead.qualification || {};
    setSource(field(q, 'source'));
    setMainEmail(field(q, 'main_email'));
    setMainPhone(field(q, 'main_phone'));
    setProfileImageUrl(field(q, 'profile_image_url'));
    setSalutation(field(q, 'salutation'));
    setFirstName(field(q, 'first_name'));
    setLastName(field(q, 'last_name'));
    setMobile(field(q, 'mobile'));
    setIndustry(field(q, 'industry'));
    setAnnualRevenue(field(q, 'annual_revenue'));
    setEmailOptOut(boolField(q, 'email_opt_out'));
    setFax(field(q, 'fax'));
    setNoOfEmployees(field(q, 'no_of_employees'));
    setRating(field(q, 'rating'));
    setAddr1(field(q, 'address_line_1'));
    setAddr2(field(q, 'address_line_2'));
    setCity(field(q, 'city'));
    setPostcode(field(q, 'postcode'));
    setState(field(q, 'state'));
    setCountry(field(q, 'country'));
    setPropertyType(field(q, 'property_type'));
    setPropertyValue(field(q, 'property_value'));
    setBudgetRange(field(q, 'budget_range'));
    setClosureConfidence(field(q, 'sales_closure_confidence'));
    setEstStart(field(q, 'est_project_start_date'));
    setEstEnd(field(q, 'est_project_end_date'));
    setRespondWorkspaceId(lead.respond_workspace_id || RESPOND_WORKSPACE_NONE);
  }, [lead]);

  useEffect(() => {
    if (!customer) return;
    setCompanyName(customer.customer_name ?? '');
    setWebsite(customer.website ?? '');
  }, [customer]);

  const buildQualification = (): Record<string, unknown> => {
    const prev = { ...(lead?.qualification || {}) };
    const next: Record<string, unknown> = {
      ...prev,
      source: source.trim() || undefined,
      main_email: mainEmail.trim() || undefined,
      main_phone: mainPhone.trim() || undefined,
      profile_image_url: profileImageUrl.trim() || undefined,
      salutation: salutation.trim() || undefined,
      first_name: firstName.trim() || undefined,
      last_name: lastName.trim() || undefined,
      mobile: mobile.trim() || undefined,
      industry: industry.trim() || undefined,
      annual_revenue: annualRevenue.trim() || undefined,
      email_opt_out: emailOptOut,
      fax: fax.trim() || undefined,
      no_of_employees: noOfEmployees.trim() || undefined,
      rating: rating.trim() || undefined,
      address_line_1: addr1.trim() || undefined,
      address_line_2: addr2.trim() || undefined,
      city: city.trim() || undefined,
      postcode: postcode.trim() || undefined,
      state: state.trim() || undefined,
      country: country.trim() || undefined,
      property_type: propertyType.trim() || undefined,
      property_value: propertyValue.trim() || undefined,
      budget_range: budgetRange.trim() || undefined,
      sales_closure_confidence: closureConfidence.trim() || undefined,
      est_project_start_date: estStart.trim() || undefined,
      est_project_end_date: estEnd.trim() || undefined,
    };
    if (!emailOptOut) {
      delete next.email_opt_out;
    }
    Object.keys(next).forEach((k) => {
      if (next[k] === undefined) delete next[k];
    });
    return next;
  };

  const persist = async () => {
    if (!lead) return;
    await updateLead.mutateAsync({
      title: title.trim(),
      owner_user_id: ownerId || null,
      lead_stage_id: stageId,
      respond_workspace_id:
        respondWorkspaceId === RESPOND_WORKSPACE_NONE ? null : respondWorkspaceId,
      qualification_summary: summary.trim() || null,
      qualification: buildQualification(),
    });
    if (customer) {
      const name = companyName.trim();
      const web = website.trim();
      if (name !== (customer.customer_name || '') || web !== (customer.website || '')) {
        await updateCustomer(customer.id, {
          customer_name: name,
          website: web || undefined,
        });
        void qc.invalidateQueries({ queryKey: ['customer', customer.id] });
      }
    }
  };

  const validate = (): boolean => {
    if (!title.trim() || !ownerId || !stageId) {
      toast.error('Title, lead owner, and lead status are required');
      return false;
    }
    if (!companyName.trim()) {
      toast.error('Company is required');
      return false;
    }
    if (!lastName.trim()) {
      toast.error('Last name is required');
      return false;
    }
    return true;
  };

  const onSave = async () => {
    try {
      if (!validate()) return;
      await persist();
      router.push(`/commercial/leads/${leadId}`);
    } catch {
      /* mutation toast */
    }
  };

  const onSaveAndNew = async () => {
    try {
      if (!validate()) return;
      await persist();
      router.push('/commercial/leads/new');
    } catch {
      /* mutation toast */
    }
  };

  const pending = updateLead.isPending;

  if (leadLoading || !lead) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  const imgSrc = profileImageUrl.trim() || null;
  const headerSubtitle = companyName.trim() || title.trim() || '';
  const stageLabel =
    stages.find((s) => s.id === stageId)?.stage_name ?? lead.stage_name ?? '';
  const initials = initialsFromLead(firstName, lastName, companyName);

  return (
    <div className="min-h-[60vh] bg-white">
      <LeadEditPageHero
        leadCode={lead.lead_code}
        stageName={stageLabel}
        stageCode={lead.stage_code}
        subtitle={headerSubtitle}
        avatarUrl={imgSrc}
        initials={initials}
        onCameraClick={() => setPhotoUploadOpen(true)}
      />
      <AttachmentUploadDialog
        open={photoUploadOpen}
        onOpenChange={setPhotoUploadOpen}
        entityType="commercial_lead"
        entityId={leadId}
        onSuccess={(attachmentId) => {
          if (attachmentId) {
            setProfileImageUrl(`/api/v1/resource-management/attachments/${attachmentId}/download`);
          }
        }}
      />
      <div className="mx-auto max-w-[1600px] space-y-8 px-6 py-6">
        <Card className="rounded-[10px] border border-[#e5e7eb] shadow-none">
          <CardHeader className="px-[25px] pb-0 pt-[25px]">
            <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Lead Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6 px-[25px] pb-[25px] pt-6">
            <div className="grid gap-x-8 gap-y-5 lg:grid-cols-2">
                <div className="space-y-5">
                  <StackField label="Lead Owner" missing={!ownerId.trim()}>
                    <SearchableSelect
                      value={ownerId}
                      onValueChange={setOwnerId}
                      options={userSearchOptions}
                      placeholder="Select owner"
                    />
                  </StackField>

                  <StackField label="Respond workspace">
                    <SearchableSelect
                      value={respondWorkspaceId}
                      onValueChange={setRespondWorkspaceId}
                      options={respondWorkspaceOptions}
                      placeholder="Optional — inbox / messaging"
                    />
                  </StackField>

                  <div className="flex flex-col gap-2">
                    <Label className="text-[#4a5565] text-sm font-medium leading-5">First Name</Label>
                    <div className="flex gap-2">
                      <div
                        className={cn(
                          'min-w-0 w-24 shrink-0 overflow-hidden rounded-[4px] border border-[#d1d5dc] bg-background',
                          !firstName.trim() && 'border-l-4 border-l-[#fb2c36]',
                          '[&_[data-slot=select-trigger]]:h-[38px] [&_[data-slot=select-trigger]]:rounded-none [&_[data-slot=select-trigger]]:border-0 [&_[data-slot=select-trigger]]:shadow-none',
                        )}
                      >
                        <SearchableSelect
                          value={salutation ? salutation : SALUTATION_NONE}
                          onValueChange={(v) => setSalutation(v === SALUTATION_NONE ? '' : v)}
                          options={salutationSearchOptions}
                          placeholder="None"
                        />
                      </div>
                      <div className="min-w-0 flex-1 overflow-hidden rounded-[4px] border border-[#d1d5dc] bg-background [&_input]:h-[38px] [&_input]:rounded-none [&_input]:border-0 [&_input]:shadow-none">
                        <Input
                          id="first_name"
                          value={firstName}
                          onChange={(e) => setFirstName(e.target.value)}
                          className="bg-background"
                        />
                      </div>
                    </div>
                  </div>

                  <StackField label="Title" htmlFor="title">
                    <Input
                      id="title"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Phone" htmlFor="main_phone" missing={!mainPhone.trim()}>
                    <Input
                      id="main_phone"
                      value={mainPhone}
                      onChange={(e) => setMainPhone(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Mobile" htmlFor="mobile" missing={!mobile.trim()}>
                    <Input
                      id="mobile"
                      value={mobile}
                      onChange={(e) => setMobile(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <LeadMasterStackSelect
                    label="Lead Source"
                    htmlFor="source"
                    value={source}
                    onValueChange={setSource}
                    options={leadSourceOpts}
                    loading={leadSourcesLoading}
                    placeholder="Select source"
                  />

                  <LeadMasterStackSelect
                    label="Industry"
                    htmlFor="industry"
                    value={industry}
                    onValueChange={setIndustry}
                    options={leadIndustryOpts}
                    loading={leadIndustriesLoading}
                    placeholder="Select industry"
                  />

                  <StackField label="Annual Revenue" htmlFor="annual_revenue">
                    <div className="relative">
                      <span className="text-muted-foreground pointer-events-none absolute start-3 top-1/2 -translate-y-1/2 text-sm">
                        RM
                      </span>
                      <Input
                        id="annual_revenue"
                        value={annualRevenue}
                        onChange={(e) => setAnnualRevenue(e.target.value)}
                        className="bg-background border-0 ps-11 shadow-none focus-visible:ring-1"
                        inputMode="decimal"
                      />
                    </div>
                  </StackField>
                </div>

                <div className="space-y-5">
                  <StackField label="Company" htmlFor="company" missing={!companyName.trim()}>
                    <Input
                      id="company"
                      value={companyName}
                      onChange={(e) => setCompanyName(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Last Name" htmlFor="last_name" missing={!lastName.trim()}>
                    <Input
                      id="last_name"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Email" htmlFor="main_email">
                    <Input
                      id="main_email"
                      type="email"
                      value={mainEmail}
                      onChange={(e) => setMainEmail(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Fax" htmlFor="fax">
                    <Input
                      id="fax"
                      value={fax}
                      onChange={(e) => setFax(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Website" htmlFor="website">
                    <Input
                      id="website"
                      value={website}
                      onChange={(e) => setWebsite(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                    />
                  </StackField>

                  <StackField label="Lead Status">
                    <SearchableSelect
                      value={stageId}
                      onValueChange={setStageId}
                      options={stageSearchOptions}
                      placeholder="None"
                    />
                  </StackField>

                  <StackField label="No. of Employees" htmlFor="no_of_employees">
                    <Input
                      id="no_of_employees"
                      value={noOfEmployees}
                      onChange={(e) => setNoOfEmployees(e.target.value)}
                      className="bg-background border-0 shadow-none focus-visible:ring-1"
                      inputMode="numeric"
                    />
                  </StackField>

                  <StackField label="Rating">
                    <SearchableSelect
                      value={rating ? rating : RATING_NONE}
                      onValueChange={(v) => setRating(v === RATING_NONE ? '' : v)}
                      options={ratingSearchOptions}
                      placeholder="None"
                    />
                  </StackField>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-1">
                <Checkbox
                  id="email_opt_out"
                  checked={emailOptOut}
                  onCheckedChange={(v) => setEmailOptOut(v === true)}
                />
                <Label htmlFor="email_opt_out" className="text-sm font-medium text-[#364153]">
                  Email Opt Out
                </Label>
              </div>

              <div className="space-y-2 border-t border-[#e5e7eb] pt-6">
                <Label htmlFor="summary" className="text-[#4a5565] text-sm font-medium">
                  Summary
                </Label>
                <Textarea
                  id="summary"
                  value={summary}
                  onChange={(e) => setSummary(e.target.value)}
                  rows={3}
                  className="resize-y rounded-[4px] border border-[#d1d5dc] bg-background px-3 py-2 text-base shadow-none focus-visible:ring-1"
                />
              </div>
            </CardContent>
          </Card>

        <Card className="rounded-[10px] border border-[#e5e7eb] shadow-none">
          <CardHeader className="px-[25px] pb-0 pt-[25px]">
            <CardTitle className="text-lg font-semibold tracking-tight text-[#0a0a0a]">Property details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5 px-[25px] pb-[25px] pt-6">
            <div className="grid gap-x-8 gap-y-5 lg:grid-cols-2">
              <StackField label="Address line 1" htmlFor="addr1">
                <Input
                  id="addr1"
                  value={addr1}
                  onChange={(e) => setAddr1(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
              <StackField label="Address line 2" htmlFor="addr2">
                <Input
                  id="addr2"
                  value={addr2}
                  onChange={(e) => setAddr2(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
              <StackField label="City" htmlFor="city">
                <Input
                  id="city"
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
              <StackField label="Postcode" htmlFor="postcode">
                <Input
                  id="postcode"
                  value={postcode}
                  onChange={(e) => setPostcode(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
              <LeadMasterStackSelect
                label="State"
                htmlFor="state"
                value={state}
                onValueChange={setState}
                options={leadStateOpts}
                loading={leadStatesLoading}
              />
              <LeadMasterStackSelect
                label="Country"
                htmlFor="country"
                value={country}
                onValueChange={setCountry}
                options={leadCountryOpts}
                loading={leadCountriesLoading}
              />
              <LeadMasterStackSelect
                label="Property type"
                htmlFor="ptype"
                value={propertyType}
                onValueChange={setPropertyType}
                options={leadPropertyTypeOpts}
                loading={leadPropertyTypesLoading}
              />
              <StackField label="Property value" htmlFor="pvalue">
                <Input
                  id="pvalue"
                  value={propertyValue}
                  onChange={(e) => setPropertyValue(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
              <LeadMasterStackSelect
                label="Budget range"
                htmlFor="budget"
                value={budgetRange}
                onValueChange={setBudgetRange}
                options={leadBudgetOpts}
                loading={leadBudgetsLoading}
              />
              <LeadMasterStackSelect
                label="Sales closure confidence"
                htmlFor="confidence"
                value={closureConfidence}
                onValueChange={setClosureConfidence}
                options={leadClosureOpts}
                loading={leadClosuresLoading}
              />
              <StackField label="Est. project start" htmlFor="est_start">
                <Input
                  id="est_start"
                  type="date"
                  value={estStart}
                  onChange={(e) => setEstStart(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
              <StackField label="Est. project end" htmlFor="est_end">
                <Input
                  id="est_end"
                  type="date"
                  value={estEnd}
                  onChange={(e) => setEstEnd(e.target.value)}
                  className="bg-background border-0 shadow-none focus-visible:ring-1"
                />
              </StackField>
            </div>
          </CardContent>
        </Card>

        <EditFormFooter
          disabled={pending}
          onCancel={() => router.back()}
          onSaveAndNew={onSaveAndNew}
          onSave={onSave}
        />
      </div>
    </div>
  );
}
