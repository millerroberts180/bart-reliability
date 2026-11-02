import { useShowcase } from '../data/ShowcaseContext';
import { formatLongMoment } from '../domain/eta';
import { useDataSource } from '../hooks/useDataSource';

export const MODEL_SCOPE = 'The model predicts revisions to BART’s published ETA, not physical arrival times.';

/**
 * Shown under the header on every view: what the data is, when it is from, that it is
 * not live, and what the model does and does not predict.
 */
export function ReplayStrip() {
  const showcase = useShowcase();
  const { source, retry } = useDataSource();

  let label: string;
  let moment: string | null = null;
  if (showcase.status === 'ready') {
    label = 'Fixed historical replay';
    moment = showcase.showcase.meta.localTime;
  } else if (source.kind === 'simulated') {
    label = 'Simulated data, not BART data';
  } else if (source.kind === 'replay') {
    label = 'Fixed historical replay';
    moment = `${formatLongMoment(source.asOf)} Pacific`;
  } else if (source.kind === 'checking' || showcase.status === 'loading') {
    label = 'Loading the replay';
  } else {
    label = 'Replay data unavailable';
  }

  return (
    <section className="replay-strip" aria-label="About this data">
      <p className="replay-strip__text">
        <strong className="replay-strip__label">{label}</strong>
        {moment && (
          <>
            <span aria-hidden="true"> · </span>
            <span className="replay-strip__moment">{moment}</span>
          </>
        )}
        <span aria-hidden="true"> · </span>
        <span>Not live</span>
        <span aria-hidden="true"> · </span>
        <span className="replay-strip__scope">{MODEL_SCOPE}</span>
      </p>
      {source.kind === 'unavailable' && showcase.status !== 'ready' && (
        <button type="button" className="button replay-strip__retry" onClick={retry}>
          Try again
        </button>
      )}
    </section>
  );
}
