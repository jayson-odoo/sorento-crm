'use client';

import { useState } from 'react';
import { Card } from '@/components/ui/card';
import type { HealthState, Perspective } from '../types/scm.types';
import {
  EMPTY_SCM_FILTERS,
  type ScmFilters,
} from '../services/scmDashboardService';
import {
  useScmRollups,
  useSuppliers,
  useWarehouseHealth,
} from '../hooks/useScmDashboard';
import { DeadStockSettings } from './DeadStockSettings';
import { PerspectiveToggle } from './PerspectiveToggle';
import { ProductPerspectiveGrid } from './ProductPerspectiveGrid';
import { RollupTiles } from './RollupTiles';
import { ScmFilterBar } from './ScmFilterBar';
import { ScmScopeChip } from './ScmScopeChip';
import { SupplierPerspectiveList } from './SupplierPerspectiveList';
import { WarehouseHealthGrid } from './WarehouseHealthGrid';

export function ScmDashboard() {
  const [perspective, setPerspective] = useState<Perspective>('warehouse');
  const [filters, setFilters] = useState<ScmFilters>({ ...EMPTY_SCM_FILTERS });

  // `overstock` (days-of-cover over the ceiling) is now computed + filtered
  // server-side, so filters flow straight through — no client-side stripping.
  // (`low` / below reorder point is DEFERRED to M3 and can never be set here.)
  const rollups = useScmRollups(filters);
  const warehouses = useWarehouseHealth(filters);
  const suppliers = useSuppliers(filters);

  /** Deep-link into the Product perspective, optionally scoped to a warehouse
   *  and/or a health status. Backs every drill-down / "view in list" action. */
  const viewProducts = (target: { warehouse?: string; status?: HealthState | null }) => {
    setFilters((f) => ({
      ...f,
      warehouses: target.warehouse ? [target.warehouse] : f.warehouses,
      healthStatus: target.status ?? null,
    }));
    setPerspective('product');
  };

  /** Legend chip / stat-card toggle — filters the current perspective to a
   *  status (or clears). Shared state, so legend chips + stat cards agree. */
  const toggleHealth = (state: HealthState) => {
    setFilters((f) => ({ ...f, healthStatus: f.healthStatus === state ? null : state }));
  };

  /** Warehouse-card body toggle: apply → scope to that warehouse + Product
   *  perspective; re-click the same (sole) warehouse → clear + back to the
   *  Warehouse perspective. Idempotent, driven off `filters.warehouses`. */
  const toggleWarehouse = (code: string) => {
    const isSole = filters.warehouses.length === 1 && filters.warehouses[0] === code;
    if (isSole) {
      setFilters((f) => ({ ...f, warehouses: [] }));
      setPerspective('warehouse');
    } else {
      setFilters((f) => ({ ...f, warehouses: [code] }));
      setPerspective('product');
    }
  };

  return (
    <div className="space-y-5">
      {/* Scope transparency — the focused default silently narrows the tiles
          below, so surface the active lifecycle scope + a one-click "Show all". */}
      <ScmScopeChip filters={filters} onChange={setFilters} />

      <RollupTiles
        data={rollups.data}
        isLoading={rollups.isLoading}
        isError={rollups.isError}
        // Drill-down popup base scope — health (incl. overstock) + ABC/XYZ are all
        // filtered server-side, so pass the live filters straight through.
        filters={filters}
        onViewInList={(status) => viewProducts({ status })}
        activeStatus={filters.healthStatus}
        onToggleFilter={toggleHealth}
      />

      <Card className="p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <PerspectiveToggle value={perspective} onChange={setPerspective} />
          <div className="flex items-center gap-2">
            {/* M8-B6: the reorder-planning launch moved to the page header as a
                "Reorder plan" nav button; the dashboard keeps only its settings. */}
            <DeadStockSettings />
          </div>
        </div>
        <div className="mt-4">
          <ScmFilterBar filters={filters} onChange={setFilters} />
        </div>
      </Card>

      {perspective === 'warehouse' ? (
        <WarehouseHealthGrid
          data={warehouses.data?.data}
          isLoading={warehouses.isLoading}
          isError={warehouses.isError}
          onRetry={() => void warehouses.refetch()}
          filters={filters}
          activeState={filters.healthStatus}
          onToggleHealth={toggleHealth}
          activeWarehouses={filters.warehouses}
          onToggleWarehouse={toggleWarehouse}
          onViewProducts={(warehouse, status) => viewProducts({ warehouse, status })}
        />
      ) : null}

      {perspective === 'product' ? (
        <ProductPerspectiveGrid
          filters={filters}
          onToggleHealth={toggleHealth}
        />
      ) : null}

      {perspective === 'supplier' ? (
        <SupplierPerspectiveList
          data={suppliers.data?.data}
          isLoading={suppliers.isLoading}
          isError={suppliers.isError}
          onRetry={() => void suppliers.refetch()}
          activeState={filters.healthStatus}
          onToggleHealth={toggleHealth}
        />
      ) : null}
    </div>
  );
}
