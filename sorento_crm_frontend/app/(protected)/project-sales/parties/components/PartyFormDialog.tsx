'use client';

import * as React from 'react';
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
import { Textarea } from '@/components/ui/textarea';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { usePartyMutations } from '../../_shared/hooks/useProjects';
import type { PartyType, ProjectParty } from '../../_shared/types/project.types';
import { PARTY_TYPE_OPTIONS } from './partyTypes';

/**
 * Create and edit in one modal, per the CRUD standard.
 *
 * It is reached from the list (Add) and from the detail page (Edit), so both routes
 * write exactly the same fields with exactly the same validation.
 */
export function PartyFormDialog({
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
