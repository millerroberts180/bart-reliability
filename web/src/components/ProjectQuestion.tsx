/** The project's question in full. It follows the forecast, so the tool comes first. */
export function ProjectQuestion() {
  return (
    <section className="question" id="question" aria-labelledby="question-title">
      <h2 id="question-title" className="question__title">
        The question
      </h2>
      <div className="question__prose">
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
