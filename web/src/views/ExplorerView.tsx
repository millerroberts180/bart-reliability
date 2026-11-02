import { VIEW_TITLE_ID } from '../App';
import { PredictionExample, type FeaturedTrain } from '../components/PredictionExample';
import { useShowcase } from '../data/ShowcaseContext';
import { HORIZONS } from '../domain/showcase';

export const EXPLORER_DISCLOSURE =
  'This curated replay shows only trains eligible for the model’s 5-, 10- and 15-minute forecast windows.';

export function ExplorerView() {
  const state = useShowcase();
  const showcase = state.status === 'ready' ? state.showcase : null;
  // With no train in the address, open the Highlights view's first entry.
  const first = showcase ? HORIZONS.map((h) => showcase.changes[h][0]).find(Boolean) : undefined;
  const featured: FeaturedTrain | null = first
    ? { station: first.stationId, boarding: first.boardingGroupId, train: first.predictionId }
    : null;

  return (
    <div className="view view--explorer">
      <div className="view-head">
        <h1 id={VIEW_TITLE_ID} className="view-head__title" tabIndex={-1}>
          Train explorer
        </h1>
        <p className="view-head__lede">Choose a station, which way you’re going and a train to read its forecast.</p>
        <p className="view-head__disclosure">{showcase?.meta.disclosure ?? EXPLORER_DISCLOSURE}</p>
      </div>
      {/* Wait for the showcase so the featured train and outcomes are known before the first board loads. */}
      {state.status === 'loading' ? (
        <p className="notice" role="status">
          Loading the replay…
        </p>
      ) : (
        <PredictionExample featured={featured} retrospective={showcase?.retrospective ?? null} />
      )}
    </div>
  );
}
