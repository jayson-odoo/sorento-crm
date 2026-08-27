'use client';

import { Loader2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useRematchSupplierCodes } from '../../hooks/useSupplierCodeAliases';

/**
 * Run the supplier-code ladder again over the rows still unbound (R18).
 *
 * Master data moves after the file lands: a product is created, an alias is recorded on the
 * invoice screen, and the stock rows uploaded last week stay unbound under a code the ladder
 * can now answer. Re-uploading the same file to make them catch up is a ceremony, not a
 * decision, so it is one button.
 *
 * Lives on the queue panel, where the consequence is read, AND on the toolbar, because the
 * queue hides itself when it is empty and that is exactly the state somebody is trying to
 * change after adding the missing products.
 */
export function RefreshMatchingButton({
  supplierId,
  size = 'sm',
}: {
  supplierId: string;
  size?: 'sm' | 'md' | 'lg';
}) {
  const rematch = useRematchSupplierCodes();

  return (
    <Button
      type="button"
      variant="outline"
      size={size}
      data-testid="refresh-matching"
      disabled={!supplierId || rematch.isPending}
      onClick={() => rematch.mutate({ supplier_id: supplierId })}
    >
      {rematch.isPending ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <RefreshCw className="size-4" />
      )}
      Refresh matching
    </Button>
  );
}

export default RefreshMatchingButton;
