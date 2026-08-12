---
name: Incident Investigator
description: A calm evidence-led operations console where investigations unfold step by step.
colors:
  paper: "#f5f3ec"
  ink: "#20231f"
  muted: "#687069"
  rule: "#d9d7cd"
  vermilion: "#c94735"
  gold-fold: "#b68a35"
  success: "#307257"
  white-sheet: "#fffefa"
typography:
  display:
    fontFamily: "Segoe UI Variable, Aptos, system-ui, sans-serif"
    fontSize: "clamp(1.7rem, 3vw, 2.75rem)"
    fontWeight: 680
    lineHeight: 1.03
    letterSpacing: "-0.045em"
  body:
    fontFamily: "Segoe UI Variable, Aptos, system-ui, sans-serif"
    fontSize: "0.9rem"
    fontWeight: 400
    lineHeight: 1.48
  label:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.68rem"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "0.11em"
rounded:
  none: "0"
  status: "50%"
spacing:
  xs: "0.45rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.45rem"
components:
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    height: "2.45rem"
  fold:
    backgroundColor: "{colors.white-sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: "1.1rem 1.2rem 1.15rem"
---

# Design System: Incident Investigator

## Overview

**Creative North Star: "The Unfolding Case File"**

The interface behaves like a precise paper investigation record. A single signal unfolds into evidence, hypotheses, reflection, action, and result; every conclusion remains visually traceable to the previous fold. The atmosphere is calm, tactile, and operational rather than futuristic or theatrical.

The construction grid, numbered spine, clipped paper corners, and sparse vermilion marks form one coherent world. Density is welcome when it preserves the reading path. The surface should feel trustworthy enough for an approval decision and lightweight enough for one developer to run every day.

**Key Characteristics:**

- Warm paper ground with dark ink and rare vermilion emphasis.
- A numbered vertical investigation spine as the signature component.
- Square, clipped geometry; circles are reserved for compact status markers.
- Evidence and action remain more prominent than decorative chrome.
- Motion is limited to the currently active investigation step and respects reduced motion.

## Colors

The palette resembles an annotated engineering case file: warm neutrals carry the content, while vermilion, gold, and green communicate deliberate state.

### Primary

- **Investigation Vermilion:** Marks the current fold, selected language, high-severity text, confidence meters, and primary action.

### Secondary

- **Fold Gold:** Appears only on clipped sheet corners and reflection emphasis.
- **Verified Green:** Indicates connected and successfully completed states.

### Neutral

- **Case Paper:** The persistent workspace ground.
- **Sumi Ink:** Main copy and structural controls.
- **Field Note Gray:** Secondary labels, timestamps, and supporting details.
- **Crease Rule:** Dividers, construction lines, and resting borders.
- **White Sheet:** Investigation folds and selected queue items.

### Named Rules

**The Red Pencil Rule.** Vermilion marks decisions, risk, and active state; it is never used as general decoration.

**The Evidence Contrast Rule.** Status is always carried by text or a symbol as well as color.

## Typography

**Display Font:** Segoe UI Variable with Aptos and system fallbacks  
**Body Font:** Segoe UI Variable with Aptos and system fallbacks  
**Label/Mono Font:** UI monospace with SFMono and Consolas fallbacks

**Character:** A humanist system face keeps operational prose readable, while compact monospaced labels distinguish source, time, status, and identifiers from agent-authored reasoning.

### Hierarchy

- **Display** (680, responsive 1.7–2.75rem, 1.03): Incident titles only; tight tracking gives the case a clear focal point.
- **Title** (660, 0.9–1.12rem): Product name, queue items, action summaries, and fold headings.
- **Body** (400–560, 0.84–0.9rem, 1.45–1.5): Evidence, hypotheses, reflection, and descriptions.
- **Label** (650–750, 0.65–0.68rem, tracked uppercase): Section indices, sources, status metadata, and field names.

### Named Rules

**The Instrument Label Rule.** Monospace type is reserved for data-bearing labels and identifiers, not long-form prose.

## Layout

The desktop surface is a three-column cockpit: incident queue, investigation path, and technical detail rail. The center column is dominant. Its numbered spine provides the primary reading order and allows stages to grow independently with real content.

The background uses a restrained 32px construction grid because this is a measurement and diagnostic surface. Spacing follows a compact 0.45rem, 0.75rem, 1rem, and 1.45rem rhythm. Below 900px, page gutters tighten, the investigation spine contracts, and action metadata becomes a single column; Streamlit columns then stack naturally.

## Elevation & Depth

The system is flat by default. Depth comes from sheet color, rules, clipped corners, and overlap. A single low ambient shadow is permitted on the selected queue item (`0 8px 26px rgba(43,46,40,.06)`) to show focus without turning every region into a floating card.

### Named Rules

**The Flat Case File Rule.** Resting content is separated by paper tone and crease lines; shadow exists only to indicate current selection.

## Shapes

Square corners are the default. Investigation folds clip their upper-right corner by 18px and expose a small gold triangular crease. The product mark echoes the same folded geometry. Circular forms are restricted to 17–28px status and step markers, where the shape communicates a point on a path.

## Components

### Buttons

- **Shape:** Square instrument control with no corner radius and a minimum height of 2.45rem.
- **Primary:** Vermilion-backed when the action or language state is active.
- **Hover / Focus:** Border and label shift to vermilion; keyboard focus remains browser-visible.
- **Secondary:** Transparent paper with a one-pixel ink border.

### Cards / Containers

- **Corner Style:** Square by default; investigation stages use one clipped fold corner.
- **Background:** Translucent white sheet at rest and opaque white sheet for selected content.
- **Shadow Strategy:** Flat except for a selected queue row.
- **Border:** One-pixel crease rule.
- **Internal Padding:** Approximately 1rem, expanding slightly for investigation folds.

### Inputs / Fields

- **Style:** Compact square Streamlit controls with ink surfaces and clear text labels.
- **Focus:** Native focus semantics are retained; color is not the only state indicator.

### Navigation

The incident queue is both navigation and operational status. Each row presents source and time first, incident title second, then explicit status and service. Current selection uses an opaque sheet, a fine border, low elevation, and vermilion source label.

### Investigation Spine

The signature component connects numbered stages from signal to result with one vertical crease. The active stage replaces its paper node with vermilion and a restrained breathing ring. Each stage must remain understandable as a standalone audit record and in sequence.

## Do's and Don'ts

### Do:

- **Do** keep the evidence → hypothesis → reflection → action sequence visibly continuous.
- **Do** pair every status color with a word or symbol.
- **Do** reserve the strongest visual emphasis for current risk, active work, and approval.
- **Do** let real evidence determine vertical density instead of forcing equal-height panels.

### Don't:

- **Don't** replace the spine with a generic equal-card dashboard grid.
- **Don't** add neon glows, glass panels, or terminal-themed decoration.
- **Don't** use rounded containers as the default silhouette.
- **Don't** animate completed or idle stages; the moving signal belongs only to active work.

