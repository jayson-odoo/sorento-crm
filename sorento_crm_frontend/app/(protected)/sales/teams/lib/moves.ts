import type { SalesTeamAgentOption } from '../types/salesTeam.types';

/**
 * Picked agents who are in ANOTHER team now, so a save moves them (owner ruling
 * 26 Sep 06:09, T2). Moves on is asked for only when this is not empty (UAC S6-15).
 * `teamId` null is a team that does not exist yet, where every placed agent is moving.
 */
export function agentsMovingIn(
  pickedIds: readonly string[],
  options: readonly SalesTeamAgentOption[],
  teamId: string | null,
): SalesTeamAgentOption[] {
  const picked = new Set(pickedIds);
  return options.filter((o) => picked.has(o.id) && o.team_id !== null && o.team_id !== teamId);
}

/** `SEAN I - Sean Lee (now in Central)`; `(no team)`; no note for this team's own agents. */
export function agentOptionLabel(option: SalesTeamAgentOption, teamId: string | null): string {
  if (option.team_id === null) return `${option.label} (no team)`;
  if (option.team_id === teamId) return option.label;
  return `${option.label} (now in ${option.team_name})`;
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** `2026-10-14` -> `Left 14 Oct`. A calendar date, so no timezone conversion applies. */
export function leftLabel(validTo: string): string {
  const [, month, day] = validTo.split('-').map(Number);
  return `Left ${day} ${MONTHS[month - 1]}`;
}
