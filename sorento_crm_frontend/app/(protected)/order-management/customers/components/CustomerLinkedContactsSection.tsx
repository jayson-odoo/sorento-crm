'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateInMalaysia } from '@/lib/helpers';
import { useCustomerLinkedContacts } from '../hooks/useCustomers';

/**
 * Customer detail -> WhatsApp contacts: who is linked to this account. Read-only: a link is
 * made from the contact's Customers card, so this section has no button.
 */
export default function CustomerLinkedContactsSection({ customerId }: { customerId: string }) {
  const { data, isLoading } = useCustomerLinkedContacts(customerId);
  const contacts = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>WhatsApp contacts</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : contacts.length === 0 ? (
          <div className="py-4 text-center">
            <p className="text-sm font-medium text-foreground">No WhatsApp contacts linked</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Link this customer from a contact&apos;s Customers card
            </p>
          </div>
        ) : (
          <ul className="divide-y rounded-md border">
            {contacts.map((c) => {
              const label = c.name?.trim() || c.phone_number || '-';
              return (
                <li
                  key={c.id}
                  className="flex flex-col gap-1 px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
                >
                  <Link
                    href={`/user-management/contacts/${c.contact_id}`}
                    className="min-w-0 truncate text-sm font-medium text-primary hover:underline"
                    title={label}
                  >
                    {label}
                  </Link>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                    <span className="font-mono">{c.phone_number ?? '-'}</span>
                    <span>{formatDateInMalaysia(c.created_at)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
