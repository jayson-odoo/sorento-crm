'use client';

import * as React from 'react';
import { ArrowLeft, ArrowRight, Check, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useCustomerSelectQuery } from '@/app/(protected)/order-management/shared/hooks/use-customer-select-query';
import {
  useLeadMutations,
  useProjectParties,
} from '../../_shared/hooks/useProjects';
import type { LeadNewCustomer, LeadSource } from '../../_shared/types/project.types';

const SOURCE_OPTIONS = [
  { value: 'site_visit', label: 'Site visit', description: 'Saw it on the ground' },
  { value: 'architect', label: 'Architect', description: 'A consultant told us' },
  { value: 'contractor', label: 'Contractor', description: 'A main contractor told us' },
  { value: 'dealer', label: 'Dealer', description: 'A dealer passed it on' },
  { value: 'inbound', label: 'Inbound enquiry', description: 'They came to us' },
  { value: 'other', label: 'Other' },
];

const STEPS = [
  { id: 'customer', label: 'Who told us' },
  { id: 'development', label: 'The development' },
  { id: 'detail', label: 'Lead detail' },
  { id: 'confirm', label: 'Confirm' },
] as const;

type StepId = (typeof STEPS)[number]['id'];

/**
 * The wizard from the plan: select-or-create customer, development info, lead detail,
 * confirm.
 *
 * Four steps rather than one long form on purpose. Step 1 is the only REQUIRED
 * decision (AC-O1), and a single form would bury it among eight optional fields, which
 * is how a required field ends up being filled with whatever is nearest.
 *
 * A lead is never clash-checked (AC-O3), so there is no warning panel here. That check
 * happens once, at qualify, where it means something.
 */
export function LeadWizardDialog({ onDone }: { onDone: () => void }) {
  const { create } = useLeadMutations();
  const [step, setStep] = React.useState<StepId>('customer');

  const [customerId, setCustomerId] = React.useState('');
  const [creatingCustomer, setCreatingCustomer] = React.useState(false);
  const [newCustomer, setNewCustomer] = React.useState<LeadNewCustomer>({
    customer_name: '',
  });

  const [title, setTitle] = React.useState('');
  const [developerPartyId, setDeveloperPartyId] = React.useState('');
  const [location, setLocation] = React.useState('');

  const [source, setSource] = React.useState<string>('');
  const [sourceDetail, setSourceDetail] = React.useState('');
  const [estimatedValue, setEstimatedValue] = React.useState('');
  const [notes, setNotes] = React.useState('');

  const developers = useProjectParties({ party_type: 'developer', limit: 200 });

  // The shared customer-select hook, not a bespoke fetch: one definition of "the
  // customer list" across the app, per the architecture rules. SearchableSelect
  // filters it client-side, which is what every other customer picker does.
  const customers = useCustomerSelectQuery();

  const selectedCustomer = (customers.data ?? []).find((row) => row.id === customerId);

  const customerReady = creatingCustomer
    ? newCustomer.customer_name.trim().length > 0
    : Boolean(customerId);
  const developmentReady = title.trim().length > 0;

  const stepIndex = STEPS.findIndex((candidate) => candidate.id === step);
  const canAdvance =
    step === 'customer' ? customerReady : step === 'development' ? developmentReady : true;

  async function submit() {
    await create.mutateAsync({
      title: title.trim(),
      customer_id: creatingCustomer ? null : customerId,
      new_customer: creatingCustomer ? newCustomer : null,
      developer_party_id: developerPartyId || null,
      source: (source || null) as LeadSource | null,
      source_detail: sourceDetail.trim() || null,
      estimated_value: estimatedValue.trim() || null,
      location: location.trim() || null,
      notes: notes.trim() || null,
    });
    onDone();
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>Record a lead</DialogTitle>
          <DialogDescription>
            A lead claims nothing. Ownership locks when you qualify it into a project.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap gap-1.5 px-6">
          {STEPS.map((candidate, index) => (
            <Badge
              key={candidate.id}
              variant={
                candidate.id === step
                  ? 'primary'
                  : index < stepIndex
                    ? 'secondary'
                    : 'outline'
              }
              className="text-[11px]"
            >
              {index < stepIndex && <Check className="size-3" aria-hidden />}
              {candidate.label}
            </Badge>
          ))}
        </div>

        <DialogBody className="max-h-[60vh] space-y-4 overflow-y-auto">
          {step === 'customer' && (
            <div className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Somebody told us about this. That person or firm is the lead&apos;s
                customer, even when they have never bought anything from us.
              </p>

              {creatingCustomer ? (
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="lead-new-customer">
                      Name <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="lead-new-customer"
                      value={newCustomer.customer_name}
                      onChange={(event) =>
                        setNewCustomer((previous) => ({
                          ...previous,
                          customer_name: event.target.value,
                        }))
                      }
                      placeholder="Veritas Architects Sdn Bhd"
                    />
                    <p className="text-xs text-muted-foreground">
                      Created as a prospect. An existing customer with this name is
                      reused rather than duplicated.
                    </p>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label htmlFor="lead-new-phone">Phone</Label>
                      <Input
                        id="lead-new-phone"
                        value={newCustomer.phone_number ?? ''}
                        onChange={(event) =>
                          setNewCustomer((previous) => ({
                            ...previous,
                            phone_number: event.target.value,
                          }))
                        }
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="lead-new-email">Email</Label>
                      <Input
                        id="lead-new-email"
                        type="email"
                        value={newCustomer.email ?? ''}
                        onChange={(event) =>
                          setNewCustomer((previous) => ({
                            ...previous,
                            email: event.target.value,
                          }))
                        }
                      />
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setCreatingCustomer(false)}
                  >
                    Pick an existing customer instead
                  </Button>
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="lead-customer">
                      Customer <span className="text-destructive">*</span>
                    </Label>
                    <SearchableSelect
                      id="lead-customer"
                      value={customerId}
                      onChange={setCustomerId}
                      options={(customers.data ?? []).map((row) => ({
                        value: row.id,
                        label: row.customer_name,
                        description: row.customer_code ?? undefined,
                      }))}
                      placeholder="Search customers"
                      emptyMessage="No match. Create the customer instead."
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setCreatingCustomer(true)}
                  >
                    <Plus className="size-4" aria-hidden />
                    They are not a customer yet
                  </Button>
                </div>
              )}
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
                <p className="text-xs text-muted-foreground">
                  Vague is fine. Nobody is claiming anything yet, and a lead you did not
                  record is worth less than one with a rough name.
                </p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lead-developer">Developer</Label>
                <SearchableSelect
                  id="lead-developer"
                  value={developerPartyId}
                  onChange={setDeveloperPartyId}
                  clearable
                  options={(developers.data?.data ?? []).map((party) => ({
                    value: party.id,
                    label: party.name,
                  }))}
                  placeholder="Often unknown at this stage"
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
            </div>
          )}

          {step === 'detail' && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="lead-source">Where it came from</Label>
                <SearchableSelect
                  id="lead-source"
                  value={source}
                  onChange={setSource}
                  clearable
                  options={SOURCE_OPTIONS}
                  placeholder="Not recorded"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lead-source-detail">Who said what</Label>
                <Input
                  id="lead-source-detail"
                  value={sourceDetail}
                  onChange={(event) => setSourceDetail(event.target.value)}
                  placeholder="e.g. QS at Veritas mentioned it on 12 Jul"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lead-value">Rough value (RM)</Label>
                <Input
                  id="lead-value"
                  type="number"
                  min={0}
                  value={estimatedValue}
                  onChange={(event) => setEstimatedValue(event.target.value)}
                  placeholder="A guess is better than nothing"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="lead-notes">Notes</Label>
                <Textarea
                  id="lead-notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={3}
                  placeholder="What you heard, and what would confirm it"
                />
              </div>
            </div>
          )}

          {step === 'confirm' && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Did we get this right? Nothing here is locked in: a lead is editable, and
                qualifying it later is what registers the project.
              </p>
              <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                <Fact
                  label="Told us"
                  value={
                    creatingCustomer
                      ? `${newCustomer.customer_name.trim()} (new)`
                      : (selectedCustomer?.customer_name ?? 'Selected customer')
                  }
                />
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
                    SOURCE_OPTIONS.find((option) => option.value === source)?.label ?? null
                  }
                />
                <Fact
                  label="Rough value"
                  value={estimatedValue.trim() ? `RM ${estimatedValue.trim()}` : null}
                />
              </dl>
            </div>
          )}
        </DialogBody>

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
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            {step === 'confirm' ? (
              <Button type="button" disabled={create.isPending} onClick={submit}>
                Record lead
              </Button>
            ) : (
              <Button
                type="button"
                disabled={!canAdvance}
                onClick={() => setStep(STEPS[stepIndex + 1].id)}
              >
                Next
                <ArrowRight className="size-4" aria-hidden />
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Fact({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="break-words text-sm">
        {value ?? <span className="text-muted-foreground">Not recorded</span>}
      </dd>
    </div>
  );
}
