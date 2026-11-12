import { formatDateInMalaysia } from '@/lib/helpers';
import type { TownDueCustomer, TownShipment, TownShop, TownSite, TownSnapshot, TownTradingHouse } from '@/types/town.types';
import { count, rm0, shopLabel, shortName } from './townFormat';
import { LOOK_WORDS, siteLook, siteTitle, stageLabel } from './townMap';

/** What the pointer is over. A mouse shows its tooltip; a tap on touch opens the lightbox instead. */
export type TipSubject =
  | { kind: 'sales' }
  | { kind: 'bought'; others: number }
  | { kind: 'shop'; shop: TownShop }
  | { kind: 'warehouse'; index: number }
  | { kind: 'low' }
  | { kind: 'deliver' }
  | { kind: 'approve' }
  | { kind: 'port' }
  | { kind: 'shipment'; row: TownShipment }
  | { kind: 'lorry'; customer: TownDueCustomer }
  | { kind: 'site'; site: TownSite }
  | { kind: 'trading_house'; row: TownTradingHouse }
  | { kind: 'projects' }
  | { kind: 'state'; name: string; detail: string }
  | { kind: 'project_lorry'; state: string }
  | { kind: 'coaster' };

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
    case 'bought':
      return { title: 'Bought today', detail: `${count(subject.others)} more dealers invoiced today` };
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
    case 'site': {
      const { site } = subject;
      return {
        title: siteTitle(site),
        detail: `${stageLabel(site)}${site.final_negotiation ? ', final negotiation' : ''} · ${LOOK_WORDS[siteLook(site, snapshot.day)]}`,
      };
    }
    case 'trading_house': {
      const { row } = subject;
      return {
        title: row.name ?? 'Trading house',
        detail: `${count(row.open_projects)} open project${row.open_projects === 1 ? '' : 's'} · ${row.today_docs ? 'bought today' : 'no project invoice today'}`,
      };
    }
    case 'projects': {
      const p = snapshot.projects;
      return { title: 'Open projects', detail: p ? `${count(p.open_count)} open · ${count(p.dormant)} dormant` : 'None' };
    }
    case 'state':
      return { title: subject.name, detail: subject.detail || 'Nothing here today' };
    case 'project_lorry':
      return { title: 'Lorry to a project', detail: `Project orders to ${subject.state}` };
    case 'coaster':
      return { title: 'Coaster', detail: 'Port Klang · Sabah, Sarawak, Labuan' };
  }
}
