'use client';

import * as React from 'react';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  usePartiesOnProject,
  usePartyMutations,
  usePartyRoles,
} from '../hooks/useProjects';
import { listParties } from '../services/projectService';
import { PARTY_ROLE_DEVELOPER } from '../lib/partyRoles';

/** What the picker knows about a party it offered, so the caller can autoload from it. */
export type KnownParty = {
  id: string;
  name: string;
  partyType: string;
  address?: string | null;
  phone?: string | null;
  email?: string | null;
  fax?: string | null;
  /** Address / phone / email were read (a names-only search leaves them unknown). */
  detailed: boolean;
};

/**
 * A party chosen for one project: the project's own parties first ("On this project"), any other
 * party of the company below, or a new one. A party not on the project asks for the role it plays;
 * the caller's save links it (PROJECT-PARTY-ROLES PR 2). The one picker behind the proposal "To"
 * (`QuotationRecipientPicker`) and the sample request "Ship to" (SAMPLE-REQUEST-V2 rule 2).
 * Without a project every party is listed and no role is asked.
 */
export function ProjectPartyPicker({
  projectId,
  id,
  roleSelectId,
  label,
  partyId,
  role,
  fallbackName,
  error,
  onPick,
  onRoleChange,
}: {
  projectId?: string | null;
  id: string;
  /** The "Add as" role select's id (default `<id>-role`). */
  roleSelectId?: string;
  label: React.ReactNode;
  partyId: string;
  /** The role staged for a party not on the project yet. */
  role: string | null | undefined;
  /** The name to show for a saved pick before the lists load. */
  fallbackName?: string | null;
  error?: string;
  /** `role` is the role it plays on the project, or the one it would most likely be added in. */
  onPick: (party: KnownParty | null, role: string | null) => void;
  onRoleChange: (role: string | null) => void;
}) {
  const onProject = usePartiesOnProject(projectId || null);
  const roles = usePartyRoles();
  const canCreateParty = useHasPermission('projects.parties.edit');
  const { create: createParty, update: updateParty } = usePartyMutations();
  const known = React.useRef<Record<string, KnownParty>>({});
  // Parties made on the spot here: their usual role follows the role picked under "Add as".
  const createdHere = React.useRef<Set<string>>(new Set());

  const onProjectRows = React.useMemo(() => onProject.data ?? [], [onProject.data]);
  // The role each party plays on THIS project, read fresh each render (a party can leave it).
  const roleOnProject = React.useMemo(() => {
    const out = new Map<string, string>();
    for (const row of onProjectRows) if (!out.has(row.party_id)) out.set(row.party_id, row.role);
    return out;
  }, [onProjectRows]);
  const fromProject = React.useCallback(
    (row: (typeof onProjectRows)[number]): KnownParty => ({
      id: row.party_id,
      name: row.name,
      partyType: row.party_type,
      address: row.address,
      phone: row.phone,
      email: row.email,
      fax: row.fax,
      detailed: true,
    }),
    [],
  );

  const pickedRow = onProjectRows.find((row) => row.party_id === partyId);
  const picked = partyId ? (pickedRow ? fromProject(pickedRow) : known.current[partyId]) : undefined;
  const onProjectIds = new Set(onProjectRows.map((row) => row.party_id));
  const needsRole =
    Boolean(projectId) && Boolean(partyId) && onProject.isSuccess && !onProjectIds.has(partyId);

  const fetchOptions = React.useCallback(
    async (query: string) => {
      const q = query.trim().toLowerCase();
      const mine = onProjectRows
        .filter((row) => !q || row.name.toLowerCase().includes(q))
        .filter((row, i, all) => all.findIndex((r) => r.party_id === row.party_id) === i)
        // One line per option (owner hand test 10 Nov): the group says where it is, no subtitle.
        .map((row) => ({ value: row.party_id, label: row.name, group: 'On this project' }));
      const result = await listParties({ query: query || undefined, limit: 20 });
      const ids = new Set(onProjectRows.map((row) => row.party_id));
      for (const party of result.data) {
        known.current[party.id] = {
          id: party.id,
          name: party.name,
          partyType: party.party_type,
          address: party.address,
          phone: party.phone,
          email: party.email,
          fax: party.fax,
          // A caller without the parties view grant gets names only: nothing else is known.
          detailed: 'address' in party || 'phone' in party,
        };
      }
      const others = result.data
        .filter((party) => !ids.has(party.id))
        .map((party) => ({
          value: party.id,
          label: party.name,
          group: projectId ? 'Other parties' : 'Parties',
        }));
      return [...mine, ...others];
    },
    [onProjectRows, projectId],
  );

  /** Every role a party not on the project may be added in: active, developer excepted, and a
   * one-party role only while the project has nobody in it. */
  const roleOptions = (roles.data ?? [])
    .filter(
      (r) =>
        r.is_active &&
        r.value !== PARTY_ROLE_DEVELOPER &&
        (r.allows_many || !onProjectRows.some((row) => row.role === r.value)),
    )
    .map((r) => ({ value: r.value, label: r.label }));

  function pick(party: KnownParty | null) {
    if (!party) return onPick(null, null);
    const next =
      roleOnProject.get(party.id) ??
      (roleOptions.some((r) => r.value === party.partyType) ? party.partyType : null);
    onPick(party, next);
  }

  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <SearchableSelect
        id={id}
        value={partyId}
        onChange={(next) => {
          if (!next) pick(null);
        }}
        onOptionChange={(option) => {
          if (!option) return pick(null);
          const row = onProjectRows.find((r) => r.party_id === option.value);
          pick(row ? fromProject(row) : (known.current[option.value] ?? null));
        }}
        fetchOptions={fetchOptions}
        selectedOption={
          partyId ? { value: partyId, label: picked?.name ?? fallbackName ?? '' } : undefined
        }
        clearable
        placeholder="Search parties"
        emptyMessage="No parties found"
        createOption={
          canCreateParty
            ? {
                label: (query: string) => <span>Add &ldquo;{query}&rdquo; as a new party</span>,
                onCreate: async (query: string) => {
                  // A new party's usual role is the first role it can be added in; the role
                  // picked below is what it plays on this project.
                  const type = roleOptions[0]?.value;
                  if (!type) return;
                  try {
                    const party = await createParty.mutateAsync({ name: query.trim(), party_type: type });
                    const row: KnownParty = {
                      id: party.id,
                      name: party.name,
                      partyType: party.party_type,
                      address: party.address,
                      phone: party.phone,
                      email: party.email,
                      detailed: true,
                    };
                    known.current[party.id] = row;
                    if (party.party_type === type) createdHere.current.add(party.id);
                    pick(row);
                  } catch {
                    // toasted by the mutation
                  }
                },
              }
            : undefined
        }
      />
      {error && <p className="text-xs text-destructive">{error}</p>}
      {needsRole && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-primary">
          <span>Not on this project yet. Add as</span>
          <div className="w-48">
            <SearchableSelect
              id={roleSelectId ?? `${id}-role`}
              value={role ?? ''}
              onChange={(next) => {
                onRoleChange(next || null);
                // A party made here takes the role it is first added in as its usual role
                // (card rule B), not whichever role the list happened to start with.
                if (next && createdHere.current.has(partyId)) {
                  updateParty.mutate({ id: partyId, body: { party_type: next } });
                }
              }}
              options={roleOptions}
              placeholder="Pick a role"
            />
          </div>
        </div>
      )}
    </div>
  );
}

/** The role a party plays on the project, for a read-only label next to its name. */
export function usePartyRoleOnProject(projectId: string | null | undefined, partyId: string) {
  const onProject = usePartiesOnProject(projectId || null);
  return (onProject.data ?? []).find((row) => row.party_id === partyId)?.role;
}
