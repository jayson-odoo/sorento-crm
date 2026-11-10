'use client';

import * as React from 'react';
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
import { Label } from '@/components/ui/label';
import { PhoneInput } from '@/components/common/PhoneInput';
import { usePartyContactMutations } from '../hooks/useProjects';
import type { PartyContact } from '../types/project.types';

/** Add or edit one contact. Name is the only required field. */
export function PartyContactDialog({
  partyId,
  contact,
  initialName,
  onDone,
  onCreated,
}: {
  partyId: string;
  contact: PartyContact | null;
  initialName?: string;
  onDone: () => void;
  onCreated?: (contact: PartyContact) => void;
}) {
  const { create, update } = usePartyContactMutations(partyId);
  const [name, setName] = React.useState(contact?.name ?? initialName ?? '');
  const [jobTitle, setJobTitle] = React.useState(contact?.job_title ?? '');
  // E.164 from the app's PhoneInput; optional, but a typed number must be a complete one.
  const [phone, setPhone] = React.useState({ e164: contact?.phone ?? '', valid: true });
  const [tried, setTried] = React.useState(false);
  const [email, setEmail] = React.useState(contact?.email ?? '');
  const pending = create.isPending || update.isPending;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setTried(true);
    if (!name.trim() || !phone.valid) return;
    const body = {
      name: name.trim(),
      job_title: jobTitle.trim() || null,
      phone: phone.e164 || null,
      email: email.trim() || null,
    };
    try {
      if (contact) {
        await update.mutateAsync({ id: contact.id, body });
      } else {
        const row = await create.mutateAsync(body);
        onCreated?.(row);
      }
      onDone();
    } catch {
      // toasted by the mutation; the dialog stays open with what was typed
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onDone()}>
      <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{contact ? 'Edit contact' : 'Add contact'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={save}>
          <DialogBody className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="party-contact-name">
                Name <span className="text-destructive">*</span>
              </Label>
              <Input
                id="party-contact-name"
                value={name}
                maxLength={255}
                onChange={(event) => setName(event.target.value)}
              />
              {tried && !name.trim() && <p className="text-xs text-destructive">Enter a name.</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="party-contact-job">Job title</Label>
              <Input
                id="party-contact-job"
                value={jobTitle}
                maxLength={120}
                onChange={(event) => setJobTitle(event.target.value)}
                placeholder="Optional"
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="party-contact-phone">Phone</Label>
                <PhoneInput
                  id="party-contact-phone"
                  value={phone.e164}
                  showError={tried}
                  errorMessage="Enter a valid phone number, e.g. 12-345 6789."
                  onChange={(e164, meta) => setPhone({ e164, valid: !e164 || meta.valid })}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="party-contact-email">Email</Label>
                <Input
                  id="party-contact-email"
                  type="email"
                  value={email}
                  maxLength={150}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="Optional"
                />
              </div>
            </div>
          </DialogBody>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="ghost" onClick={onDone}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {contact ? 'Save' : 'Add contact'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
