import { ExampleLink } from './ExampleLink';

export function Opening() {
  return (
    <section className="opening" id="question" aria-labelledby="page-title">
      <h1 id="page-title" className="opening__title">
        ETA Reliability
      </h1>
      <p className="opening__lede">How stable are BART’s published arrival estimates?</p>
      <p className="opening__cta">
        <ExampleLink className="cta">Try a simulated prediction</ExampleLink>
      </p>

      <aside className="disclosure" aria-labelledby="disclosure-label">
        <p id="disclosure-label" className="disclosure__label">
          Prototype using simulated data
        </p>
        <p className="disclosure__body">
          Every station reading, train and number on this page is simulated. It shows how the finished site will
          work, not what BART’s data says.
        </p>
      </aside>

      <div className="opening__prose">
        <p>
          This project studies how BART changes its published arrival estimates as a train approaches the platform.
          BART publishes an estimated arrival time for every train and keeps updating it. A train shown as six
          minutes away may become seven, then eight, before it reaches the platform.
        </p>
        <p>
          This project predicts those changes: how far BART’s published ETA is likely to move, and how likely it is
          to move by more than a minute. <strong>It does not predict when a train physically arrives.</strong> BART
          publishes no independent record of arrivals, so the reference is BART’s own final published estimate for
          each stop.
        </p>
      </div>
    </section>
  );
}
