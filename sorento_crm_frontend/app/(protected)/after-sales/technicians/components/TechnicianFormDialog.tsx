'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { PhoneInput } from '@/components/common/PhoneInput';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { EmploymentType, Technician, TechnicianFormValues } from '../types/technician.types';

const TYPE_OPTIONS = [
  { value: 'employee', label: 'Employee' },
  { value: 'contractor', label: 'Contractor' },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  technician?: Technician | null;
  onSubmit: (values: TechnicianFormValues) => void | Promise<void>;
  isSubmitting?: boolean;
}

/** One dialog for create and edit: the same fields in the same order. */
export default function TechnicianFormDialog({
  open,
  onOpenChange,
  technician,
  onSubmit,
  isSubmitting,
}: Props) {
  const [name, setName] = useState('');
  // E.164 from the app's PhoneInput; optional, but a typed number must be a complete one.
  const [phone, setPhone] = useState({ e164: '', valid: true });
  const [tried, setTried] = useState(false);
  const [type, setType] = useState<EmploymentType>('employee');
  const [error, setError] = useState<string | null>(null);
  // A refetched row is a new object for the same technician; it must not wipe what is being typed.
  const [filledFor, setFilledFor] = useState<string | null>(null);

  useEffect(() => {
    const key = open ? (technician?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setName(technician?.name ?? '');
    setPhone({ e164: technician?.phone ?? '', valid: true });
    setTried(false);
    setType(technician?.employment_type === 'contractor' ? 'contractor' : 'employee');
    setError(null);
  }, [open, technician, filledFor]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!name.trim()) return setError('Name is required.');
    setError(null);
    if (!phone.valid) return;
    void onSubmit({ name: name.trim(), phone: phone.e164 || null, employment_type: type });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{technician ? 'Edit technician' : 'Create technician'}</DialogTitle>
          <DialogDescription className="sr-only">Technician details.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1">
            <Label htmlFor="technician-name">Name</Label>
            <Input id="technician-name" value={name} onChange={(e) => setName(e.target.value)} />
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="technician-phone">Phone</Label>
            <PhoneInput
              id="technician-phone"
              value={phone.e164}
              showError={tried}
              errorMessage="Enter a valid phone number, e.g. 12-345 6789."
              onChange={(e164, meta) => setPhone({ e164, valid: !e164 || meta.valid })}
            />
          </div>
          <div className="space-y-1">
            <Label>Type</Label>
            <SearchableSelect
              value={type}
              onChange={(v) => setType((v as EmploymentType) || 'employee')}
              options={TYPE_OPTIONS}
              aria-label="Type"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
