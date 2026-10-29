'use client';

import * as React from 'react';
import { useSession } from 'next-auth/react';
import { ArrowLeft, ArrowRight } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { WizardSteps } from '@/components/common/WizardSteps';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useFetchCustomerOptions,
  useLeadMutations,
  useProjectParties,
} from '../../_shared/hooks/useProjects';
import {
  useAssignableUsers,
  useLeadAcceptanceMutations,
} from '../../_shared/hooks/useLeadAcceptance';
import type {
  ProjectLead,
  ProjectLeadBody,
} from '../../_shared/types/project.types';
import type { LeadInformantBody } from '../../_shared/types/leadAcceptance.types';
import {
  EMPTY_INFORMANT,
  InformantFieldset,
  informantBody,
  type InformantDraft,
} from './InformantFieldset';
import { informantSourceLabel } from './acceptance';

const STEPS = [
  { id: 'customer', label: 'Customer' },
  { id: 'development', label: 'The development' },
  { id: 'informant', label: 'Who told us' },
  { id: 'confirm', label: 'Assign and confirm' },
] as const;

type StepId = (typeof STEPS)[number]['id'];

/**
 * Create a lead: the customer, the development, who told us, and who it goes to.
 *
 * The customer comes FIRST because the project registered from the lead takes it
 * (LEAD-GOVERNS-REGISTER). It is picked from the server search, never created here.
 *
 * A lead is never clash-checked (AC-O3), so there is no warning panel here. That check
 * happens once, at qualify, where it means something.
 */
export function LeadWizardDialog({
  onDone,
  initialTitle = '',
}: {
  /** Called with the created lead, or with nothing when the dialog is closed without one. */
  onDone: (created?: ProjectLead) => void;
  /** What the caller already knows the development as, e.g. text typed into a lead picker. */
  initialTitle?: string;
}) {
  const { create } = useLeadMutations();
  const { assign } = useLeadAcceptanceMutations();
  const [step, setStep] = React.useState<StepId>('customer');
  const canEdit = useHasPermission('projects.projects.edit');
  const canSubmit = useHasPermission('projects.registrations.submit');
  // A submit-only salesperson's lead is theirs: the server owns it to them, nothing to assign.
  const submitOnly = !canEdit && canSubmit;

  const [title, setTitle] = React.useState(initialTitle);
  const [developerPartyId, setDeveloperPartyId] = React.useState('');
  const [location, setLocation] = React.useState('');

  const [informant, setInformant] =
    React.useState<InformantDraft>(EMPTY_INFORMANT);

  const [customerId, setCustomerId] = React.useState('');
  const [customerNames, setCustomerNames] = React.useState<
    Record<string, string>
  >({});
  const customerName = customerNames[customerId] ?? '';
  const [estimatedValue, setEstimatedValue] = React.useState('');
  const [notes, setNotes] = React.useState('');

  const [ownerUserId, setOwnerUserId] = React.useState('');

  const developers = useProjectParties({ party_type: 'developer', limit: 200 });
  const searchCustomers = useFetchCustomerOptions();
  // The picked name is read back from the search results, so Confirm needs no second lookup.
  const fetchCustomers = React.useCallback(
    async (query: string) => {
      const options = await searchCustomers(query);
      setCustomerNames((previous) => ({
        ...previous,
        ...Object.fromEntries(
          options.map((option) => [option.value, option.label]),
        ),
      }));
      return options;
    },
    [searchCustomers],
  );
  const users = useAssignableUsers();

  const customerReady = customerId.length > 0;
  const developmentReady = title.trim().length > 0;
  const stepIndex = STEPS.findIndex((candidate) => candidate.id === step);
  // Rough value may stay blank; a typed one that cannot be read stops the walk at its step.
  const valueError = numberFieldError(estimatedValue, {
    min: 0,
    optional: true,
  });
  // The sentence stays hidden while typing; a refused press shows it, then it follows the box live.
  const [valueErrorShown, setValueErrorShown] = React.useState(false);
  const canAdvance =
    step === 'customer'
      ? customerReady
      : step === 'development'
        ? developmentReady
        : true;

  async function submit() {
    const body: ProjectLeadBody & LeadInformantBody = {
      title: title.trim(),
      customer_id: customerId,
      developer_party_id: developerPartyId || null,
      estimated_value: estimatedValue.trim() || null,
      location: location.trim() || null,
      notes: notes.trim() || null,
      ...informantBody(informant),
    };
    const lead = await create.mutateAsync(body);

    // Assignment is its own step server-side: it stamps the clock and notifies the
    // salesperson. A failure here leaves a perfectly good unassigned lead, so it must
    // not roll the wizard back (the mutation reports it).
    if (ownerUserId && !submitOnly) {
      try {
        await assign.mutateAsync({ id: lead.id, ownerUserId });
      } catch {
        /* reported by the mutation */
      }
    }
    onDone(lead);
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent
        className="max-h-[92vh] w-full max-w-lg overflow-hidden"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>Create lead</DialogTitle>
        </DialogHeader>

        {/* A real form, like every other dialog in this module, so Enter advances the
            step instead of doing nothing. No `px-6`: DialogContent already pads, and
            the extra padding indented the step strip past the header above it. */}
        <form
          onSubmit={(event) => {
            event.preventDefault();
            // React bubbles a portalled submit up the COMPONENT tree, so a caller that ever
            // renders this inside its own form must not receive the wizard's submit.
            event.stopPropagation();
            if (valueError && (step === 'development' || step === 'confirm')) {
              setValueErrorShown(true);
              setStep('development');
              return;
            }
            if (step === 'confirm') {
              void submit();
              return;
            }
            if (canAdvance) setStep(STEPS[stepIndex + 1].id);
          }}
        >
          <WizardSteps steps={STEPS} currentId={step} className="mb-4" />

          <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
            {step === 'customer' && (
              <div className="space-y-1.5">
                <Label htmlFor="lead-customer">
                  Customer <span className="text-destructive">*</span>
                </Label>
                <SearchableSelect
                  id="lead-customer"
                  value={customerId}
                  onChange={setCustomerId}
                  fetchOptions={fetchCustomers}
                  selectedOption={
                    customerId
                      ? { value: customerId, label: customerName }
                      : undefined
                  }
                  placeholder="Search customers"
                  emptyMessage="No customers found"
                />
              </div>
            )}

            {step === 'development' && (
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="lead-title">
                    What is it <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="lead-title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g. Tower behind the Setia showroom"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="lead-developer">Developer</Label>
                  <SearchableSelect
                    id="lead-developer"
                    value={developerPartyId}
                    onChange={setDeveloperPartyId}
                    clearable
                    loadError={developers.error}
                    onRetry={() => void developers.refetch()}
                    options={(developers.data?.data ?? []).map((party) => ({
                      value: party.id,
                      label: party.name,
                    }))}
                    placeholder="Search developers"
                    emptyMessage="No developers yet. Add one under Parties"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="lead-location">Location</Label>
                  <Input
                    id="lead-location"
                    value={location}
                    onChange={(event) => setLocation(event.target.value)}
                    placeholder="e.g. Setia Alam, Selangor"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="lead-value">Rough value (RM)</Label>
                  <NumberInput
                    id="lead-value"
                    min={0}
                    value={estimatedValue}
                    error={
                      valueErrorShown && estimatedValue.trim()
                        ? valueError
                        : undefined
                    }
                    onChange={(event) => setEstimatedValue(event.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="lead-notes">Notes</Label>
                  <Textarea
                    id="lead-notes"
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    rows={3}
                  />
                </div>
              </div>
            )}

            {step === 'informant' && (
              <InformantFieldset
                value={informant}
                onChange={setInformant}
                showTitle={false}
              />
            )}

            {step === 'confirm' && (
              <div className="space-y-4">
                {!submitOnly && (
                  <div className="space-y-1.5">
                    <Label htmlFor="lead-owner">Assign to</Label>
                    <SearchableSelect
                      id="lead-owner"
                      value={ownerUserId}
                      onChange={setOwnerUserId}
                      clearable
                      loadError={users.error}
                      onRetry={() => void users.refetch()}
                      options={(users.data ?? []).map((user) => ({
                        value: user.id,
                        label: user.name || 'Unnamed user',
                      }))}
                      placeholder="Select a salesperson"
                      emptyMessage="No match"
                    />
                  </div>
                )}

                <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                  <Fact label="Customer" value={customerName || null} />
                  <Fact label="Development" value={title.trim()} />
                  <Fact
                    label="Developer"
                    value={
                      (developers.data?.data ?? []).find(
                        (party) => party.id === developerPartyId,
                      )?.name ?? null
                    }
                  />
                  <Fact label="Location" value={location.trim() || null} />
                  <Fact
                    label="Source"
                    value={
                      informantSourceLabel(
                        informantBody(informant).informant_source,
                      ) || null
                    }
                  />
                  <Fact
                    label="Contact"
                    value={informant.informant_contact_name.trim() || null}
                  />
                  <Fact
                    label="Reference"
                    value={informant.informant_ref.trim() || null}
                  />
                  <Fact
                    label="Rough value"
                    value={
                      estimatedValue.trim()
                        ? `RM ${estimatedValue.trim()}`
                        : null
                    }
                  />
                  {submitOnly && <SalespersonFact />}
                </dl>
              </div>
            )}
          </DialogBody>

          {/* Back sits on the left because it walks the wizard backwards rather than
              leaving it; Cancel and the forward action keep the end alignment every
              other dialog in this module uses. */}
          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
            <Button
              type="button"
              variant="outline"
              disabled={stepIndex === 0}
              onClick={() => setStep(STEPS[Math.max(stepIndex - 1, 0)].id)}
            >
              <ArrowLeft className="size-4" aria-hidden />
              Back
            </Button>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button type="button" variant="outline" onClick={() => onDone()}>
                Cancel
              </Button>
              {step === 'confirm' ? (
                <Button
                  type="submit"
                  disabled={
                    create.isPending || assign.isPending || !developmentReady
                  }
                >
                  Create lead
                </Button>
              ) : (
                <Button type="submit" disabled={!canAdvance}>
                  Next
                  <ArrowRight className="size-4" aria-hidden />
                </Button>
              )}
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SalespersonFact() {
  const { data: session } = useSession();
  return <Fact label="Salesperson" value={session?.user?.name ?? null} />;
}

function Fact({
  label,
  value,
  emptyText = '-',
}: {
  label: string;
  value?: string | null;
  emptyText?: string;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">
        {value ?? <span className="text-muted-foreground">{emptyText}</span>}
      </dd>
    </div>
  );
}
