import type { SPOAllocation } from '../types/spoAllocation.types';

/**
 * Where an SPO line's goods are meant to go, in one sentence, for every surface that
 * shows one.
 *
 * A shipping order can name a stock location we do not hold - 6,520 lines of the 2026 book
 * do - so the warehouse is optional and the raw code the book spelled is kept beside it.
 * Showing a dash for those would say "nowhere stated" about a line that stated a place
 * perfectly clearly; showing the code says the truth, which is that we cannot place it.
 *
 * One function because the grid and the grouped table both answer this question, and two
 * copies is how they come to disagree.
 */
export function allocationLocation(
  allocation: Pick<SPOAllocation, 'warehouse' | 'location_code'>,
): string {
  return (
    allocation.warehouse?.warehouse_code ??
    allocation.warehouse?.warehouse_name ??
    allocation.location_code ??
    '-'
  );
}
