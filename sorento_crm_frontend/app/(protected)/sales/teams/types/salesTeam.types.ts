/**
 * Sales teams as `/api/v1/sales/teams` serialises them (plan 3.8; UAC S6-1, S6-14, S6-15).
 * Dates are `YYYY-MM-DD` strings, datetimes naive UTC.
 */
export interface SalesTeamAgentRef {
  sales_agent_id: string;
  /** `ALI - Ali Hassan`: code and name, never an id. */
  label: string;
}

export interface SalesTeamListItem {
  id: string;
  name: string;
  is_active: boolean;
  /** One of `members` (W1), or null when the team has no leader. */
  leader_sales_agent_id: string | null;
  member_count: number;
  members: SalesTeamAgentRef[];
  created_at: string | null;
  updated_at: string | null;
}

export interface SalesTeamMember {
  sales_agent_id: string;
  code: string;
  name: string | null;
  label: string;
  /** Empty = from the beginning (the agent's first team). */
  valid_from: string | null;
  /** The last day that counts for this team; empty = still in it. */
  valid_to: string | null;
  /** Left on or before the date shown: drawn muted with a "Left <date>" pill. */
  left: boolean;
}

export interface SalesTeamMove {
  sales_agent_id: string;
  label: string;
  from_team_id: string;
  from_team_name: string;
}

export interface SalesTeamDetail {
  id: string;
  name: string;
  is_active: boolean;
  /** The leader now, one of the team's agents (W1); null when none is picked. */
  leader_sales_agent_id: string | null;
  leader_label: string | null;
  /** Members on the date shown, not counting those who left. */
  member_count: number;
  on: string;
  members: SalesTeamMember[];
  /** Agents the last write moved out of another team. */
  moved: SalesTeamMove[];
  created_at: string | null;
  updated_at: string | null;
}

export interface SalesTeamAgentOption {
  id: string;
  code: string;
  label: string;
  /** The team the agent is in now. */
  team_id: string | null;
  team_name: string | null;
}

export interface SalesTeamCreatePayload {
  name: string;
  sales_agent_ids: string[];
  is_active?: boolean;
  /** `YYYY-MM-DD`; the day a picked agent from another team starts counting here. */
  moves_on?: string;
  /** One of the agents; one not in `sales_agent_ids` joins the team (W1). */
  leader_sales_agent_id?: string | null;
}

export interface SalesTeamUpdatePayload {
  name?: string;
  is_active?: boolean;
  /** Sent together with the name so the team page's save is one transaction. */
  sales_agent_ids?: string[];
  moves_on?: string;
  /** Sent: set the leader, null clearing it. Left out: the leader stays (W1). */
  leader_sales_agent_id?: string | null;
}

export interface SalesTeamMembersPayload {
  sales_agent_ids: string[];
  moves_on?: string;
}

/** What the modal and the team page save: a create, or a rename plus the member list. */
export interface SalesTeamSaveInput {
  teamId: string | null;
  name: string;
  is_active: boolean;
  sales_agent_ids: string[];
  moves_on?: string;
  leader_sales_agent_id?: string | null;
}
