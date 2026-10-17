// Data contracts shared by every PredictionClient implementation.
//
// Terminology follows the analysis project: the model predicts how BART will
// revise its own published ETA. Nothing here represents an observed arrival.
// Timestamps are ISO 8601 strings in UTC; durations are whole seconds.

/**
 * One way a train can leave a station: the trains a rider boards from one side of the
 * line (docs/boarding_groups.md). Built from the schedule's platforms and neighbouring
 * stations, never from GTFS direction_id, which each route defines for itself.
 */
export interface BoardingGroup {
  /** Stable ID from the shape of the network, e.g. "to-SHAY" (toward South Hayward). */
  id: string;
  /** Short label for the choice, e.g. "Toward Daly City and Richmond". */
  label: string;
  /** Train destinations served from this side of the station. */
  destinations: string[];
  /** The platform every train in the group leaves from, or null when they use more than one. */
  platform: string | null;
  /** GTFS direction_id values of the group's trains: route-relative, read only to translate old ?direction= links. */
  gtfsDirectionIds: string[];
}

export interface Station {
  /** GTFS stop_id of the parent station, e.g. "EMBR". */
  id: string;
  name: string;
  boardingGroups: BoardingGroup[];
  /** Every train here starts or ends its trip here (a terminal): none passes through. */
  endOfLine: boolean;
}

/** Model view of how stable a published ETA is, derived from revisionProbability. */
export type StabilityClass = 'likely_to_hold' | 'may_be_revised' | 'likely_to_be_revised';

/** A range of predicted revisions, e.g. the central 80%. */
export interface RevisionInterval {
  lowerSeconds: number;
  upperSeconds: number;
  /** Coverage as a fraction, e.g. 0.8. */
  level: number;
}

/**
 * Why a train has, or lacks, a model forecast. Only "ok" carries model numbers; every
 * other status means the model has not demonstrated support for this train, so only
 * BART's published ETA may be shown (see docs/local_api.md).
 */
export type PredictionStatus =
  | 'ok'
  | 'outside_model_horizon'
  | 'outside_model_population'
  | 'fallback_required'
  | 'features_unavailable';

interface TrainBase {
  /** Stable identifier for this trip-stop prediction; keys the history endpoint. */
  predictionId: string;
  tripId: string;
  /** Rider-facing line name, e.g. "Yellow line". */
  lineName: string;
  /** Destination shown on the train. */
  headsign: string;
  carCount: number | null;
  /** BART's current published ETA, in seconds after the feed snapshot. */
  currentEtaSeconds: number;
  /** BART's current published arrival estimate as a clock time. */
  currentEtaAt: string;
  /** Scheduled platform at this station; null when it is not known for certain. */
  platform: string | null;
}

/** A train the model supports: a forecast, with a range only when one can be supported. */
export interface ForecastTrain extends TrainBase {
  predictionStatus: 'ok';
  statusReason: null;
  /** Predicted change BART will make to this ETA. Positive = later. */
  predictedRevisionSeconds: number;
  /** null when no honest range is available; never replaced by an invented one. */
  revisionInterval: RevisionInterval | null;
  /** Probability that BART revises this ETA by more than the threshold (either way). */
  revisionProbability: number;
  stability: StabilityClass;
}

/** A train outside the model's support: BART's published ETA only, no model numbers. */
export interface EtaOnlyTrain extends TrainBase {
  predictionStatus: Exclude<PredictionStatus, 'ok'>;
  statusReason: string | null;
  predictedRevisionSeconds: null;
  revisionInterval: null;
  revisionProbability: null;
  stability: null;
}

export type TrainPrediction = ForecastTrain | EtaOnlyTrain;

export function hasForecast(train: TrainPrediction): train is ForecastTrain {
  return train.predictionStatus === 'ok';
}

/** One published ETA in a prediction's history. */
export interface PredictionHistoryPoint {
  /** Feed snapshot time at which BART published this ETA. */
  feedTimestamp: string;
  /** Published ETA at that snapshot, as a clock time. */
  publishedEtaAt: string;
  /** Seconds from the snapshot to the published ETA. */
  publishedEtaSeconds: number;
}

export type AlertScope = 'system' | 'route' | 'station';
export type AlertCategory = 'planned_work' | 'incident' | 'unclassified';

/**
 * A service alert that was visible in BART's alert feed when the prediction was
 * made. Visibility is not evidence of an operational disruption.
 */
export interface AlertContext {
  alertId: string;
  scope: AlertScope;
  category: AlertCategory;
  headerText: string;
  /** First feed snapshot in which this alert version appeared. */
  visibleSince: string;
}

export interface ModelMetadata {
  modelVersion: string;
  /** End of the training window. */
  trainedThrough: string;
  /** Revision size that counts as "revised" for revisionProbability. */
  revisionThresholdSeconds: number;
  /** True while the site runs on simulated fixtures instead of a trained model. */
  simulated: boolean;
}

/**
 * Where a response's data came from. "historical_replay" is recorded BART data
 * answered as of a past moment; it must always be labelled and never called live.
 */
export type DataProvenance = 'simulated' | 'historical_replay';

export interface ReplayInfo {
  /** The past moment the replay answers as of; the reference clock for freshness. */
  asOf: string;
}

export interface PredictionResponse {
  dataProvenance: DataProvenance;
  /** Present exactly when dataProvenance is "historical_replay". */
  replay: ReplayInfo | null;
  stationId: string;
  boardingGroupId: string;
  /** BART feed snapshot the predictions were computed from. */
  feedTimestamp: string;
  /** When the model produced these predictions; in a replay, the replay time. */
  generatedAt: string;
  /** Upcoming trains in published-ETA order; empty when none are scheduled. */
  trains: TrainPrediction[];
  /**
   * Trains the feed lists at this station that match no scheduled trip, so which way
   * they leave is unknown and they are not in `trains`. Always 0 for simulated data.
   */
  unplacedTrainCount: number;
  /**
   * Trains the feed lists at this station whose trips end here: they cannot be boarded,
   * so they are not in `trains`. Always 0 for simulated data.
   */
  terminatingTrainCount: number;
  alerts: AlertContext[];
  model: ModelMetadata;
}

export interface HealthStatus {
  status: 'ok' | 'degraded';
  /** Latest feed snapshot available to the API; null only when none is loaded. */
  latestFeedTimestamp: string | null;
  dataProvenance: DataProvenance;
  replay: ReplayInfo | null;
}
