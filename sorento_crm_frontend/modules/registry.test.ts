/**
 * The uninstall dialog reads its table list from `MODULE_REGISTRY`, not from the JSON file.
 *
 * A `modules/<key>/purge_tables.json` that nobody imports is inert: the App Store shows the
 * module as having no automated purge, the operator is told their data will be left behind,
 * and the file sits there looking correct. That is the failure this pins - the wiring, not
 * the contents.
 */
import { describe, expect, it } from 'vitest';

import projectsPurgeTables from './projects/purge_tables.json';
import { MODULE_REGISTRY, modulePurgeTables, modulesWithDataPurge } from './registry';

describe('module registry purge manifests', () => {
  it('exposes the projects module as one with an automated data purge', () => {
    expect(modulesWithDataPurge()).toContain('projects');
  });

  it('serves the projects table list under its module key', () => {
    const discovered = modulePurgeTables().projects;

    expect(discovered).toBeDefined();
    expect(discovered.tables).toEqual(projectsPurgeTables.tables);
    expect(discovered.description).toBe(projectsPurgeTables.description);
  });

  it('names every table once, so the dialog cannot list one twice', () => {
    for (const entry of MODULE_REGISTRY) {
      if (!entry.purgeTables) continue;
      const { tables } = entry.purgeTables;
      expect(new Set(tables).size, `${entry.key} lists a table twice`).toBe(tables.length);
    }
  });

  it('keys every manifest by the module it belongs to', () => {
    for (const entry of MODULE_REGISTRY) {
      if (!entry.purgeTables) continue;
      expect(entry.purgeTables.moduleKey).toBe(entry.key);
    }
  });
});
