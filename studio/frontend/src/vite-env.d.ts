/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端鉴权令牌（与后端 STUDIO_AUTH_TOKEN 一致；留空 = 本地开放模式） */
  readonly VITE_STUDIO_TOKEN?: string;
  /** dev 代理目标后端地址 */
  readonly VITE_BACKEND?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
