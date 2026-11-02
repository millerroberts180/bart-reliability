import { VIEW_LABELS, VIEWS, type View } from '../hooks/useView';
import { ViewLink } from './ViewLink';

export const REPOSITORY_URL = 'https://github.com/millerroberts180/bart-reliability';
export const METHODOLOGY_URL = `${REPOSITORY_URL}#readme`;

/** The persistent header. The three views stay visible as text links at every width. */
export function SiteHeader({ view }: { view: View }) {
  return (
    <header className="site-header">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <div className="site-header__inner">
        <ViewLink view="highlights" className="wordmark">
          ETA Reliability
        </ViewLink>
        <nav className="site-nav" aria-label="Primary">
          <ul className="site-nav__views">
            {VIEWS.map((v) => (
              <li key={v}>
                <ViewLink view={v} className="site-nav__link" aria-current={v === view ? 'page' : undefined}>
                  {VIEW_LABELS[v]}
                </ViewLink>
              </li>
            ))}
          </ul>
          <a className="site-nav__source" href={REPOSITORY_URL}>
            Source on GitHub
          </a>
        </nav>
      </div>
    </header>
  );
}
