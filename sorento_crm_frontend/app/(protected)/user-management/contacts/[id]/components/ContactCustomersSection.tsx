'use client';

import { Unlink } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardHeading, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useHasPermission } from '@/hooks/usePermissions';
import {
  CUSTOMER_SELECT_PAGE_SIZE,
  searchCustomersSelect,
} from '@/app/(protected)/order-management/customers/services/customerService';
import {
  contactCustomersKey,
  useContactCustomers,
  useLinkContactCustomer,
  useSetContactCustomerPrimary,
} from '../hooks/useContactCustomers';

function agentLabel(code: string | null, name: string | null): string | null {
  if (!code) return null;
  return name ? `${code} - ${name}` : code;
}

/**
 * Contact Details -> Customers card: the customer accounts this WhatsApp number belongs to,
 * each with the sales agent handling that account (derived off the customer, never typed here).
 * Read-only without `user_management.contacts.edit`.
 */
export default function ContactCustomersSection({ contactId }: { contactId: string }) {
  const canEdit = useHasPermission('user_management.contacts.edit');
  const { data, isLoading } = useContactCustomers(contactId);
  const link = useLinkContactCustomer(contactId);
  const setPrimary = useSetContactCustomerPrimary(contactId);

  // Unlink asks nothing (D7): the button becomes the countdown, the server commits on lapse.
  const unlink = useDeferredRowAction({
    actionKey: 'contact_customer_link.unlink',
    entityType: 'contact_customer_link',
    verb: 'Unlinking',
    successMessage: 'Customer unlinked',
    surface: 'inline',
    invalidateKeys: [contactCustomersKey(contactId)],
  });

  const links = data?.data ?? [];
  const suggested = data?.suggested ?? [];

  return (
    <Card>
      <CardHeader>
        <CardHeading>
          <CardTitle>Customers</CardTitle>
        </CardHeading>
      </CardHeader>
      <CardContent className="space-y-4">
        {canEdit ? (
          <SearchableSelect
            value=""
            onChange={(customerId) => {
              if (customerId) link.mutate({ customerId });
            }}
            fetchOptions={searchCustomersSelect}
            paginated
            pageSize={CUSTOMER_SELECT_PAGE_SIZE}
            clearable
            placeholder="Add customer"
            emptyMessage="No customers match."
            aria-label="Add customer"
            disabled={link.isPending}
            className="w-full"
          />
        ) : null}

        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : links.length === 0 ? (
          <div className="py-4 text-center">
            <p className="text-sm font-medium text-foreground">No customers linked</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Link the customer accounts this contact belongs to
            </p>
          </div>
        ) : (
          <ul className="divide-y rounded-md border">
            {links.map((row) => {
              const agent = agentLabel(row.sales_agent_code, row.sales_agent_name);
              const customer = `${row.customer_code} - ${row.customer_name}`;
              const counting = unlink.targetId === row.id && unlink.countdown;
              return (
                <li
                  key={row.id}
                  className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate text-sm font-medium" title={customer}>
                      {customer}
                    </span>
                    {!row.is_active ? (
                      <Badge variant="secondary" appearance="light" size="md">
                        Inactive
                      </Badge>
                    ) : null}
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 sm:justify-end">
                    <span
                      className="min-w-0 truncate text-sm text-muted-foreground"
                      title={agent ?? 'No sales agent'}
                    >
                      {agent ?? 'No sales agent'}
                    </span>
                    {row.is_primary ? (
                      <Badge variant="info" appearance="light" size="md">
                        Primary
                      </Badge>
                    ) : null}
                    {canEdit ? (
                      <>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={setPrimary.isPending}
                          onClick={() =>
                            setPrimary.mutate({
                              customerId: row.customer_id,
                              isPrimary: !row.is_primary,
                            })
                          }
                        >
                          {row.is_primary ? 'Clear primary' : 'Make primary'}
                        </Button>
                        {counting ? (
                          counting
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={unlink.isPending}
                            onClick={() =>
                              unlink.run({ id: row.id, subject: row.customer_name })
                            }
                          >
                            <Unlink className="size-4" />
                            Unlink
                          </Button>
                        )}
                      </>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {suggested.length > 0 ? (
          <div className="space-y-2">
            <p className="text-sm font-medium">Suggested</p>
            <ul className="divide-y rounded-md border">
              {suggested.map((s) => {
                const agent = agentLabel(s.sales_agent_code, s.sales_agent_name);
                const customer = `${s.customer_code} - ${s.customer_name}`;
                return (
                  <li
                    key={s.customer_id}
                    className="flex flex-col gap-2 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <span className="min-w-0 truncate text-sm font-medium" title={customer}>
                      {customer}
                    </span>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 sm:justify-end">
                      <span className="font-mono text-sm text-muted-foreground">
                        {s.phone_number ?? '-'}
                      </span>
                      <span
                        className="min-w-0 truncate text-sm text-muted-foreground"
                        title={agent ?? 'No sales agent'}
                      >
                        {agent ?? 'No sales agent'}
                      </span>
                      {canEdit ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={link.isPending}
                          onClick={() => link.mutate({ customerId: s.customer_id })}
                        >
                          Link
                        </Button>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
