'use client';

import * as React from 'react';
import Link from 'next/link';
import { ArrowLeft, FileText, History } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import ProductStockTab from '@/app/(protected)/master-data-management/products/[id]/components/ProductStockTab';
import { useStockTransfer } from '../../hooks/useStockTransfers';
import {
  TRANSFER_KIND_LABEL,
  type StockTransfer,
} from '../../types/stockTransfer.types';
import {
  StockTransferActionDialogs,
  availableActions,
  type TransferAction,
} from '../../components/StockTransferActions';
import { TransferStatePill } from '../../components/StockTransfersPanel';
import StockTransferNavigation from '../../components/StockTransferNavigation';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="mt-0.5 text-sm break-words">{children}</div>
    </div>
  );
}

/**
 * One stock transfer (`PLAN-scm-cs-planning-uat.md` section E).
 *
 * Two tabs, the same set in view and in edit - and there is no edit: a transfer is not a
 * form somebody fills in, it is a movement a decision implied, and the only writes are the
 * three verbs in the header. Read-only metadata (the number, the state, the actions) lives
 * in the page header rather than in a tab body, per the CRUD standard.
 */
export function StockTransferDetail({ id }: { id: string }) {
  const { data, isLoading, isError } = useStockTransfer(id);
  const [tab, setTab] = React.useState('general');
  const [action, setAction] = React.useState<TransferAction | null>(null);

  const backLink = (
    <Button variant="outline" size="sm" asChild>
      <Link href="/inventory-management/stock-transfers">
        <ArrowLeft className="size-4" />
        Back to transfers
      </Link>
    </Button>
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="space-y-4">
        <div className="flex justify-end">{backLink}</div>
        <Card className="flex flex-col items-center gap-3 p-10 text-center">
          <div className="text-sm font-semibold">Stock transfer not found</div>
          <p className="max-w-md text-sm text-muted-foreground">
            This transfer doesn&apos;t exist, or it was removed after this link was made.
            Head back to the list to pick another.
          </p>
        </Card>
      </div>
    );
  }

  const transfer: StockTransfer = data;
  const can = availableActions(transfer.state);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="block py-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex min-w-0 flex-wrap items-center gap-3">
              <CardTitle className="text-lg">{transfer.transfer_no}</CardTitle>
              <TransferStatePill state={transfer.state} />
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <StockTransferNavigation transferId={transfer.id} />
              {can.approve ? (
                <Button size="sm" onClick={() => setAction('approve')}>
                  Approve
                </Button>
              ) : null}
              {can.markMoved ? (
                <Button size="sm" onClick={() => setAction('mark-moved')}>
                  Mark moved
                </Button>
              ) : null}
              {can.cancel ? (
                <Button variant="outline" size="sm" onClick={() => setAction('cancel')}>
                  Cancel
                </Button>
              ) : null}
              {backLink}
            </div>
          </div>
        </CardHeader>
      </Card>

      <Tabs value={tab} onValueChange={setTab} className="w-full">
        <TabsList variant="line" className="mb-4 w-full justify-start overflow-x-auto">
          <TabsTrigger value="general">
            <FileText />
            <span>General</span>
          </TabsTrigger>
          <TabsTrigger value="history">
            <History />
            <span>History</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="mt-0 space-y-4 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Movement</CardTitle>
              </CardHeading>
            </CardHeader>
            <section
              aria-label="Movement"
              className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2"
            >
              <Field label="Item">
                {transfer.item_code ?? '-'}
                {transfer.product_name ? (
                  <span className="block text-xs text-muted-foreground">
                    {transfer.product_name}
                  </span>
                ) : null}
              </Field>
              <Field label="Quantity">
                <span className="tabular-nums">{transfer.qty}</span>
              </Field>
              <Field label="From">{transfer.from_location ?? '-'}</Field>
              <Field label="To">{transfer.to_location ?? '-'}</Field>
              <Field label="Source">{TRANSFER_KIND_LABEL[transfer.kind]}</Field>
              <Field label="AutoCount transfer">{transfer.autocount_ref ?? '-'}</Field>
            </section>
          </Card>

          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>Sales order</CardTitle>
              </CardHeading>
            </CardHeader>
            <section
              aria-label="Sales order"
              className="grid grid-cols-1 gap-4 p-4 sm:grid-cols-2"
            >
              <Field label="Sales order">
                {transfer.so_number ? (
                  transfer.sales_order_id ? (
                    <Link
                      className="text-primary hover:underline"
                      href={`/scm/sales-orders/${transfer.sales_order_id}`}
                    >
                      {transfer.so_number}
                    </Link>
                  ) : (
                    transfer.so_number
                  )
                ) : (
                  <span className="text-muted-foreground">
                    Not linked to a sales-order line any more
                  </span>
                )}
              </Field>
              <Field label="Line">
                {transfer.so_line_no != null ? `L${transfer.so_line_no}` : '-'}
              </Field>
              <Field label="Customer">{transfer.customer_name ?? '-'}</Field>
              <Field label="Agent">
                {transfer.agent_name
                  ? `${transfer.agent_code ?? ''} · ${transfer.agent_name}`
                  : (transfer.agent_code ?? '-')}
              </Field>
              <Field label="Decision revision">
                {transfer.revision_no != null ? `Revision ${transfer.revision_no}` : '-'}
              </Field>
            </section>
          </Card>

          {/* Where this product actually sits, from the stock master - the same component
              the product page's Stock tab is, so the two cannot state a level two ways.
              Always rendered: it carries its own empty state. */}
          {transfer.product_id ? (
            <ProductStockTab productId={transfer.product_id} />
          ) : (
            <Card>
              <CardHeader>
                <CardHeading>
                  <CardTitle>Stock Information</CardTitle>
                </CardHeading>
              </CardHeader>
              <div className="p-4 text-sm text-muted-foreground">
                No product on this transfer, so there are no stock levels to show.
              </div>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="history" className="mt-0 focus-visible:outline-none">
          <Card>
            <CardHeader>
              <CardHeading>
                <CardTitle>History</CardTitle>
              </CardHeading>
            </CardHeader>
            <section aria-label="History" className="space-y-3 p-4">
              <HistoryRow
                label="Proposed"
                when={transfer.proposed_at}
                who={transfer.revision_no != null ? `Revision ${transfer.revision_no}` : null}
                empty="Not recorded"
              />
              <HistoryRow
                label="Approved"
                when={transfer.approved_at}
                who={transfer.approved_by_name}
                empty="Not approved yet"
              />
              <HistoryRow
                label="Moved"
                when={transfer.moved_at}
                who={transfer.moved_by_name}
                empty="Not moved yet"
              />
              <HistoryRow
                label="Cancelled"
                when={transfer.state === 'cancelled' ? transfer.updated_at : null}
                who={transfer.cancelled_reason}
                empty="Not cancelled"
              />
            </section>
          </Card>
        </TabsContent>
      </Tabs>

      <StockTransferActionDialogs
        transfer={transfer}
        action={action}
        onClose={() => setAction(null)}
      />
    </div>
  );
}

function HistoryRow({
  label,
  when,
  who,
  empty,
}: {
  label: string;
  when: string | null;
  who: string | null;
  empty: string;
}) {
  return (
    <div className="flex flex-col gap-1 border-b border-border pb-3 last:border-0 last:pb-0 sm:flex-row sm:items-baseline sm:gap-4">
      <span className="w-28 shrink-0 text-xs text-muted-foreground">{label}</span>
      {when ? (
        <span className="min-w-0 break-words text-sm">
          {formatDateTimeInMalaysia(when)}
          {who ? <span className="text-muted-foreground">{` · ${who}`}</span> : null}
        </span>
      ) : (
        <span className="text-sm text-muted-foreground">{empty}</span>
      )}
    </div>
  );
}

export default StockTransferDetail;
