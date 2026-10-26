/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "mock" (default), "http" (local API) or "static" (the published replay). */
  readonly VITE_DATA_MODE?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_BASE_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/**
 * The page for this build's data mode. vite.config.ts resolves '@data-mode' to one of
 * src/modes/mock.tsx, http.tsx or static.tsx, from VITE_DATA_MODE, so a build bundles only
 * that mode's prediction client and data. src/modes/modes.test.tsx checks that all three
 * match this declaration.
 */
declare module '@data-mode' {
  export function Site(): import('react').JSX.Element;
}
