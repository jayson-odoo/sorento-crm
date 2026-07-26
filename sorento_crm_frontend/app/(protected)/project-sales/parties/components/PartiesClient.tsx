'use client';

import * as React from 'react';
import { Pencil, Plus, Search, Trash2, X } from 'lucide-react';
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
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { usePartyMutations, useProjectParties } from '../../_shared/hooks/useProjects';
import type { PartyType, ProjectParty } from '../../_shared/types/project.types';

const PARTY_TYPE_OPTIONS: { value: PartyType; label: string; hint: string }[] = [
  {
    value: 'developer',
    label: 'Developer',
    hint: 'Owns the development. Identity for the registration lock.',
  },
  {
    value: 'architect',
    label: 'Architect',
    hint: 'Specifies products. Never buys, which is why they are not a customer.',
  },
  { value: 'main_contractor', label: 'Main contractor', hint: 'Builds it.' },
  { value: 'trading_house', label: 'Trading house', hint: 'Buys on the project’s behalf.' },
  { value: 'consultant', label: 'Consultant', hint: 'QS, M&E, ID and similar.' },
];

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  PARTY_TYPE_OPTIONS.map((option) => [option.value, option.label]),
);

/**
 * The organisation master.
 *
 * One row per firm, reused across projects. That reuse is the entire value: "which
 * architects should we prioritise visiting" is only answerable when Veritas Architects
 * is one record rather than four spellings, which is why the project count sits on
 * every card and why same-name duplicates are refused rather than merged.
 */
export function PartiesClient() {
  const [search, setSearch] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [typeFilter, setTypeFilter] = React.useState('');
  const [editing, setEditing] = React.useState<ProjectParty | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [deleting, setDeleting] = React.useState<ProjectParty | null>(null);

  const { remove } = usePartyMutations();

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const parties = useProjectParties({
    query: debounced || undefined,
    party_type: typeFilter || undefined,
    include_inactive: true,
    limit: 200,
  });

  // Memoised so the grouping below is not rebuilt on every render by a fresh []
  // literal from the ?? fallback.
  const rows = React.useMemo(() => parties.data?.data ?? [], [parties.data]);
  const grouped = React.useMemo(() => {
    const map = new Map<string, ProjectParty[]>();
    PARTY_TYPE_OPTIONS.forEach((option) => map.set(option.value, []));
    rows.forEach((party) => {
      if (!map.has(party.party_type)) map.set(party.party_type, []);
      map.get(party.party_type)!.push(party);
    });
    return map;
  }, [rows]);

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Parties</h1>
          <p className="text-sm text-muted-foreground">
            Developers, architects, contractors and consultants, reused across projects.
          </p>
        </div>
        <Button type="button" onClick={() => setCreating(true)}>
          <Plus className="size-4" aria-hidden />
          Add party
        </Button>
      </header>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="relative flex-1">
          <Search
            className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            placeholder="Search by name…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="ps-9"
            aria-label="Search parties"
          />
          {search && (
            <Button
              mode="icon"
              variant="dim"
              className="absolute end-1.5 top-1/2 h-6 w-6 -translate-y-1/2"
              onClick={() => setSearch('')}
              aria-label="Clear search"
            >
              <X />
            </Button>
          )}
        </div>
        <div className="w-full space-y-1.5 sm:w-56">
          <Label htmlFor="party-type-filter" className="text-xs">
            Type
          </Label>
          <SearchableSelect
            id="party-type-filter"
            value={typeFilter}
            onChange={setTypeFilter}
            clearable
            size="sm"
            options={PARTY_TYPE_OPTIONS.map((option) => ({
              value: option.value,
              label: option.label,
            }))}
            placeholder="All types"
          />
        </div>
      </div>

      {parties.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <h3 className="text-sm font-semibold">
            {debounced || typeFilter ? 'No parties match' : 'No parties yet'}
          </h3>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {debounced || typeFilter
              ? 'Clear the filters to see everything.'
              : 'Add the developer you are about to register a project with. Every project references one.'}
          </p>
          {!debounced && !typeFilter && (
            <Button type="button" className="mt-4" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden />
              Add the first party
            </Button>
          )}
        </div>
      ) : (
        // Grouped by type rather than one flat table: the question is almost always
        // "which architects do we know", not "list every organisation".
        <div className="space-y-6">
          {PARTY_TYPE_OPTIONS.filter(
            (option) => (grouped.get(option.value) ?? []).length > 0,
          ).map((option) => (
            <section key={option.value} className="space-y-2">
              <div className="flex flex-wrap items-baseline gap-2">
                <h2 className="text-sm font-semibold">{option.label}</h2>
                <Badge variant="secondary">{grouped.get(option.value)!.length}</Badge>
                <p className="text-xs text-muted-foreground">{option.hint}</p>
              </div>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {grouped.get(option.value)!.map((party) => (
                  <li
                    key={party.id}
                    className="rounded-lg border border-border bg-background p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 space-y-1">
                        <p className="truncate font-medium" title={party.name}>
                          {party.name}
                        </p>
                        {party.registration_no && (
                          <p className="truncate text-xs text-muted-foreground">
                            {party.registration_no}
                          </p>
                        )}
                        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                          <Badge variant="outline" className="text-[11px]">
                            {party.project_count ?? 0} project
                            {(party.project_count ?? 0) === 1 ? '' : 's'}
                          </Badge>
                          {party.customer_name && (
                            <Badge variant="secondary" className="text-[11px]">
                              Buys as {party.customer_name}
                            </Badge>
                          )}
                          {!party.is_active && (
                            <Badge variant="outline" className="text-[11px]">
                              Inactive
                            </Badge>
                          )}
                        </div>
                        {(party.phone || party.email) && (
                          <p className="truncate pt-0.5 text-xs text-muted-foreground">
                            {[party.phone, party.email].filter(Boolean).join(' · ')}
                          </p>
                        )}
                      </div>
                      <div className="flex shrink-0 gap-1">
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditing(party)}
                          aria-label={`Edit ${party.name}`}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                        <Button
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleting(party)}
                          aria-label={`Delete ${party.name}`}
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </Button>
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {(creating || editing) && (
        <PartyFormDialog
          party={editing}
          onDone={() => {
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        onOpenChange={(next) => !next && setDeleting(null)}
        title="Confirm delete"
        description={
          deleting
            ? `Delete "${deleting.name}"? This action cannot be undone. A party used as a developer on any project cannot be deleted, so deactivate it instead.`
            : ''
        }
        onDelete={async () => {
          if (!deleting) return;
          await remove.mutateAsync(deleting.id);
        }}
        onSuccess={() => setDeleting(null)}
        successMessage="Party deleted"
      />
    </div>
  );
}

function PartyFormDialog({
  party,
  onDone,
}: {
  party: ProjectParty | null;
  onDone: () => void;
}) {
  const { create, update } = usePartyMutations();
  const [partyType, setPartyType] = React.useState<string>(party?.party_type ?? 'developer');
  const [name, setName] = React.useState(party?.name ?? '');
  const [registrationNo, setRegistrationNo] = React.useState(party?.registration_no ?? '');
  const [phone, setPhone] = React.useState(party?.phone ?? '');
  const [email, setEmail] = React.useState(party?.email ?? '');
  const [address, setAddress] = React.useState(party?.address ?? '');
  const [notes, setNotes] = React.useState(party?.notes ?? '');
  const [isActive, setIsActive] = React.useState(party?.is_active ?? true);

  const isEdit = Boolean(party);
  const pending = create.isPending || update.isPending;
  const selectedHint = PARTY_TYPE_OPTIONS.find((option) => option.value === partyType)?.hint;

  return (
    <Dialog open onOpenChange={(next) => !next && onDone()}>
      <DialogContent className="max-h-[92vh] w-full max-w-lg overflow-hidden">
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${party?.name}` : 'Add a party'}</DialogTitle>
          <DialogDescription>
            One record per organisation. Reuse it on every project they appear on.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={async (event) => {
            event.preventDefault();
            const body = {
              party_type: partyType as PartyType,
              name: name.trim(),
              registration_no: registrationNo.trim() || null,
              phone: phone.trim() || null,
              email: email.trim() || null,
              address: address.trim() || null,
              notes: notes.trim() || null,
              is_active: isActive,
            };
            if (party) {
              await update.mutateAsync({ id: party.id, body });
            } else {
              await create.mutateAsync(body);
            }
            onDone();
          }}
        >
          <DialogBody className="max-h-[65vh] space-y-4 overflow-y-auto">
            <div className="space-y-1.5">
              <Label htmlFor="party-type">
                Type <span className="text-destructive">*</span>
              </Label>
              <SearchableSelect
                id="party-type"
                value={partyType}
                onChange={setPartyType}
                options={PARTY_TYPE_OPTIONS.map((option) => ({
                  value: option.value,
                  label: option.label,
                }))}
                placeholder="Select a type"
              />
              {selectedHint && (
                <p className="text-xs text-muted-foreground">{selectedHint}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="party-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="party-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. SP Setia Berhad"
                required
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="party-reg">Registration no.</Label>
                <Input
                  id="party-reg"
                  value={registrationNo}
                  onChange={(event) => setRegistrationNo(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="party-phone">Phone</Label>
                <Input
                  id="party-phone"
                  value={phone}
                  onChange={(event) => setPhone(event.target.value)}
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="party-email">Email</Label>
                <Input
                  id="party-email"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="party-address">Address</Label>
              <Textarea
                id="party-address"
                value={address}
                onChange={(event) => setAddress(event.target.value)}
                rows={2}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="party-notes">Notes</Label>
              <Textarea
                id="party-notes"
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={2}
                placeholder="Who to speak to, what they specify, past history"
              />
            </div>

            {isEdit && (
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={isActive}
                  onChange={(event) => setIsActive(event.target.checked)}
                  className="size-4 rounded border-border"
                />
                Active. Inactive parties stay on their projects but stop appearing in
                pickers
              </label>
            )}
          </DialogBody>

          <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
            <Button type="button" variant="outline" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || pending}>
              {isEdit ? 'Save changes' : 'Add party'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export { TYPE_LABEL };
