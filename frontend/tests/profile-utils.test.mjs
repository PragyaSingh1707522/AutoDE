import test from 'node:test';
import assert from 'node:assert/strict';
import { isNavActive, profileWarnings, sourceVersions } from '../lib/profile-utils.mjs';

test('navigation marks overview exactly and nested source details as active', () => {
  assert.equal(isNavActive('/', '/'), true);
  assert.equal(isNavActive('/', '/sources'), false);
  assert.equal(isNavActive('/sources', '/sources/abc'), true);
});

test('source versions follow upload time for each filename', () => {
  const versions = sourceVersions([
    { id: 'new', filename: 'people.csv', created_at: '2026-02-02T00:00:00Z' },
    { id: 'other', filename: 'visits.csv', created_at: '2026-02-01T00:00:00Z' },
    { id: 'old', filename: 'people.csv', created_at: '2026-01-01T00:00:00Z' },
  ]);
  assert.equal(versions.get('old'), 1);
  assert.equal(versions.get('new'), 2);
  assert.equal(versions.get('other'), 1);
});

test('quality warnings only report missing and repeated values present in profile metrics', () => {
  const warnings = profileWarnings({ row_count: 5, profile: { columns: {
    id: { inferred_type: 'integer', null_count: 0, distinct_count: 4 },
    note: { inferred_type: 'string', null_count: 2, distinct_count: 2 },
    blank: { inferred_type: 'string', null_count: 5, distinct_count: 0 },
  } } });
  assert.deepEqual(warnings.missing, [{ column: 'note', count: 2 }, { column: 'blank', count: 5 }]);
  assert.deepEqual(warnings.repeatedValues, [{ column: 'id', count: 1 }, { column: 'note', count: 1 }]);
});
