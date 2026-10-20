import { ExampleLink } from './ExampleLink';

export const REPOSITORY_URL = 'https://github.com/millerroberts180/bart-reliability';

export function SiteHeader() {
  return (
    <header className="site-header">
      <ExampleLink className="skip-link">Skip to the ETA forecast</ExampleLink>
      <div className="site-header__inner">
        <a className="wordmark" href="#top">
          ETA Reliability
        </a>
        <nav aria-label="Primary">
          <ul className="site-nav">
            <li>
              <a href="#question">The question</a>
            </li>
            <li>
              <ExampleLink>ETA forecast</ExampleLink>
            </li>
            <li>
              <a href={REPOSITORY_URL}>Source on GitHub</a>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
