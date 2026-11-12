/**
 * Test stand-in for `RequestCustomersSelect` (use: `vi.mock('@/components/dealer-kit/RequestCustomersSelect')`).
 * A native single `<select>` labelled "Customer", so `selectOption('Customer', code)` picks one
 * customer the way the form's suites picked the old single select. The real chips are covered
 * by `RequestCustomersSelect.test.tsx`.
 */
import type {
  DebtorOption,
  RequestCustomer,
} from '@/app/(auth)/portal/lib/price-tag-request-service';

export function RequestCustomersSelect(props: {
  value: RequestCustomer[];
  options: DebtorOption[];
  onChange: (customers: RequestCustomer[]) => void;
}) {
  const first = props.value[0];
  return (
    <select
      aria-label="Customer"
      value={first ? first.code || first.name : ''}
      onChange={(e) => {
        const d = props.options.find((o) => o.code === e.target.value);
        props.onChange(d ? [{ code: d.code, name: d.name }] : []);
      }}
    >
      <option value="" />
      {props.options.map((o) => (
        <option key={o.code} value={o.code}>
          {o.name}
        </option>
      ))}
    </select>
  );
}
