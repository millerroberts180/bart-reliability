// Generated from BART static GTFS (feed of 2026-10-08) by a one-off script; do not edit by hand.
// Station names, IDs, and the terminals and lines served from each station in each GTFS
// direction (weekday service) are real. Trains and every number derived from this
// fixture are simulated by MockPredictionClient.

import type { Station } from '../../domain/types';

export interface NetworkService {
  headsign: string;
  lineName: string;
}

export const NETWORK_STATIONS: Station[] = [
  {
    id: '12TH',
    name: '12th Street / Oakland City Center',
    directions: [
      { id: '0', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Berryessa / North San Jose and Millbrae', destinations: ['SF Airport', 'Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: '16TH',
    name: '16th Street / Mission',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: '19TH',
    name: '19th Street Oakland',
    directions: [
      { id: '0', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Berryessa / North San Jose and Millbrae', destinations: ['SF Airport', 'Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: '24TH',
    name: '24th Street / Mission',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'ANTC',
    name: 'Antioch',
    directions: [
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'ASHB',
    name: 'Ashby',
    directions: [
      { id: '0', label: 'Toward Richmond', destinations: ['Richmond'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'BALB',
    name: 'Balboa Park',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'BAYF',
    name: 'Bay Fair',
    directions: [
      { id: '0', label: 'Toward Richmond, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Richmond', 'Dublin / Pleasanton', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'BERY',
    name: 'Berryessa / North San Jose',
    directions: [
      { id: '0', label: 'Toward Richmond', destinations: ['Richmond'] },
      { id: '1', label: 'Toward Daly City', destinations: ['Daly City'] },
    ],
  },
  {
    id: 'CAST',
    name: 'Castro Valley',
    directions: [
      { id: '0', label: 'Toward Dublin / Pleasanton', destinations: ['Dublin / Pleasanton'] },
      { id: '1', label: 'Toward Daly City and Bay Fair', destinations: ['Daly City', 'Bay Fair'] },
    ],
  },
  {
    id: 'CIVC',
    name: 'Civic Center / UN Plaza',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'COLS',
    name: 'Coliseum',
    directions: [
      { id: '0', label: 'Toward Richmond, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Richmond', 'Dublin / Pleasanton', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward OAK Airport, Berryessa / North San Jose and Daly City', destinations: ['OAK Airport', 'Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'COLM',
    name: 'Colma',
    directions: [
      { id: '0', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'CONC',
    name: 'Concord',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'DALY',
    name: 'Daly City',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'DBRK',
    name: 'Downtown Berkeley',
    directions: [
      { id: '0', label: 'Toward Richmond', destinations: ['Richmond'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'DUBL',
    name: 'Dublin / Pleasanton',
    directions: [
      { id: '1', label: 'Toward Daly City and Bay Fair', destinations: ['Daly City', 'Bay Fair'] },
    ],
  },
  {
    id: 'DELN',
    name: 'El Cerrito Del Norte',
    directions: [
      { id: '0', label: 'Toward Richmond', destinations: ['Richmond'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'PLZA',
    name: 'El Cerrito Plaza',
    directions: [
      { id: '0', label: 'Toward Richmond', destinations: ['Richmond'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'EMBR',
    name: 'Embarcadero',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'FRMT',
    name: 'Fremont',
    directions: [
      { id: '0', label: 'Toward Richmond and Berryessa / North San Jose', destinations: ['Richmond', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'FTVL',
    name: 'Fruitvale',
    directions: [
      { id: '0', label: 'Toward Richmond, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Richmond', 'Dublin / Pleasanton', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'GLEN',
    name: 'Glen Park',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'HAYW',
    name: 'Hayward',
    directions: [
      { id: '0', label: 'Toward Richmond and Berryessa / North San Jose', destinations: ['Richmond', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'LAFY',
    name: 'Lafayette',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'LAKE',
    name: 'Lake Merritt',
    directions: [
      { id: '0', label: 'Toward Richmond, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Richmond', 'Dublin / Pleasanton', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'MCAR',
    name: 'MacArthur',
    directions: [
      { id: '0', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Berryessa / North San Jose and Millbrae', destinations: ['SF Airport', 'Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'MLBR',
    name: 'Millbrae',
    directions: [
      { id: '0', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport', destinations: ['SF Airport'] },
    ],
  },
  {
    id: 'MLPT',
    name: 'Milpitas',
    directions: [
      { id: '0', label: 'Toward Richmond and Berryessa / North San Jose', destinations: ['Richmond', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'MONT',
    name: 'Montgomery Street',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'NBRK',
    name: 'North Berkeley',
    directions: [
      { id: '0', label: 'Toward Richmond', destinations: ['Richmond'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'NCON',
    name: 'North Concord / Martinez',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'OAKL',
    name: 'Oakland International Airport',
    directions: [
      { id: '0', label: 'Toward Coliseum', destinations: ['Coliseum'] },
    ],
  },
  {
    id: 'ORIN',
    name: 'Orinda',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'PITT',
    name: 'Pittsburg / Bay Point',
    directions: [
      { id: '0', label: 'Toward Antioch', destinations: ['Antioch'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'PCTR',
    name: 'Pittsburg Center',
    directions: [
      { id: '0', label: 'Toward Antioch', destinations: ['Antioch'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'PHIL',
    name: 'Pleasant Hill / Contra Costa Centre',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'POWL',
    name: 'Powell Street',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
  {
    id: 'RICH',
    name: 'Richmond',
    directions: [
      { id: '1', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'] },
    ],
  },
  {
    id: 'ROCK',
    name: 'Rockridge',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'SBRN',
    name: 'San Bruno',
    directions: [
      { id: '0', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'SFIA',
    name: 'San Francisco International Airport',
    directions: [
      { id: '0', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward Millbrae', destinations: ['Millbrae'] },
    ],
  },
  {
    id: 'SANL',
    name: 'San Leandro',
    directions: [
      { id: '0', label: 'Toward Richmond, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Richmond', 'Dublin / Pleasanton', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'SHAY',
    name: 'South Hayward',
    directions: [
      { id: '0', label: 'Toward Richmond and Berryessa / North San Jose', destinations: ['Richmond', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'SSAN',
    name: 'South San Francisco',
    directions: [
      { id: '0', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'UCTY',
    name: 'Union City',
    directions: [
      { id: '0', label: 'Toward Richmond and Berryessa / North San Jose', destinations: ['Richmond', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'WCRK',
    name: 'Walnut Creek',
    directions: [
      { id: '0', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'] },
    ],
  },
  {
    id: 'WARM',
    name: 'Warm Springs / South Fremont',
    directions: [
      { id: '0', label: 'Toward Richmond and Berryessa / North San Jose', destinations: ['Richmond', 'Berryessa / North San Jose'] },
      { id: '1', label: 'Toward Berryessa / North San Jose and Daly City', destinations: ['Berryessa / North San Jose', 'Daly City'] },
    ],
  },
  {
    id: 'WDUB',
    name: 'West Dublin / Pleasanton',
    directions: [
      { id: '0', label: 'Toward Dublin / Pleasanton', destinations: ['Dublin / Pleasanton'] },
      { id: '1', label: 'Toward Daly City and Bay Fair', destinations: ['Daly City', 'Bay Fair'] },
    ],
  },
  {
    id: 'WOAK',
    name: 'West Oakland',
    directions: [
      { id: '0', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'] },
      { id: '1', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'] },
    ],
  },
];

/** Keyed by `${stationId}:${directionId}`, most frequent destination first. */
export const NETWORK_SERVICE: Record<string, NetworkService[]> = {
  '12TH:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  '12TH:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  '16TH:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  '16TH:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  '19TH:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  '19TH:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  '24TH:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  '24TH:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'ANTC:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'ASHB:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Richmond', lineName: 'Red line' }],
  'ASHB:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }],
  'BALB:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'BALB:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'BAYF:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'BAYF:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'BERY:0': [{ headsign: 'Richmond', lineName: 'Orange line' }],
  'BERY:1': [{ headsign: 'Daly City', lineName: 'Green line' }],
  'CAST:0': [{ headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }],
  'CAST:1': [{ headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Bay Fair', lineName: 'Blue line' }],
  'CIVC:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'CIVC:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'COLS:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'COLS:1': [{ headsign: 'OAK Airport', lineName: 'Grey line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'COLM:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'COLM:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'CONC:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'CONC:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'DALY:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'DALY:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'DBRK:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Richmond', lineName: 'Red line' }],
  'DBRK:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }],
  'DUBL:1': [{ headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Bay Fair', lineName: 'Blue line' }],
  'DELN:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Richmond', lineName: 'Red line' }],
  'DELN:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }],
  'PLZA:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Richmond', lineName: 'Red line' }],
  'PLZA:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }],
  'EMBR:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'EMBR:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'FRMT:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'FRMT:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'FTVL:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'FTVL:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'GLEN:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'GLEN:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'HAYW:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'HAYW:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'LAFY:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'LAFY:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'LAKE:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'LAKE:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'MCAR:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'MCAR:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'MLBR:0': [{ headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'MLBR:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }],
  'MLPT:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'MLPT:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'MONT:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'MONT:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'NBRK:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Richmond', lineName: 'Red line' }],
  'NBRK:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }],
  'NCON:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'NCON:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'OAKL:0': [{ headsign: 'Coliseum', lineName: 'Grey line' }],
  'ORIN:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'ORIN:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'PITT:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }],
  'PITT:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'PCTR:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }],
  'PCTR:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'PHIL:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'PHIL:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'POWL:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'POWL:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'RICH:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Millbrae', lineName: 'Red line' }],
  'ROCK:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'ROCK:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'SBRN:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'SBRN:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'SFIA:0': [{ headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'SFIA:1': [{ headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'SANL:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'SANL:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'SHAY:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'SHAY:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'SSAN:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'SSAN:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'UCTY:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'UCTY:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'WCRK:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'WCRK:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
  'WARM:0': [{ headsign: 'Richmond', lineName: 'Orange line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }],
  'WARM:1': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line' }, { headsign: 'Daly City', lineName: 'Green line' }],
  'WDUB:0': [{ headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }],
  'WDUB:1': [{ headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Bay Fair', lineName: 'Blue line' }],
  'WOAK:0': [{ headsign: 'Antioch', lineName: 'Yellow line' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line' }, { headsign: 'Richmond', lineName: 'Red line' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line' }],
  'WOAK:1': [{ headsign: 'SF Airport', lineName: 'Yellow line' }, { headsign: 'Daly City', lineName: 'Blue line' }, { headsign: 'Daly City', lineName: 'Green line' }, { headsign: 'Millbrae', lineName: 'Red line' }, { headsign: 'Millbrae', lineName: 'Yellow line' }],
};
