/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Dev always serves from "/". Production builds default to the GitHub Pages
// project path and can be overridden with VITE_BASE_PATH (e.g. "/" for a root
// deployment). Components never hard-code this: use import.meta.env.BASE_URL.
const DEFAULT_PRODUCTION_BASE = '/bart-reliability/';

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const base = command === 'build' ? env.VITE_BASE_PATH || DEFAULT_PRODUCTION_BASE : '/';

  return {
    base,
    plugins: [react()],
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
