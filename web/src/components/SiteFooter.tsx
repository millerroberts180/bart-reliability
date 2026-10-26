// BART's open data is used under its Developer License Agreement, which does not allow BART
// trademarks or copyrighted materials with the data: the site credits BART in words and
// uses no BART logo or official system map.
export const BART_DEVELOPER_URL = 'https://www.bart.gov/about/developers';
export const BART_LICENSE_URL = 'https://www.bart.gov/schedules/developers/developer-license-agreement';

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <p>
        Source data: GTFS schedule and GTFS-Realtime feeds from BART (San Francisco Bay Area Rapid Transit District),
        published through BART’s <a href={BART_DEVELOPER_URL}>developer program</a> and used under the{' '}
        <a href={BART_LICENSE_URL}>BART Developer License Agreement</a>.
      </p>
      <p>
        ETA Reliability is an independent project. It is not an official BART product, and it is not affiliated with or
        endorsed by BART.
      </p>
    </footer>
  );
}
