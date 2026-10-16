import { useEffect, useId, useRef, useState, type FocusEvent, type KeyboardEvent } from 'react';
import { alphabetical, searchStations } from '../domain/stationSearch';
import type { Station } from '../domain/types';

interface StationPickerProps {
  stations: Station[];
  selected: Station | undefined;
  /** Recently chosen station IDs, most recent first. */
  recentIds: string[];
  onSelect: (station: Station) => void;
}

type Section = 'recent' | 'suggested' | 'results' | 'all';

const SECTION_TITLES: Record<Section, string> = {
  recent: 'Recent',
  suggested: 'Suggested',
  results: 'Matching stations',
  all: 'All stations',
};

/**
 * "Where are you boarding?" Closed: the chosen station and a Change button. Open: a
 * searchable combobox (ARIA 1.2: focus stays in the input, the active option is
 * conveyed with aria-activedescendant) over a panel listing recent stations, search
 * results or, on request, every station. The list lives in the panel, never the page.
 */
export function StationPicker({ stations, selected, recentIds, onSelect }: StationPickerProps) {
  const id = useId();
  const labelId = `${id}-label`;
  const inputId = `${id}-input`;
  const listId = `${id}-list`;
  const optionId = (i: number) => `${id}-option-${i}`;

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [browsing, setBrowsing] = useState(false);
  const [active, setActive] = useState(0);
  const [announcement, setAnnouncement] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const changeRef = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);

  const q = query.trim();
  let section: Section;
  let options: Station[];
  let total: number;
  if (q) {
    const result = searchStations(stations, q);
    section = 'results';
    options = result.stations;
    total = result.total;
  } else if (browsing) {
    section = 'all';
    options = alphabetical(stations);
    total = options.length;
  } else {
    const recent = recentIds.flatMap((rid) => stations.filter((s) => s.id === rid));
    // No recents yet: suggest the current (default) station rather than guess a location.
    section = recent.length ? 'recent' : 'suggested';
    options = recent.length ? recent : selected ? [selected] : stations.slice(0, 1);
    total = options.length;
  }
  const activeIndex = Math.max(0, Math.min(active, options.length - 1));
  const activeOption = options[activeIndex];

  useEffect(() => {
    if (open) inputRef.current?.focus();
    else if (restoreFocus.current) {
      restoreFocus.current = false;
      changeRef.current?.focus();
    }
  }, [open]);

  // Keep the active option visible inside the scrolling panel.
  useEffect(() => {
    if (open) document.getElementById(optionId(activeIndex))?.scrollIntoView?.({ block: 'nearest' });
    // optionId is derived from a stable useId value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, activeIndex, section]);

  // A press outside the picker closes it without moving focus.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [open]);

  const openPicker = () => {
    setQuery('');
    setBrowsing(false);
    setActive(0);
    setOpen(true);
  };
  const close = (returnFocus: boolean) => {
    restoreFocus.current = returnFocus;
    setOpen(false);
  };
  const choose = (station: Station) => {
    onSelect(station);
    setAnnouncement(`${station.name} selected as your boarding station.`);
    close(true);
  };

  const onInputKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive(Math.min(activeIndex + 1, options.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(Math.max(activeIndex - 1, 0));
    } else if (e.key === 'Enter' && activeOption) {
      e.preventDefault();
      choose(activeOption);
    }
  };
  const onRootKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (open && e.key === 'Escape') {
      e.preventDefault();
      close(true);
    }
  };
  // Tabbing past the panel closes it and lets focus continue to the next control.
  // A blur with no next element (e.g. the Change button unmounting as the picker
  // opens) is ignored; presses outside are handled by the pointer listener above.
  const onRootBlur = (e: FocusEvent<HTMLDivElement>) => {
    const next = e.relatedTarget as Node | null;
    if (open && next && !rootRef.current?.contains(next)) setOpen(false);
  };

  const status = (() => {
    if (section === 'results') {
      if (total === 0) return `No stations match “${q}”.`;
      const count = total > options.length ? `${options.length} of ${total} stations` : `${total} ${total === 1 ? 'station' : 'stations'}`;
      return `${count} match “${q}”.`;
    }
    if (section === 'all') return `All ${total} stations, alphabetical.`;
    if (section === 'recent') return `${total} recent ${total === 1 ? 'station' : 'stations'}. Type to search all ${stations.length}.`;
    return `Suggested: ${options[0]?.name ?? 'none'}. Type to search all ${stations.length} stations.`;
  })();

  return (
    // The div only routes Escape and focus-out from its controls; it is not interactive itself.
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div className={`picker${open ? ' is-open' : ''}`} ref={rootRef} onKeyDown={onRootKeyDown} onBlur={onRootBlur}>
      {open ? (
        <label id={labelId} htmlFor={inputId} className="field__label">
          Where are you boarding?
        </label>
      ) : (
        <p id={labelId} className="field__label">
          Where are you boarding?
        </p>
      )}

      {open ? (
        <div className="picker__open">
          <input
            ref={inputRef}
            id={inputId}
            className="picker__input"
            type="text"
            role="combobox"
            value={query}
            placeholder="Search stations"
            autoComplete="off"
            autoCapitalize="none"
            spellCheck={false}
            enterKeyHint="go"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={activeOption ? optionId(activeIndex) : undefined}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={onInputKeyDown}
          />
          <div className="picker__panel">
            <p className="visually-hidden" aria-live="polite" data-testid="picker-status">
              {status}
            </p>
            <p className="picker__section" aria-hidden="true">
              {SECTION_TITLES[section]}
            </p>
            <div id={listId} role="listbox" aria-label={SECTION_TITLES[section]} className="picker__list">
              {options.map((station, i) => (
                // Keyboard use is handled on the combobox input via aria-activedescendant.
                // eslint-disable-next-line jsx-a11y/click-events-have-key-events
                <div
                  key={station.id}
                  id={optionId(i)}
                  role="option"
                  tabIndex={-1}
                  aria-selected={i === activeIndex}
                  className={`picker__option${i === activeIndex ? ' is-active' : ''}`}
                  onMouseDown={(e) => e.preventDefault()}
                  onMouseMove={() => setActive(i)}
                  onClick={() => choose(station)}
                >
                  <span className="picker__option-name">{station.name}</span>
                  {station.id === selected?.id && <span className="picker__option-note">Current</span>}
                </div>
              ))}
            </div>
            {section === 'results' && total === 0 && (
              <p className="picker__empty">No stations match “{q}”. Check the spelling, or browse all stations.</p>
            )}
            {section === 'results' && total > options.length && (
              <p className="picker__more">
                Showing {options.length} of {total}. Keep typing to narrow the list.
              </p>
            )}
            {section !== 'all' && (
              <button
                type="button"
                className="picker__browse"
                onClick={() => {
                  setQuery('');
                  setBrowsing(true);
                  setActive(0);
                  inputRef.current?.focus();
                }}
              >
                Browse all {stations.length} stations
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="picker__selected">
          <span className="picker__current">{selected?.name ?? 'Loading stations…'}</span>
          <button
            ref={changeRef}
            type="button"
            className="picker__change"
            disabled={stations.length === 0}
            aria-haspopup="listbox"
            aria-expanded="false"
            aria-label={selected ? `Change boarding station, currently ${selected.name}` : 'Choose a boarding station'}
            onClick={openPicker}
          >
            Change
          </button>
        </div>
      )}

      <p className="visually-hidden" aria-live="polite">
        {announcement}
      </p>
    </div>
  );
}
