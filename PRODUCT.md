# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

CreativeForge is built for game developers, indie studios, technical artists, designers, and solo creators who turn a natural-language brief into playable game assets and engine-ready packages. They work in a browser-based production studio, often alternating between rapid ideation, generation monitoring, visual review, animation checks, playtesting, and export.

## Product Purpose

CreativeForge Studio is an AI game-asset production workbench. It turns a natural-language goal into planned, traceable, reusable game assets through multi-agent orchestration, 2D/3D generation pipelines, animation alignment, engine import, preview, and export. Success means the user can move from concept to an inspectable, playable, exportable asset without losing context or control.

## Positioning

CreativeForge is not a single model call or a generic image generator. Its distinctive mechanism is a shared CreativeAsset protocol spanning planning, generation, animation, 3D, preview, and Unity/Cocos/Godot-oriented export, backed by visible multi-agent execution and in-house production pipelines.

## Operating Context

- The primary surface is the Studio web application at the project root route.
- Users supervise long-running asynchronous work through live events, task state, progress, and failure recovery.
- Asset work spans character art, three-view sheets, animation frames, sprite/2D assets, 3D assets, playtests, arcade scenes, versions, and export packages.
- The interface is Chinese-first, with technical identifiers and pipeline terminology in English.
- The product runs locally or in a hosted deployment and can connect to optional external model providers.
- The existing Studio frontend is React 18 + TypeScript + Vite + Tailwind CSS 4, with Framer Motion, TanStack Query, Zustand, React Router, Three.js, and Konva already in use.

## Capabilities and Constraints

- Preserve all existing routes and workflows: workspace, agent dashboard, history, versions, asset inspection, three-view design, animation studio, export, model settings, 2D playtest, 3D playtest, and arcade.
- Preserve API, WebSocket, task-feed, asset-store, export, model-provider, and playtest behavior.
- Preserve loading, empty, error, disconnected, progress, and retry states.
- Heavy canvas and 3D surfaces must remain usable; decorative chrome must not reduce their working area or frame rate.
- Long-running work and large event streams require bounded, scan-friendly information density.
- No customer names, benchmarks, testimonials, pricing, or commercial claims may be invented.
- The current backend data and unrelated export/history artifacts must not be altered by frontend work.

## Brand Commitments

- The product name is CreativeForge / CreativeForge Studio.
- The product voice is precise, calm, capable, and slightly artisanal; it should not become theatrical or cryptic.
- The user has pinned the Trianon concept as the reference for atmosphere, material language, and opening-animation ambition. The result must be an original CreativeForge expression, not a copy of Kimi branding, logos, copy, or page content.

## Evidence on Hand

- Product and architecture facts: `README.md` and `docs/`.
- Existing visual system and prior design decisions: `docs/design/02-visual-spec.md`, `docs/design/03-key-screens.md`, and `docs/design/ui-refresh-20261006/`.
- Existing rendered evidence: screenshots under `docs/design/ui-refresh-20261006/` and `D:/pyProject/.screenshots/`.
- Reference concept source and licensed assets: the public Trianon repository and its MIT/OFL/CC0 notices.
- No approved customer case studies, commercial metrics, or production testimonials are available.

## Product Principles

1. Make agent work legible: planning, state, progress, and failure should never feel like a black box.
2. Keep the asset as the center of gravity: every screen should make the current creative object easier to understand or improve.
3. Preserve continuity from idea to playable output: the same asset identity should follow generation, review, animation, playtest, versioning, and export.
4. Earn decoration with function: visual character should clarify hierarchy, state, or material provenance, not compete with the task.
5. Prefer recoverable, inspectable workflows over opaque automation.

## Accessibility & Inclusion

The redesign targets WCAG 2.2 AA for contrast, keyboard operation, focus visibility, semantic structure, reduced motion, and touch target sizing. Every animation requires a reduced-motion path, and all critical status information must have a text or shape cue in addition to color.
