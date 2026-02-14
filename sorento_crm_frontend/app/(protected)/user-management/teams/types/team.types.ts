export interface Team {
  id: string;
  name: string;
  description?: string | null;
  created_at: string;
}

export interface TeamMember {
  id: string;
  team_id: string;
  user_id: string;
  sort_order: number | null;
  created_at: string;
}

export interface TeamCreatePayload {
  name: string;
  description?: string | null;
}

export interface TeamUpdatePayload {
  name?: string;
  description?: string | null;
}

export interface TeamAddMemberPayload {
  user_id: string;
  sort_order?: number | null;
}
