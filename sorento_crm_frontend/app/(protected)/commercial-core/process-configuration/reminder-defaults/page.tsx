'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listReminderDefaults } from '../services/reminderDefaultsService';

export default function ReminderDefaultsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['commercial-reminder-defaults'],
    queryFn: () => listReminderDefaults(1, 100),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Reminder defaults</CardTitle>
        <Button asChild size="sm">
          <Link href="/commercial-core/process-configuration/reminder-defaults/new">
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
                <TableHead>Context</TableHead>
                <TableHead>Name</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.data || []).map((r) => (
                <TableRow key={r.context}>
                  <TableCell>
                    <Link
                      className="text-primary hover:underline"
                      href={`/commercial-core/process-configuration/reminder-defaults/${encodeURIComponent(r.context)}/edit`}
                    >
                      {r.context}
                    </Link>
                  </TableCell>
                  <TableCell>{r.display_name}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
