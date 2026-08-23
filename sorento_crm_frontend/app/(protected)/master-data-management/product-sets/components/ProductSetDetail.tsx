'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowLeft, Layers, Pencil, Plus, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useProductSet, useUpdateProductSet } from '../hooks/useProductSets';
import type { ProductSetDetail as ProductSetDetailType } from '../types/productSet.types';
import { ProductSetFormModal } from './ProductSetFormModal';

function money(value: number | null): string {
  return value === null ? '-' : `RM ${value.toLocaleString('en-MY', { minimumFractionDigits: 2 })}`;
}

/** The header's price block: resolved figure, and the computed one it replaced. */
function PriceBlock({ set }: { set: ProductSetDetailType }) {
  const { resolved, computed, is_overridden, reason, override_set_by_name } = set.price;
  if (resolved === null) {
    return (
      <div>
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Price</div>
        <div className="text-sm text-muted-foreground">
          {reason === 'no_members'
            ? 'No members yet'
            : 'No member sets the price'}
        </div>
      </div>
    );
  }
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">Price</div>
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="text-lg font-semibold tabular-nums">{money(resolved)}</span>
        {is_overridden ? (
          <>
            <Badge variant="warning" size="sm">
              Override
            </Badge>
            <span className="text-xs text-muted-foreground">
              computed {money(computed)}
              {override_set_by_name ? ` · set by ${override_set_by_name}` : ''}
            </span>
          </>
        ) : (
          <span className="text-xs text-muted-foreground">computed from members</span>
        )}
      </div>
    </div>
  );
}

export default function ProductSetDetail({ id }: { id: string }) {
  const { data: set, isLoading, isError, error } = useProductSet(id);
  const [editingHeader, setEditingHeader] = useState(false);
  const [removingMember, setRemovingMember] = useState<string | null>(null);
  const update = useUpdateProductSet();

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (isError || !set) {
    return (
      <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        {error instanceof Error ? error.message : 'Failed to load this product set.'}
        <div className="pt-3">
          <Button variant="outline" asChild>
            <Link href="/master-data-management/product-sets">
              <ArrowLeft className="size-4" /> Back to product sets
            </Link>
          </Button>
        </div>
      </div>
    );
  }

  const memberBeingRemoved = set.members.find((m) => m.id === removingMember) ?? null;

  return (
    <div className="space-y-4">
      {/* Read-only metadata lives in the header, never in a section body. */}
      <Card>
        <CardContent className="flex flex-wrap items-start justify-between gap-4 pt-6">
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-xl font-semibold" title={set.set_code}>
                {set.set_code}
              </h2>
              <Badge variant={set.is_active ? 'success' : 'secondary'} size="sm">
                {set.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
            <p className="truncate text-sm text-muted-foreground" title={set.name}>
              {set.name}
            </p>
            {set.company_name ? (
              <p className="text-xs text-muted-foreground">{set.company_name}</p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-start gap-6">
            <PriceBlock set={set} />
            <div>
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                Complete sets
              </div>
              {set.complete_sets === null ? (
                <span className="text-sm text-muted-foreground">-</span>
              ) : set.complete_sets === 0 && set.limiting_member_code ? (
                <div className="flex items-center gap-1.5">
                  <span className="text-lg font-semibold tabular-nums text-destructive">0</span>
                  <span className="text-xs text-muted-foreground">
                    short on {set.limiting_member_code}
                  </span>
                </div>
              ) : (
                <span className="text-lg font-semibold tabular-nums">{set.complete_sets}</span>
              )}
            </div>
            <Button variant="outline" onClick={() => setEditingHeader(true)}>
              <Pencil className="size-4" /> Edit
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Members</CardTitle>
          <Button variant="outline" size="sm">
            <Plus className="size-4" /> Add member
          </Button>
        </CardHeader>
        <CardContent>
          {set.members.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-10 text-center">
              <div className="rounded-full bg-muted p-3">
                <Layers className="size-5 text-muted-foreground" />
              </div>
              <p className="max-w-sm text-sm text-muted-foreground">
                This set names no products yet, so it has no price and no stock answer. Add the
                parts it is made of.
              </p>
              <Button size="sm">
                <Plus className="size-4" /> Add member
              </Button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="py-2 pe-3 text-start font-medium">Product</th>
                    <th className="py-2 pe-3 text-start font-medium">List price</th>
                    <th className="py-2 pe-3 text-start font-medium">Qty</th>
                    <th className="py-2 pe-3 text-start font-medium">Sets the price</th>
                    <th className="py-2 pe-3 text-start font-medium">Available</th>
                    <th className="py-2 text-end font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {set.members.map((member) => (
                    <tr key={member.id} className="border-b last:border-0">
                      <td className="py-3 pe-3">
                        <div className="flex min-w-0 flex-col">
                          <span className="flex items-center gap-1.5">
                            <span className="truncate font-medium" title={member.product_code}>
                              {member.product_code}
                            </span>
                            {member.is_discontinued ? (
                              <Badge
                                variant="destructive"
                                size="sm"
                                title="Discontinued. The set survives; it cannot complete."
                              >
                                <AlertTriangle className="size-3" /> Discontinued
                              </Badge>
                            ) : null}
                          </span>
                          <span
                            className="truncate text-xs text-muted-foreground"
                            title={member.description ?? ''}
                          >
                            {member.description ?? 'No description'}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 pe-3 tabular-nums">{money(member.list_price)}</td>
                      <td className="py-3 pe-3">
                        <Input
                          className="h-8 w-20"
                          defaultValue={member.quantity}
                          aria-label={`Quantity for ${member.product_code}`}
                        />
                      </td>
                      <td className="py-3 pe-3">
                        <Checkbox
                          defaultChecked={member.contributes_to_price}
                          aria-label={`${member.product_code} sets the price`}
                        />
                      </td>
                      <td className="py-3 pe-3 tabular-nums">
                        {member.available === null ? (
                          <span className="text-muted-foreground">-</span>
                        ) : member.available === 0 ? (
                          <span className="font-medium text-destructive">0</span>
                        ) : (
                          member.available
                        )}
                      </td>
                      <td className="py-3 text-end">
                        <Button
                          mode="icon"
                          variant="ghost"
                          title="Remove from set"
                          aria-label={`Remove ${member.product_code} from set`}
                          onClick={() => setRemovingMember(member.id)}
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Linked documents</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="py-6 text-center text-sm text-muted-foreground">
            Attachments and promotions naming this set code will appear here once linking fans
            out to its members.
          </p>
        </CardContent>
      </Card>

      <ProductSetFormModal
        open={editingHeader}
        onOpenChange={setEditingHeader}
        productSet={set}
      />

      {/* Detaching is destructive, so it confirms like a delete. */}
      <ConfirmDeleteDialog
        open={removingMember !== null}
        onOpenChange={(open) => {
          if (!open) setRemovingMember(null);
        }}
        title="Remove this member from the set?"
        description={
          memberBeingRemoved
            ? `${memberBeingRemoved.product_code} will no longer be part of ${set.set_code}. The product itself is not deleted.`
            : ''
        }
        successMessage="Member removed"
        onDelete={async () => {
          if (!memberBeingRemoved) return;
          await update.mutateAsync({
            id: set.id,
            data: {
              set_code: set.set_code,
              name: set.name,
              members: set.members
                .filter((m) => m.id !== memberBeingRemoved.id)
                .map((m) => ({
                  product_code: m.product_code,
                  quantity: m.quantity,
                  contributes_to_price: m.contributes_to_price,
                  sort_order: m.sort_order,
                })),
            },
          });
        }}
        onSuccess={() => setRemovingMember(null)}
      />
    </div>
  );
}
