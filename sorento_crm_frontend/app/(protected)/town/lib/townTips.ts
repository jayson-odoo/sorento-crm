import { formatDateInMalaysia } from '@/lib/helpers';
import type { TownDueCustomer, TownShipment, TownShop, TownSnapshot } from '@/types/town.types';
import { count, rm0, shopLabel, shortName } from './townFormat';

/** What the pointer is over. A mouse shows its tooltip; a tap on touch opens the lightbox instead. */
export type TipSubject =
  | { kind: 'sales' }
  | { kind: 'shop'; shop: TownShop }
  | { kind: 'warehouse'; index: number }
  | { kind: 'low' }
  | { kind: 'deliver' }
  | { kind: 'approve' }
  | { kind: 'port' }
  | { kind: 'shipment'; row: TownShipment }
  | { kind: 'lorry'; customer: TownDueCustomer };

const orders = (n: number) => `${count(n)} order${n === 1 ? '' : 's'} due today or overdue`;

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
    case 'shipment': {
      const { row } = subject;
      const eta = row.eta ? `ETA ${formatDateInMalaysia(row.eta)}` : 'No ETA';
      return {
        title: `${row.shipment_number ?? 'Shipment'}${row.late ? ' · late' : ' on the water'}`,
        detail: [eta, `${count(row.products)} products`, row.supplier].filter(Boolean).join(' · '),
      };
    }
    case 'lorry': {
      const { customer } = subject;
      if (customer.key === null) {
        // a customer with no shop in the town: its name only exists on the personal view
        return {
          title: 'Customer outside the town',
          detail: [customer.name ? shortName(customer.name) : null, orders(customer.orders)].filter(Boolean).join(' · '),
        };
      }
      const shop = snapshot.shops.find((s) => s.key === customer.key);
      return { title: `Lorry to ${shop ? shopLabel(shop) : 'Dealer'}`, detail: orders(customer.orders) };
    }
  }
}
