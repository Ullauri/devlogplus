/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Override the API base URL. Defaults to "/api/v1" (uses Vite dev proxy).
   * Set to "http://localhost:4010/api/v1" to hit the Prism mock server.
   */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
