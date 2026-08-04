'use client';

import * as React from 'react';
import { DollarSign, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatMyrExact } from '../../../components/POIntakeMoney';
import type { QuotationScope } from '../../../../_shared/services/quotationDocumentService';

/**
 * The scope switcher, with the money kept behind one toggle.
 *
 * The first version printed each scope's total next to its name. The client's verdict: "this is
 * too much information fatigue la, you can have a $ icon there where on click it shows the
 * amount, but i don't want to show the money and the scope tgt". So a tab reads as a name and
 * nothing more until the reader asks for figures, and the figures are the server's own
 * `scope_total` - never a second arithmetic in the browser.
 *
 * ONE toggle for the strip, not one per tab. A row of $ buttons is the same fatigue in a new
 * shape, and anyone who wants a scope's amount is comparing it against the others anyway, so
 * revealing them individually costs a click per scope and buys nothing.
 */
export function QuotationScopeTabs({
  scopes,
  activeScopeId,
  onSelect,
  canEdit,
  onAddScope,
}: {
  scopes: QuotationScope[];
  activeScopeId: string;
  onSelect: (scopeId: string) => void;
  canEdit: boolean;
  onAddScope?: () => void;
}) {
  // Hidden until asked for, and it stays asked-for while the reader moves between tabs: a
  // toggle that reset on every switch would have to be pressed again to compare anything.
  const [showAmounts, setShowAmounts] = React.useState(false);

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <Tabs value={activeScopeId} onValueChange={onSelect} className="min-w-0">
          <TabsList className="flex-wrap">
            {scopes.map((scope) => (
              <TabsTrigger key={scope.id} value={scope.id}>
                <span className="min-w-0 truncate" title={scope.scope_label}>
                  {scope.scope_label}
                </span>
                {showAmounts && (
                  <span className="ms-2 text-xs tabular-nums text-muted-foreground">
                    {formatMyrExact(scope.scope_total)}
                  </span>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        {/* The label flips with state so a screen reader is told what the press will DO, not
            what the button is called. `aria-pressed` carries the on/off part. */}
        <Button
          type="button"
          variant={showAmounts ? 'primary' : 'outline'}
          size="sm"
          mode="icon"
          aria-pressed={showAmounts}
          aria-label={showAmounts ? 'Hide scope amounts' : 'Show scope amounts'}
          onClick={() => setShowAmounts((current) => !current)}
        >
          <DollarSign aria-hidden />
        </Button>
      </div>

      {canEdit && onAddScope && (
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onAddScope}>
            <Plus className="size-4" aria-hidden />
            Add a scope
          </Button>
        </div>
      )}
    </div>
  );
}
