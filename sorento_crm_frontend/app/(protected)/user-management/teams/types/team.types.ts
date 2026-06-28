export interface TeamMemberPreview {
  user_id: string;
  name: string;
}

export interface Team {
  id: string;
  name: string;
  description?: string | null;
  parent_team_id?: string | null;
  created_at: string;
  member_count?: number;
  members?: TeamMemberPreview[];
}

export interface TeamMember {
  id: string;
  team_id: string;
  user_id: string;
  sort_order: number | null;
  include_in_round_robin: boolean;
  created_at: string;
}

export interface TeamCreatePayload {
  name: string;
  description?: string | null;
  parent_team_id?: string | null;
}

export interface TeamUpdatePayload {
  name?: string;
  description?: string | null;
  parent_team_id?: string | null;
}

export interface TeamAddMemberPayload {
  user_id: string;
  sort_order?: number | null;
  include_in_round_robin?: boolean;
}

export interface TeamMemberUpdatePayload {
  include_in_round_robin: boolean;
}
