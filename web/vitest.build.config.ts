import { defineConfig } from 'vitest/config';

// The build-artifact tests (npm run test:build). They make the three production builds
// before any test runs, so they run apart from the unit tests (vite.config.ts), in Node,
// and allow the builds minutes rather than seconds.
export default defineConfig({
  test: {
    include: ['build-tests/**/*.test.ts'],
    environment: 'node',
    hookTimeout: 300_000,
  },
});
