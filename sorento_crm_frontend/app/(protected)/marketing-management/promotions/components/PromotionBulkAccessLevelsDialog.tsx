'use client';

import { useState, useEffect } from 'react';
import { LoaderCircleIcon } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { useBulkUpdatePromotionAccessLevels } from '../hooks/usePromotions';
import { useContactAccessTypes } from '@/app/(protected)/user-management/contact-access-types/hooks/useContactAccessTypes';

interface PromotionBulkAccessLevelsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  promotionIds: string[];
  onSuccess?: () => void;
}

export default function PromotionBulkAccessLevelsDialog({
  open,
  onOpenChange,
  promotionIds,
  onSuccess,
}: PromotionBulkAccessLevelsDialogProps) {
  const { data: accessTypeOptions = [] } = useContactAccessTypes();
  const defaultCodes = accessTypeOptions.length > 0 ? accessTypeOptions.map((o) => o.code) : ['dealer', 'end_user'];
  const [selected, setSelected] = useState<Set<string>>(new Set(defaultCodes));
  const bulkUpdateMutation = useBulkUpdatePromotionAccessLevels();

  useEffect(() => {
    if (open) {
      setSelected(new Set(defaultCodes));
    }
  }, [open, defaultCodes.join(',')]);

  const toggle = (value: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value);
      else next.add(value);
      return next;
    });
  };

  const handleApply = () => {
    const levels = Array.from(selected);
    if (levels.length === 0) return;
    if (promotionIds.length === 0) return;
    bulkUpdateMutation.mutate(
      { ids: promotionIds, access_levels: levels },
      {
        onSuccess: () => {
          onOpenChange(false);
          onSuccess?.();
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Set access levels</DialogTitle>
          <DialogDescription>
            Choose who can view the selected promotion
            {promotionIds.length !== 1 ? 's' : ''}. This will update {promotionIds.length} promotion
            {promotionIds.length !== 1 ? 's' : ''}.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap gap-4 py-4">
          {accessTypeOptions.map((opt) => (
            <label key={opt.code} className="flex items-center gap-2 text-sm cursor-pointer">
              <Checkbox
                checked={selected.has(opt.code)}
                onCheckedChange={() => toggle(opt.code)}
                aria-label={opt.name || opt.code}
              />
              {opt.name || opt.code}
            </label>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={bulkUpdateMutation.isPending}>
            Cancel
          </Button>
          <Button
            onClick={handleApply}
            disabled={selected.size === 0 || promotionIds.length === 0 || bulkUpdateMutation.isPending}
          >
            {bulkUpdateMutation.isPending && <LoaderCircleIcon className="size-4 animate-spin mr-2" />}
            Apply to {promotionIds.length} promotion{promotionIds.length !== 1 ? 's' : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
