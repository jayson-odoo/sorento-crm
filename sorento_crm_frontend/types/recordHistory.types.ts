/**
 * STANDARD-HISTORY: one entry of a record's History tab (`components/history/RecordHistory`).
 * The backend sends it already merged and in plain words; a batch press is ONE event whose
 * `lines` name every row it touched. Ids are React keys only, never shown (no UUIDs in the UI).
 */
export interface RecordHistoryLine {
  row_id: string;
  so_line_no: number | null;
  item_code: string | null;
  qty: number | null;
  change: string;
}

export interface RecordHistoryEvent {
  id: string;
  kind: string;
  at: string | null;
  actor: string | null;
  title: string;
  lines: RecordHistoryLine[];
}
