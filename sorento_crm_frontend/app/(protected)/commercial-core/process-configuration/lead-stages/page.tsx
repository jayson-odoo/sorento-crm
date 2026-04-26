'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useLeadStagesList } from '@/app/(protected)/commercial/leads/hooks/useLeadStages';

export default function LeadStagesProcessPage() {
  const router = useRouter();
  const { data, isLoading } = useLeadStagesList();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Lead stages</CardTitle>
        <Button asChild size="sm">
          <Link href="/commercial-core/process-configuration/lead-stages/new">
            <Plus className="size-4" />
            Add
          </Link>
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Order</TableHead>
                <TableHead>Terminal</TableHead>
                <TableHead>Allows conversion</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data || []).map((row) => (
                <TableRow
                  key={row.stage_code}
                  className="cursor-pointer"
                  onClick={() =>
                    router.push(
                      `/commercial-core/process-configuration/lead-stages/${encodeURIComponent(row.stage_code)}`,
                    )
                  }
                >
                  <TableCell>{row.stage_code}</TableCell>
                  <TableCell>{row.stage_name}</TableCell>
                  <TableCell>{row.sort_order}</TableCell>
                  <TableCell>{row.is_terminal ? 'Yes' : 'No'}</TableCell>
                  <TableCell>{row.allows_conversion ? 'Yes' : 'No'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
