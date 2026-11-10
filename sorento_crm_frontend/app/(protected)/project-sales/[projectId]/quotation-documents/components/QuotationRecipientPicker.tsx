'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  usePartiesOnProject,
  usePartyContacts,
  usePartyMutations,
  usePartyRoleLabel,
  usePartyRoles,
} from '../../../_shared/hooks/useProjects';
import { listParties } from '../../../_shared/services/projectService';
import type { QuotationDocumentBody } from '../../../_shared/services/quotationDocumentService';
import { PARTY_ROLE_DEVELOPER } from '../../../_shared/lib/partyRoles';
import { PartyContactsDialog } from '../../../_shared/components/PartyContactsDialog';
import type { PartyContact } from '../../../_shared/types/project.types';

/** What the picker knows about a party it offered, to autoload the TO block from it. */
type KnownParty = {
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
 * The proposal / quotation "To" chosen from the parties (PROJECT-PARTY-ROLES PR 2, owner addition
 * 2, 10 Nov, mock v4 screen 4). The project's parties come first; any other party of the company,
 * or a new one, can be picked and is linked to the project on Save in the role picked here.
 * Picking autoloads name, address (the party's, else the project's site address), phone and email;
 * every field stays editable. Fixed once revision A is issued (owner Q5 a).
 */
export function QuotationRecipientPicker({
  projectId,
  siteAddress,
  value,
  locked,
  onChange,
}: {
  projectId: string;
  /** The project's site address: the fallback for a party with none (owner Q7 a). */
  siteAddress?: string | null;
  /** The header as staged: party, role, name. */
  value: QuotationDocumentBody;
  locked: boolean;
  onChange: (patch: QuotationDocumentBody) => void;
}) {
  const onProject = usePartiesOnProject(projectId);
  const roles = usePartyRoles();
  const roleLabel = usePartyRoleLabel();
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

  const partyId = value.recipient_party_id ?? '';
  const pickedRow = onProjectRows.find((row) => row.party_id === partyId);
  const picked = partyId ? (pickedRow ? fromProject(pickedRow) : known.current[partyId]) : undefined;
  const pickedRole = partyId ? roleOnProject.get(partyId) : undefined;
  const onProjectIds = new Set(onProjectRows.map((row) => row.party_id));
  const needsRole = Boolean(partyId) && onProject.isSuccess && !onProjectIds.has(partyId);

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
        .map((party) => ({ value: party.id, label: party.name, group: 'Other parties' }));
      return [...mine, ...others];
    },
    [onProjectRows],
  );

  /** Every role a party not on the project may be added in: active, developer excepted, and a
   * one-party role only while the project has nobody in it. */
  const roleOptions = (roles.data ?? [])
    .filter(
      (role) =>
        role.is_active &&
        role.value !== PARTY_ROLE_DEVELOPER &&
        (role.allows_many || !onProjectRows.some((row) => row.role === role.value)),
    )
    .map((role) => ({ value: role.value, label: role.label }));

  function pick(party: KnownParty | null) {
    if (!party) {
      onChange({ recipient_party_id: null, recipient_role: null, attn_contact_ids: [] });
      return;
    }
    const role =
      roleOnProject.get(party.id) ??
      (roleOptions.some((r) => r.value === party.partyType) ? party.partyType : null);
    // Unknown details go as null: the save leaves them out and the server fills them from the
    // party, so a guess (the site address) never stands in for the party's own address.
    onChange({
      recipient_party_id: party.id,
      recipient_role: role,
      recipient_name_snapshot: party.name,
      recipient_address_snapshot: party.detailed ? party.address || siteAddress || null : null,
      recipient_phone_snapshot: party.detailed ? party.phone || null : null,
      recipient_email_snapshot: party.detailed ? party.email || null : null,
      recipient_fax_snapshot: party.detailed ? party.fax || null : null,
      attn_name: null,
      attn_contact_ids: [],
    });
  }

  if (locked) {
    return (
      <div className="flex min-w-0 items-center gap-2 text-sm">
        <span className="truncate font-medium" title={value.recipient_name_snapshot ?? ''}>
          {value.recipient_name_snapshot ?? '-'}
        </span>
        {pickedRole && <Badge variant="secondary">{roleLabel(pickedRole)}</Badge>}
      </div>
    );
  }

  return (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor="quotation-recipient-party">Party</Label>
      <SearchableSelect
        id="quotation-recipient-party"
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
          partyId
            ? {
                value: partyId,
                label: picked?.name ?? value.recipient_name_snapshot ?? '',
              }
            : undefined
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
      {needsRole && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-primary">
          <span>Not on this project yet. Add as</span>
          <div className="w-48">
            <SearchableSelect
              id="quotation-recipient-role"
              value={value.recipient_role ?? ''}
              onChange={(role) => {
                onChange({ recipient_role: role || null });
                // A party made here takes the role it is first added in as its usual role
                // (card rule B), not whichever role the list happened to start with.
                if (role && createdHere.current.has(partyId)) {
                  updateParty.mutate({ id: partyId, body: { party_type: role } });
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

/**
 * "Choose contacts" next to Attn: the registration form's contacts popup for the picked party.
 * The ticked names fill Attn joined with " & " (real sample: "MS. ANNE CHEW & MS IIYANA"); phone
 * and email follow the first of them, else the party's own. Attn stays editable.
 */
export function QuotationAttnChooser({
  value,
  partyName,
  partyPhone,
  partyEmail,
  locked,
  autoPick = false,
  onChange,
}: {
  value: QuotationDocumentBody;
  partyName: string;
  partyPhone?: string | null;
  partyEmail?: string | null;
  locked: boolean;
  /** A party just picked: its only contact becomes the Attn without opening the popup. */
  autoPick?: boolean;
  onChange: (patch: QuotationDocumentBody) => void;
}) {
  const partyId = value.recipient_party_id ?? '';
  const canEdit = useHasPermission('projects.parties.edit');
  const contacts = usePartyContacts(partyId || null);
  const [open, setOpen] = React.useState(false);
  // What the party pick loaded, held per party so re-choosing contacts never loses it.
  const partyFallback = React.useRef<{ party: string; phone?: string | null; email?: string | null }>({
    party: '',
  });
  if (partyFallback.current.party !== partyId) {
    partyFallback.current = {
      party: partyId,
      phone: value.recipient_phone_snapshot,
      email: value.recipient_email_snapshot,
    };
  }
  // Owner hand test 10 Nov: "if only got 1 contact then should just default to it". Once per party.
  const autoDone = React.useRef<string | null>(null);
  const only = (contacts.data ?? []).filter((c) => c.is_active !== false);
  const shouldAuto =
    autoPick &&
    !locked &&
    Boolean(partyId) &&
    autoDone.current !== partyId &&
    contacts.isSuccess &&
    only.length === 1 &&
    (value.attn_contact_ids ?? []).length === 0 &&
    !value.attn_name;
  React.useEffect(() => {
    if (!shouldAuto) return;
    autoDone.current = partyId;
    void apply([only[0].id]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldAuto]);
  if (!partyId || locked) return null;

  async function apply(ids: string[]) {
    // A contact added inside the popup may not be in the cached list yet: read it fresh then.
    let list = contacts.data ?? [];
    if (ids.some((id) => !list.some((c) => c.id === id))) {
      list = (await contacts.refetch()).data ?? list;
    }
    const rows = ids
      .map((id) => list.find((c) => c.id === id))
      .filter((c): c is PartyContact => Boolean(c));
    const first = rows[0];
    onChange({
      attn_contact_ids: ids,
      attn_name: rows.map((c) => c.name).join(' & ') || null,
      // A contact without one keeps the party's own, which the pick loaded into the block.
      recipient_phone_snapshot:
        first?.phone || partyPhone || partyFallback.current.phone || null,
      recipient_email_snapshot:
        first?.email || partyEmail || partyFallback.current.email || null,
    });
  }

  return (
    <>
      <Button
        type="button"
        variant="link"
        size="sm"
        className="h-auto p-0 text-xs"
        onClick={() => setOpen(true)}
      >
        Choose contacts
      </Button>
      {open && (
        <PartyContactsDialog
          title={(name) => `Attn at ${name}`}
          parties={[{ partyId, name: partyName }]}
          picks={{ [partyId]: value.attn_contact_ids ?? [] }}
          canEdit={canEdit}
          onSave={(next) => void apply(next[partyId] ?? [])}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
