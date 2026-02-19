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
import { useDeleteBrand } from '../hooks/useBrands';
import type { Brand } from '../types/brand.types';

export interface BrandDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  brand: Brand;
}

export default function BrandDeleteDialog({
  open,
  closeDialog,
  brand,
}: BrandDeleteDialogProps) {
  const deleteMutation = useDeleteBrand();

  const handleDelete = () => {
    deleteMutation.mutate(brand.id, {
      onSuccess: () => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="success">
              <AlertIcon>
                <RiCheckboxCircleFill />
              </AlertIcon>
              <AlertTitle>Brand deleted successfully</AlertTitle>
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
                {error.message || 'Failed to delete brand'}
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
            Are you sure you want to delete the brand{' '}
            <strong className="text-foreground">{brand.brand_name}</strong> (
            {brand.brand_code})? This action cannot be undone.
          </DialogDescription>
          {(brand.product_count ?? 0) > 0 && (
            <p className="text-sm text-muted-foreground">
              This brand is used by {brand.product_count} product(s). Their
              brand will be set to empty (unlinked).{' '}
              <Button variant="link" className="h-auto p-0 text-primary" asChild>
                <Link
                  href={`/master-data-management/products?brand=${brand.id}`}
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
