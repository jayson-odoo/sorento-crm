/** One figure with its label. Shared by every SCM upload dialog so the diffs read alike. */
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
