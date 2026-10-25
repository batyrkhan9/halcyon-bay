/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Where the core runs. Default http://localhost:8000 */
  readonly VITE_CORE_URL?: string;
  /** "1" runs the whole app on the built-in sample world, no core needed. */
  readonly VITE_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
