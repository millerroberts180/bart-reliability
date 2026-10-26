// The page for VITE_DATA_MODE=http: the local prediction API (docs/local_api.md).
// vite.config.ts points '@data-mode' here for this mode only, so this build contains no
// other prediction client or its data.

import { App } from '../App';
import { HttpPredictionClient } from '../data/HttpPredictionClient';

// Only this mode reads the API address (VITE_API_BASE_URL, in web/.env.local), so no other
// build can carry it.
const client = new HttpPredictionClient(import.meta.env.VITE_API_BASE_URL ?? '');

export function Site() {
  return <App client={client} />;
}
