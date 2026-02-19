'use client';

import Link from 'next/link';
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
import { LoaderCircleIcon, ExternalLink } from 'lucide-react';
import { useDeleteUOM } from '../hooks/useUOM';
import type { UnitOfMeasure } from '../types/uom.types';

export interface UOMDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  uom: UnitOfMeasure;
}

export default function UOMDeleteDialog({
  open,
  closeDialog,
  uom,
}: UOMDeleteDialogProps) {
  const deleteMutation = useDeleteUOM();

  const handleDelete = () => {
    deleteMutation.mutate(uom.id, {
      onSuccess: () => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="success">
              <AlertIcon>
                <RiCheckboxCircleFill />
              </AlertIcon>
              <AlertTitle>UOM deleted successfully</AlertTitle>
            </Alert>
          ),
          {
            position: 'top-center',
          },
        );
        closeDialog();
      },
      onError: (error: Error) => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="destructive">
              <AlertIcon>
                <RiErrorWarningFill />
              </AlertIcon>
              <AlertTitle>
                {error.message || 'Failed to delete UOM'}
              </AlertTitle>
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
        <div className="space-y-2">
          <DialogDescription>
            Are you sure you want to delete the UOM{' '}
            <strong className="text-foreground">{uom.uom_name}</strong> (
            {uom.uom_code})? This action cannot be undone.
          </DialogDescription>
          {(uom.product_count ?? 0) > 0 && (
            <p className="text-sm text-muted-foreground">
              This UOM is used by {uom.product_count} product(s). You must change
              their UOM before deleting.{' '}
              <Button variant="link" className="h-auto p-0 text-primary" asChild>
                <Link
                  href="/master-data-management/products"
                  className="inline-flex items-center gap-1"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  View products <ExternalLink className="size-3" />
                </Link>
              </Button>
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
            {deleteMutation.isPending && (
              <LoaderCircleIcon className="animate-spin" />
            )}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
