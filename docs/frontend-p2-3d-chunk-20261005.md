# Studio 前端 P2：3D 查看器按需加载

日期：2026-10-05。

## 改动

- `AssetInspector` 不再静态导入 `three`、R3F 和 Drei；`AssetViewer` 改为进入 3D 分支后懒加载。
- 入口 `App` 删除 2.5 秒后无条件预载 `AssetInspector` 的逻辑，普通工作台首屏不会为了可能访问资产检查器而下载 3D 依赖。
- 3D 查看器加载期间显示明确的状态占位；已有 AI 原画的资产不会挂载 3D 查看器。

## 构建结果

改造前构建产物中 `AssetInspector` 约 **853.86 kB**（gzip 231.72 kB）。改造后：

- `AssetInspector` 路由 chunk：**14.45 kB**（gzip 5.50 kB）
- `AssetViewer` 独立 chunk：**839.73 kB**（gzip 226.78 kB）
- 主入口 chunk：约 **356.65 kB**，基本不变

这减少了普通路由进入资产检查器时的首屏下载压力；真正打开 3D 查看器时仍需下载 Three 依赖，属于按需转移，不能宣称总下载量消失。

## 验证

- Vitest：45 / 45 通过
- TypeScript：通过
- 相关 ESLint：通过
- Vite 生产构建：通过
- 架构边界测试继续通过，页面没有直接引入 Three 包。

构建仍会提示 `AssetViewer` 单 chunk 大于 500 kB。后续可按功能进一步拆分 Drei/材质控制面板，或评估是否用轻量 2D 预览替代部分场景；这需要真实使用数据和浏览器性能采样后决定。
