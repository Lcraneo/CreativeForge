import { Component, type ErrorInfo, type ReactNode } from "react";
import { RococoCrest, RococoDivider } from "./rococo/RococoOrnaments";

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** 路由级错误兜底：渲染异常落在暖纸风格的恢复页，而不是白屏。 */
export default class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Uncaught render error:", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  private reload = () => window.location.reload();

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="grid min-h-screen place-items-center bg-canvas p-6">
        <div className="w-full max-w-md rounded-lg border border-line bg-paper p-6 shadow-e2">
          <RococoCrest className="mb-3 h-12 w-11 text-ink" />
          <p className="font-mono text-[10px] font-semibold tracking-[0.2em] text-ink-4">
            RENDER ERROR
          </p>
          <h1 className="mt-2 font-serif text-2xl font-black text-ink">页面渲染出错了</h1>
          <RococoDivider className="mt-3 h-4 w-40 text-line-strong/70" />
          <pre className="mt-3 max-h-40 overflow-auto rounded-md border border-line bg-surface-1 p-3 font-mono text-[11px] leading-5 text-ink-3">
            {error.message || String(error)}
          </pre>
          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={this.reset}
              className="min-h-10 rounded-sm border border-primary bg-primary px-5 text-sm font-medium text-paper transition-colors hover:bg-primary-hover"
            >
              重试
            </button>
            <button
              type="button"
              onClick={this.reload}
              className="min-h-10 rounded-sm border border-line bg-paper px-5 text-sm font-medium text-ink-2 transition-colors hover:border-line-strong hover:bg-surface-1"
            >
              刷新页面
            </button>
          </div>
        </div>
      </div>
    );
  }
}
