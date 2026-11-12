/** A price tag request's customers (PRICETAG-REQUEST-LAYOUT): how one is keyed and labelled. */
import type { RequestCustomer } from '@/app/(auth)/portal/lib/price-tag-request-service';

/** The key a customer is picked by: its code, or its name when it has none. */
export function customerKey(customer: RequestCustomer): string {
  return customer.code || customer.name;
}

/** "First customer", or "First customer +2" for a request with three. */
export function customersLabel(customers: RequestCustomer[]): string | null {
  if (customers.length === 0) return null;
  const more = customers.length - 1;
  return more > 0 ? `${customers[0].name} +${more}` : customers[0].name;
}

/** A request's customers; one saved before the list existed reads as its one debtor. */
export function requestCustomers(request: {
  customers?: RequestCustomer[] | null;
  debtor_code?: string | null;
  debtor_name?: string | null;
}): RequestCustomer[] {
  if (request.customers) return request.customers;
  return request.debtor_name ? [{ code: request.debtor_code ?? null, name: request.debtor_name }] : [];
}
