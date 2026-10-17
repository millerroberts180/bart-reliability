// Generated from BART static GTFS (feed of 2026-10-08) by a one-off script; do not edit by hand.
// Station names, IDs, boarding groups (docs/boarding_groups.md, the API's own rule) and
// the terminals, lines and platforms of weekday trains leaving each way are real.
// Trains and every number derived from this fixture are simulated by MockPredictionClient.

import type { Station } from '../../domain/types';

export interface NetworkService {
  headsign: string;
  lineName: string;
  platform: string;
}

export const NETWORK_STATIONS: Station[] = [
  {
    id: '12TH',
    name: '12th Street / Oakland City Center',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-19TH', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'], platform: null, gtfsDirectionIds: ['0'] },
      { id: 'to-LAKE-WOAK', label: 'Toward SF Airport, Berryessa / North San Jose and Millbrae', destinations: ['SF Airport', 'Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: '16TH',
    name: '16th Street / Mission',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-24TH', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-CIVC', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: '19TH',
    name: '19th Street Oakland',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-MCAR', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'], platform: null, gtfsDirectionIds: ['0'] },
      { id: 'to-12TH', label: 'Toward SF Airport, Berryessa / North San Jose and Millbrae', destinations: ['SF Airport', 'Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: '24TH',
    name: '24th Street / Mission',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-GLEN', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-16TH', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'ANTC',
    name: 'Antioch',
    endOfLine: true,
    boardingGroups: [
      { id: 'to-PCTR', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'ASHB',
    name: 'Ashby',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-DBRK', label: 'Toward Richmond', destinations: ['Richmond'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-MCAR', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'BALB',
    name: 'Balboa Park',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-DALY', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-GLEN', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'BAYF',
    name: 'Bay Fair',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-CAST-HAYW', label: 'Toward Berryessa / North San Jose and Dublin / Pleasanton', destinations: ['Berryessa / North San Jose', 'Dublin / Pleasanton'], platform: null, gtfsDirectionIds: ['0', '1'] },
      { id: 'to-SANL', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'BERY',
    name: 'Berryessa / North San Jose',
    endOfLine: true,
    boardingGroups: [
      { id: 'to-MLPT', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: null, gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'CAST',
    name: 'Castro Valley',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-WDUB', label: 'Toward Dublin / Pleasanton', destinations: ['Dublin / Pleasanton'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-BAYF', label: 'Toward Daly City and Bay Fair', destinations: ['Daly City', 'Bay Fair'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'CIVC',
    name: 'Civic Center / UN Plaza',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-16TH', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-POWL', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'COLS',
    name: 'Coliseum',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-SANL', label: 'Toward Berryessa / North San Jose and Dublin / Pleasanton', destinations: ['Berryessa / North San Jose', 'Dublin / Pleasanton'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-FTVL', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-OAKL', label: 'Toward OAK Airport', destinations: ['OAK Airport'], platform: '3', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'COLM',
    name: 'Colma',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-SSAN', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-DALY', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'CONC',
    name: 'Concord',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-NCON', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-PHIL', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'DALY',
    name: 'Daly City',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-COLM', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-BALB', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'DBRK',
    name: 'Downtown Berkeley',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-NBRK', label: 'Toward Richmond', destinations: ['Richmond'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-ASHB', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'DUBL',
    name: 'Dublin / Pleasanton',
    endOfLine: true,
    boardingGroups: [
      { id: 'to-WDUB', label: 'Toward Daly City and Bay Fair', destinations: ['Daly City', 'Bay Fair'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'DELN',
    name: 'El Cerrito Del Norte',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-RICH', label: 'Toward Richmond', destinations: ['Richmond'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-PLZA', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'PLZA',
    name: 'El Cerrito Plaza',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-DELN', label: 'Toward Richmond', destinations: ['Richmond'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-NBRK', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'EMBR',
    name: 'Embarcadero',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-MONT', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-WOAK', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'FRMT',
    name: 'Fremont',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-WARM', label: 'Toward Berryessa / North San Jose', destinations: ['Berryessa / North San Jose'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-UCTY', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'FTVL',
    name: 'Fruitvale',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-COLS', label: 'Toward Berryessa / North San Jose and Dublin / Pleasanton', destinations: ['Berryessa / North San Jose', 'Dublin / Pleasanton'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-LAKE', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'GLEN',
    name: 'Glen Park',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-BALB', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-24TH', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'HAYW',
    name: 'Hayward',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-SHAY', label: 'Toward Berryessa / North San Jose', destinations: ['Berryessa / North San Jose'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-BAYF', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'LAFY',
    name: 'Lafayette',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-WCRK', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-ORIN', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'LAKE',
    name: 'Lake Merritt',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-FTVL', label: 'Toward Berryessa / North San Jose and Dublin / Pleasanton', destinations: ['Berryessa / North San Jose', 'Dublin / Pleasanton'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-12TH-WOAK', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'MCAR',
    name: 'MacArthur',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-ASHB-ROCK', label: 'Toward Richmond, Antioch and Pittsburg / Bay Point', destinations: ['Richmond', 'Antioch', 'Pittsburg / Bay Point'], platform: null, gtfsDirectionIds: ['0'] },
      { id: 'to-19TH', label: 'Toward SF Airport, Berryessa / North San Jose and Millbrae', destinations: ['SF Airport', 'Berryessa / North San Jose', 'Millbrae'], platform: null, gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'MLBR',
    name: 'Millbrae',
    endOfLine: true,
    boardingGroups: [
      { id: 'to-SFIA', label: 'Toward Richmond, SF Airport and Antioch', destinations: ['Richmond', 'SF Airport', 'Antioch', 'Pittsburg / Bay Point'], platform: '3', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'MLPT',
    name: 'Milpitas',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-BERY', label: 'Toward Berryessa / North San Jose', destinations: ['Berryessa / North San Jose'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-WARM', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'MONT',
    name: 'Montgomery Street',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-POWL', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-EMBR', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'NBRK',
    name: 'North Berkeley',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-PLZA', label: 'Toward Richmond', destinations: ['Richmond'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-DBRK', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'NCON',
    name: 'North Concord / Martinez',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-PITT', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-CONC', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'OAKL',
    name: 'Oakland International Airport',
    endOfLine: true,
    boardingGroups: [
      { id: 'to-COLS', label: 'Toward Coliseum', destinations: ['Coliseum'], platform: '1', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'ORIN',
    name: 'Orinda',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-LAFY', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-ROCK', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'PITT',
    name: 'Pittsburg / Bay Point',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-PCTR', label: 'Toward Antioch', destinations: ['Antioch'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-NCON', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'PCTR',
    name: 'Pittsburg Center',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-ANTC', label: 'Toward Antioch', destinations: ['Antioch'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-PITT', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'PHIL',
    name: 'Pleasant Hill / Contra Costa Centre',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-CONC', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-WCRK', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'POWL',
    name: 'Powell Street',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-CIVC', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-MONT', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'RICH',
    name: 'Richmond',
    endOfLine: true,
    boardingGroups: [
      { id: 'to-DELN', label: 'Toward Berryessa / North San Jose and Millbrae', destinations: ['Berryessa / North San Jose', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'ROCK',
    name: 'Rockridge',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-ORIN', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-MCAR', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'SBRN',
    name: 'San Bruno',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-MLBR-SFIA', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-SSAN', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'SFIA',
    name: 'San Francisco International Airport',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-MLBR', label: 'Toward Millbrae', destinations: ['Millbrae'], platform: null, gtfsDirectionIds: ['1'] },
      { id: 'to-SBRN', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'], platform: null, gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'SANL',
    name: 'San Leandro',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-BAYF', label: 'Toward Berryessa / North San Jose and Dublin / Pleasanton', destinations: ['Berryessa / North San Jose', 'Dublin / Pleasanton'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-COLS', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'SHAY',
    name: 'South Hayward',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-UCTY', label: 'Toward Berryessa / North San Jose', destinations: ['Berryessa / North San Jose'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-HAYW', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'SSAN',
    name: 'South San Francisco',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-SBRN', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-COLM', label: 'Toward Antioch, Richmond and Pittsburg / Bay Point', destinations: ['Antioch', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
  {
    id: 'UCTY',
    name: 'Union City',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-FRMT', label: 'Toward Berryessa / North San Jose', destinations: ['Berryessa / North San Jose'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-SHAY', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'WCRK',
    name: 'Walnut Creek',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-PHIL', label: 'Toward Antioch and Pittsburg / Bay Point', destinations: ['Antioch', 'Pittsburg / Bay Point'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-LAFY', label: 'Toward SF Airport and Millbrae', destinations: ['SF Airport', 'Millbrae'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'WARM',
    name: 'Warm Springs / South Fremont',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-MLPT', label: 'Toward Berryessa / North San Jose', destinations: ['Berryessa / North San Jose'], platform: '1', gtfsDirectionIds: ['0', '1'] },
      { id: 'to-FRMT', label: 'Toward Richmond and Daly City', destinations: ['Richmond', 'Daly City'], platform: '2', gtfsDirectionIds: ['0', '1'] },
    ],
  },
  {
    id: 'WDUB',
    name: 'West Dublin / Pleasanton',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-DUBL', label: 'Toward Dublin / Pleasanton', destinations: ['Dublin / Pleasanton'], platform: '1', gtfsDirectionIds: ['0'] },
      { id: 'to-CAST', label: 'Toward Daly City and Bay Fair', destinations: ['Daly City', 'Bay Fair'], platform: '2', gtfsDirectionIds: ['1'] },
    ],
  },
  {
    id: 'WOAK',
    name: 'West Oakland',
    endOfLine: false,
    boardingGroups: [
      { id: 'to-EMBR', label: 'Toward SF Airport, Daly City and Millbrae', destinations: ['SF Airport', 'Daly City', 'Millbrae'], platform: '1', gtfsDirectionIds: ['1'] },
      { id: 'to-12TH-LAKE', label: 'Toward Antioch, Dublin / Pleasanton and Berryessa / North San Jose', destinations: ['Antioch', 'Dublin / Pleasanton', 'Berryessa / North San Jose', 'Richmond', 'Pittsburg / Bay Point'], platform: '2', gtfsDirectionIds: ['0'] },
    ],
  },
];

/** Keyed by `${stationId}:${boardingGroupId}`, most frequent service first. */
export const NETWORK_SERVICE: Record<string, NetworkService[]> = {
  '12TH:to-19TH': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Antioch', lineName: 'Yellow line', platform: '3' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '3' }],
  '12TH:to-LAKE-WOAK': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  '16TH:to-24TH': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  '16TH:to-CIVC': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  '19TH:to-MCAR': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Antioch', lineName: 'Yellow line', platform: '3' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '3' }],
  '19TH:to-12TH': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  '24TH:to-GLEN': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  '24TH:to-16TH': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'ANTC:to-PCTR': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'ASHB:to-DBRK': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }],
  'ASHB:to-MCAR': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }],
  'BALB:to-DALY': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'BALB:to-GLEN': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'BAYF:to-CAST-HAYW': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }],
  'BAYF:to-SANL': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'BERY:to-MLPT': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }],
  'CAST:to-WDUB': [{ headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }],
  'CAST:to-BAYF': [{ headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Bay Fair', lineName: 'Blue line', platform: '2' }],
  'CIVC:to-16TH': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'CIVC:to-POWL': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'COLS:to-SANL': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'COLS:to-FTVL': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'COLS:to-OAKL': [{ headsign: 'OAK Airport', lineName: 'Grey line', platform: '3' }],
  'COLM:to-SSAN': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'COLM:to-DALY': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'CONC:to-NCON': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'CONC:to-PHIL': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'DALY:to-COLM': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'DALY:to-BALB': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'DBRK:to-NBRK': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }],
  'DBRK:to-ASHB': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }],
  'DUBL:to-WDUB': [{ headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Bay Fair', lineName: 'Blue line', platform: '2' }],
  'DELN:to-RICH': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }],
  'DELN:to-PLZA': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }],
  'PLZA:to-DELN': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }],
  'PLZA:to-NBRK': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }],
  'EMBR:to-MONT': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'EMBR:to-WOAK': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'FRMT:to-WARM': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'FRMT:to-UCTY': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'FTVL:to-COLS': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'FTVL:to-LAKE': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'GLEN:to-BALB': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'GLEN:to-24TH': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'HAYW:to-SHAY': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'HAYW:to-BAYF': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'LAFY:to-WCRK': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'LAFY:to-ORIN': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'LAKE:to-FTVL': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'LAKE:to-12TH-WOAK': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'MCAR:to-ASHB-ROCK': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Antioch', lineName: 'Yellow line', platform: '3' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '3' }],
  'MCAR:to-19TH': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '4' }, { headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '4' }],
  'MLBR:to-SFIA': [{ headsign: 'Richmond', lineName: 'Red line', platform: '3' }, { headsign: 'SF Airport', lineName: 'Yellow line', platform: '3' }, { headsign: 'Antioch', lineName: 'Yellow line', platform: '3' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '3' }],
  'MLPT:to-BERY': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'MLPT:to-WARM': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'MONT:to-POWL': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'MONT:to-EMBR': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'NBRK:to-PLZA': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '1' }, { headsign: 'Richmond', lineName: 'Red line', platform: '1' }],
  'NBRK:to-DBRK': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }],
  'NCON:to-PITT': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'NCON:to-CONC': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'OAKL:to-COLS': [{ headsign: 'Coliseum', lineName: 'Grey line', platform: '1' }],
  'ORIN:to-LAFY': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'ORIN:to-ROCK': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'PITT:to-PCTR': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }],
  'PITT:to-NCON': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'PCTR:to-ANTC': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }],
  'PCTR:to-PITT': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'PHIL:to-CONC': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'PHIL:to-WCRK': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'POWL:to-CIVC': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'POWL:to-MONT': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'RICH:to-DELN': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '2' }],
  'ROCK:to-ORIN': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'ROCK:to-MCAR': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'SBRN:to-MLBR-SFIA': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'SBRN:to-SSAN': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'SFIA:to-MLBR': [{ headsign: 'Millbrae', lineName: 'Red line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'SFIA:to-SBRN': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'SANL:to-BAYF': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'SANL:to-COLS': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'SHAY:to-UCTY': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'SHAY:to-HAYW': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'SSAN:to-SBRN': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'SSAN:to-COLM': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
  'UCTY:to-FRMT': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'UCTY:to-SHAY': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'WCRK:to-PHIL': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '1' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '1' }],
  'WCRK:to-LAFY': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '2' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '2' }],
  'WARM:to-MLPT': [{ headsign: 'Berryessa / North San Jose', lineName: 'Orange line', platform: '1' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '1' }],
  'WARM:to-FRMT': [{ headsign: 'Richmond', lineName: 'Orange line', platform: '2' }, { headsign: 'Daly City', lineName: 'Green line', platform: '2' }],
  'WDUB:to-DUBL': [{ headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '1' }],
  'WDUB:to-CAST': [{ headsign: 'Daly City', lineName: 'Blue line', platform: '2' }, { headsign: 'Bay Fair', lineName: 'Blue line', platform: '2' }],
  'WOAK:to-EMBR': [{ headsign: 'SF Airport', lineName: 'Yellow line', platform: '1' }, { headsign: 'Daly City', lineName: 'Blue line', platform: '1' }, { headsign: 'Daly City', lineName: 'Green line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Red line', platform: '1' }, { headsign: 'Millbrae', lineName: 'Yellow line', platform: '1' }],
  'WOAK:to-12TH-LAKE': [{ headsign: 'Antioch', lineName: 'Yellow line', platform: '2' }, { headsign: 'Dublin / Pleasanton', lineName: 'Blue line', platform: '2' }, { headsign: 'Berryessa / North San Jose', lineName: 'Green line', platform: '2' }, { headsign: 'Richmond', lineName: 'Red line', platform: '2' }, { headsign: 'Pittsburg / Bay Point', lineName: 'Yellow line', platform: '2' }],
};
