---
name: work-radar
description: A manager's weekly review drawn as an Admiralty chart; one magenta means overdue, nothing else.
colors:
  sea: "#e8edf0"
  sheet: "#fbfcfc"
  sheet-sunk: "#eff3f5"
  sheet-hover: "#e8eff2"
  ink: "#1f3340"
  ink-2: "#3f5561"
  ink-3: "#586f7c"
  rule: "#ccd7dd"
  rule-strong: "#3b5565"
  field-border: "#8ea3ae"
  shell: "#2f5f7a"
  shell-ink: "#eaf2f5"
  shell-muted: "#a3bac6"
  chart-blue: "#1d5c88"
  chart-blue-hover: "#164a6d"
  hazard-magenta: "#ad1259"
  hazard-wash: "#f8e5ed"
  light-amber: "#c88a1b"
  light-amber-ink: "#84500a"
  light-amber-wash: "#fbf0d9"
  done-green: "#2f6e57"
  review-blue: "#3a73a3"
  waiting-violet: "#6b5a8e"
  idle-grey: "#7d8e98"
typography:
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'PingFang TC', 'Noto Sans TC', 'Microsoft JhengHei', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1.1875rem"
    fontWeight: 700
    lineHeight: 1.35
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'PingFang TC', 'Noto Sans TC', 'Microsoft JhengHei', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.55
  table:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'PingFang TC', 'Noto Sans TC', 'Microsoft JhengHei', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'PingFang TC', 'Noto Sans TC', 'Microsoft JhengHei', 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    lineHeight: 1.55
rounded:
  sharp: "2px"
  sheet: "3px"
  pill: "999px"
spacing:
  s-1: "0.25rem"
  s-2: "0.5rem"
  s-3: "0.75rem"
  s-4: "1rem"
  s-5: "1.5rem"
  s-6: "2rem"
components:
  button-primary:
    backgroundColor: "{colors.chart-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.sharp}"
    padding: "0.4rem 1rem"
  button-primary-hover:
    backgroundColor: "{colors.chart-blue-hover}"
  button-danger:
    backgroundColor: "transparent"
    textColor: "{colors.hazard-magenta}"
    rounded: "{rounded.sharp}"
    padding: "0.4rem 1rem"
  board:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sheet}"
    padding: "1rem 1.5rem 1.5rem"
  input-field:
    backgroundColor: "{colors.sheet}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sharp}"
    padding: "0.4rem 0.65rem"
  shell-band:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.shell-ink}"
  row-overdue:
    backgroundColor: "{colors.hazard-wash}"
  row-scheduled:
    backgroundColor: "{colors.light-amber-wash}"
  urgency-critical:
    backgroundColor: "{colors.hazard-magenta}"
    textColor: "#ffffff"
    rounded: "{rounded.sharp}"
    padding: "0 0.45rem"
---

# Design System: work-radar

## Overview

**Creative North Star: "The Admiralty Chart"**

A weekly review is a passage plan, not a dashboard: every row is a position to check against hazards and dates. A mid chart-blue band carries brand and navigation. The working ground is a pale sea tint, with near-white sheets laid on it, hairline ink rules, and 2-3px corners. There are no shadows and no big-number tiles. Ink is blue-black. Numerals are tabular and small.

The page lets one colour mean one thing. Magenta is reserved for work that is overdue or needs attention now, and it appears nowhere else. Everything else is quiet: chart blue for structure and anything clickable, amber for work under way, sea green for done.

Density is high and deliberate: 13px table text, many rows per sheet, fixed column grids. The interface is light only (`color-scheme: light`): a dark theme was built and removed because it was tiring to read for long review sessions.

**Key Characteristics:**
- Chart-blue shell band, pale sea ground, near-white sheets with a 2px dark top rule.
- One loud colour, one meaning (magenta = overdue / needs attention now).
- Status is a small CSS-drawn chart symbol plus plain text, never a coloured block.
- Fixed column grid: the same column has the same width in every table.
- Flat: depth comes from tone, hairlines and the dark top rule, never from shadow.
- Gantt drawn as chart furniture: graticule scale, bearing line, dashed open-ended work.

## Colors

A cold, blue-black palette with a single hot exception.

### Primary
- **Chart Blue** (`colors.chart-blue`, #1d5c88): links, issue keys, focus rings, the primary button fill, group-title default marker, the loading spinner arc. Structure and anything clickable. Dark mode lifts the text link to #78b6e0 and keeps a separate button fill (#2a6f9c).

### Secondary
- **Light Amber** (`colors.light-amber`, #c88a1b): work under way: half-disc status, due-soon gantt bars, the beyond-window arrowhead. Text on tint uses `light-amber-ink` (#84500a) for legibility; `light-amber-wash` (#fbf0d9) tints scheduled rows and medium urgency.
- **Done Green** (`colors.done-green`, #2f6e57): done only: filled disc, completed gantt bars.

### Tertiary
- **Hazard Magenta** (`colors.hazard-magenta`, #ad1259): overdue and needs-attention-now. Overdue dates (bold), overdue gantt bars, high priority text, stuck status, critical/high urgency tags, alert stat counts, error banners, destructive button text. `hazard-wash` (#f8e5ed) is its tint for overdue rows and the error banner.

### Status symbol colours
- **Review Blue** (#3a73a3) diamond, **Waiting Violet** (#6b5a8e) triangle, **Idle Grey** (#7d8e98) ring and dashed hold square. These are symbol fills only, never text or surfaces.

### Neutral
- **Sea** (#e8edf0) page ground; **Sheet** (#fbfcfc) panels and fields; **Sheet Sunk** (#eff3f5) inset areas (gantt track, comments, note log); **Sheet Hover** (#e8eff2) row/chip hover.
- **Ink** (#1f3340) text; **Ink 2** (#3f5561) secondary text; **Ink 3** (#586f7c) placeholders and tertiary text.
- **Rule** (#ccd7dd) hairlines; **Rule Strong** (#3b5565) sheet top rule, table header underline, graticule; **Field Border** (#8ea3ae) input outlines.
- **Shell** (#2f5f7a), **Shell Ink** (#f4f8fa), **Shell Muted** (#c6d9e3): the navigation band.

Avatar and group-accent colours are not CSS tokens. They live in Python (`src/work_radar/web/presenters.py`, `_AVATAR_PALETTE` and `_GROUP_ACCENT_PALETTE`): muted, dark hues (chart blue, sea green, plum, umber, slate, teal, violet, sienna, olive) chosen so white initials stay legible. Group accent arrives as the `--accent` custom property on `.group-title`.

### Named Rules
**The One Meaning Rule.** Magenta means overdue or needs attention now, and nothing else. Never use it for brand, decoration, emphasis, categories or "important" in general.

**The Symbol-Not-Block Rule.** Status colours appear only inside the small status symbol or a gantt bar; they never fill a cell, chip or card.

**The Quiet Majority Rule.** If every row in a group is flagged, the tint says nothing. Such tables get `all-flagged` and drop the row tint; the date stays magenta and bold.

## Typography

**Display Font:** none; there is no display face.
**Body Font:** system stack: -apple-system, BlinkMacSystemFont, "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", "Segoe UI", Roboto, Helvetica, Arial, sans-serif. There is no static file mount, so no web fonts are loaded.
**Mono:** `ui-monospace, SFMono-Regular, Menlo, Consolas` for the weekly-overview textarea only.

**Character:** Plain, small and numeric. Traditional Chinese reads through PingFang TC / Noto Sans TC. `font-variant-numeric: tabular-nums` is set on the body so digits align in columns.

### Hierarchy
- **Title** (700, 1.1875rem, 1.35): board titles, h2, person name in large person-cell.
- **Body** (400, 0.875rem, 1.55): default text, form fields, buttons (600), group titles (700), brand (1rem, 700).
- **Table** (400/600, 0.8125rem): table cells, status text, stat counts, tabs; item column is weight 600.
- **Label** (600, 0.75rem): table headers, key-value labels, comment meta, gantt labels, parent-issue lines.
- Scale tokens: `--t-xs` 0.75rem, `--t-sm` 0.8125rem, `--t-base` 0.875rem, `--t-md` 1rem, `--t-lg` 1.1875rem. Avatar initials use 0.6875rem at the small size.

### Named Rules
**The Atomic Value Rule.** Dates, keys, statuses and names are `white-space: nowrap` and never break mid-value. Only the item column wraps.

## Layout

Single column page, `max-width: 1560px`, 1.5rem side padding (1rem under 720px). Spacing is a 4-based scale from 0.25rem to 2rem (`s-1` to `s-6`); sheets are separated by 1rem, groups within a sheet by 1.5rem.

Tables use `table-layout: fixed` with a `<colgroup>` defined in the macros, so a given column (assignee 10rem, status 10.5rem, priority 5.5rem, due 7rem, completed 9.5rem, updated 9.5rem) has the same width in every table. The item column is the unsized flexible one. Tables have `min-width: 980px` inside an `overflow-x: auto` wrapper.

The workload page is two columns: main (flexible) and a 320px sticky gantt sheet that scrolls inside itself (`max-height: calc(100vh - 2rem)`). Below 900px it stacks and the gantt becomes static.

Below 720px the shell wraps (all tabs stay visible, no scrolling), the table header and colgroup are hidden, and each row becomes a flex-wrap card. Date cells carry `data-label` attributes that render as a small prefix via `::before`. The item cell takes the full row. Stat strips become a 3-column grid.

Stat counts are a ruled strip of small figures (top and bottom hairline, vertical dividers), not tiles.

## Elevation & Depth

Flat. There are no box-shadows anywhere. Depth is tonal: chart-blue band over sea ground over near-white sheets over sunk insets. A sheet is identified by a 1px rule border with a 2px `rule-strong` top edge. Hover is a tonal step (`sheet-hover`). Focus is a 2px chart-blue outline with 2px offset. The only overlay is the loading veil, a translucent sea tint (rgba(232,237,240,0.78)) with a spinner.

### Named Rules
**The No-Shadow Rule.** Separate things with a hairline or a tonal step, not a shadow.

## Shapes

Hard-edged and chart-like. Radius is 2px on controls, tags, comments and error banners; 3px on the bottom corners of sheets (top is square under the 2px top rule); 999px only for member jump chips; 50% for avatars and the spinner. Status symbols are drawn in CSS: filled disc (done), half disc via a 50% gradient inside a ring (in progress), rotated square diamond (review), clip-path triangle (waiting), ring (to do), dashed-border square (on hold). The stuck status is a magenta square. Group titles carry a 9px square marker in the group accent colour.

Icons are inline SVG from the `icon` macro in `_macros.html`: 20-unit viewBox, one 1.6 stroke weight, round caps and joins, `currentColor`, sized 1em.

## Components

### Buttons
- **Shape:** 2px radius, 0.4rem 1rem padding, 0.875rem weight 600.
- **Primary:** chart-blue fill, white text; hover darkens to #164a6d. Disabled is 55% opacity.
- **Danger:** transparent with a field-border outline and magenta text; hover washes to hazard-wash with a magenta border.
- **Small / collapse-toggle:** reduced padding (0.2rem 0.6rem), toggle is outlined with ink text. The refresh control in the shell is a bare icon button behind a hairline divider.

### Inputs / Fields
- Sheet fill, 1px field-border outline, 2px radius, 0.4rem 0.65rem padding. Focus: chart-blue border plus 2px chart-blue outline.

### Navigation
- Shell band with brand (circle-and-bearing glyph, 700) on the left, seven text tabs on the right, 0.8125rem weight 600 in shell-muted. Active tab is shell-ink with a 2px bottom border. The refresh icon appears only on Jira-backed pages.

### Tables and rows
- Header: 0.75rem, ink-2, 1.5px rule-strong underline. Cells: 0.5rem 0.75rem padding, 1px rule bottom. Row hover uses sheet-hover.
- `row-overdue` tints the row hazard-wash; `row-scheduled` tints it amber wash; `all-flagged` on the table removes both tints. Overdue date text is magenta bold; scheduled date text is amber-ink bold.

### Status
- Symbol (0.72rem) plus plain 600 text. See Shapes for the symbol vocabulary.

### Urgency tag
- Small 2px-radius tag: critical is solid magenta with white text; high is magenta on magenta wash; medium is amber-ink on amber wash; low is ink-2 on sheet-sunk.

### Avatar
- Round, white bold initials on a palette colour from Python; 24px default, 20px small, 36px large.

### Gantt (signature)
- A chart border. The axis is a 6px bar split into three equal segments (one per week) alternating rule-strong and sheet. The track is a sunk strip with hairlines at the thirds. Today is a 1px ink bearing line extending 2px above and below. Bars are 10px tall: done green, due-soon amber, overdue magenta, open-ended work is a dashed outline only (no fill), work beyond the window is amber with an arrowhead. Row labels are a fixed 76px gutter that mirrors the axis gutter.

### Comments and notes
- Expanded in place in a following row; comments are sunk-fill 2px blocks, the note log a scrollable (9rem) sunk box.

### Member list
- A ruled list, not boxes: top hairline, rows separated by hairlines, avatar and name left, inline form and links right.

## Do's and Don'ts

### Do:
- **Do** use magenta (`hazard-magenta`) only for overdue or needs-attention-now.
- **Do** use chart blue for links, keys and structure; amber for work under way; sea green for done.
- **Do** show status as the CSS-drawn symbol plus plain text.
- **Do** give new tables a `<colgroup>` and `table-layout: fixed`, reusing existing column widths.
- **Do** add `all-flagged` when every row in a group would be overdue or scheduled.
- **Do** keep `row-overdue` / `row-scheduled` classes on rows; tests assert them.
- **Do** add `data-label` to date cells so they read in the stacked mobile card.
- **Do** route new colours through custom properties in `base.html`.
- **Do** keep icons on the `icon` macro: 20-unit grid, 1.6 stroke.

### Don't:
- **Don't** use magenta for brand, decoration or generic emphasis.
- **Don't** fill a cell, chip or card with a status colour.
- **Don't** add shadows, big-number metric tiles or saturated colour-block cards (the old monday-style look is the anti-reference).
- **Don't** add web fonts or image/icon files; there is no static mount, so type is the system stack and icons are inline SVG.
- **Don't** let dates, keys, statuses or names wrap mid-value.
- **Don't** draw open-ended work as a filled bar.
- **Don't** put person names, emails, company domains or Jira site URLs into any committed file.

### Not canonized (drift in the build)
- Avatar initials use a literal `#fff`, and primary button text uses `--on-link-fill`; neither is a theme-aware role. Left as is because both sit on dark fills.
