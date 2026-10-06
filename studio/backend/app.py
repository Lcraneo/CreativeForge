"""FastAPI application factory.

Serves the REST + WebSocket API and, when studio/frontend/dist exists,
the built CreativeForge Studio frontend — one process hosts the demo.
"""

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# repo root on sys.path so the backend can import the CreativeForge core
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

FRONTEND_DIST = os.path.join(REPO_ROOT, "studio", "frontend", "dist")


def create_app():
    from studio.backend.agent_runtime.runtime import AgentRuntime
    from studio.backend.api.routes import build_router
    from studio.backend.security import (
        AuthMiddleware,
        RateLimitMiddleware,
        SecurityHeadersMiddleware,
        allowed_origins,
    )
    from studio.backend.websocket.hub import build_ws_router

    app = FastAPI(
        title="CreativeForge Studio",
        description="AI Game Asset Factory — agent console + asset workbench",
        version="1.0.0",
    )
    # add_middleware 后加的在外层：CORS 最外（先应答预检），限流最内
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type"],
        allow_credentials=True,
    )

    runtime = AgentRuntime()
    app.state.runtime = runtime
    app.include_router(build_router(runtime))
    app.include_router(build_ws_router(runtime))

    if os.path.isdir(FRONTEND_DIST):
        from fastapi.responses import FileResponse, JSONResponse
        from fastapi.staticfiles import StaticFiles

        # hashed build assets served straight from disk…
        app.mount(
            "/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets"
        )

        # 仓库级小游戏（games/coin-arena）静态伺服。必须注册在 SPA 兜底
        # 路由之前——catch-all 会把 /game/* 吞成 index.html
        game_dir = os.path.join(REPO_ROOT, "games", "coin-arena")
        if os.path.isdir(game_dir):
            app.mount("/game", StaticFiles(directory=game_dir, html=True), name="game")

        # /api 前缀的未知路径必须 404 JSON——SPA 兜底会把它们当成前端路由
        # 返回 200 index.html，前端 request() 会拿 HTML 当 JSON 解析报错
        @app.get("/api/{full_path:path}", include_in_schema=False)
        def api_not_found(full_path: str):
            return JSONResponse({"detail": "not found"}, status_code=404)

        # …everything else falls back to index.html so client-side routes
        # (/asset, /agents, ...) survive a hard refresh
        index_file = os.path.join(FRONTEND_DIST, "index.html")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa_fallback(full_path: str):
            candidate = os.path.join(FRONTEND_DIST, full_path)
            if full_path and os.path.isfile(candidate):
                return FileResponse(candidate)
            return FileResponse(index_file)

    return app


app = create_app()
