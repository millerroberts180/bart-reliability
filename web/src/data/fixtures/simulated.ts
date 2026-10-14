// Simulated fixtures for the prototype. Station names, lines and destinations
// follow BART's public network; every number below is invented. Times are
// stored as offsets so MockPredictionClient can place them against any clock.

import type { AlertContext, ModelMetadata, Station } from '../../domain/types';

export const SIMULATED_STATIONS: Station[] = [
  {
    id: 'EMBR',
    name: 'Embarcadero',
    directions: [
      {
        id: '0',
        label: 'Toward the East Bay',
        destinations: ['Antioch', 'Richmond', 'Berryessa/North San José', 'Dublin/Pleasanton'],
      },
      { id: '1', label: 'Toward Daly City, SFO and Millbrae', destinations: ['SF Airport', 'Millbrae', 'Daly City'] },
    ],
  },
  {
    id: 'MCAR',
    name: 'MacArthur',
    directions: [
      { id: '0', label: 'Toward Antioch and Richmond', destinations: ['Antioch', 'Richmond'] },
      {
        id: '1',
        label: 'Toward San Francisco and Berryessa',
        destinations: ['SF Airport', 'Millbrae', 'Berryessa/North San José'],
      },
    ],
  },
  {
    id: 'BALB',
    name: 'Balboa Park',
    directions: [
      {
        id: '0',
        label: 'Toward the East Bay',
        destinations: ['Antioch', 'Richmond', 'Berryessa/North San José', 'Dublin/Pleasanton'],
      },
      { id: '1', label: 'Toward Daly City, SFO and Millbrae', destinations: ['SF Airport', 'Millbrae', 'Daly City'] },
    ],
  },
];

export interface SimulatedTrain {
  tripId: string;
  lineName: string;
  headsign: string;
  carCount: number | null;
  etaSeconds: number;
  revisionSeconds: number;
  interval: readonly [number, number];
  probability: number;
}

/** Keyed by `${stationId}:${directionId}`. */
export const SIMULATED_TRAINS: Record<string, SimulatedTrain[]> = {
  'EMBR:0': [
    { tripId: '1561', lineName: 'Yellow line', headsign: 'Antioch', carCount: 10, etaSeconds: 130, revisionSeconds: 12, interval: [-10, 35], probability: 0.08 },
    { tripId: '1782', lineName: 'Red line', headsign: 'Richmond', carCount: 8, etaSeconds: 370, revisionSeconds: 85, interval: [20, 150], probability: 0.41 },
    { tripId: '1937', lineName: 'Green line', headsign: 'Berryessa/North San José', carCount: 9, etaSeconds: 610, revisionSeconds: 140, interval: [45, 260], probability: 0.67 },
    { tripId: '2105', lineName: 'Blue line', headsign: 'Dublin/Pleasanton', carCount: null, etaSeconds: 905, revisionSeconds: -40, interval: [-130, 50], probability: 0.33 },
  ],
  'EMBR:1': [
    { tripId: '1544', lineName: 'Yellow line', headsign: 'SF Airport', carCount: 10, etaSeconds: 95, revisionSeconds: 6, interval: [-8, 22], probability: 0.05 },
    { tripId: '1690', lineName: 'Green line', headsign: 'Daly City', carCount: 8, etaSeconds: 410, revisionSeconds: 48, interval: [0, 110], probability: 0.29 },
    { tripId: '1823', lineName: 'Red line', headsign: 'Millbrae', carCount: 9, etaSeconds: 780, revisionSeconds: 110, interval: [30, 210], probability: 0.58 },
  ],
  'MCAR:0': [
    { tripId: '1418', lineName: 'Orange line', headsign: 'Richmond', carCount: 6, etaSeconds: 200, revisionSeconds: 20, interval: [-5, 50], probability: 0.12 },
    { tripId: '1563', lineName: 'Yellow line', headsign: 'Antioch', carCount: 10, etaSeconds: 480, revisionSeconds: 95, interval: [30, 170], probability: 0.52 },
    { tripId: '1784', lineName: 'Red line', headsign: 'Richmond', carCount: 8, etaSeconds: 860, revisionSeconds: 30, interval: [-60, 125], probability: 0.36 },
  ],
  'MCAR:1': [
    { tripId: '1546', lineName: 'Yellow line', headsign: 'SF Airport', carCount: 10, etaSeconds: 160, revisionSeconds: -15, interval: [-45, 10], probability: 0.1 },
    { tripId: '1421', lineName: 'Orange line', headsign: 'Berryessa/North San José', carCount: 6, etaSeconds: 520, revisionSeconds: 70, interval: [10, 140], probability: 0.38 },
    { tripId: '1825', lineName: 'Red line', headsign: 'Millbrae', carCount: 8, etaSeconds: 940, revisionSeconds: 155, interval: [60, 280], probability: 0.71 },
  ],
  'BALB:0': [
    { tripId: '1692', lineName: 'Green line', headsign: 'Berryessa/North San José', carCount: 8, etaSeconds: 240, revisionSeconds: 35, interval: [0, 80], probability: 0.22 },
    { tripId: '2107', lineName: 'Blue line', headsign: 'Dublin/Pleasanton', carCount: 9, etaSeconds: 545, revisionSeconds: 100, interval: [35, 190], probability: 0.55 },
    { tripId: '1565', lineName: 'Yellow line', headsign: 'Antioch', carCount: 10, etaSeconds: 820, revisionSeconds: -25, interval: [-95, 40], probability: 0.27 },
  ],
  'BALB:1': [
    { tripId: '2109', lineName: 'Blue line', headsign: 'Daly City', carCount: 9, etaSeconds: 70, revisionSeconds: 0, interval: [-10, 10], probability: 0.03 },
    { tripId: '1548', lineName: 'Yellow line', headsign: 'SF Airport', carCount: 10, etaSeconds: 450, revisionSeconds: 60, interval: [10, 120], probability: 0.34 },
    { tripId: '1827', lineName: 'Red line', headsign: 'Millbrae', carCount: 8, etaSeconds: 730, revisionSeconds: 125, interval: [40, 230], probability: 0.62 },
  ],
};

export interface SimulatedAlert extends Omit<AlertContext, 'visibleSince'> {
  /** Seconds before the feed snapshot that the alert first appeared. */
  visibleForSeconds: number;
}

/** Keyed by station id. A station without an entry has no visible alerts. */
export const SIMULATED_ALERTS: Record<string, SimulatedAlert[]> = {
  MCAR: [
    {
      alertId: 'sim-elevator-mcar',
      scope: 'station',
      category: 'unclassified',
      headerText: 'Street-to-concourse elevator out of service at MacArthur.',
      visibleForSeconds: 5400,
    },
  ],
  BALB: [
    {
      alertId: 'sim-trackwork-balb',
      scope: 'route',
      category: 'planned_work',
      headerText: 'Planned trackwork near Balboa Park may add up to 10 minutes to some trips this evening.',
      visibleForSeconds: 14400,
    },
  ],
};

export const SIMULATED_MODEL: ModelMetadata = {
  modelVersion: 'simulated-0.1',
  trainedThrough: '2026-10-11T07:00:00.000Z',
  revisionThresholdSeconds: 60,
  simulated: true,
};

/** Feed age for the normal scenario and for the stale scenario. */
export const FEED_AGE_SECONDS = { live: 34, stale: 580 } as const;

/** The model runs a few seconds after each feed snapshot. */
export const MODEL_LAG_SECONDS = 4;
