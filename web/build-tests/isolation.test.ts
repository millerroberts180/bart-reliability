// Each production build contains only its own data mode's prediction client and that
// client's data: vite.config.ts resolves '@data-mode' to src/modes/<mode>.tsx alone. These
// tests make the three builds as `npm run build` does (without the type check), into
// temporary directories, and fail if another mode's modules, chunks, strings or data
// appear in a build. Run with: npm run test:build

import { execFile } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { promisify } from 'node:util';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

const WEB = path.resolve(import.meta.dirname, '..');
const MODES = ['mock', 'http', 'static'] as const;
type Mode = (typeof MODES)[number];

// Every build is given this API address; only the HTTP build may contain it.
const API_ADDRESS = 'http://127.0.0.1:8000';
const BASE_PATH = '/bart-reliability/';

/** Source modules that belong to one mode alone. */
const MODULES: Record<Mode, string[]> = {
  mock: [
    'src/modes/mock.tsx',
    'src/data/MockPredictionClient.ts',
    'src/data/fixtures/simulated.ts',
    'src/data/fixtures/fullNetwork.ts',
    'src/data/fixtures/network.ts',
    'src/data/fixtures/networkTrains.ts',
  ],
  http: ['src/modes/http.tsx', 'src/data/HttpPredictionClient.ts'],
  static: ['src/modes/static.tsx', 'src/data/StaticReplayClient.ts'],
};

/** Text found only in one mode's client or data. Each is also required in its own build. */
const STRINGS: Record<Mode, string[]> = {
  mock: [
    // The simulated fixtures' made-up alerts, and the simulated client's own messages.
    'Street-to-concourse elevator out of service at MacArthur.',
    'Planned trackwork near Balboa Park may add up to 10 minutes to some trips this evening.',
    'The prediction service did not respond.',
    'The full-network fixture has not loaded.',
  ],
  http: ['/api/v1', 'No API address is configured. Set VITE_API_BASE_URL.', API_ADDRESS],
  static: ['static-replay-1', 'The historical replay could not be loaded.', `${BASE_PATH}replay/`],
};

const REPLAY_DESCRIPTION = 'A historical replay of recorded BART data, with a model';
const SIMULATED_DESCRIPTION = 'shown with simulated data';

interface Build {
  /** Every file, by path relative to the build directory. */
  files: Map<string, Buffer>;
  /** Source modules in each JavaScript chunk (build-tests/buildMode.ts). */
  chunks: { fileName: string; modules: string[] }[];
}

const run = promisify(execFile);
let root = '';
const builds = {} as Record<Mode, Build>;

async function listFiles(dir: string, base = dir): Promise<Map<string, Buffer>> {
  const files = new Map<string, Buffer>();
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) for (const [k, v] of await listFiles(full, base)) files.set(k, v);
    else files.set(path.relative(base, full).split(path.sep).join('/'), await readFile(full));
  }
  return files;
}

async function buildMode(mode: Mode): Promise<Build> {
  const outDir = path.join(root, mode);
  const report = path.join(root, `${mode}.json`);
  // A fresh process with only the settings a build reads, so nothing from the test runner
  // (NODE_ENV=test, its VITE_* values) reaches it.
  await run(process.execPath, ['build-tests/buildMode.ts', outDir, report], {
    cwd: WEB,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, VITE_DATA_MODE: mode, VITE_API_BASE_URL: API_ADDRESS, VITE_BASE_PATH: BASE_PATH },
  });
  const { chunks } = JSON.parse(await readFile(report, 'utf8')) as Pick<Build, 'chunks'>;
  return { files: await listFiles(outDir), chunks };
}

beforeAll(async () => {
  root = await mkdtemp(path.join(tmpdir(), 'eta-reliability-builds-'));
  // One at a time: each build already uses every core.
  for (const mode of MODES) builds[mode] = await buildMode(mode);
}, 300_000);

afterAll(async () => {
  if (root) await rm(root, { recursive: true, force: true });
});

const textOf = (build: Build) =>
  [...build.files].filter(([name]) => !name.endsWith('.woff2')).map(([name, body]) => ({ name, text: body.toString('utf8') }));
const modulesOf = (build: Build) => new Set(build.chunks.flatMap((c) => c.modules));
const others = (mode: Mode) => MODES.filter((m) => m !== mode);

describe.each(MODES)('the %s build', (mode) => {
  it('bundles its own client modules and none of another mode’s', () => {
    const modules = modulesOf(builds[mode]);
    for (const own of MODULES[mode]) expect(modules, own).toContain(own);
    for (const other of others(mode)) for (const foreign of MODULES[other]) expect(modules, foreign).not.toContain(foreign);
    // The development state selector is never shipped.
    expect([...modules].filter((m) => m.startsWith('src/dev/'))).toEqual([]);
    // The API decoders serve the HTTP and static clients only.
    expect(modules.has('src/data/apiDecode.ts')).toBe(mode !== 'mock');
  });

  it('has only its own chunks: the page, plus the full-network fixture for mock', () => {
    const scripts = [...builds[mode].files.keys()].filter((f) => f.endsWith('.js')).sort();
    const expected = mode === 'mock' ? [/^assets\/fullNetwork-[\w-]+\.js$/, /^assets\/index-[\w-]+\.js$/] : [/^assets\/index-[\w-]+\.js$/];
    expect(scripts).toHaveLength(expected.length);
    scripts.forEach((script, i) => expect(script).toMatch(expected[i] as RegExp));
    expect(builds[mode].chunks.map((c) => c.fileName).sort()).toEqual(scripts);
  });

  it('contains its own distinctive strings and no other mode’s', () => {
    const texts = textOf(builds[mode]);
    const found = (s: string) => texts.filter((t) => t.text.includes(s)).map((t) => t.name);
    for (const own of STRINGS[mode]) expect(found(own), own).not.toEqual([]);
    for (const other of others(mode)) for (const foreign of STRINGS[other]) expect(found(foreign), foreign).toEqual([]);
    expect(found('Dev · preview state')).toEqual([]);
  });

  it('contains no local or API address unless it is the HTTP build', () => {
    const texts = textOf(builds[mode]);
    const addresses = texts.filter((t) => /localhost|127\.0\.0\.1|0\.0\.0\.0/.test(t.text)).map((t) => t.name);
    expect(addresses).toEqual(mode === 'http' ? [expect.stringMatching(/^assets\/index-[\w-]+\.js$/)] : []);
  });

  it('describes its own data in index.html', () => {
    const html = builds[mode].files.get('index.html')?.toString('utf8') ?? '';
    expect(html.includes(SIMULATED_DESCRIPTION)).toBe(mode === 'mock');
    expect(html.includes(REPLAY_DESCRIPTION)).toBe(mode !== 'mock');
  });

  it(mode === 'static' ? 'ships the published replay, byte for byte' : 'ships no replay or other data files', async () => {
    const json = [...builds[mode].files.keys()].filter((f) => f.endsWith('.json'));
    if (mode !== 'static') {
      expect(json).toEqual([]);
      return;
    }
    const published = await listFiles(path.join(WEB, 'public'));
    expect(json.sort()).toEqual([...published.keys()].sort());
    const sha = (b: Buffer) => createHash('sha256').update(b).digest('hex');
    for (const [name, body] of published) expect(sha(builds.static.files.get(name) ?? Buffer.alloc(0)), name).toBe(sha(body));
    expect(json).toHaveLength(1157);
  });
});
