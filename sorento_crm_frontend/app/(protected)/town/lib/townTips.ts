import type { TownShop, TownSnapshot } from '@/types/town.types';
import { count, rm0, shopLabel } from './townFormat';

/** What the pointer is over. A mouse shows its tooltip; a tap on touch opens the lightbox instead. */
export type TipSubject =
  | { kind: 'sales' }
  | { kind: 'shop'; shop: TownShop }
  | { kind: 'warehouse'; index: number }
  | { kind: 'low' }
  | { kind: 'deliver' }
  | { kind: 'approve' }
  | { kind: 'port' };

/** The hover tooltip: the thing's name and its one key number (TOWN-V2 rule 1). */
export function townTip(snapshot: TownSnapshot, subject: TipSubject): { title: string; detail: string } {
  const { today, reorder, deliveries, approvals, incoming } = snapshot;
  switch (subject.kind) {
    case 'sales':
      return {
        title: "Today's sales",
        detail: today.amount != null
          ? `${rm0(today.amount)} · ${count(today.invoice_count)} invoices`
          : `${count(today.invoice_count)} invoices`,
      };
    case 'shop': {
      const { shop } = subject;
      const detail = !shop.today_docs
        ? 'No invoice today'
        : shop.today_amount
          ? `${rm0(shop.today_amount)} today`
          : `${shop.today_docs} invoice${shop.today_docs === 1 ? '' : 's'} today`;
      return { title: shopLabel(shop), detail };
    }
    case 'warehouse': {
      const warehouse = snapshot.warehouses[subject.index];
      return { title: `Warehouse ${warehouse?.pool ?? ''}`.trim(), detail: `${count(warehouse?.on_hand ?? 0)} on hand` };
    }
    case 'low':
      return { title: 'Low stock', detail: `${count(reorder.below_count)} products below reorder level` };
    case 'deliver':
      return { title: 'Depot', detail: `${deliveries ? count(deliveries.to_deliver) : '-'} sales orders to deliver` };
    case 'approve':
      return { title: 'Approvals', detail: approvals.total ? `${approvals.total} waiting for a decision` : 'All clear' };
    case 'port': {
      const total = incoming ? incoming.incoming + incoming.late : 0;
      return {
        title: 'Port',
        detail: incoming && total
          ? `${count(incoming.incoming)} incoming${incoming.late ? ` · ${count(incoming.late)} late` : ''}`
          : 'Nothing on the way',
      };
    }
  }
}
