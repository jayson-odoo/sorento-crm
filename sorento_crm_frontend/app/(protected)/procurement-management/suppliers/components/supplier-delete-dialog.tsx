'use client';

import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { toast } from 'sonner';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LoaderCircleIcon } from 'lucide-react';
import { useDeleteSupplier } from '../hooks/useSuppliers';
import type { Supplier } from '../types/supplier.types';

export interface SupplierDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  supplier: Supplier;
  onSuccess?: () => void;
}

const SupplierDeleteDialog = ({
  open,
  closeDialog,
  supplier,
  onSuccess,
}: SupplierDeleteDialogProps) => {
  const deleteMutation = useDeleteSupplier();

  const handleDelete = () => {
    deleteMutation.mutate(supplier.id, {
      onSuccess: () => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="success">
              <AlertIcon>
                <RiCheckboxCircleFill />
              </AlertIcon>
              <AlertTitle>Supplier deleted successfully</AlertTitle>
            </Alert>
          ),
          {
            position: 'top-center',
          },
        );
        closeDialog();
        if (onSuccess) {
          onSuccess();
        }
      },
      onError: (error: Error) => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="destructive">
              <AlertIcon>
                <RiErrorWarningFill />
              </AlertIcon>
              <AlertTitle>{error.message || 'Failed to delete supplier'}</AlertTitle>
            </Alert>
          ),
          {
            position: 'top-center',
          },
        );
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm Delete</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          Are you sure you want to delete the supplier{' '}
          <strong className="text-foreground">{supplier.supplier_name}</strong> (
          {supplier.supplier_code})? This action cannot be undone.
        </DialogDescription>
        <DialogFooter>
          <Button variant="outline" onClick={closeDialog}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin" />
            )}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default SupplierDeleteDialog;
