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
import { useDeleteCategory } from '../hooks/useProductCategories';
import type { CategoryTreeItem } from '../types/category.types';

export interface CategoryDeleteDialogProps {
  open: boolean;
  closeDialog: () => void;
  category: CategoryTreeItem;
}

const CategoryDeleteDialog = ({
  open,
  closeDialog,
  category,
}: CategoryDeleteDialogProps) => {
  const deleteMutation = useDeleteCategory();

  const handleDelete = () => {
    deleteMutation.mutate(category.id, {
      onSuccess: () => {
        toast.custom(
          () => (
            <Alert variant="mono" icon="success">
              <AlertIcon>
                <RiCheckboxCircleFill />
              </AlertIcon>
              <AlertTitle>Category deleted successfully</AlertTitle>
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
              <AlertTitle>{error.message || 'Failed to delete category'}</AlertTitle>
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
            Are you sure you want to delete the category{' '}
            <strong className="text-foreground">{category.category_name}</strong> (
            {category.category_code})? This action cannot be undone.
          </DialogDescription>
          {(category.product_count ?? 0) > 0 && (
            <p className="text-sm text-muted-foreground">
              This category has {category.product_count} product(s). You must change their
              category before deleting.{' '}
              <Button variant="link" className="h-auto p-0 text-primary" asChild>
                <Link
                  href={`/master-data-management/products?category=${category.id}`}
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
};

export default CategoryDeleteDialog;
