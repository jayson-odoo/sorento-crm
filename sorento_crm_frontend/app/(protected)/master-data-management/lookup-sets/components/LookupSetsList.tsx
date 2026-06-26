'use client';
import { useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import { ScrollArea, ScrollBar } from '@/components/ui/scroll-area';
import { useLookupSets } from '../hooks/useLookupSets';
import LookupSetTable from './LookupSetTable';
import LookupSetFormDialog from './LookupSetFormDialog';

export default function LookupSetsList() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState('');
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | undefined>();

  const { data, isLoading } = useLookupSets({
    pageIndex: 0,
    pageSize: 100,
    sorting: [{ id: 'name', desc: false }],
    searchQuery,
  });

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative">
            <Search className="size-4 text-muted-foreground absolute start-3 top-1/2 -translate-y-1/2" />
            <Input
              placeholder="Search lookup sets..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="ps-9 w-64"
            />
          </div>
          <Button
            onClick={() => {
              setEditingId(undefined);
              setFormOpen(true);
            }}
          >
            <Plus className="size-4" /> Add lookup set
          </Button>
        </CardHeader>
        <CardTable>
          {isLoading ? (
            <div className="py-12 text-center text-muted-foreground">Loading…</div>
          ) : (
            <ScrollArea>
              <LookupSetTable
                rows={data?.data ?? []}
                onView={(s) => router.push(`/master-data-management/lookup-sets/${s.id}`)}
                onEdit={(s) => {
                  setEditingId(s.id);
                  setFormOpen(true);
                }}
              />
              <ScrollBar orientation="horizontal" />
            </ScrollArea>
          )}
        </CardTable>
      </Card>
      <LookupSetFormDialog open={formOpen} onOpenChange={setFormOpen} setId={editingId} />
    </>
  );
}
