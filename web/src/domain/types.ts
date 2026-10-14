// Data contracts shared by every PredictionClient implementation.
//
// Terminology follows the analysis project: the model predicts how BART will
// revise its own published ETA. Nothing here represents an observed arrival.
// Timestamps are ISO 8601 strings in UTC; durations are whole seconds.

/** A travel direction at a station, described by where its trains go. */
export interface Direction {
  /** GTFS direction_id as a string ("0" or "1"). */
  id: string;
  /** Short label for the choice, e.g. "Toward Antioch and Richmond". */
  label: string;
  /** Train headsigns served in this direction from this station. */
  destinations: string[];
}

export interface Station {
  /** GTFS stop_id of the platform group, e.g. "EMBR". */
  id: string;
  name: string;
  directions: Direction[];
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

export interface TrainPrediction {
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
  /** Predicted change BART will make to this ETA. Positive = later. */
  predictedRevisionSeconds: number;
  revisionInterval: RevisionInterval;
  /** Probability that BART revises this ETA by more than the threshold (either way). */
  revisionProbability: number;
  stability: StabilityClass;
}

/** One published ETA in a prediction's history (displayed in a later milestone). */
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

export interface PredictionResponse {
  stationId: string;
  directionId: string;
  /** BART feed snapshot the predictions were computed from. */
  feedTimestamp: string;
  /** When the model produced these predictions (the model timestamp). */
  generatedAt: string;
  /** Upcoming trains in published-ETA order; empty when none are scheduled. */
  trains: TrainPrediction[];
  alerts: AlertContext[];
  model: ModelMetadata;
}

export interface HealthStatus {
  status: 'ok' | 'degraded';
  /** Latest feed snapshot available to the API. */
  latestFeedTimestamp: string;
}
