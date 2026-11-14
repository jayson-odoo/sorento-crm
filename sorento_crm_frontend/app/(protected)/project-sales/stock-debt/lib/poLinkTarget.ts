import { SNAPSHOTS_KEY } from '../hooks/useStockDebtSnapshots';
import {
  changePoLines,
  getPoLinkOptions,
  linkPoLines,
  relocatePoLine,
  resumePoLink,
  relinkPoLines,
  unlinkPoLines,
} from '../services/stockDebtSnapshotService';
import type { PoLinkTarget } from '../../_shared/po-link/poLink.types';

/** The PO link calls of one Stock Debt snapshot row. */
export function snapshotPoLinkTarget(snapshotId: string, rowId: string): PoLinkTarget {
  return {
    key: [...SNAPSHOTS_KEY, 'po-link', snapshotId, rowId],
    api: {
      options: () => getPoLinkOptions(snapshotId, rowId),
      link: (lines) => linkPoLines(snapshotId, rowId, lines),
      unlink: (ids) => unlinkPoLines(snapshotId, rowId, ids),
      change: (changes) => changePoLines(snapshotId, rowId, changes),
      relocate: (poLineId) => relocatePoLine(poLineId),
      resume: (input) => resumePoLink(input),
      relink: (moves) => relinkPoLines(snapshotId, rowId, moves),
    },
    refresh: (queryClient) => {
      queryClient.invalidateQueries({ queryKey: [...SNAPSHOTS_KEY, 'lines', snapshotId] });
    },
  };
}
