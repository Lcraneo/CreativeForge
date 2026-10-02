# onetake (vendored snapshot)

Upstream: https://github.com/feitangyuan/onetake — skill snapshot, lineage `otk-7f3e1c`.
Snapshot date: 2026-10-02, taken from `D:/onetake-main.zip`.
License: **PolyForm Noncommercial 1.0.0** (see `LICENSE`) — free for noncommercial use only.
CreativeForge 定位：External Creative Capability（发布视频 / Showcase Engine），不属于自研核心
（PReCon / FAlign / GImport）。方案与验收标准见 `docs/onetake-integration-plan.md`。

## Rules

- Never edit vendored files in place. Local changes go to `patches/` (replayed on upgrade);
  runtime behavior is adjusted by the caller (`adapters/onetake/render_client.py`) via CLI
  flags / env only.
- Upgrade = re-snapshot from upstream + replay `patches/`.
- Curated subset only: render/verify pipeline, motion library, looks, authoring docs.
  Cases / gallery / heavy assets stay upstream (本仓库不入库 ~70MB 案例资产)。

## Inventory

- `lib/motion.js` → `window.OM`（39 个 f(t) 动效原语；确定性，渲染路径禁 Math.random）
- `lib/ui_kit.js` → `window.UIK`（产品 UI 重建助手）
- `templates/comp.html` → 合成骨架（`__seek/__ready/__meta` 契约，`?play/?t=` 预览）
- `looks/` → 八色令牌主题 + OFL 字体（`look.py apply/from-shot`）
- `scripts/` → render.py（1080p30 草稿 / 4K60 终稿，快门运动模糊）、stills.py、probe.py、
  verify_promo.py（验收 oracle 五腿）、analyze_ref.py、look.py、sfx_palette.py、test_motion.js
- `SKILL.md` + `references/{composition,motion-library,rhythm}.md` → 创作协议与硬规则
