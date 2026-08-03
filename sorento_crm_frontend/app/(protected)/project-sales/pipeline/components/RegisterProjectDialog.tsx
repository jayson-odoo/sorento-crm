'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
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
import { DateRangePicker } from '@/components/ui/date-range-picker';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  useClashPreview,
  useProjectParties,
  useProjectTemplates,
  useProjectTypes,
  useRegisterProject,
  useTakeoverMutations,
} from '../../_shared/hooks/useProjects';
import type { ClashCandidate } from '../../_shared/types/project.types';
import { ClashWarningPanel } from './ClashWarningPanel';

/**
 * Registration: claim a development before spending time on it.
 *
 * The form asks for the fewest decisions that make the claim meaningful. Only
 * developer and title decide identity, so those come first and the clash check runs
 * against them live; everything else is knowable later and demanding it up front is
 * how a registration screen becomes something people put off until after they have
 * already started working the project.
 */
export function RegisterProjectDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const register = useRegisterProject();

  const [title, setTitle] = React.useState('');
  const [developerId, setDeveloperId] = React.useState('');
  const [typeId, setTypeId] = React.useState('');
  const [templateId, setTemplateId] = React.useState('');
  const [registeredCompany, setRegisteredCompany] = React.useState('');
  const [location, setLocation] = React.useState('');
  const [architectId, setArchitectId] = React.useState('');
  const [mainContractorId, setMainContractorId] = React.useState('');
  const [estimatedValue, setEstimatedValue] = React.useState('');
  const [launchDate, setLaunchDate] = React.useState('');
  const [deliveryFrom, setDeliveryFrom] = React.useState('');
  const [deliveryTo, setDeliveryTo] = React.useState('');

  const [joinTarget, setJoinTarget] = React.useState<{
    candidate: ClashCandidate;
    kind: 'join' | 'dispute';
  } | null>(null);

  const developers = useProjectParties({ party_type: 'developer', limit: 200 });
  const architects = useProjectParties({ party_type: 'architect', limit: 200 });
  const contractors = useProjectParties({ party_type: 'main_contractor', limit: 200 });
  const types = useProjectTypes();
  const templates = useProjectTemplates(typeId || undefined);
  const clash = useClashPreview(title, developerId || null);

  const selectedType = types.data?.find((type) => type.id === typeId);
  // A property development infers its delivery window from the launch date plus a
  // configurable lag; anything else has to state the window, because a hotel
  // refurbishment has no launch date to count from (AC-C4).
  const derivesDelivery = selectedType?.derives_delivery_from_launch ?? false;

  const reset = React.useCallback(() => {
    setTitle('');
    setDeveloperId('');
    setTypeId('');
    setTemplateId('');
    setRegisteredCompany('');
    setLocation('');
    setArchitectId('');
    setMainContractorId('');
    setEstimatedValue('');
    setLaunchDate('');
    setDeliveryFrom('');
    setDeliveryTo('');
    setJoinTarget(null);
  }, []);

  React.useEffect(() => {
    // Clearing the type must clear the template too, or a stale template from the
    // previous type is submitted and the project gets roles it should not offer.
    setTemplateId('');
  }, [typeId]);

  const wouldBlock = clash.data?.would_block ?? false;
  const canSubmit = title.trim().length > 0 && !wouldBlock && !register.isPending;

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    const project = await register.mutateAsync({
      title: title.trim(),
      developer_party_id: developerId || null,
      type_id: typeId || null,
      template_id: templateId || null,
      registered_company_name: registeredCompany.trim() || null,
      location: location.trim() || null,
      architect_party_id: architectId || null,
      main_contractor_party_id: mainContractorId || null,
      estimated_sales_value: estimatedValue.trim() || null,
      launch_date: launchDate || null,
      expected_delivery_from: deliveryFrom || null,
      expected_delivery_to: deliveryTo || null,
    });
    reset();
    onOpenChange(false);
    router.push(`/project-sales/${project.id}`);
  }

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) reset();
          onOpenChange(next);
        }}
      >
        {/* max-h + scrolling body so the submit button stays reachable at phone width */}
        <DialogContent className="max-h-[92vh] w-full max-w-2xl overflow-hidden">
          <DialogHeader>
            <DialogTitle>Register a project</DialogTitle>
            <DialogDescription>
              Claim the development first.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSubmit} className="flex min-h-0 flex-col">
            <DialogBody className="max-h-[calc(92vh-11rem)] space-y-5 overflow-y-auto">
              <fieldset className="space-y-4">
                <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Who and what
                </legend>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="project-developer">Developer</Label>
                    <SearchableSelect
                      id="project-developer"
                      value={developerId}
                      onChange={setDeveloperId}
                      clearable
                      options={(developers.data?.data ?? []).map((party) => ({
                        value: party.id,
                        label: party.name,
                        description: party.registration_no ?? undefined,
                      }))}
                      placeholder="Search developers"
                      emptyMessage="No developers yet. Add one under Parties"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="project-type">Project type</Label>
                    <SearchableSelect
                      id="project-type"
                      value={typeId}
                      onChange={setTypeId}
                      clearable
                      options={(types.data ?? []).map((type) => ({
                        value: type.id,
                        label: type.name,
                      }))}
                      placeholder="Select a type"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="project-title">
                    Project title <span className="text-destructive">*</span>
                  </Label>
                  <Input
                    id="project-title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="e.g. Setia Alam Phase 3B"
                    autoComplete="off"
                    required
                  />
                </div>

                <ClashWarningPanel
                  candidates={clash.data?.candidates ?? []}
                  isLoading={clash.isFetching}
                  onRequestJoin={(candidate) => setJoinTarget({ candidate, kind: 'join' })}
                  onDispute={(candidate) => setJoinTarget({ candidate, kind: 'dispute' })}
                />

                {typeId && (
                  <div className="space-y-1.5">
                    <Label htmlFor="project-template">Template</Label>
                    <SearchableSelect
                      id="project-template"
                      value={templateId}
                      onChange={setTemplateId}
                      clearable
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
              </fieldset>

              <fieldset className="space-y-4 border-t border-border pt-5">
                <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Details (optional)
                </legend>

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
                  <div className="space-y-1.5">
                    <Label htmlFor="project-architect">Architect</Label>
                    <SearchableSelect
                      id="project-architect"
                      value={architectId}
                      onChange={setArchitectId}
                      clearable
                      options={(architects.data?.data ?? []).map((party) => ({
                        value: party.id,
                        label: party.name,
                      }))}
                      placeholder="Search architects"
                      emptyMessage="No architects yet. Add one under Parties"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="project-contractor">Main contractor</Label>
                    <SearchableSelect
                      id="project-contractor"
                      value={mainContractorId}
                      onChange={setMainContractorId}
                      clearable
                      options={(contractors.data?.data ?? []).map((party) => ({
                        value: party.id,
                        label: party.name,
                      }))}
                      placeholder="Search main contractors"
                      emptyMessage="No main contractors yet. Add one under Parties"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="project-value">Estimated sales value (RM)</Label>
                    <Input
                      id="project-value"
                      type="number"
                      min="0"
                      step="0.01"
                      inputMode="decimal"
                      value={estimatedValue}
                      onChange={(event) => setEstimatedValue(event.target.value)}
                      placeholder="0.00"
                    />
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
                      <p className="text-xs text-muted-foreground">
                        Expected delivery is derived from this plus the configured lag.
                      </p>
                    </div>
                  ) : (
                    // One range, one control: two date fields let "to" land before
                    // "from" and stop reading as a single fact once they wrap apart.
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
                </div>
              </fieldset>
            </DialogBody>

            <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  reset();
                  onOpenChange(false);
                }}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {register.isPending && (
                  <Loader2 className="size-4 animate-spin" aria-hidden />
                )}
                {wouldBlock ? 'Blocked by an existing project' : 'Register project'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {joinTarget && (
        <TakeoverRequestDialog
          candidate={joinTarget.candidate}
          kind={joinTarget.kind}
          onDone={() => setJoinTarget(null)}
        />
      )}
    </>
  );
}

/**
 * The way out of a hard block.
 *
 * Without a recourse path, blocking produces defensive land-grabbing and pushes the
 * argument back into WhatsApp, which is the problem the module was built to solve.
 * The reason is mandatory because the owner or manager has to decide on something.
 */
function TakeoverRequestDialog({
  candidate,
  kind,
  onDone,
}: {
  candidate: ClashCandidate;
  kind: 'join' | 'dispute';
  onDone: () => void;
}) {
  const [reason, setReason] = React.useState('');
  const { request } = useTakeoverMutations(candidate.project_id);

  const isJoin = kind === 'join';

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isJoin ? 'Ask to join this project' : 'Dispute this project'}</DialogTitle>
          <DialogDescription>
            {isJoin
              ? `${candidate.owner_name ?? 'The owner'} decides. If they approve, you get edit rights on ${candidate.project_code}.`
              : `A sales manager decides. If they agree, ${candidate.project_code} moves to you and ${candidate.owner_name ?? 'the current owner'} stays on as a collaborator.`}
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            if (!reason.trim()) return;
            await request.mutateAsync({ kind, reason: reason.trim() });
            onDone();
          }}
        >
          <DialogBody className="max-h-[60vh] space-y-3 overflow-y-auto">
            <div className="rounded-md border border-border bg-muted/40 p-2.5 text-sm">
              <span className="text-sm text-muted-foreground">
                {candidate.project_code}
              </span>
              <p className="font-medium">{candidate.title}</p>
              <p className="text-xs text-muted-foreground">
                Owner: {candidate.owner_name ?? 'Unassigned'}
                {candidate.status_label ? ` · ${candidate.status_label}` : ''}
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="takeover-reason">
                Reason <span className="text-destructive">*</span>
              </Label>
              <Textarea
                id="takeover-reason"
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                rows={4}
                placeholder={
                  isJoin
                    ? 'e.g. I hold the specifying architect relationship on this tender.'
                    : 'e.g. I registered this with the developer in March and have the meeting notes.'
                }
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
              {isJoin ? 'Send request' : 'Raise dispute'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
