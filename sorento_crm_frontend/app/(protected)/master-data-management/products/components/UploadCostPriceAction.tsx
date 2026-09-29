'use client';

import { useState } from 'react';
import { Upload } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { useHasPermission } from '@/hooks/usePermissions';
import { UploadPriceListDialog } from '@/app/(protected)/procurement-management/cost-price-uploads/components/UploadPriceListDialog';

/**
 * The Products list's primary action (owner ruling, #1288 round 5): the same
 * supplier price list upload Purchasing > Cost price lists offers, behind the
 * same permission, opening the same dialog.
 */
export function UploadCostPriceAction() {
  const canUpload = useHasPermission('procurement.cost_price_changes.upload');
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);

  if (!canUpload) return null;

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Upload className="size-4" />
        Upload cost price
      </Button>
      <UploadPriceListDialog
        open={open}
        onOpenChange={setOpen}
        onUploaded={() => queryClient.invalidateQueries({ queryKey: ['products'] })}
      />
    </>
  );
}

export default UploadCostPriceAction;
