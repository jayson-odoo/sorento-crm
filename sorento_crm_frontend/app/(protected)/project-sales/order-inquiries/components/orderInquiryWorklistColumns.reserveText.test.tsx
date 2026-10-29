import { describe, expect, it } from 'vitest';
import { reserveTextOfRows } from './orderInquiryWorklistColumns';

// OI-AUTO-CONFIRM review round 2 (AC-AC-10b): each reserve prints its own warehouse label
// beside its own quantity, never one summed quantity after several labels.
describe('reserveTextOfRows', () => {
  it('prints one reserve as "Reserved @ BRW 3"', () => {
    expect(reserveTextOfRows([{ reserve_label: 'Reserved @ BRW', reserved_qty: '3' }])).toBe(
      'Reserved @ BRW 3',
    );
  });

  it('prints two reserves at two warehouses separately, each with its own qty', () => {
    const text = reserveTextOfRows([
      { reserve_label: 'Reserved @ BRW', reserved_qty: '3' },
      { reserve_label: 'Reserved @ KL', reserved_qty: '2' },
    ]);
    expect(text).toContain('Reserved @ BRW 3');
    expect(text).toContain('Reserved @ KL 2');
    expect(text).not.toContain('5');
  });

  it('returns null when nothing is reserved', () => {
    expect(reserveTextOfRows([{ reserve_label: null, reserved_qty: '0' }])).toBeNull();
  });
});
