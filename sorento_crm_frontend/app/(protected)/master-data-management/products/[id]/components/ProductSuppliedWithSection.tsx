'use client';

import { useState } from 'react';
import { LoaderCircleIcon, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  useCompanionRuleDelete,
  useCompanionRulesForCompanion,
} from '../../hooks/useProductCompanions';
import type { ProductCompanionRuleRow } from '../../types/productCompanion.types';
import { AddCompanionRuleModal } from './AddCompanionRuleModal';

interface ProductSuppliedWithSectionProps {
  companionProductId: string;
}

function RuleRow({
  rule,
  onDelete,
  isDeleting,
  canEdit,
}: {
  rule: ProductCompanionRuleRow;
  onDelete: () => void;
  isDeleting: boolean;
  canEdit: boolean;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0 space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-muted-foreground">Included with:</span>
          {rule.hosts.map((host) => (
            <Badge key={host.product_id} variant="secondary" size="sm">
              {host.item_code}
            </Badge>
          ))}
        </div>
        <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted-foreground">Supplier</dt>
            <dd className="truncate" title={rule.supplier_name ?? 'Any'}>
              {rule.supplier_name ? `${rule.supplier_code} - ${rule.supplier_name}` : 'Any'}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Ratio</dt>
            <dd className="tabular-nums">{rule.ratio}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">Status</dt>
            <dd>
              <Badge variant={rule.is_active ? 'success' : 'secondary'} appearance="light" size="sm">
                {rule.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </dd>
          </div>
        </dl>
      </div>
      {canEdit ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="shrink-0"
          onClick={onDelete}
          disabled={isDeleting}
          aria-label={`Delete rule for ${rule.companion_item_code} with ${rule.hosts
            .map((h) => h.item_code)
            .join(' + ')}`}
        >
          {isDeleting ? (
            <LoaderCircleIcon className="size-4 animate-spin" />
          ) : (
            <Trash2 className="size-4 text-destructive" />
          )}
        </Button>
      ) : null}
    </div>
  );
}

/**
 * "Supplied with" (UAC group A): the rules where THIS product is the companion - it
 * rides inside one or more host products' own line rather than getting its own PO
 * line, whenever every host on the rule is present on the same order. Configured
 * here (S1); a host reads the mirror of this, read-only, as "Ships with"
 * (`ProductShipsWithSection`).
 */
export function ProductSuppliedWithSection({
  companionProductId,
}: ProductSuppliedWithSectionProps) {
  const [addOpen, setAddOpen] = useState(false);
  const canEdit = useHasPermission('master_data.products.edit');
  const { data: rules, isLoading, isError } = useCompanionRulesForCompanion(companionProductId);
  // Every host across the rules on screen, so deleting ANY of them also refetches
  // that host's own "Ships with" mirror (review round 1 item 14).
  const hostProductIds = [
    ...new Set((rules ?? []).flatMap((rule) => rule.hosts.map((host) => host.product_id))),
  ];
  const deletion = useCompanionRuleDelete(companionProductId, hostProductIds);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle>Supplied with</CardTitle>
        {canEdit ? (
          <Button type="button" size="sm" onClick={() => setAddOpen(true)}>
            <Plus className="size-4" />
            Add
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : isError ? (
          <p className="text-sm text-destructive">
            Could not load supplied-with rules. Try reloading the page.
          </p>
        ) : !rules || rules.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This product has no supplied-with rule.
          </p>
        ) : (
          <div className="space-y-2">
            {rules.map((rule) => (
              <RuleRow
                key={rule.id}
                rule={rule}
                canEdit={canEdit}
                isDeleting={deletion.targetId === rule.id}
                onDelete={() =>
                  deletion.run({
                    id: rule.id,
                    subject: `${rule.companion_item_code} with ${rule.hosts
                      .map((h) => h.item_code)
                      .join(' + ')}`,
                  })
                }
              />
            ))}
          </div>
        )}
      </CardContent>
      {canEdit ? (
        <AddCompanionRuleModal
          open={addOpen}
          onOpenChange={setAddOpen}
          companionProductId={companionProductId}
        />
      ) : null}
    </Card>
  );
}

export default ProductSuppliedWithSection;
