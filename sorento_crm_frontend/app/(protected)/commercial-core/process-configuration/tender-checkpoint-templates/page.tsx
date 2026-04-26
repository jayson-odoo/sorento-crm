'use client';

import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { listCheckpointTemplates } from '../services/checkpointTemplateService';

export default function CheckpointTemplatesPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['commercial-checkpoint-templates'],
    queryFn: () => listCheckpointTemplates(1, 100),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Tender checkpoint templates</CardTitle>
        <Button asChild size="sm">
          <Link href="/commercial-core/process-configuration/tender-checkpoint-templates/new">
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
                <TableHead>Active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(data?.data || []).map((r) => (
                <TableRow key={r.checkpoint_code}>
                  <TableCell>
                    <Link
                      className="text-primary hover:underline"
                      href={`/commercial-core/process-configuration/tender-checkpoint-templates/${encodeURIComponent(r.checkpoint_code)}/edit`}
                    >
                      {r.checkpoint_code}
                    </Link>
                  </TableCell>
                  <TableCell>{r.name}</TableCell>
                  <TableCell>{r.is_active ? 'Yes' : 'No'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
