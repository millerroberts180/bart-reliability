/// <reference types="vitest/config" />
import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Dev always serves from "/". Production builds default to the GitHub Pages
// project path and can be overridden with VITE_BASE_PATH (e.g. "/" for a root
// deployment). Components never hard-code this: use import.meta.env.BASE_URL.
const DEFAULT_PRODUCTION_BASE = '/bart-reliability/';

// index.html describes the historical-replay site (the static replay on GitHub Pages, or the
// local API). A simulated build shows no BART data, so its description (and the social
// copies of it) says so instead.
const REPLAY_DESCRIPTION =
  'A historical replay of recorded BART data, with a model of how BART revises a train’s published arrival estimate before it arrives. Not live, and not a prediction of physical arrival.';
const SIMULATED_DESCRIPTION =
  'A prototype of a model of how BART revises a train’s published arrival estimate before it arrives, shown with simulated data. Not live, and not a prediction of physical arrival.';

// VITE_DATA_MODE picks the page's prediction client when the site is built or served:
// "mock" (simulated fixtures, the default), "http" (the local API) or "static" (the
// published replay). Anything else is refused, so a mistyped mode can never quietly
// build the simulated site.
const DATA_MODES = ['mock', 'http', 'static'] as const;
type DataMode = (typeof DATA_MODES)[number];

function dataModeFrom(value: string | undefined): DataMode {
  if (!value) return 'mock';
  const mode = DATA_MODES.find((m) => m === value);
  if (!mode) throw new Error(`VITE_DATA_MODE must be ${DATA_MODES.join(', ')} or unset (mock); got "${value}".`);
  return mode;
}

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const base = command === 'build' ? env.VITE_BASE_PATH || DEFAULT_PRODUCTION_BASE : '/';

  const dataMode = dataModeFrom(env.VITE_DATA_MODE);
  const simulated = dataMode === 'mock';

  return {
    base,
    resolve: {
      // src/main.tsx imports '@data-mode', which resolves to this mode's module alone
      // (src/modes/<mode>.tsx). Each build therefore bundles only its own prediction client
      // and that client's data; build-tests/ checks the three builds.
      alias: [{ find: /^@data-mode$/, replacement: fileURLToPath(new URL(`./src/modes/${dataMode}.tsx`, import.meta.url)) }],
    },
    // public/ holds only the published replay (public/replay/), which only static mode reads;
    // the simulated and HTTP builds do not ship it.
    publicDir: dataMode === 'static' ? 'public' : false,
    plugins: [
      react(),
      {
        name: 'data-mode',
        configResolved(config) {
          if (!process.env.VITEST) config.logger.info(`Data mode: ${dataMode} (VITE_DATA_MODE)`);
        },
        transformIndexHtml: (html) => (simulated ? html.replaceAll(REPLAY_DESCRIPTION, SIMULATED_DESCRIPTION) : html),
      },
    ],
    test: {
      // Tests always start from simulated data, whatever a developer's .env.local says;
      // a test that needs the HTTP client injects one.
      env: { VITE_DATA_MODE: 'mock', VITE_API_BASE_URL: '' },
      // The build-artifact tests (build-tests/) make production builds, so they run on their
      // own: npm run test:build.
      include: ['src/**/*.test.{ts,tsx}'],
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      // Each file runs in its own jsdom worker; with all of them at once, a test that takes
      // half a second alone can take several, so the per-test limit allows 15 s.
      testTimeout: 15_000,
      css: false,
    },
  };
});
