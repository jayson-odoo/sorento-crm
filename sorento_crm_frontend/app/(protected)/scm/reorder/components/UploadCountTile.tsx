/**
 * One figure with its label. Shared by every SCM upload dialog so the diffs read alike.
 *
 * The implementation moved to `components/common/CountTile` when the customer importer
 * needed the same tile: one tile, two import families, no drift. This file stays as the
 * import site the SCM dialogs already use.
 */
export { CountTile, default } from '@/components/common/CountTile';
