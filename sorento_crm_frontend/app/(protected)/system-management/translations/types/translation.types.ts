/**
 * Translation memory (R15/R16, purchasing consolidation batch, lane C).
 *
 * One row per Chinese -> English phrase, read by the supplier-document upload preview
 * before anything is stored, filled by the AI Assistant's configured model on a miss,
 * and correctable here without ever going near the upload again.
 */

export interface Translation {
  id: string;
  source_text: string;
  source_lang: string;
  target_lang: string;
  target_text: string;
  /** Who said so: a person typed it (`manual`, always wins), or the AI Assistant's
   *  configured model filled a gap the memory had never seen (`ai`). */
  source: 'manual' | 'ai';
  /** A name, never a UUID - null when the AI wrote it, or the writing user is gone. */
  created_by_name: string | null;
  updated_at: string;
  hit_count: number;
}

export interface TranslationUpdateBody {
  target_text: string;
}
