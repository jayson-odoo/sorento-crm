'use client';

import * as React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PhoneInput } from '@/components/common/PhoneInput';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { usePartyContactMutations, usePartyContacts } from '../hooks/useProjects';
import type { PartyContact } from '../types/project.types';

export interface ContactsDialogParty {
  partyId: string;
  name: string;
}

/**
 * The contacts popup of one role field (PROJECT-PARTY-ROLES mock v4, screen 1c): tick the people
 * at the picked party, add one that is missing, fill a missing number. A role holding several
 * parties shows one line tab per party. The popup only ADDS (owner Q6 b): a contact already on
 * the project shows ticked and fixed.
 */
export function PartyContactsDialog({
  title,
  parties,
  picks,
  fixed,
  canEdit,
  onSave,
  onClose,
}: {
  /** Overrides the dialog title (the proposal uses "Attn at X"). */
  title?: (partyName: string) => string;
  parties: ContactsDialogParty[];
  /** Contact ids picked so far, per party id. */
  picks: Record<string, string[]>;
  /** Contact ids already the project's stakeholders, per party id: ticked and not removable. */
  fixed?: Record<string, string[]>;
  /** Holds `projects.parties.edit`: may add a contact or a number. */
  canEdit: boolean;
  onSave: (next: Record<string, string[]>) => void;
  onClose: () => void;
}) {
  const [active, setActive] = React.useState(parties[0]?.partyId ?? '');
  const [draft, setDraft] = React.useState<Record<string, string[]>>(picks);
  const party = parties.find((p) => p.partyId === active) ?? parties[0];
  if (!party) return null;

  const heading = title ? title(party.name) : `Contacts at ${party.name}`;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle className="truncate" title={heading}>
            {heading}
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {parties.length > 1 && (
            <Tabs value={party.partyId} onValueChange={setActive}>
              <TabsList variant="line" className="w-full">
                {parties.map((p) => (
                  <TabsTrigger key={p.partyId} value={p.partyId} className="max-w-[12rem] truncate" title={p.name}>
                    {p.name}
                  </TabsTrigger>
                ))}
              </TabsList>
            </Tabs>
          )}
          <PartyContactRows
            key={party.partyId}
            partyId={party.partyId}
            picked={draft[party.partyId] ?? []}
            fixed={fixed?.[party.partyId] ?? []}
            canEdit={canEdit}
            onChange={(ids) => setDraft((prev) => ({ ...prev, [party.partyId]: ids }))}
          />
        </DialogBody>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => {
              onSave(draft);
              onClose();
            }}
          >
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PartyContactRows({
  partyId,
  picked,
  fixed,
  canEdit,
  onChange,
}: {
  partyId: string;
  picked: string[];
  fixed: string[];
  canEdit: boolean;
  onChange: (ids: string[]) => void;
}) {
  const contacts = usePartyContacts(partyId);
  const { create, update } = usePartyContactMutations(partyId);
  const [numberFor, setNumberFor] = React.useState<string | null>(null);
  // Numbers are E.164 from the app's PhoneInput (libphonenumber); `valid` is a complete number.
  const [number, setNumber] = React.useState({ e164: '', valid: false });
  const [adding, setAdding] = React.useState(false);
  const [name, setName] = React.useState('');
  const [nameTried, setNameTried] = React.useState(false);
  const [jobTitle, setJobTitle] = React.useState('');
  const [phone, setPhone] = React.useState({ e164: '', valid: true });
  const rows = (contacts.data ?? []).filter((c) => c.is_active !== false);

  function toggle(id: string, on: boolean) {
    onChange(on ? [...picked.filter((p) => p !== id), id] : picked.filter((p) => p !== id));
  }

  async function saveNumber(contact: PartyContact) {
    if (!number.valid) return;
    try {
      await update.mutateAsync({ id: contact.id, body: { phone: number.e164 } });
      setNumberFor(null);
      setNumber({ e164: '', valid: false });
    } catch {
      // toasted by the mutation
    }
  }

  async function addContact() {
    setNameTried(true);
    if (!name.trim() || !phone.valid) return;
    try {
      const row = await create.mutateAsync({
        name: name.trim(),
        job_title: jobTitle.trim() || null,
        phone: phone.e164 || null,
      });
      onChange([...picked, row.id]);
      setAdding(false);
      setName('');
      setNameTried(false);
      setJobTitle('');
      setPhone({ e164: '', valid: true });
    } catch {
      // toasted by the mutation; the typed values stay
    }
  }

  if (contacts.isLoading) return <p className="py-2 text-sm text-muted-foreground">Loading contacts</p>;
  if (contacts.error)
    return (
      <div className="flex items-center gap-2 py-2 text-sm text-destructive">
        Contacts did not load.
        <Button type="button" variant="ghost" size="sm" onClick={() => void contacts.refetch()}>
          Retry
        </Button>
      </div>
    );

  return (
    <div className="divide-y divide-border">
      {rows.length === 0 && !adding && (
        <p className="py-2 text-sm text-muted-foreground">No contacts at this party yet</p>
      )}
      {rows.map((contact) => {
        const isFixed = fixed.includes(contact.id);
        const checked = isFixed || picked.includes(contact.id);
        const boxId = `party-contact-${contact.id}`;
        const detail = [contact.job_title, contact.phone].filter(Boolean).join(', ');
        return (
          <div key={contact.id} className="flex flex-wrap items-center gap-3 py-2.5">
            <Checkbox
              id={boxId}
              checked={checked}
              disabled={isFixed}
              onCheckedChange={(next) => toggle(contact.id, next === true)}
            />
            <label htmlFor={boxId} className="min-w-0 flex-1 cursor-pointer">
              <span className="block truncate text-sm font-medium" title={contact.name}>
                {contact.name}
              </span>
              {detail && <span className="block truncate text-xs text-muted-foreground">{detail}</span>}
            </label>
            {isFixed && <Badge variant="secondary">On this project</Badge>}
            {!contact.phone && canEdit && numberFor !== contact.id && (
              <Button
                type="button"
                variant="link"
                size="sm"
                className="h-auto p-0"
                onClick={() => {
                  setNumberFor(contact.id);
                  setNumber({ e164: '', valid: false });
                }}
              >
                Add number
              </Button>
            )}
            {numberFor === contact.id && (
              <div className="flex w-full items-start gap-2">
                <PhoneInput
                  aria-label={`Phone for ${contact.name}`}
                  id={`contact-number-${contact.id}`}
                  value={number.e164}
                  autoFocus
                  errorMessage="Enter a valid phone number, e.g. 12-345 6789."
                  onChange={(e164, meta) => setNumber({ e164, valid: meta.valid })}
                  className="min-w-0 flex-1"
                />
                <Button
                  type="button"
                  size="sm"
                  disabled={!number.valid || update.isPending}
                  onClick={() => void saveNumber(contact)}
                >
                  Save
                </Button>
              </div>
            )}
          </div>
        );
      })}
      {canEdit && !adding && (
        <div className="py-2.5">
          <Button type="button" variant="link" size="sm" className="h-auto p-0" onClick={() => setAdding(true)}>
            + Add contact
          </Button>
        </div>
      )}
      {adding && (
        <div className="grid gap-3 py-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`new-contact-name-${partyId}`}>
              Name <span className="text-destructive">*</span>
            </Label>
            <Input
              id={`new-contact-name-${partyId}`}
              value={name}
              maxLength={255}
              autoFocus
              aria-invalid={nameTried && !name.trim() ? true : undefined}
              onChange={(event) => setName(event.target.value)}
            />
            {nameTried && !name.trim() && <p className="text-xs text-destructive">Enter a name.</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor={`new-contact-job-${partyId}`}>Job title</Label>
            <Input
              id={`new-contact-job-${partyId}`}
              value={jobTitle}
              maxLength={120}
              onChange={(event) => setJobTitle(event.target.value)}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor={`new-contact-phone-${partyId}`}>Phone</Label>
            <PhoneInput
              id={`new-contact-phone-${partyId}`}
              value={phone.e164}
              errorMessage="Enter a valid phone number, e.g. 12-345 6789."
              // Optional: blank is fine, a number must be a complete one.
              onChange={(e164, meta) => setPhone({ e164, valid: !e164 || meta.valid })}
            />
          </div>
          <div className="flex gap-2 sm:col-span-2">
            <Button type="button" size="sm" disabled={!phone.valid || create.isPending} onClick={() => void addContact()}>
              Add contact
            </Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
