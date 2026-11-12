'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useHasPermission } from '@/hooks/usePermissions';
import { usePartyContacts, usePartyRoleLabel } from '../../../_shared/hooks/useProjects';
import type { QuotationDocumentBody } from '../../../_shared/services/quotationDocumentService';
import {
  ProjectPartyPicker,
  usePartyRoleOnProject,
  type KnownParty,
} from '../../../_shared/components/ProjectPartyPicker';
import { PartyContactsDialog } from '../../../_shared/components/PartyContactsDialog';
import type { PartyContact } from '../../../_shared/types/project.types';
import { formatPhone } from '../../../_shared/lib/phoneDisplay';

/**
 * The proposal / quotation "To" chosen from the parties (PROJECT-PARTY-ROLES PR 2, owner addition
 * 2, 10 Nov, mock v4 screen 4), on the shared `ProjectPartyPicker`. The project's parties come
 * first; any other party of the company, or a new one, can be picked and is linked to the project
 * on Save in the role picked here. Picking autoloads name, address (the party's, else the project's
 * site address), phone and email; every field stays editable. Fixed once revision A is issued
 * (owner Q5 a).
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
  const roleLabel = usePartyRoleLabel();
  const partyId = value.recipient_party_id ?? '';
  const pickedRole = usePartyRoleOnProject(projectId, partyId);

  function pick(party: KnownParty | null, role: string | null) {
    if (!party) {
      onChange({ recipient_party_id: null, recipient_role: null, attn_contact_ids: [] });
      return;
    }
    // Unknown details go as null: the save leaves them out and the server fills them from the
    // party, so a guess (the site address) never stands in for the party's own address.
    onChange({
      recipient_party_id: party.id,
      recipient_role: role,
      recipient_name_snapshot: party.name,
      recipient_address_snapshot: party.detailed ? party.address || siteAddress || null : null,
      recipient_phone_snapshot: party.detailed ? formatPhone(party.phone) || null : null,
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
    <ProjectPartyPicker
      projectId={projectId}
      id="quotation-recipient-party"
      roleSelectId="quotation-recipient-role"
      label="Party"
      partyId={partyId}
      role={value.recipient_role}
      fallbackName={value.recipient_name_snapshot}
      onPick={pick}
      onRoleChange={(role) => onChange({ recipient_role: role })}
    />
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
  title = (name: string) => `Attn at ${name}`,
  onChange,
}: {
  value: QuotationDocumentBody;
  partyName: string;
  partyPhone?: string | null;
  partyEmail?: string | null;
  locked: boolean;
  /** A party just picked: its only contact becomes the Attn without opening the popup. */
  autoPick?: boolean;
  /** The popup's title; the sample request's Contact person reuses this chooser (SAMPLE-REQUEST-V2). */
  title?: (partyName: string) => string;
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
  // Owner hand test 10 Nov: "if only got 1 contact then should just default to it", on EVERY
  // selection of a party (re-test: switching away and back must default again). Once per selection.
  const autoDone = React.useRef<string | null>(null);
  const shownParty = React.useRef(partyId);
  const [selected, setSelected] = React.useState(false);
  if (shownParty.current !== partyId) {
    shownParty.current = partyId;
    autoDone.current = null;
    if (!selected) setSelected(true);
  }
  const only = (contacts.data ?? []).filter((c) => c.is_active !== false);
  const shouldAuto =
    (autoPick || selected) &&
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

  /** `keep`: Attn text that names no contact (typed, or a contact renamed since), kept after. */
  async function apply(ids: string[], keep: string[] = []) {
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
      attn_name: [...rows.map((c) => c.name), ...keep].join(' & ') || null,
      // A contact without one keeps the party's own, which the pick loaded into the block.
      recipient_phone_snapshot:
        formatPhone(first?.phone || partyPhone || partyFallback.current.phone) || null,
      recipient_email_snapshot:
        first?.email || partyEmail || partyFallback.current.email || null,
    });
  }

  /**
   * What the Attn already says, read when the popup opens: the contacts it names (ticked) and any
   * text that names no contact (kept on Done). A saved document keeps only the Attn text ("A & B"),
   * not the ids, so the text is matched to the party's contacts, each contact at most once; ids
   * picked earlier in this session are used only while the text still reads exactly their names.
   * Without this an edit opened with nothing ticked and Done blanked Attn (crew pass, 11 Nov).
   */
  function readAttn(): { ids: string[]; unmatched: string[] } {
    const rows = (contacts.data ?? []).filter((c) => c.is_active !== false);
    const fold = (text: string) => text.trim().toLowerCase();
    const text = value.attn_name ?? '';
    const picked = value.attn_contact_ids ?? [];
    if (picked.length > 0) {
      const names = picked.map((id) => rows.find((c) => c.id === id)?.name ?? '');
      if (fold(names.join(' & ')) === fold(text)) return { ids: picked, unmatched: [] };
    }
    const ids: string[] = [];
    const unmatched: string[] = [];
    for (const part of text.split('&').map((t) => t.trim()).filter(Boolean)) {
      const hit = rows.find((c) => fold(c.name) === fold(part) && !ids.includes(c.id));
      if (hit) ids.push(hit.id);
      else unmatched.push(part);
    }
    return { ids, unmatched };
  }
  const attn = open && !contacts.isLoading ? readAttn() : { ids: [], unmatched: [] };

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
      {/* Mounted once the contacts have answered: the popup takes its ticks when it opens. */}
      {open && !contacts.isLoading && (
        <PartyContactsDialog
          title={title}
          parties={[{ partyId, name: partyName }]}
          picks={{ [partyId]: attn.ids }}
          canEdit={canEdit}
          onSave={(next) => {
            const ids = next[partyId] ?? [];
            // Nothing changed: leave Attn exactly as it reads.
            if (ids.length === attn.ids.length && ids.every((id, i) => id === attn.ids[i])) return;
            void apply(ids, attn.unmatched);
          }}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}
