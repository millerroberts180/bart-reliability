import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
  // The picker keeps the selection in the URL and recent stations in localStorage.
  window.history.replaceState(null, '', '/');
  window.localStorage.clear();
});
