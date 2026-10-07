FROM node:24-slim AS frontend
WORKDIR /app/studio/frontend
COPY studio/frontend/package.json studio/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY studio/frontend ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY studio/backend/requirements.txt ./studio/backend/
RUN pip install --no-cache-dir -r studio/backend/requirements.txt
COPY core/ protocol/ schemas/ packages/ adapters/ precon/ falign/ gimport/ agent/ agents/ benchmark/ studio/ examples/ tests/ ./
COPY --from=frontend /app/studio/frontend/dist ./studio/frontend/dist
# ModelScope 创空间 docker 模式固定访问 7860；本地 compose 用 PORT=8600 覆盖。
# 创空间运行时可能不从 WORKDIR 启动进程：cd + PYTHONPATH 双保证 studio 包可导入
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["sh", "-c", "cd /app && exec python -m studio.backend.main --host 0.0.0.0 --port ${PORT:-7860}"]
