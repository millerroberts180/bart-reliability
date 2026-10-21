import { formatLongMoment } from '../domain/eta';
import { useDataSource, type DataSource } from '../hooks/useDataSource';
import { ExampleLink } from './ExampleLink';

const DISCLOSURE: Record<DataSource['kind'], { label: string; body: (asOf: string) => string; cta: string }> = {
  simulated: {
    label: 'Prototype using simulated data',
    body: () =>
      'Every station reading, train and number on this page is simulated. It shows how the finished site will work, not what BART’s data says.',
    cta: 'Try a simulated prediction',
  },
  replay: {
    label: 'Historical replay of recorded BART data',
    body: (asOf) =>
      `This page replays BART’s recorded feeds as they stood on ${asOf} Pacific. The data is fixed at that moment: it is not live, and nothing on the page updates or counts down. Forecasts use only what was known then, and every forecast is provisional.`,
    cta: 'Try a historical replay',
  },
  // Worded for any source of recorded data: the local API or the published static replay.
  checking: {
    label: 'Loading the data',
    body: () => 'Checking which data this page is showing…',
    cta: 'Try an ETA forecast',
  },
  unavailable: {
    label: 'Data unavailable',
    body: () => 'The page could not load its data, so no BART data or forecasts can be shown.',
    cta: 'Try an ETA forecast',
  },
};

export function Opening() {
  const { source, retry } = useDataSource();
  const disclosure = DISCLOSURE[source.kind];
  const asOf = source.kind === 'replay' ? formatLongMoment(source.asOf) : '';

  return (
    <section className="opening" aria-labelledby="page-title">
      <h1 id="page-title" className="opening__title">
        ETA Reliability
      </h1>
      <p className="opening__lede">How stable are BART’s published arrival estimates?</p>
      <p className="opening__summary">
        A model of how BART will revise a train’s published ETA before it arrives.{' '}
        <strong>It does not predict when a train physically arrives.</strong>
      </p>
      <p className="opening__cta">
        <ExampleLink className="cta">{disclosure.cta}</ExampleLink>
      </p>

      <aside
        className={`disclosure disclosure--${source.kind}`}
        aria-labelledby="disclosure-label"
        aria-busy={source.kind === 'checking'}
      >
        <p id="disclosure-label" className="disclosure__label">
          {disclosure.label}
        </p>
        <p className="disclosure__body">{disclosure.body(asOf)}</p>
        {source.kind === 'unavailable' && (
          <button type="button" className="button disclosure__retry" onClick={retry}>
            Try again
          </button>
        )}
      </aside>
    </section>
  );
}
