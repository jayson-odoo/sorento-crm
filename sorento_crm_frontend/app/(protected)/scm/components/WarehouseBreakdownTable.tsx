'use client';

import { EM_DASH, fmtInt, fmtMoney, fmtSigned } from '../lib/format';
import type { NetPositionRow } from '../types/scm.types';
import { StateChip } from './HealthIndicators';

/** Per-warehouse expansion body for an aggregated product row. */
export function WarehouseBreakdownTable({ row }: { row: NetPositionRow }) {
  return (
    <div className="bg-muted/30 px-4 py-3">
      <div className="mb-2 text-2xs font-medium uppercase tracking-wide text-muted-foreground">
        Per-warehouse breakdown
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-2xs text-muted-foreground">
            <th className="py-1 text-left font-medium">Warehouse</th>
            <th className="py-1 text-right font-medium">On hand</th>
            <th className="py-1 text-right font-medium">On order</th>
            <th className="py-1 text-right font-medium">Committed</th>
            <th className="py-1 text-right font-medium">Net position</th>
            <th className="py-1 text-right font-medium">Valuation</th>
            <th className="py-1 pl-4 text-left font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {row.warehouses.map((w) => (
            <tr key={w.warehouse_code} className="border-t border-border/60">
              <td className="py-1.5 pr-2">{w.warehouse_name}</td>
              <td className="py-1.5 text-right tabular-nums">{fmtInt(w.on_hand)}</td>
              <td className="py-1.5 text-right tabular-nums">{fmtInt(w.on_order)}</td>
              <td className="py-1.5 text-right tabular-nums">{fmtInt(w.committed)}</td>
              <td
                className={`py-1.5 text-right font-medium tabular-nums ${
                  w.net_position < 0 ? 'text-scm-stockout' : ''
                }`}
              >
                {fmtSigned(w.net_position)}
              </td>
              <td className="whitespace-nowrap py-1.5 text-right tabular-nums text-muted-foreground">
                {w.stock_valuation === null ? EM_DASH : fmtMoney(w.stock_valuation)}
              </td>
              <td className="py-1.5 pl-4">
                <StateChip state={w.status} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {row.imbalance ? (
        <div className="mt-2 text-2xs text-scm-stockout">
          Imbalance: one warehouse is stocked out while another holds surplus - a network
          transfer may clear the shortage without buying.
        </div>
      ) : null}
    </div>
  );
}
