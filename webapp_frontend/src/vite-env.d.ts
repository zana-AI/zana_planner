/// <reference types="vite/client" />

interface Window {
  Telegram?: {
    WebApp?: {
      openTelegramLink: (url: string) => void;
      [key: string]: unknown;
    };
  };
}

interface ImportMetaEnv {
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
