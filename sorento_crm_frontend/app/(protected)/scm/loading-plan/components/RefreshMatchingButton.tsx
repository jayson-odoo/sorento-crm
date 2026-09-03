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
 * Lives on the queue panel, where the consequence is read. The queue hides itself when it is
 * empty and that is exactly the state somebody is trying to reach after adding the missing
 * products, so the loading-plan toolbar offers the same action from its gear menu - calling
 * the hook directly, since a menu item is not a button.
 */
export function RefreshMatchingButton({
  planId,
  size = 'sm',
}: {
  /** The ladder is re-run over THIS plan's rows only (S6, AC-C7): the queue beside the
   *  button is the plan's own, and a rematch that moved another plan's rows would report
   *  counts nobody on this screen can see. */
  planId: string;
  size?: 'sm' | 'md' | 'lg';
}) {
  const rematch = useRematchSupplierCodes();

  return (
    <Button
      type="button"
      variant="outline"
      size={size}
      data-testid="refresh-matching"
      disabled={!planId || rematch.isPending}
      onClick={() => rematch.mutate({ plan_id: planId })}
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
