'use client';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { LoaderCircleIcon } from 'lucide-react';
import { useDeleteCompany } from '../hooks/useCompanies';
import type { Company } from '../types/company.types';

export interface CompanyDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  company: Company;
}

export default function CompanyDeleteDialog({
  open,
  closeDialog,
  company,
}: CompanyDeleteDialogProps) {
  const deleteMutation = useDeleteCompany();

  const handleDelete = () => {
    deleteMutation.mutate(company.id, {
      onSuccess: () => closeDialog(),
    });
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm delete</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <DialogDescription>
            Are you sure you want to delete the company{' '}
            <strong className="text-foreground">{company.name}</strong> ({company.code})? This
            action cannot be undone.
          </DialogDescription>
          {((company.user_count ?? 0) > 0 || (company.contact_count ?? 0) > 0) && (
            <p className="text-sm text-muted-foreground">
              This company has {company.user_count ?? 0} assigned user(s) and{' '}
              {company.contact_count ?? 0} tagged contact(s). Those grants will be removed.
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={closeDialog}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending && <LoaderCircleIcon className="animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
