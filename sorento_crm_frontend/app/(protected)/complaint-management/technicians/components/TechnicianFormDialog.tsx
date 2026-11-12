'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
  const [phone, setPhone] = useState('');
  const [type, setType] = useState<EmploymentType>('employee');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(technician?.name ?? '');
    setPhone(technician?.phone ?? '');
    setType(technician?.employment_type === 'contractor' ? 'contractor' : 'employee');
    setError(null);
  }, [open, technician]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError('Name is required.');
    setError(null);
    void onSubmit({ name: name.trim(), phone: phone.trim() || null, employment_type: type });
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
            <Input id="technician-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
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
