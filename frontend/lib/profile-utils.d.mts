export type ProfileColumn = { inferred_type: string; null_count: number; distinct_count: number };
export type ProfiledSource = { id: string; filename: string; row_count: number; created_at: string; profile: { columns: Record<string, ProfileColumn> } };
export const NAV_ITEMS: { href: string; label: string; icon: string }[];
export function isNavActive(href: string, pathname: string): boolean;
export function sourceVersions(sources: ProfiledSource[]): Map<string, number>;
export function profileWarnings(source: ProfiledSource): { missing: { column: string; count: number }[]; repeatedValues: { column: string; count: number }[] };
