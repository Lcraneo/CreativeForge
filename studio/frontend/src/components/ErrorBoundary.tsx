import { Component, type ErrorInfo, type ReactNode } from "react";

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
      <div className="grid min-h-screen place-items-center bg-[#f1efe9] p-6">
        <div className="w-full max-w-md rounded-2xl border border-line bg-white p-6 shadow-sm">
          <p className="font-mono text-[10px] font-semibold tracking-[0.2em] text-ink-4">
            RENDER ERROR
          </p>
          <h1 className="mt-2 text-lg font-semibold text-ink">页面渲染出错了</h1>
          <pre className="mt-3 max-h-40 overflow-auto rounded-lg bg-[#f6f5ef] p-3 font-mono text-[11px] leading-5 text-ink-3">
            {error.message || String(error)}
          </pre>
          <div className="mt-5 flex gap-3">
            <button
              type="button"
              onClick={this.reset}
              className="min-h-10 rounded-lg bg-ink px-5 text-sm font-medium text-white transition-colors hover:bg-ink-2"
            >
              重试
            </button>
            <button
              type="button"
              onClick={this.reload}
              className="min-h-10 rounded-lg border border-line px-5 text-sm font-medium text-ink-2 transition-colors hover:border-line-strong"
            >
              刷新页面
            </button>
          </div>
        </div>
      </div>
    );
  }
}
