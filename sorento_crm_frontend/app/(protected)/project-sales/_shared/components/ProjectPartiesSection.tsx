'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useFetchPartyOptions } from '../hooks/useProjects';
import { PARTY_ROLE_DEVELOPER } from '../lib/partyRoles';
import type { PartyRole } from '../types/project.types';
import { PartyContactsDialog } from './PartyContactsDialog';

export type PartyPick = { value: string; label: string; description?: string };

/**
 * The registration form's "Parties and contacts" body (PROJECT-PARTY-ROLES, mock v4 screen 1):
 * one line per role of the editable list, in its order, the developer excepted (a fixed field on
 * page 1). A "many parties" role gets a multi picker. Once a party is picked, a small link next to
 * the label opens the contacts popup for that role's parties.
 */
export function ProjectPartiesSection({
  roles,
  developer,
  picks,
  onPicksChange,
  contactPicks,
  onContactPicksChange,
  fixedContacts,
  canCreateParty,
  createParty,
  typedByRole,
}: {
  roles: PartyRole[];
  /** The developer picked on page 1: shown read-only here so its contacts can be picked too. */
  developer?: PartyPick;
  /** Picked parties per role key. */
  picks: Record<string, PartyPick[]>;
  onPicksChange: (role: string, next: PartyPick[]) => void;
  /** Newly picked contact ids per party id. */
  contactPicks: Record<string, string[]>;
  onContactPicksChange: (next: Record<string, string[]>) => void;
  /** Contact ids already the project's stakeholders, per party id (edit). */
  fixedContacts?: Record<string, string[]>;
  canCreateParty: boolean;
  /** Creates a party from the typed name in the role; resolves null when it failed (toasted). */
  createParty: (role: string, name: string) => Promise<PartyPick | null>;
  /** What a portal registration typed for a role, shown until a party is picked. */
  typedByRole?: Record<string, string | null | undefined>;
}) {
  const [contactsRole, setContactsRole] = React.useState<string | null>(null);
  const shown = roles.filter(
    (role) =>
      role.value !== PARTY_ROLE_DEVELOPER && (role.is_active || (picks[role.value] ?? []).length > 0),
  );
  // The developer is not a link role, so its popup reads the page 1 pick, not `picks`.
  const dialogParties: PartyPick[] =
    contactsRole === PARTY_ROLE_DEVELOPER
      ? developer
        ? [developer]
        : []
      : (shown.find((role) => role.value === contactsRole) && picks[contactsRole ?? '']) || [];
  const developerLabel =
    roles.find((role) => role.value === PARTY_ROLE_DEVELOPER)?.label ?? 'Developer';
  const developerCount = developer ? countContacts([developer], contactPicks, fixedContacts) : 0;

  return (
    <>
      <div className="grid gap-4 sm:grid-cols-2">
        {developer && (
          <div className="min-w-0 space-y-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-sm font-medium">{developerLabel}</span>
              <ContactsLink count={developerCount} onClick={() => setContactsRole(PARTY_ROLE_DEVELOPER)} />
            </div>
            <p className="truncate py-2 text-sm" title={developer.label}>
              {developer.label}
            </p>
          </div>
        )}
        {shown.map((role) => (
          <PartyRoleField
            key={role.value}
            role={role}
            picks={picks[role.value] ?? []}
            onChange={(next) => onPicksChange(role.value, next)}
            contactCount={countContacts(picks[role.value] ?? [], contactPicks, fixedContacts)}
            onOpenContacts={() => setContactsRole(role.value)}
            canCreateParty={canCreateParty}
            createParty={async (name) => {
              const created = await createParty(role.value, name);
              // A party made on the spot has nobody yet: its contacts popup opens straight away.
              if (created) setContactsRole(role.value);
              return created;
            }}
            typed={typedByRole?.[role.value]}
          />
        ))}
      </div>
      {dialogParties.length > 0 && (
        <PartyContactsDialog
          parties={dialogParties.map((p) => ({ partyId: p.value, name: p.label }))}
          picks={contactPicks}
          fixed={fixedContacts}
          canEdit={canCreateParty}
          onSave={(next) => onContactPicksChange({ ...contactPicks, ...next })}
          onClose={() => setContactsRole(null)}
        />
      )}
    </>
  );
}

function countContacts(
  parties: PartyPick[],
  contactPicks: Record<string, string[]>,
  fixed?: Record<string, string[]>,
): number {
  const ids = new Set<string>();
  for (const party of parties) {
    for (const id of fixed?.[party.value] ?? []) ids.add(id);
    for (const id of contactPicks[party.value] ?? []) ids.add(id);
  }
  return ids.size;
}

/** "2 contacts" / "Add contacts" next to a role's label: opens that role's contacts popup. */
function ContactsLink({ count, onClick }: { count: number; onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="link"
      size="sm"
      className={`h-auto shrink-0 p-0 text-xs ${count ? '' : 'text-muted-foreground'}`}
      onClick={onClick}
    >
      {count === 0 ? 'Add contacts' : count === 1 ? '1 contact' : `${count} contacts`}
    </Button>
  );
}

function PartyRoleField({
  role,
  picks,
  onChange,
  contactCount,
  onOpenContacts,
  canCreateParty,
  createParty,
  typed,
}: {
  role: PartyRole;
  picks: PartyPick[];
  onChange: (next: PartyPick[]) => void;
  contactCount: number;
  onOpenContacts: () => void;
  canCreateParty: boolean;
  createParty: (name: string) => Promise<PartyPick | null>;
  typed?: string | null;
}) {
  const fetchOptions = useFetchPartyOptions(role.value);
  const seen = React.useRef<Record<string, PartyPick>>({});
  const id = `project-party-${role.value.replace(/_/g, '-')}`;
  // A role switched to "one" that already holds several keeps the multi picker for them.
  const many = role.allows_many || picks.length > 1;
  const create =
    canCreateParty && role.is_active
      ? {
          label: (query: string) => (
            <span>
              Add &ldquo;{query}&rdquo; as a new party
            </span>
          ),
          onCreate: async (query: string) => {
            const created = await createParty(query.trim());
            if (created) {
              seen.current[created.value] = created;
              onChange(many ? [...picks, created] : [created]);
            }
          },
        }
      : undefined;
  // An inactive role still on this project: keep and clear only, no search for a new pick.
  const fetchForRole = role.is_active ? fetchOptions : async () => [];

  return (
    <div className="min-w-0 space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id} className="flex min-w-0 items-center gap-2">
          <span className="truncate" title={role.label}>
            {role.label}
          </span>
          {!role.is_active && <Badge variant="secondary">Inactive</Badge>}
        </Label>
        {picks.length > 0 && <ContactsLink count={contactCount} onClick={onOpenContacts} />}
      </div>
      {many ? (
        <SearchableMultiSelect
          id={id}
          value={picks.map((p) => p.value)}
          onChange={(ids) =>
            onChange(
              ids.map(
                (value) =>
                  picks.find((p) => p.value === value) ?? seen.current[value] ?? { value, label: value },
              ),
            )
          }
          fetchOptions={async (query: string) => {
            const rows = await fetchForRole(query);
            for (const row of rows) seen.current[row.value] = row;
            return rows;
          }}
          selectedOptions={picks}
          clearable
          placeholder="Search parties"
          emptyMessage="No parties found"
          createOption={
            create ? { label: create.label, onCreate: (q: string) => void create.onCreate(q) } : undefined
          }
        />
      ) : (
        <SearchableSelect
          id={id}
          value={picks[0]?.value ?? ''}
          onChange={(value) => {
            if (!value) onChange([]);
          }}
          onOptionChange={(option) => onChange(option ? [option] : [])}
          fetchOptions={fetchForRole}
          selectedOption={picks[0]}
          clearable
          placeholder="Search parties"
          emptyMessage="No parties found"
          createOption={create}
        />
      )}
      {typed?.trim() && picks.length === 0 && (
        <p className="text-xs text-muted-foreground">Typed: {typed.trim()}</p>
      )}
    </div>
  );
}
