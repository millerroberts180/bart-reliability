// The page for VITE_DATA_MODE=static, the GitHub Pages build: the historical replay
// published with the site (docs/static_replay.md). vite.config.ts points '@data-mode' here
// for this mode only, so this build contains no other prediction client or its data.

import { App } from '../App';
import { StaticReplayClient } from '../data/StaticReplayClient';

// The published replay is served with the site, under Vite's base path (e.g. /bart-reliability/).
const client = new StaticReplayClient(`${import.meta.env.BASE_URL}replay/`);

export function Site() {
  return <App client={client} />;
}
