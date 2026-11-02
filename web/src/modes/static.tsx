// The page for VITE_DATA_MODE=static, the GitHub Pages build: the curated historical replay
// published with the site (docs/showcase_replay.md, docs/static_replay.md) and its showcase
// files. vite.config.ts points '@data-mode' here for this mode only, so this build contains
// no other prediction client or its data.

import { App } from '../App';
import { StaticShowcaseSource, type ShowcaseSource } from '../data/ShowcaseSource';
import { StaticReplayClient } from '../data/StaticReplayClient';

// Both are served with the site, under Vite's base path (e.g. /bart-reliability/).
const client = new StaticReplayClient(`${import.meta.env.BASE_URL}replay/`);
const showcase: ShowcaseSource = new StaticShowcaseSource(`${import.meta.env.BASE_URL}showcase/`);

export function Site() {
  return <App client={client} showcase={showcase} />;
}
