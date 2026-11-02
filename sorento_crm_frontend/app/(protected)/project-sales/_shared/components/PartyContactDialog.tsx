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
  const [phone, setPhone] = React.useState(contact?.phone ?? '');
  const [email, setEmail] = React.useState(contact?.email ?? '');
  const pending = create.isPending || update.isPending;

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    const body = {
      name: name.trim(),
      job_title: jobTitle.trim() || null,
      phone: phone.trim() || null,
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
                <Input
                  id="party-contact-phone"
                  type="tel"
                  inputMode="tel"
                  value={phone}
                  maxLength={50}
                  onChange={(event) => setPhone(event.target.value)}
                  placeholder="Optional"
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
            <Button type="submit" disabled={!name.trim() || pending}>
              {contact ? 'Save' : 'Add contact'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
