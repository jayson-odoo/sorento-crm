/**
 * Text glossary (S2, text glossary lane): one row per phrase Jayson has typed the
 * English for, source-first (the supplier's own wording, e.g. `连体马桶`) -> target
 * (`One-piece toilet`). Locale is `en` throughout slice 1 (R9) and is not shown on this
 * page - it appears only once a second target language exists.
 */
export interface TextGlossaryEntry {
  id: string;
  source_text: string;
  translation: string;
  /** A person typed it (`manual`, always wins) - `ai` is a later trigger (R6/plan "Not
   *  built"), never produced by this slice. */
  source: 'manual' | 'ai';
  /** A name, never a UUID - null when the writing user is gone. */
  created_by_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface TextGlossaryUpsertBody {
  source_text: string;
  translation: string;
}
