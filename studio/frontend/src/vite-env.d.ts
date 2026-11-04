/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 后端鉴权令牌（与后端 STUDIO_AUTH_TOKEN 一致；留空 = 本地开放模式） */
  readonly VITE_STUDIO_TOKEN?: string;
  /** dev 代理目标后端地址 */
  readonly VITE_BACKEND?: string;
  /** 分离部署时的后端源站，例如 https://api.example.com */
  readonly VITE_BACKEND_URL?: string;
  /** 可选 WebSocket 源站；不设置时由 VITE_BACKEND_URL 自动转换为 ws(s) */
  readonly VITE_WS_BACKEND_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
