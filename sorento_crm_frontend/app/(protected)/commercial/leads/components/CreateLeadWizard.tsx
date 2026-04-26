'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  MapPin,
  Pencil,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { getCustomer } from '@/app/(protected)/order-management/customers/services/customerService';
import { getUsersSelect } from '@/services/userSelectService';
import { useCreateCommercialLead } from '../hooks/useCommercialLeads';
import { listRespondWorkspaceSelect } from '../services/leadRespondContactsService';
import { useLeadAssignmentSelect } from '../hooks/useLeadAssignmentSelect';
import { ClientSelectCombobox } from './ClientSelectCombobox';
import { CreateClientModal } from './CreateClientModal';
import { LeadMasterFieldSelect } from './LeadMasterSelect';
import { cn } from '@/lib/utils';

const STEPS = [
  { label: 'Select Client' },
  { label: 'Property Info' },
  { label: 'Lead Detail' },
  { label: 'Confirmation' },
] as const;

const PROPERTY_STATUS_OPTS = ['Planning', 'Under construction', 'Completed', 'Operational', 'Other'] as const;

const RESPOND_WORKSPACE_NONE = '__respond_workspace_none__';

function FieldColumn({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      <Label className="text-[#364153] text-sm font-medium leading-5">{label}</Label>
      {children}
    </div>
  );
}

function StepCircle({
  index,
  step,
}: {
  index: number;
  step: number;
}) {
  const completed = step > index;
  const current = step === index;
  return (
    <div
      className={cn(
        'flex size-12 shrink-0 items-center justify-center rounded-full border-2 text-lg font-semibold leading-7 transition-colors',
        completed && 'border-[#e7000b] bg-[#e7000b] text-white',
        current &&
          !completed &&
          'border-[#e7000b] bg-white text-[#e7000b]',
        !current && !completed && 'border-[#d1d5dc] bg-white text-[#99a1af]',
      )}
    >
      {completed ? (
        <Check className="size-6 text-white" strokeWidth={2.5} aria-hidden />
      ) : (
        <span>{index + 1}</span>
      )}
    </div>
  );
}

function LeadCreateStepper({ step }: { step: number }) {
  return (
    <div className="grid w-full grid-cols-4 gap-0">
      {STEPS.map((s, index) => (
        <div key={s.label} className="flex flex-col items-center gap-3">
          <div className="flex w-full items-center">
            {index > 0 ? (
              <div
                className={cn(
                  'h-0.5 min-w-0 flex-1',
                  step >= index ? 'bg-[#e7000b]' : 'bg-[#d1d5dc]',
                )}
              />
            ) : (
              <div className="min-w-0 flex-1" aria-hidden />
            )}
            <StepCircle index={index} step={step} />
            {index < STEPS.length - 1 ? (
              <div
                className={cn(
                  'h-0.5 min-w-0 flex-1',
                  step > index ? 'bg-[#e7000b]' : 'bg-[#d1d5dc]',
                )}
              />
            ) : (
              <div className="min-w-0 flex-1" aria-hidden />
            )}
          </div>
          <p
            className={cn(
              'text-center text-sm leading-5',
              step === index ? 'font-medium text-[#e7000b]' : 'font-normal text-[#6a7282]',
            )}
          >
            {s.label}
          </p>
        </div>
      ))}
    </div>
  );
}

function WizardFooter({
  step,
  pending,
  onCancel,
  onBack,
  onNext,
  onSubmit,
  canNext,
}: {
  step: number;
  pending: boolean;
  onCancel: () => void;
  onBack: () => void;
  onNext: () => void;
  onSubmit: () => void;
  canNext: boolean;
}) {
  const isLast = step === STEPS.length - 1;
  return (
    <div className="flex h-[46px] w-full max-w-[960px] items-center justify-between gap-4">
      {step === 0 ? (
        <Button
          type="button"
          variant="outline"
          className="h-[46px] rounded-md border-[#d1d5dc] px-6 text-base font-medium text-[#0a0a0a] shadow-none"
          onClick={onCancel}
        >
          <ArrowLeft className="size-[18px]" aria-hidden />
          Cancel
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          className="h-[46px] rounded-md border-[#d1d5dc] px-6 text-base font-medium text-[#0a0a0a] shadow-none"
          onClick={onBack}
        >
          <ArrowLeft className="size-[18px]" aria-hidden />
          Back
        </Button>
      )}
      {isLast ? (
        <Button
          type="button"
          disabled={pending || !canNext}
          className="h-[46px] min-w-[137px] rounded-md bg-[#e7000b] px-6 text-base font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-60"
          onClick={onSubmit}
        >
          {pending ? <Loader2 className="size-4 animate-spin" aria-hidden /> : 'Create Lead'}
        </Button>
      ) : (
        <Button
          type="button"
          disabled={!canNext}
          className="h-[46px] min-w-[108px] rounded-md bg-[#e7000b] px-6 text-base font-medium text-white hover:bg-[#e7000b]/90 disabled:opacity-60"
          onClick={onNext}
        >
          Next
          <ArrowRight className="size-[18px]" aria-hidden />
        </Button>
      )}
    </div>
  );
}

export default function CreateLeadWizard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCustomer = searchParams.get('customer_id') || '';

  const [step, setStep] = useState(0);
  const [customerId, setCustomerId] = useState(initialCustomer);

  const [addr1, setAddr1] = useState('');
  const [addr2, setAddr2] = useState('');
  const [postcode, setPostcode] = useState('');
  const [city, setCity] = useState('');
  const [state, setState] = useState('');
  const [country, setCountry] = useState('Malaysia');

  const [propertyType, setPropertyType] = useState('');
  const [propertyStatus, setPropertyStatus] = useState('');
  const [propertyCurrency, setPropertyCurrency] = useState('MYR');
  const [propertyValue, setPropertyValue] = useState('');

  const [title, setTitle] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [budgetRange, setBudgetRange] = useState('');
  const [closureConfidence, setClosureConfidence] = useState('');
  const [referral, setReferral] = useState('');
  const [estStart, setEstStart] = useState('');
  const [estEnd, setEstEnd] = useState('');
  const [respondWorkspaceId, setRespondWorkspaceId] = useState(RESPOND_WORKSPACE_NONE);

  const [createClientOpen, setCreateClientOpen] = useState(false);
  const [createClientPrefill, setCreateClientPrefill] = useState('');

  const createLead = useCreateCommercialLead();

  const { data: selectedCustomer } = useQuery({
    queryKey: ['customer', customerId],
    queryFn: () => getCustomer(customerId),
    enabled: !!customerId,
  });

  const { data: users = [] } = useQuery({
    queryKey: ['users-select', 'create-lead'],
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

  const qualification = () => ({
    ...(selectedCustomer?.phone_number?.trim()
      ? { client_phone: String(selectedCustomer.phone_number).trim() }
      : {}),
    ...(addr1.trim() ? { address_line_1: addr1.trim() } : {}),
    ...(addr2.trim() ? { address_line_2: addr2.trim() } : {}),
    ...(postcode.trim() ? { postcode: postcode.trim() } : {}),
    ...(city.trim() ? { city: city.trim() } : {}),
    ...(state.trim() ? { state: state.trim() } : {}),
    ...(country.trim() ? { country: country.trim() } : {}),
    ...(propertyType.trim() ? { property_type: propertyType.trim() } : {}),
    ...(propertyStatus.trim() ? { property_status: propertyStatus.trim() } : {}),
    ...(propertyValue.trim()
      ? {
          property_value: propertyValue.trim(),
          property_value_currency: propertyCurrency,
        }
      : {}),
    ...(budgetRange.trim() ? { budget_range: budgetRange.trim() } : {}),
    ...(closureConfidence.trim() ? { sales_closure_confidence: closureConfidence.trim() } : {}),
    ...(referral.trim() ? { referral: referral.trim() } : {}),
    ...(estStart.trim() ? { est_project_start: estStart.trim() } : {}),
    ...(estEnd.trim() ? { est_project_end: estEnd.trim() } : {}),
  });

  const qualificationSummary = () =>
    [
      budgetRange && `Budget: ${budgetRange}`,
      closureConfidence && `Confidence: ${closureConfidence}`,
      referral && `Referral: ${referral}`,
    ]
      .filter(Boolean)
      .join(' · ');

  const addressLineDisplay = () => {
    const parts = [addr1, addr2, postcode, city, state, country].filter((p) => p.trim());
    return parts.length ? parts.join(', ') : '—';
  };

  const canGoNext = () => {
    if (step === 0) return !!customerId;
    if (step === 1) return true;
    if (step === 2) return !!title.trim() && !!ownerId;
    return !!customerId && !!title.trim() && !!ownerId;
  };

  const onSubmit = () => {
    if (!customerId || !title.trim() || !ownerId) return;
    const q = qualification();
    createLead.mutate(
      {
        customer_id: customerId,
        title: title.trim(),
        owner_user_id: ownerId,
        respond_workspace_id:
          respondWorkspaceId === RESPOND_WORKSPACE_NONE ? undefined : respondWorkspaceId,
        qualification: Object.keys(q).length ? q : undefined,
        qualification_summary: qualificationSummary().trim() || undefined,
      },
      {
        onSuccess: (lead) => {
          router.push(`/commercial/leads/${lead.id}`);
        },
      },
    );
  };

  const openMaps = () => {
    const q = [addr1, city, state, country].filter(Boolean).join(', ');
    const url = q
      ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(q)}`
      : 'https://www.google.com/maps';
    window.open(url, '_blank', 'noopener,noreferrer');
  };

  const inputClass =
    'h-[42px] rounded-[4px] border border-[#d1d5dc] bg-background px-3 shadow-none focus-visible:ring-1';

  const selectTriggerClass =
    'h-[38px] w-full rounded-[4px] border border-[#d1d5dc] bg-background shadow-none focus:ring-1';

  return (
    <div className="min-h-[60vh] bg-[#f9fafb] pb-16">
      <div className="mx-auto w-full max-w-[960px] px-8 pt-8">
        <button
          type="button"
          onClick={() => router.push('/commercial/leads')}
          className="mb-6 flex size-6 items-center justify-center text-[#0a0a0a] hover:opacity-80"
          aria-label="Back to leads"
        >
          <ArrowLeft className="size-6" />
        </button>

        <div className="mb-10 space-y-2">
          <h1 className="text-[30px] font-semibold leading-9 tracking-tight text-[#0a0a0a]">
            Create New Lead
          </h1>
          <p className="text-base leading-6 text-[#6a7282]">
            Add a new lead to your organization
          </p>
        </div>

        <div className="mb-10">
          <LeadCreateStepper step={step} />
        </div>

        {/* Step 0 — Select Client */}
        {step === 0 && (
          <Card className="mb-10 rounded-[10px] border border-[#e5e7eb] bg-white px-[33px] pb-[33px] pt-[33px] shadow-none">
            <div className="space-y-6">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold leading-8 text-[#0a0a0a]">Select Client</h2>
                <p className="text-base leading-6 text-[#6a7282]">
                  Search and select an existing client, or create a new one.
                </p>
              </div>
              <ClientSelectCombobox
                value={customerId}
                onChange={setCustomerId}
                selectedCustomer={selectedCustomer ?? null}
                emptyLabel="Select client..."
                className="h-[50px] rounded-[10px] border-[#d1d5dc] bg-[#fef2f2] px-4 text-[#101828] shadow-none hover:bg-[#fef2f2]"
                onCreateNew={(q) => {
                  setCreateClientPrefill(q);
                  setCreateClientOpen(true);
                }}
              />
              <Button
                type="button"
                variant="outline"
                className="rounded-md border-[#d1d5dc]"
                onClick={() => {
                  setCreateClientPrefill('');
                  setCreateClientOpen(true);
                }}
              >
                New client
              </Button>
            </div>
          </Card>
        )}

        {/* Step 1 — Property Info */}
        {step === 1 && (
          <Card className="mb-10 rounded-[10px] border border-[#e5e7eb] bg-white px-[33px] pb-[33px] pt-[33px] shadow-none">
            <div className="flex flex-col gap-8">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-1">
                  <h2 className="text-xl font-semibold leading-7 text-[#0a0a0a]">Property Address</h2>
                  <p className="text-sm leading-5 text-[#6a7282]">
                    Enter the property address or use Google Maps to find it.
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="h-[42px] shrink-0 rounded-md border-[#e7000b] text-base font-medium text-[#e7000b] hover:bg-[#fef2f2] hover:text-[#e7000b]"
                  onClick={openMaps}
                >
                  <MapPin className="size-[18px]" aria-hidden />
                  Open Maps
                </Button>
              </div>

              <div className="flex flex-col gap-4">
                <FieldColumn label="Address Line 1">
                  <Input
                    value={addr1}
                    onChange={(e) => setAddr1(e.target.value)}
                    className={inputClass}
                  />
                </FieldColumn>
                <FieldColumn label="Address Line 2">
                  <Input
                    value={addr2}
                    onChange={(e) => setAddr2(e.target.value)}
                    className={inputClass}
                  />
                </FieldColumn>
                <div className="grid gap-4 md:grid-cols-2 md:gap-6">
                  <FieldColumn label="Postcode">
                    <Input
                      value={postcode}
                      onChange={(e) => setPostcode(e.target.value)}
                      className={inputClass}
                    />
                  </FieldColumn>
                  <FieldColumn label="Area / City">
                    <Input value={city} onChange={(e) => setCity(e.target.value)} className={inputClass} />
                  </FieldColumn>
                </div>
                <div className="grid gap-4 md:grid-cols-2 md:gap-6">
                  <LeadMasterFieldSelect
                    label="State"
                    value={state}
                    onValueChange={setState}
                    options={leadStateOpts}
                    loading={leadStatesLoading}
                    placeholder="Select state"
                  />
                  <LeadMasterFieldSelect
                    label="Country"
                    value={country}
                    onValueChange={setCountry}
                    options={leadCountryOpts}
                    loading={leadCountriesLoading}
                    placeholder="Select country"
                  />
                </div>
              </div>

              <div className="border-t border-[#e5e7eb] pt-6">
                <h3 className="mb-4 text-xl font-semibold leading-7 text-[#0a0a0a]">Property Details</h3>
                <div className="grid gap-4 lg:grid-cols-3">
                  <LeadMasterFieldSelect
                    label="Property Type"
                    value={propertyType}
                    onValueChange={setPropertyType}
                    options={leadPropertyTypeOpts}
                    loading={leadPropertyTypesLoading}
                    placeholder="Select"
                  />
                  <FieldColumn label="Property Status">
                    <Select
                      value={propertyStatus || '__none__'}
                      onValueChange={(v) => setPropertyStatus(v === '__none__' ? '' : v)}
                    >
                      <SelectTrigger className={selectTriggerClass}>
                        <SelectValue placeholder="Select" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__none__">Select</SelectItem>
                        {PROPERTY_STATUS_OPTS.map((t) => (
                          <SelectItem key={t} value={t}>
                            {t}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </FieldColumn>
                  <FieldColumn label="Property Value">
                    <div className="flex gap-2">
                      <Select value={propertyCurrency} onValueChange={setPropertyCurrency}>
                        <SelectTrigger className={cn(selectTriggerClass, 'w-[79px] shrink-0 px-2')}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="MYR">MYR</SelectItem>
                          <SelectItem value="SGD">SGD</SelectItem>
                          <SelectItem value="USD">USD</SelectItem>
                        </SelectContent>
                      </Select>
                      <Input
                        value={propertyValue}
                        onChange={(e) => setPropertyValue(e.target.value)}
                        className={cn(inputClass, 'min-w-0 flex-1')}
                        inputMode="decimal"
                        placeholder="0"
                      />
                    </div>
                  </FieldColumn>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Step 2 — Lead Detail */}
        {step === 2 && (
          <Card className="mb-10 rounded-[10px] border border-[#e5e7eb] bg-white px-[33px] pb-[33px] pt-[33px] shadow-none">
            <div className="space-y-6">
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold leading-8 text-[#0a0a0a]">Lead Details</h2>
                <p className="text-base leading-6 text-[#6a7282]">
                  Provide the budget, confidence level, and referral information.
                </p>
              </div>

              <div className="grid gap-6 border-b border-[#e5e7eb] pb-6 md:grid-cols-2">
                <FieldColumn label="Lead title">
                  <Input
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    className={inputClass}
                    placeholder="e.g. Tower A — façade package"
                  />
                </FieldColumn>
                <FieldColumn label="Lead owner">
                  <Select value={ownerId || undefined} onValueChange={setOwnerId}>
                    <SelectTrigger className={selectTriggerClass}>
                      <SelectValue placeholder="Select owner" />
                    </SelectTrigger>
                    <SelectContent>
                      {users.map((u) => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name || u.email}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FieldColumn>
                <FieldColumn label="Respond workspace (optional)" className="md:col-span-2">
                  <Select
                    value={respondWorkspaceId === RESPOND_WORKSPACE_NONE ? '__none__' : respondWorkspaceId}
                    onValueChange={(v) =>
                      setRespondWorkspaceId(v === '__none__' ? RESPOND_WORKSPACE_NONE : v)
                    }
                  >
                    <SelectTrigger className={selectTriggerClass}>
                      <SelectValue placeholder="None" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__">None</SelectItem>
                      {respondWorkspaces.map((w) => (
                        <SelectItem key={w.id} value={w.id}>
                          {(w.name || '').trim() || w.space_id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </FieldColumn>
              </div>

              <div className="grid gap-6 md:grid-cols-2">
                <LeadMasterFieldSelect
                  label="Budget Range (RM)"
                  value={budgetRange}
                  onValueChange={setBudgetRange}
                  options={leadBudgetOpts}
                  loading={leadBudgetsLoading}
                  placeholder="Select range"
                />
                <LeadMasterFieldSelect
                  label="Sales Closure Confidence"
                  value={closureConfidence}
                  onValueChange={setClosureConfidence}
                  options={leadClosureOpts}
                  loading={leadClosuresLoading}
                  placeholder="Select"
                />
              </div>

              <FieldColumn label="Referral">
                <Input
                  value={referral}
                  onChange={(e) => setReferral(e.target.value)}
                  className={inputClass}
                  placeholder="e.g. Friend, Social Media, Agent Name"
                />
              </FieldColumn>

              <div className="grid gap-6 md:grid-cols-2">
                <FieldColumn label="Est. Project Start Date">
                  <Input
                    type="date"
                    value={estStart}
                    onChange={(e) => setEstStart(e.target.value)}
                    className={inputClass}
                  />
                </FieldColumn>
                <FieldColumn label="Est. Project End Date">
                  <Input
                    type="date"
                    value={estEnd}
                    onChange={(e) => setEstEnd(e.target.value)}
                    className={inputClass}
                  />
                </FieldColumn>
              </div>
            </div>
          </Card>
        )}

        {/* Step 3 — Confirmation */}
        {step === 3 && (
          <Card className="mb-10 rounded-[10px] border border-[#e5e7eb] bg-white px-[33px] pb-[33px] pt-[33px] shadow-none">
            <div className="flex flex-col gap-6">
              <div className="rounded-[10px] border border-[#e5e7eb] px-[25px] pb-[25px] pt-[25px]">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-semibold leading-7 text-[#0a0a0a]">Client</h3>
                  <button
                    type="button"
                    className="flex items-center gap-1 text-base font-medium text-[#4a5565] hover:text-[#0a0a0a]"
                    onClick={() => setStep(0)}
                  >
                    <Pencil className="size-4" aria-hidden />
                    Edit
                  </button>
                </div>
                <div className="flex items-start justify-between gap-4 text-base leading-6">
                  <span className="text-[#6a7282]">Client Name</span>
                  <span className="max-w-[60%] text-end font-medium text-[#0a0a0a]">
                    {selectedCustomer
                      ? `${selectedCustomer.customer_name} (${selectedCustomer.customer_code})`
                      : '—'}
                  </span>
                </div>
              </div>

              <div className="rounded-[10px] border border-[#e5e7eb] px-[25px] pb-[25px] pt-[25px]">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-semibold leading-7 text-[#0a0a0a]">Property Information</h3>
                  <button
                    type="button"
                    className="flex items-center gap-1 text-base font-medium text-[#4a5565] hover:text-[#0a0a0a]"
                    onClick={() => setStep(1)}
                  >
                    <Pencil className="size-4" aria-hidden />
                    Edit
                  </button>
                </div>
                <div className="flex items-start justify-between gap-4 text-base leading-6">
                  <span className="text-[#6a7282]">Address</span>
                  <span className="max-w-[65%] text-end font-medium text-[#0a0a0a]">
                    {addressLineDisplay()}
                  </span>
                </div>
              </div>

              <div className="rounded-[10px] border border-[#e5e7eb] px-[25px] pb-[25px] pt-[25px]">
                <div className="mb-4 flex items-center justify-between">
                  <h3 className="text-lg font-semibold leading-7 text-[#0a0a0a]">Lead Details</h3>
                  <button
                    type="button"
                    className="flex items-center gap-1 text-base font-medium text-[#4a5565] hover:text-[#0a0a0a]"
                    onClick={() => setStep(2)}
                  >
                    <Pencil className="size-4" aria-hidden />
                    Edit
                  </button>
                </div>
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-4 text-base leading-6">
                    <span className="text-[#6a7282]">Lead title</span>
                    <span className="max-w-[60%] text-end font-medium text-[#0a0a0a]">
                      {title.trim() || '—'}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4 text-base leading-6">
                    <span className="text-[#6a7282]">Owner</span>
                    <span className="max-w-[60%] text-end font-medium text-[#0a0a0a]">
                      {users.find((u) => u.id === ownerId)?.name ||
                        users.find((u) => u.id === ownerId)?.email ||
                        '—'}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4 text-base leading-6">
                    <span className="text-[#6a7282]">Budget Range</span>
                    <span className="max-w-[60%] text-end font-medium text-[#0a0a0a]">
                      {budgetRange.trim() || '—'}
                    </span>
                  </div>
                  <div className="flex items-start justify-between gap-4 text-base leading-6">
                    <span className="text-[#6a7282]">Sales Closure Confidence</span>
                    <span className="max-w-[60%] text-end font-medium text-[#0a0a0a]">
                      {closureConfidence.trim() || '—'}
                    </span>
                  </div>
                  {referral.trim() ? (
                    <div className="flex items-start justify-between gap-4 text-base leading-6">
                      <span className="text-[#6a7282]">Referral</span>
                      <span className="max-w-[60%] text-end font-medium text-[#0a0a0a]">{referral}</span>
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          </Card>
        )}

        <WizardFooter
          step={step}
          pending={createLead.isPending}
          onCancel={() => router.push('/commercial/leads')}
          onBack={() => setStep((s) => Math.max(0, s - 1))}
          onNext={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
          onSubmit={onSubmit}
          canNext={canGoNext()}
        />
      </div>

      <CreateClientModal
        open={createClientOpen}
        onOpenChange={setCreateClientOpen}
        initialFullName={createClientPrefill}
        onCreated={(c) => setCustomerId(c.id)}
      />
    </div>
  );
}
