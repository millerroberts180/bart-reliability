// Each data mode's module renders the page with its own prediction client. Production
// builds take exactly one of them through '@data-mode' (vite.config.ts); the builds
// themselves are checked in build-tests/.

import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type * as Selected from '@data-mode';
import { API_BASE, createFakeApi } from '../test/fakeApi';
import { createPublishedReplayHost } from '../test/publishedReplay';
import type * as HttpMode from './http';
import type * as MockMode from './mock';
import type * as StaticMode from './static';

// Compile time: each mode's module provides what src/main.tsx imports from '@data-mode'.
type Provides<T extends typeof Selected> = T;
export type ModeModules = [Provides<typeof MockMode>, Provides<typeof HttpMode>, Provides<typeof StaticMode>];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

const disclosure = (name: string) =>
  within(screen.getByRole('region', { name: 'ETA Reliability' })).findByRole('complementary', { name });

describe('data mode modules', () => {
  it('mock: the simulated client, with the development state selector', async () => {
    const { Site } = await import('./mock');
    render(<Site />);
    expect(await disclosure('Prototype using simulated data')).toBeInTheDocument();
    expect(await screen.findByTestId('forecast')).toBeInTheDocument();
    expect(await screen.findByText('Dev · preview state')).toBeInTheDocument();
  });

  it('static: the published replay, read from the site’s own origin under the base path', async () => {
    // Tests serve from "/", so the replay is at /replay/ (/bart-reliability/replay/ on Pages).
    const host = createPublishedReplayHost('/replay/');
    vi.stubGlobal('fetch', host.fetch);
    const { Site } = await import('./static');
    render(<Site />);
    expect(await disclosure('Historical replay of recorded BART data')).toHaveTextContent(
      'Tuesday, October 20, 2026 at 10:00 AM Pacific',
    );
    expect(await screen.findByTestId('forecast')).toBeInTheDocument();
    expect(host.requests[0]).toBe('index.json');
    expect(screen.queryByText('Dev · preview state')).not.toBeInTheDocument();
  });

  it('http: the local API at VITE_API_BASE_URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', API_BASE);
    const api = createFakeApi();
    vi.stubGlobal('fetch', api.fetch);
    const { Site } = await import('./http');
    render(<Site />);
    expect(await disclosure('Historical replay of recorded BART data')).toHaveTextContent(
      'Thursday, October 15, 2026 at 10:00 AM Pacific',
    );
    expect(api.requests).toContain('/api/v1/health');
    expect(screen.queryByText('Dev · preview state')).not.toBeInTheDocument();
  });
});
