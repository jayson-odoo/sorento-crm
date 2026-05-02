// Resolve a k6 `scenarios` block by PROFILE env var.
// Usage in a scenario script:
//   import { resolveOptions } from '../../profiles/index.js';
//   import { standard } from '../../lib/thresholds.js';
//   export const options = resolveOptions({ exec: 'default', thresholds: standard });

import { smoke } from './smoke.js';
import { load } from './load.js';
import { stress } from './stress.js';
import { spike } from './spike.js';
import { soak } from './soak.js';

const profiles = { smoke, load, stress, spike, soak };

export function resolveOptions({ exec = 'default', thresholds = {}, scenarioOverrides = {} } = {}) {
  const name = (__ENV.PROFILE || 'smoke').toLowerCase();
  const factory = profiles[name];
  if (!factory) {
    throw new Error(`unknown PROFILE=${name}; expected smoke|load|stress|spike|soak`);
  }
  const scenarios = factory({ exec, ...scenarioOverrides });
  return { scenarios, thresholds };
}
