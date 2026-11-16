---
name: DeepHire
description: A bright recording booth for practising interviews out loud; grey hardware faceplates, colour only in meters and state lamps.
colors:
  plate: "#d6d8da"
  plate-lo: "#c8cbce"
  plate-edge: "#a9adb2"
  glow: "#f8f8f5"
  paper: "#fcfcfa"
  rule: "#c7d2df"
  ink: "#17181a"
  ink-2: "#44464a"
  ink-3: "#56585c"
  dial: "#efe6c8"
  key: "#2f5da8"
  key-hi: "#3b6bbd"
  key-lo: "#284f90"
  lamp: "#d99a12"
  lamp-off: "#9c9d98"
  ok: "#3f7d47"
  ok-text: "#2b6133"
  warn-text: "#6b4600"
  hot: "#b8301c"
typography:
  heading:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, system-ui, sans-serif"
    fontSize: "clamp(2rem, 4.2vw, 3rem)"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "-0.005em"
  legend:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.09em"
  key-label:
    fontFamily: "Barlow Semi Condensed, Arial Narrow, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 600
    lineHeight: 1.1
    letterSpacing: "0.03em"
  body:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  question:
    fontFamily: "Segoe UI Variable Text, Segoe UI, system-ui, sans-serif"
    fontSize: "clamp(1.15rem, 1.6vw, 1.5rem)"
    fontWeight: 500
    lineHeight: 1.4
  number:
    fontFamily: "ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "1.0625rem"
    fontWeight: 500
    letterSpacing: "-0.02em"
rounded:
  key: "6px"
  plate: "12px"
  well: "8px"
  window: "18px"
spacing:
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "32px"
components:
  key:
    backgroundColor: "#f3f4f5"
    textColor: "{colors.ink}"
    typography: "{typography.key-label}"
    rounded: "{rounded.key}"
    height: "44px"
    padding: "8.8px 16px"
  key-primary:
    backgroundColor: "{colors.key}"
    textColor: "#ffffff"
    rounded: "{rounded.key}"
    height: "50px"
  key-primary-hover:
    backgroundColor: "{colors.key-hi}"
  key-pressed:
    backgroundColor: "{colors.plate-lo}"
  plate:
    backgroundColor: "#dfe1e3"
    rounded: "{rounded.plate}"
  track-sheet:
    backgroundColor: "{colors.paper}"
    rounded: "{rounded.plate}"
---

# Design System: DeepHire

Scope: the studio pages only (setup `interview.html`, `room.html`, `report.html`, with `base.html` and `studio.css`). The landing page (`index.html`) and the blog templates are the old design and have not been moved to this system yet.

## Overview

**Creative North Star: "Recording Session"**

Every answer is a take in a bright booth. Surfaces are anodised grey faceplates with engraved legends, hardware keys with LED dots, one ivory VU dial that stands in for the interviewer, and pale-blue ruled track sheets for the report. The UI is light by necessity: the student sits in a dim room and the screen is the key light on their face. Colour is not decoration here; it is quarantined to meters and state lamps, so a coloured thing always means a reading or a state.

It must never feel watched or judged: no dark video-call grid, no KPI tiles, no recording-light theatrics (red never means "recording"), no live scores while answering, no fake human avatar.

**Key Characteristics:**
- Grey plate field, ivory dial, off-white booth window and paper sheets; no dark mode (`color-scheme: light`).
- Flat hardware: hairline edges, a 1px lower lip on keys, soft plate shadows only.
- Engraved uppercase legends label every panel; numbers are monospace and tabular.
- The report opens with the multitrack word plot of every take, not a score tile.

## Colors

Neutral grey hardware with one action blue; every other hue is a meter or state colour.

### Primary
- **Key Blue** (#2f5da8): the one action colour. Primary key, selected radio-key LED, links (`key-lo` #284f90), focus ring, "side" score bars. Hover #3b6bbd, pressed #284f90.

### Secondary (state and meter colours only)
- **Lamp Amber** (#d99a12): busy / in progress, warning, mid-high meter segments, filler words in the plot and transcript.
- **Go Green** (#3f7d47): OK, inside the guide range, meter low segments, completed step ticks. Text variant #2b6133.
- **Meter Red** (#b8301c): meter red zone on the dial and top bar segments, errors, pause gaps in the plot. Never "recording".
- **Warn Text** (#6b4600): out-of-range numbers, as text.

### Neutral
- **Anodised Plate** (#d6d8da): page background; recessed wells and pressed keys #c8cbce; edge #a9adb2; panel fill #dfe1e3.
- **Booth Glow** (#f8f8f5): the camera's light frame. **Track Paper** (#fcfcfa) with **Sheet Rule** (#c7d2df) for the report.
- **Dial Ivory** (#efe6c8): the VU dial face only (and the wordmark glyph).
- **Ink** (#17181a), secondary #44464a, tertiary #56585c. Off lamp #9c9d98.

### Named Rules
**The Quarantine Rule.** Chromatic colour appears only in meters, state lamps, the one blue action/selection, and report data marks. Panels, headings and backgrounds stay grey or ink.
**The Not-Recording Rule.** Red is the meter's red zone and errors. It never signals that recording is on.

## Typography

**Legend/Heading/Key Font:** Barlow Semi Condensed, self-hosted woff2, weights 500 and 600 only (fallback Arial Narrow).
**Body Font:** system UI sans (Segoe UI Variable Text, Segoe UI, system-ui).
**Number Font:** system monospace (ui-monospace, Cascadia Mono, Consolas), only for numbers and timecodes via `.num` / tabular figures.

**Character:** a condensed, engraved voice for the machine, a plain readable voice for the human's question and explanations.

### Hierarchy
- **Heading** (600, clamp(2rem, 4.2vw, 3rem) setup / 2.75rem report, 1.15): page title; step and take headings 1.125-1.5rem.
- **Status** (600, 1.375rem, 1.15): talkback status beside the dial.
- **Question** (500, clamp(1.15rem, 1.6vw, 1.5rem), 1.4): the spoken question, always shown as text.
- **Body** (400, 16px, 1.5): descriptions at .875-1.0625rem; secondary text in ink-2; prose max 52-75ch.
- **Legend** (600, .75rem, +.09em, uppercase, ink-2): panel and row labels, table headers.
- **Key label** (600, .9375rem, +.03em): keys; primary go keys 1.0625rem.
- **Number** (500, .6875-1.375rem mono, tabular, -.02em): readouts, totals, timecodes, lane ends.

### Named Rules
**The Mono-For-Numbers Rule.** Monospace is for figures and timecodes only, never for prose or labels.

## Layout

Setup is a single column, max-width 1040px, as a label-left (9rem) / control-right sheet of rows divided by hairlines. The room is a two-column grid: camera booth left (1.55fr), stand panel right (1fr, min 320px), console strip across the bottom. The report is max-width 1180px with the lane plot first, then totals, the question table, then one take card per answer. Page gutters `clamp(1rem, 3vw, 2rem)`; component gaps follow a 8/16/24/32px rhythm.

The console is `position: sticky` only while `data-phase="live"`, so it never covers the sound-check steps. Under 900px the room stacks booth, stand, console; under 640px the sheet rows stack, lanes and table drop secondary columns, and the console's primary key goes full width. Phones start with levels hidden (`data-levels="hidden"`, toggleable, remembered).

## Elevation & Depth

Flat hardware with tonal layering. Depth comes from a 1px hairline edge (#a9adb2), recessed wells (#c8cbce), and a light plate shadow.

- **Plate** (`0 6px 18px -12px rgba(20,22,26,.35)`): grey faceplates.
- **Paper** (`0 10px 30px -16px rgba(20,22,26,.3)`): track sheets.
- **Window** (`0 0 0 1px #a9adb2, 0 18px 40px -18px rgba(20,22,26,.35)`): the camera frame.
- **Key lip** (`0 1px 0 #a9adb2`; primary uses key-lo): the 1px lower lip that makes a key read as a key.

**The Press Rule.** A key at rest has its lip; pressed (and a checked radio key) loses the shadow and drops 1px on a plate-lo fill.

## Shapes

Small, machined radii: keys 6px, wells 8px, plates and sheets 12px, the camera window 18px with a 10px video inset. Status LEDs and step numbers are circles (8px dot, 1.6rem counter); meter bars are 7px-wide 2px-radius segments. Pills appear only for the on-window cue.

## Components

### Keys
- **Default:** #f3f4f5 face, 1px edge, 6px radius, min-height 44px, Barlow 600 label with optional 8px LED dot.
- **Primary:** Key Blue face, white label, lip in key-lo; 50-52px tall for "Done answering" and "Start". One blue key per view.
- **Quiet:** transparent, edge appears on hover. **Disabled:** #e3e5e7 / ink-3, no lip (primary disabled #9aa9c2).
- **Radio keys:** native input stays focusable but hidden; the label is the key; checked = pressed + blue LED + ink border.
- **Focus:** 2px Key Blue outline, 2px offset. Transitions .12s `cubic-bezier(.16,1,.3,1)`.

### Lamps
- LED dot + text. `ok`/`on` green, `busy`/`warn` amber, `error` red, default off grey. Used for status, grading state, "Runs on this computer".

### VU dial (signature)
- Ivory face SVG, ink scale and ticks, red zone arc, needle rotating -62deg to +62deg driven per animation frame, 148px (112px on phones). It is the interviewer: the talkback status and question sit beside it. Level bars below go green, amber, red.

### Track sheet (signature)
- Paper panel, one lane per take: label, track, end time and pace. Words are ink bars, fillers amber bars, 2s+ pauses red dashed gaps with a mono duration, a mono time axis beneath. Lanes link to their take card.

### Take card and sheet table
- Paper card: replay video (8px, #2b2c2e behind), transcript with amber-underlined fillers and red dashed pause chips, score rows with 4-segment ink bars (blue for the clarity side score), feedback in a #f1f4f8 block, collapsible model answer. Table: 2px ink header rule, hairline rows, right-aligned mono numbers, state lamp column. Loading uses a grey shimmer skeleton.

### Setup sheet and steps
- Label-left rows of radio keys; numbered steps (circle counters turn green with a check when done; disabled steps at .55 opacity).

## Do's and Don'ts

### Do:
- **Do** keep every surface light and grey; colour only for readings, states and the single blue action.
- **Do** use Barlow for legends, headings and keys; monospace only for numbers and timecodes.
- **Do** show every spoken question as text, and say what a number means beside it.
- **Do** honour `prefers-reduced-motion` (transitions to .01ms, animation off).

### Don't:
- **Don't** use red for recording or put live scores on screen while answering.
- **Don't** add a dark video-call grid, KPI tiles, or an avatar interviewer.
- **Don't** introduce a second action colour or tint panels with state colours.
- **Don't** use `index.html` or blog templates as reference; they are the old design.

## Not canonized

Known build debts that are not rules: raw hex values inline in components (#dfe1e3, #f3f4f5, #f1f4f8, #2b2c2e, #e3e5e7) outside the `:root` tokens, `--ink-3` (#56585c) being close to `--ink-2` in contrast terms, and the wordmark SVG hardcoding colours.
