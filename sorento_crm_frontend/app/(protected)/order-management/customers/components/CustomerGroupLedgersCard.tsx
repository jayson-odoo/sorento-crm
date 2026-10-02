'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useCustomerGroupCustomers } from '../../customer-groups/hooks/useCustomerGroups';

/**
 * The Details tab's "Group ledgers" card: the sibling ledgers of this customer's group,
 * this one marked. Not fetched while the customer has no group.
 */
export default function CustomerGroupLedgersCard({
  customerId,
  groupId,
}: {
  customerId: string;
  groupId: string | null;
}) {
  const { data, isLoading } = useCustomerGroupCustomers(groupId, {
    pageIndex: 0,
    pageSize: 50,
    sorting: [{ id: 'customer_code', desc: false }],
    searchQuery: '',
  });
  const rows = data?.data ?? [];

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Group ledgers</CardTitle>
        {groupId ? (
          <Link
            href={`/order-management/customer-groups/${groupId}`}
            className="text-sm text-primary hover:underline"
          >
            Open group
          </Link>
        ) : null}
      </CardHeader>
      <CardContent>
        {!groupId ? (
          <div className="py-2">
            <p className="text-sm font-medium">Not in a group</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Set a group on the edit form to list its ledgers here
            </p>
          </div>
        ) : isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="px-2 py-2 font-medium">Code</th>
                  <th className="px-2 py-2 font-medium">Name</th>
                  <th className="px-2 py-2 font-medium">Account level</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b last:border-0">
                    <td className="px-2 py-2 font-medium">{row.customer_code}</td>
                    <td className="max-w-xs px-2 py-2">
                      <span className="block truncate" title={row.customer_name}>
                        {row.customer_name}
                      </span>
                      {row.id === customerId ? (
                        <span className="text-xs text-muted-foreground">(this ledger)</span>
                      ) : null}
                    </td>
                    <td className="px-2 py-2">
                      {row.account_level ? `Account ${row.account_level}` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
