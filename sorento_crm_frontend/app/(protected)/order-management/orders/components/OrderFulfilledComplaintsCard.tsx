'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useOrderFulfilledComplaints } from '../hooks/useOrderFulfilledComplaints';

interface OrderFulfilledComplaintsCardProps {
  orderId: string;
}

export default function OrderFulfilledComplaintsCard({
  orderId,
}: OrderFulfilledComplaintsCardProps) {
  const { data: complaints, isLoading } = useOrderFulfilledComplaints(orderId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Fulfils complaints</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex flex-wrap gap-2">
            <Skeleton className="h-7 w-28" />
            <Skeleton className="h-7 w-28" />
          </div>
        ) : !complaints || complaints.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">
            This delivery order is not linked to any complaint.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {complaints.map((c) => (
              <Link
                key={c.complaint_id}
                href={`/complaint-management/complaints/${c.complaint_id}`}
                className="inline-flex items-center rounded-full border border-border bg-muted/40 px-3 py-1 text-sm font-medium text-primary hover:bg-muted hover:underline underline-offset-2"
                title={c.complaint_number}
              >
                {c.complaint_number}
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
