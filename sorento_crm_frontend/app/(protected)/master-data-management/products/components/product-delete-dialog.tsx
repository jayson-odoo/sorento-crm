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
import { useDeleteProduct } from '../hooks/useProducts';
import type { ProductListItem } from '../types/product.types';

export interface ProductDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  product: ProductListItem;
  /** Called after successful delete, e.g. to redirect */
  onSuccess?: () => void;
}

const ProductDeleteDialog = ({
  open,
  closeDialog,
  product,
  onSuccess,
}: ProductDeleteDialogProps) => {
  const deleteMutation = useDeleteProduct();

  const handleDelete = () => {
    deleteMutation.mutate(product.id, {
      onSuccess: () => {
        onSuccess?.();
        toast.custom(
          () => (
            <Alert variant="mono" icon="success">
              <AlertIcon>
                <RiCheckboxCircleFill />
              </AlertIcon>
              <AlertTitle>Product deleted successfully</AlertTitle>
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
              <AlertTitle>{error.message || 'Failed to delete product'}</AlertTitle>
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
          Are you sure you want to delete the product{' '}
          <strong className="text-foreground">{product.product_name}</strong> (
          {product.product_code})? This action cannot be undone.
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

export default ProductDeleteDialog;
