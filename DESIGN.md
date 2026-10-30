---
name: CreativeForge Studio
description: A mist-blue atelier for turning natural-language ideas into game-ready assets.
colors:
  canvas: "#F3F6FA"
  paper: "#FBF9F4"
  surface-1: "#EAF0F6"
  surface-2: "#E1E8F1"
  line: "#CBD5E3"
  ink-blue: "#25345A"
  ink-blue-2: "#394968"
  ink-blue-3: "#4E5D7B"
  ink-blue-4: "#526079"
  mist-blue: "#AEBFD7"
  ember: "#93A9C4"
  ember-ink: "#4A627E"
  wax-red: "#8E4657"
  success: "#3E6553"
  warning: "#765A2C"
  danger: "#8E4657"
typography:
  display:
    fontFamily: "Cormorant Garamond, Noto Serif SC, serif"
    fontSize: "clamp(2.75rem, 5vw, 5rem)"
    fontWeight: 600
    lineHeight: 0.98
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Noto Serif SC, Cormorant Garamond, serif"
    fontSize: "2.125rem"
    fontWeight: 900
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  body:
    fontFamily: "Outfit, Noto Sans SC, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "Outfit, Noto Sans SC, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "0.06em"
  code:
    fontFamily: "IBM Plex Mono, ui-monospace, monospace"
    fontSize: "0.75rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
rounded:
  xs: "4px"
  sm: "6px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.ink-blue}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-primary-hover:
    backgroundColor: "{colors.ink-blue-2}"
    textColor: "{colors.paper}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  button-secondary:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  letter-card:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.lg}"
    padding: "24px"
  dossier-panel:
    backgroundColor: "{colors.surface-1}"
    textColor: "{colors.ink-blue}"
    rounded: "{rounded.lg}"
    padding: "20px"

---

# Design System: CreativeForge Studio

## Overview

**Creative North Star: "The Mist-Blue Atelier"**

CreativeForge should feel like a working atelier rather than a control panel: ivory work surfaces, mist-blue air, ink-blue typography, silver rules, and a few wax-red moments reserved for consequence. The visual world borrows the poise and ceremony of a rococo salon, but translates it into a production tool where the asset, the agent's reasoning, and the next action remain immediately legible.

**Key Characteristics:**

- Paper and vellum surfaces with precise silver-blue rules.
- Ink-blue type on warm ivory, with mist-blue used as atmosphere rather than decoration.
- One expressive moment in the opening sequence; routine product motion stays quiet.
- Dossier-like secondary panels, ticket-like controls, and postmark-like metadata.
- Crisp SVG scrollwork, ribbon bands, crests, and arched rules anchor the salon atmosphere.
- Dense work areas stay calm, rectangular, and scan-friendly.
- Chinese typography is designed, not left to fallback.

## Colors

### Primary

- **Ink Blue `#25345A`** — primary text, primary actions, and authoritative labels.
- **Mist Blue `#AEBFD7`** — atmospheric fields, selected surfaces, and quiet brand presence.
- **Wax Red `#8E4657`** — destructive actions, irreversible confirmation, and rare seals of consequence.

### Neutral

- **Paper / Ivory `#FBF9F4`** — primary work paper.
- **Canvas `#F3F6FA`** — application background and atmospheric wash.
- **Surface `#EAF0F6`** — secondary panels, toolbars, and dossier interiors.
- **Mist Silver `#93A9C4`** — rules, icons, muted metadata, and disabled text.
- **Line `#CBD5E3`** — one-pixel borders and separators.

Success, warning, and danger use `#3E6553`, `#765A2C`, and `#8E4657` and always pair with text or a shape cue.

### Named Rules

**The Consequence Rule.** Wax red never decorates inactive content; it marks a decision, interruption, or irreversible action.

**The Ink-on-Paper Rule.** Body text and controls use ink blue on ivory or canvas, not gray on blue. Secondary text is tinted from ink blue rather than neutral gray.

## Typography

### Hierarchy

- **Display** — Cormorant Garamond with Noto Serif SC fallback; opening titles, empty-state statements, and one focal heading per surface.
- **Title** — Noto Serif SC at 28–34px; page and section headings.
- **Body** — Outfit with a Chinese sans fallback; labels, controls, descriptions, and data.
- **Label** — Outfit at 12px, weight 600, moderate tracking; navigation and metadata.
- **Code** — IBM Plex Mono; paths, task IDs, JSON, logs, and numeric measurements.

### Named Rules

**The Chinese Voice Rule.** Latin display faces may set English and French accents, but Chinese display text always uses Noto Serif SC with its own weight and line-height tuning.

**The Label Rule.** Display and script faces never appear in buttons, form labels, table headers, or dense operational text.

## Layout

Desktop uses a three-part composition: a navigation folio on the left, the working letter in the center, and an optional dossier on the right. The center column owns the task; side regions are secondary and may collapse. At 1280px and below the left folio may rail; at 1024px and below the dossier becomes a drawer; below 768px the interface becomes a single column with a compact bottom navigation.

Page padding uses a 4px rhythm with 16/24/32/48px steps. Dense tables and logs may use compact rows, but page-level sections keep generous separation. Reading text stays within 65–75ch. The 3D, playtest, and animation canvases take all remaining space and receive only a light frame.

## Elevation & Depth

Borders carry most structure. Shadows appear only for floating menus, drawers, and the opening overlay. Elevation uses an offset and soft blur; no zero-offset colored halos. Paper surfaces may use a subtle inner highlight, but not a double border-and-heavy-shadow treatment.

## Shapes

Corners stay in the 6–18px range. Primary containers remain stable rectangles with 14px radius. Rococo expression uses authored SVG geometry: a crest for the identity, a double-rule arch for the workspace, scrollwork corners for page headers, and fleurons for card headings. Ribbon bands and oval stamps carry metadata or state. Ornament is a layer above layout, never an alternative to hit areas, text flow, or canvas space.

## Components

### Buttons

Primary buttons use ink blue with paper text and a compact rectangular shape. Secondary buttons use paper with a silver-blue border. Hover moves one pixel and strengthens the rule, never the shadow. Pressed state compresses to 98%. Focus uses a two-ring ivory/ink outline. Destructive actions use wax red and explicit verbs.

### Chips

Chips are compact stamps: ivory fill, silver rule, ink-blue label. Selected chips use mist blue with ink-blue text. Chips never use wax red unless they represent a destructive filter.

### Cards / Containers

Letter cards use ivory, a 14px radius, a one-pixel line border, and generous internal spacing. Avoid nested cards. Use a title rule and body rhythm instead of stacking decorated boxes.

### Inputs / Fields

Fields use ivory inset surfaces, a silver-blue rule, and ink-blue caret and text. Placeholder text remains at least 4.5:1 contrast. Error text names the problem and recovery in the product's language.

### Navigation

The left folio groups destinations under quiet ink-blue headings with silver rules. The active destination receives a mist-blue field and a small wax-red bookmark, not a full saturated highlight. Mobile navigation keeps the same vocabulary in a compact form.

### Signature Components

The dossier panel is the signature secondary surface: a cool paper field with a ribbon tab, a compact heading, and a vertical sequence of facts. The ornament set is its companion grammar: `RococoCrest` for identity, `RococoDivider` for section transitions, `RococoCorner` for page frames, `RococoFrame` for the workspace arch, and `RococoRibbon` for labels. Ornaments are `aria-hidden`, pointer-transparent, and never replace textual meaning.

### Ornament Budget

Each page may carry one header corner, one section divider, and one crest or ribbon at a major anchor. Cards receive only the small fleuron in their heading. Dense tables, logs, canvas controls, and 3D viewports receive no extra scrollwork.

### Motion

Routine transitions use 120–320ms with confident ease-out. The opening sequence is the one authored spectacle: the desktop version runs 4.5s once per local day, moves through typographic frames and a final seal, then pulls back into the loaded workspace over 240ms. Mobile uses a 1.6s version; reduced motion uses a 1.15s fade of the final mark. Any click, Enter, Space, or Escape skips it. Page-load choreography never repeats inside the product.

## Do's and Don'ts

### Do:

- Use real product content and actual status vocabulary.
- Pair every semantic color with text or shape.
- Keep the center work area calm and the decorative budget concentrated.
- Test Chinese, English, mixed strings, long paths, and large numbers at every breakpoint.
- Use `prefers-reduced-motion` for every authored sequence.
- Use crisp SVG linework for rococo ornament and keep it pointer-transparent.

### Don't:

- Copy Kimi Code branding, copy, or page content.
- Put display fonts in operational labels.
- Nest cards or add ornament to every panel.
- Use emoji, raster doodles, or decorative glyphs as ornaments.
- Use blur, gradients, or texture as a substitute for hierarchy.
- Let the opening animation block access when assets or routes fail.
