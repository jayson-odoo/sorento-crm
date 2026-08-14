/**
 * One figure with its label.
 *
 * Every upload dialog reports what a file would do as a row of these, so the diffs
 * read alike whichever importer the user is in. Started life in the SCM upload
 * dialogs; lives here now that the customer importer needs the same tile.
 */
export function CountTile({ label, value }: { label: string; value: number }) {
  return (
    <div data-slot="count-tile" className="rounded-lg border border-border px-3 py-2">
      <div className="text-lg font-semibold tabular-nums leading-tight">
        {value.toLocaleString()}
      </div>
      <div className="text-2xs text-muted-foreground">{label}</div>
    </div>
  );
}

export default CountTile;
