export const NAV_ITEMS = [
  { href: '/', label: 'Overview', icon: '◫' },
  { href: '/sources', label: 'Data sources', icon: '▤' },
  { href: '/quality', label: 'Quality checks', icon: '◉' },
  { href: '/approvals', label: 'Approvals', icon: '◇' },
];

export function isNavActive(href, pathname) {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function sourceVersions(sources) {
  const ordered = [...sources].sort((left, right) => new Date(left.created_at).getTime() - new Date(right.created_at).getTime());
  const counts = new Map();
  const versions = new Map();
  for (const source of ordered) {
    const version = (counts.get(source.filename) || 0) + 1;
    counts.set(source.filename, version);
    versions.set(source.id, version);
  }
  return versions;
}

export function profileWarnings(source) {
  const columns = Object.entries(source.profile?.columns || {});
  const missing = [];
  const repeatedValues = [];
  for (const [name, metrics] of columns) {
    if (metrics.null_count > 0) missing.push({ column: name, count: metrics.null_count });
    const repeated = Math.max(0, source.row_count - metrics.null_count - metrics.distinct_count);
    if (repeated > 0) repeatedValues.push({ column: name, count: repeated });
  }
  return { missing, repeatedValues };
}
