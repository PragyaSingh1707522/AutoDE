export type Role = 'owner' | 'analyst' | 'viewer';
export type Identity = { user: { id: string; email: string }; organization: { id: string; name: string }; role: Role };
export type ProfileColumn = { inferred_type: string; null_count: number; distinct_count: number };
export type Source = { id: string; filename: string; row_count: number; created_at: string; profile: { row_count: number; columns: Record<string, ProfileColumn> } };
export type Approval = { id: string; source_id: string; action: string; status: string; reason: string };
