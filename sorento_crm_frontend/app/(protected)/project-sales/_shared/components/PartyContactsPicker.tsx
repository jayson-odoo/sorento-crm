'use client';

import * as React from 'react';
import { Label } from '@/components/ui/label';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { usePartyContacts } from '../hooks/useProjects';
import { PartyContactDialog } from './PartyContactDialog';

/**
 * The contacts of ONE picked party on the register form (PS-REGISTRATION-V3 rules 5-7).
 * Register copies each pick into the project's stakeholders. The "Add contact" row creates
 * the person on the party itself, for holders of `projects.parties.edit`.
 */
export function PartyContactsPicker({
  partyId,
  partyName,
  value,
  onChange,
  canCreate,
}: {
  partyId: string;
  partyName: string;
  value: string[];
  onChange: (value: string[]) => void;
  canCreate: boolean;
}) {
  const contacts = usePartyContacts(partyId);
  const [adding, setAdding] = React.useState<string | null>(null);
  const id = `party-contacts-${partyId}`;
  const options = (contacts.data ?? []).map((contact) => ({
    value: contact.id,
    label: contact.name,
    description: [contact.job_title, contact.phone].filter(Boolean).join(', ') || undefined,
  }));

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs text-muted-foreground">
        Contacts at {partyName}
      </Label>
      <SearchableMultiSelect
        id={id}
        value={value}
        onChange={onChange}
        options={options}
        clearable
        loadError={contacts.error}
        onRetry={() => void contacts.refetch()}
        placeholder="Pick contacts"
        emptyMessage="No contacts at this party yet"
        createOption={
          canCreate
            ? {
                label: (query: string) => (
                  <span>
                    Add contact &ldquo;{query}&rdquo;
                  </span>
                ),
                onCreate: (query: string) => setAdding(query.trim()),
              }
            : undefined
        }
      />
      {adding !== null && (
        <PartyContactDialog
          partyId={partyId}
          contact={null}
          initialName={adding}
          onDone={() => setAdding(null)}
          onCreated={(row) => onChange([...value, row.id])}
        />
      )}
    </div>
  );
}
