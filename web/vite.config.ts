/// <reference types="vitest/config" />
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

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const base = command === 'build' ? env.VITE_BASE_PATH || DEFAULT_PRODUCTION_BASE : '/';

  const dataMode = env.VITE_DATA_MODE ?? 'mock';
  const simulated = dataMode !== 'http' && dataMode !== 'static';

  return {
    base,
    // public/ holds only the published replay (public/replay/), which only static mode reads;
    // the simulated and HTTP builds do not ship it.
    publicDir: dataMode === 'static' ? 'public' : false,
    plugins: [
      react(),
      {
        name: 'data-mode-description',
        transformIndexHtml: (html) => (simulated ? html.replaceAll(REPLAY_DESCRIPTION, SIMULATED_DESCRIPTION) : html),
      },
    ],
    test: {
      // Tests always start from simulated data, whatever a developer's .env.local says;
      // a test that needs the HTTP client injects one.
      env: { VITE_DATA_MODE: 'mock', VITE_API_BASE_URL: '' },
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      // Each file runs in its own jsdom worker; with all of them at once, a test that takes
      // half a second alone can take several, so the per-test limit allows 15 s.
      testTimeout: 15_000,
      css: false,
    },
  };
});
