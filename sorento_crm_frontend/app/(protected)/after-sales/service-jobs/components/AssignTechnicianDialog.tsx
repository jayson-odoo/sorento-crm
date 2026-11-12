'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
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
import { useTechniciansSelect } from '../hooks/useServiceJobs';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentTechnicianId?: string | null;
  onSubmit: (technicianId: string) => void;
  isPending?: boolean;
}

export default function AssignTechnicianDialog({
  open,
  onOpenChange,
  currentTechnicianId,
  onSubmit,
  isPending,
}: Props) {
  const { data: technicians = [] } = useTechniciansSelect();
  const [technicianId, setTechnicianId] = useState('');

  useEffect(() => {
    if (open) setTechnicianId(currentTechnicianId ?? '');
  }, [open, currentTechnicianId]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Assign technician</DialogTitle>
          <DialogDescription className="sr-only">Choose the technician for this visit.</DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label>Technician</Label>
          <SearchableSelect
            value={technicianId}
            onChange={setTechnicianId}
            options={technicians.map((t) => ({ value: t.id, label: t.name }))}
            placeholder="Select technician"
            aria-label="Technician"
          />
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!technicianId || isPending} onClick={() => onSubmit(technicianId)}>
            Assign technician
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
