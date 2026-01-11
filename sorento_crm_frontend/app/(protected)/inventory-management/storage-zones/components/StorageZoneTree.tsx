'use client';

import { useState } from 'react';
import { ChevronRight, ChevronDown, Package } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import type { StorageZoneTreeItem } from '../types/storageZone.types';

interface StorageZoneTreeProps {
  zones: StorageZoneTreeItem[];
  level?: number;
}

const zoneTypeColors: Record<string, string> = {
  shelf: 'bg-blue-100 text-blue-800',
  rack: 'bg-green-100 text-green-800',
  bin: 'bg-yellow-100 text-yellow-800',
  pallet: 'bg-purple-100 text-purple-800',
};

export default function StorageZoneTree({ zones, level = 0 }: StorageZoneTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const groupedByWarehouse = zones.reduce((acc, zone) => {
    const warehouseId = zone.warehouse_id;
    if (!acc[warehouseId]) {
      acc[warehouseId] = {
        warehouse: zone.warehouse,
        zones: [],
      };
    }
    acc[warehouseId].zones.push(zone);
    return acc;
  }, {} as Record<string, { warehouse?: { id: string; warehouse_name: string }; zones: StorageZoneTreeItem[] }>);

  return (
    <div className="space-y-2">
      {Object.entries(groupedByWarehouse).map(([warehouseId, { warehouse, zones: warehouseZones }]) => {
        const isExpanded = expanded[warehouseId];
        return (
          <div key={warehouseId}>
            <div className="flex items-center gap-2 py-2 hover:bg-accent rounded-md px-2 group">
              <Button
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0"
                onClick={() => toggleExpand(warehouseId)}
              >
                {isExpanded ? (
                  <ChevronDown className="size-4" />
                ) : (
                  <ChevronRight className="size-4" />
                )}
              </Button>
              <Package className="size-4 text-muted-foreground" />
              <span className="flex-1 font-semibold">{warehouse?.warehouse_name || 'Unknown Warehouse'}</span>
              <Badge variant="secondary" size="sm">
                {warehouseZones.length} zones
              </Badge>
            </div>
            {isExpanded && (
              <div className="ml-8 space-y-1">
                {warehouseZones.map((zone) => (
                  <div
                    key={zone.id}
                    className="flex items-center gap-2 py-1.5 hover:bg-accent rounded-md px-2"
                  >
                    <div className="w-6" />
                    <Badge className={zoneTypeColors[zone.zone_type] || 'bg-gray-100 text-gray-800'} size="sm">
                      {zone.zone_type}
                    </Badge>
                    <span className="flex-1 text-sm">{zone.zone_name || zone.zone_code}</span>
                    <span className="text-xs text-muted-foreground">
                      Capacity: {zone.capacity} | Utilization: {zone.utilization || 0}%
                    </span>
                    <div className="opacity-0 group-hover:opacity-100 flex gap-1">
                      <Button variant="ghost" size="sm" className="h-6">
                        Edit
                      </Button>
                      <Button variant="ghost" size="sm" className="h-6">
                        Delete
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
