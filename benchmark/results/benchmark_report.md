# CreativeForge Benchmark Report

Generated: 2026-09-24T09:11:50.797748+00:00
Dataset: 12 assets across 6 categories (8 animated)

## PReCon — pixel reconstruction vs naive pixelate

| Method | Colors | Contour | Pixel Consistency |
| ------ | ------ | ------- | ----------------- |
| NaivePixelate | 37 | 78% | 81% |
| PReCon | 16 | 95% | 90% |

Pixel consistency improvement: **+9.1%**

## FAlign — frame alignment vs raw AI animation

| Method | Root Drift (px/frame) | Foot Sliding | Smoothness |
| ------ | --------------------- | ------------ | ---------- |
| RawAIFrames | 2.25 | 49% | 85% |
| FAlign | 0.00 | 100% | 96% |

Drift reduction: **-100.0%**

## GImport — one-click import vs traditional manual flow

| Flow | Steps | Time |
| ---- | ----- | ---- |
| Traditional | 12 | 45 min |
| GImport | 1 | 0.00 s |

Import success rate: **100%**, speedup: **45x**

## Agent — autonomous planning

- Task completion rate: **100%** (12/12)
- Planning accuracy: **100%**
- Recovery success rate: **100%**
- Average task time: **0.00s**

## CF Score

| Component | Weight | Score |
| --------- | ------ | ----- |
| pixel | 30% | 90% |
| animation | 30% | 99% |
| engine | 25% | 100% |
| agent | 15% | 100% |
| **overall** | 1.00 | **96.6%** |
