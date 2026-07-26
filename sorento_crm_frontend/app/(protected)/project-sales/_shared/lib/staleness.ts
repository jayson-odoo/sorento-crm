/**
 * How the staleness ladder reads on screen (AC-H6).
 *
 * The wording is the feature. A badge saying "30d quiet" is a fact nobody can act on; one
 * saying "Unattended - open to takeover" tells the reader what changed and what they may now
 * do about it. The three rungs therefore get three different sentences, not three shades of
 * the same one.
 *
 * The level is READ from the server, never recomputed here. The daily sweep is what decides
 * a rung and what notified the owner, so a UI doing its own arithmetic could disagree with
 * the email in somebody's inbox - and the UI would be the one that looks broken.
 */
import type { Project } from '../types/project.types';

export type StaleTone = 'none' | 'notice' | 'warning' | 'critical';

export interface StalenessDescription {
  level: number;
  /** Short badge label. */
  label: string;
  /** One sentence: why it is on this rung, and what happens next. */
  detail: string;
  tone: StaleTone;
}

function reasonPhrase(project: Pick<Project, 'stale_reason' | 'days_since_last_activity'>): string {
  if (project.stale_reason === 'overdue_task') {
    return 'its next action is overdue';
  }
  const days = project.days_since_last_activity;
  return typeof days === 'number' ? `nobody has touched it for ${days} days` : 'it has gone quiet';
}

export function describeStaleness(
  project: Pick<
    Project,
    'stale_level' | 'stale_reason' | 'stale_since' | 'days_since_last_activity'
  >,
): StalenessDescription | null {
  const level = Number(project.stale_level ?? 0);
  if (!level) return null;
  const why = reasonPhrase(project);

  if (level === 1) {
    return {
      level,
      label: 'Needs an update',
      detail: `Flagged because ${why}. Log what happened, or set the next action.`,
      tone: 'notice',
    };
  }
  if (level === 2) {
    return {
      level,
      label: 'Falling behind',
      detail: `Flagged because ${why}. Management has been copied. Update it or hand it over.`,
      tone: 'warning',
    };
  }
  return {
    level,
    label: 'Unattended',
    detail: `Flagged because ${why}. Colleagues can now ask to take it over. Nothing has been reassigned - a manager decides.`,
    tone: 'critical',
  };
}

/** Badge classes per rung. Amber escalates to destructive only at Unattended, so the
 *  strongest colour on the board still means the strongest thing. */
export const STALE_TONE_CLASS: Record<Exclude<StaleTone, 'none'>, string> = {
  notice: 'text-amber-700 border-amber-300',
  warning: 'text-amber-800 border-amber-500',
  critical: 'text-destructive border-destructive/60',
};
