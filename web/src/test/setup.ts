import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';

// The first render in each file also loads its modules; with every file running in
// parallel that can pass the default 1 s, so waits allow 3 s before failing.
configure({ asyncUtilTimeout: 3000 });

afterEach(() => {
  cleanup();
  // The picker keeps the selection in the URL and recent stations in localStorage.
  window.history.replaceState(null, '', '/');
  window.localStorage.clear();
});
