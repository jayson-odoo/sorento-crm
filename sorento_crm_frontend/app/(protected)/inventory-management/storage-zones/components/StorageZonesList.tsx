'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useQuery } from '@tanstack/react-query';
import { getStorageZonesTree } from '../services/storageZoneService';
import StorageZoneTree from './StorageZoneTree';
import StorageZoneForm from './StorageZoneForm';

export default function StorageZonesList() {
  const [formOpen, setFormOpen] = useState(false);
  const { data: zones, isLoading } = useQuery({
    queryKey: ['storage-zones-tree'],
    queryFn: () => getStorageZonesTree(),
    staleTime: 1000 * 60 * 5,
    retry: 1,
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Storage Zones</CardTitle>
            <Button onClick={() => setFormOpen(true)}>
              <Plus className="size-4" />
              Create Zone
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">Loading zones...</div>
          ) : (
            <StorageZoneTree zones={zones || []} />
          )}
        </CardContent>
      </Card>

      <StorageZoneForm open={formOpen} onOpenChange={setFormOpen} />
    </div>
  );
}
