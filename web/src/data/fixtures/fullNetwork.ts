// The 50-station fixture as one module, so MockPredictionClient can load it on demand.
// Only the development panel and tests select the full network, so production builds
// emit it as a separate chunk that is never fetched.
export { NETWORK_STATIONS } from './network';
export { networkHistory, networkTrains } from './networkTrains';
