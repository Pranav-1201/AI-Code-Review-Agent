/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin, e.g. https://api.example.com. Defaults to localhost:8000. */
  readonly VITE_API_BASE?: string;
  /** Must match the backend's API_KEY when the backend has one configured. */
  readonly VITE_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
