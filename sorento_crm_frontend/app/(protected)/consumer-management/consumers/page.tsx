'use client';

/**
 * Consumers - finding a person in the ledger.
 *
 * Phone first, because that is what a CS agent has in hand when someone calls. The search
 * matches a phone typed the way a human types it ("012-777 3344") as well as the E.164 the
 * column holds, so nobody has to know the storage format.
 *
 * The headline strip separates confirmed consumers from provisional ones on purpose. A
 * provisional profile is a phone somebody typed into a message; folding it into "we know N
 * consumers" makes the number go up while the asset stays exactly where it was, and that is
 * the one number the module must not inflate (AC-L7).
 */

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';

import {
  getConsumerHeadline,
  listConsumers,
  type ConsumerProfile,
} from './services/consumerService';

function useDebounced<T>(value: T, ms = 300): T {
  const [held, setHeld] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setHeld(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return held;
}

export default function ConsumersPage() {
  const [search, setSearch] = useState('');
  const debounced = useDebounced(search);

  const headline = useQuery({
    queryKey: ['consumer-headline'],
    queryFn: getConsumerHeadline,
  });

  const list = useQuery({
    queryKey: ['consumers', debounced],
    queryFn: () => listConsumers({ pageIndex: 0, pageSize: 50, searchQuery: debounced }),
  });

  const rows = useMemo(() => list.data?.data ?? [], [list.data]);

  return (
    <div className="flex flex-col gap-5 p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold break-words">Consumers</h1>
          <p className="text-sm text-muted-foreground">
            The people who own Sorento products, and what they bought.
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <HeadlineCard
          label="Consumers"
          hint="Confirmed - they authenticated"
          value={headline.data?.consumers}
          loading={headline.isLoading}
        />
        <HeadlineCard
          label="Provisional"
          hint="A phone typed into a message, not yet a person"
          value={headline.data?.provisional}
          loading={headline.isLoading}
        />
        <HeadlineCard
          label="Purchases"
          hint="Receipts the ledger holds"
          value={headline.data?.purchases}
          loading={headline.isLoading}
        />
      </div>

      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by phone or name"
        className="h-11 max-w-md"
      />

      {list.isLoading ? (
        <div className="flex flex-col gap-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : list.isError ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">
            Could not load consumers. Refresh to try again.
          </CardContent>
        </Card>
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col gap-2 p-8 text-center">
            <p className="text-sm font-medium">
              {debounced ? 'Nobody matches that.' : 'No consumers yet.'}
            </p>
            <p className="text-sm text-muted-foreground">
              {debounced
                ? 'Try the phone number instead - it is the only thing every record has.'
                : 'Consumers arrive when somebody lodges a report through the portal, or when staff record a purchase against a phone number.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {rows.map((row) => (
            <ConsumerRow key={row.id} row={row} />
          ))}
        </div>
      )}
    </div>
  );
}

function HeadlineCard({
  label,
  hint,
  value,
  loading,
}: {
  label: string;
  hint: string;
  value?: number;
  loading: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1 p-4">
        <span className="text-xs text-muted-foreground">{label}</span>
        {loading ? (
          <Skeleton className="h-7 w-16" />
        ) : (
          <span className="text-2xl font-semibold">{value ?? 0}</span>
        )}
        <span className="text-xs text-muted-foreground">{hint}</span>
      </CardContent>
    </Card>
  );
}

function ConsumerRow({ row }: { row: ConsumerProfile }) {
  return (
    <Link href={`/consumer-management/consumers/${row.id}`} className="block">
      <Card className="transition-colors hover:bg-muted/40">
        <CardContent className="flex flex-col gap-2 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <p className="truncate font-medium" title={row.full_name ?? undefined}>
              {row.full_name || 'Name not recorded'}
            </p>
            {/* The phone is the identity, so it is never truncated away. */}
            <p className="text-sm text-muted-foreground">{row.phone_e164 || 'No phone'}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {row.is_provisional ? (
              <Badge variant="secondary" title="Recorded by staff; this person has not authenticated.">
                Provisional
              </Badge>
            ) : (
              <Badge variant="outline">Confirmed</Badge>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
