export type LookupListName =
  | 'category'
  | 'file_type'
  | 'sales_channel'
  | 'spec'
  | 'brand'
  | 'promotion_kind'
  | 'location'
  | 'salesperson'
  | 'customer';

export type WordHome = 'label' | 'code' | 'class' | 'alias_column' | 'alias_set' | 'description';

export interface EmbeddingsOverview {
  setting: { provider: string; model: string; backfill_rpm: number };
  records_search_model: string;
  lookup: { texts_total: number; texts_with_vector: number };
  records: { source_type: string; documents: number; chunks_by_model: Record<string, number> }[];
  guard: { target_model: string; ready: boolean; remaining: number; failed: number; running?: boolean };
}

export interface LookupWord {
  text: string;
  home: WordHome | null;
  has_vector: boolean;
}

export interface LookupWordRow {
  key: string;
  label: string;
  source: string;
  group: string | null;
  words: LookupWord[];
}

export interface LookupWordsResponse {
  list: string;
  rows: LookupWordRow[];
}

export interface TryCell {
  score: number;
  text: string | null;
  home: WordHome | null;
}

export interface TryCandidate {
  list: string;
  key: string;
  label: string;
  spelling: TryCell;
  vector: TryCell | null;
  partial: number;
  floors: { spell: number; partial: number; meaning: number };
  passed: boolean;
  signal: string;
}

export interface TryResult {
  verdict: 'resolved' | 'ambiguous' | 'unresolved';
  candidates: TryCandidate[];
}

export type BackfillAction = 'start' | 'stop';
