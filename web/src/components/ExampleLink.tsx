import type { ReactNode } from 'react';

export const EXAMPLE_HEADING_ID = 'example-title';

/**
 * Link to the forecast example. The fragment scrolls to the example heading, and
 * the click handler also moves focus there so keyboard and screen-reader users
 * continue from where they landed.
 */
export function ExampleLink({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <a
      className={className}
      href={`#${EXAMPLE_HEADING_ID}`}
      onClick={() => document.getElementById(EXAMPLE_HEADING_ID)?.focus({ preventScroll: true })}
    >
      {children}
    </a>
  );
}
