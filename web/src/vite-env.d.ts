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
