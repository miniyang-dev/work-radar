---
version: 1
slug: "src-work-radar-web-templates-base-html"
primary_target: "src/work_radar/web/templates/base.html"
related_targets: []
---

# Surface: whole web app (Operate)

Scope and mode: all seven report pages plus the shared shell. Operate. Redesign: product truth, features, page structure and data density are fixed; the old monday-style look is the anti-reference.

Audience, job, task: one engineering manager, desktop, weekly review plus short check-ins. Find who is overloaded, what is overdue or stalled, what finished; produce the weekly overview text.

Constraints: templates only (no static mount), Traditional Chinese, many rows per page, row-level overdue and scheduled flags, existing class names and form fields kept (tests depend on them), no personal data in any committed file.

Memorable moment: the workload gantt drawn as a chart border and passage plan.

Unresolved: none.

## Direction contract

THESIS: A manager's review is a passage plan, not a dashboard: every row is a position to check against hazards and dates. The page refuses the saturated colour-block card board and the big-number metric tile, and lets one colour mean one thing.

OWN-WORLD: Admiralty chart. A mid chart-blue shell band carries the brand and navigation; the working ground is a pale sea tint with near-white sheets, hairline ink rules and 2px corners, no shadows. Ink is blue-black. Chart blue marks structure and links, a single magenta is reserved for overdue and hazard and appears nowhere else, amber is a light for work under way, sea green for done. Status is a small authored chart symbol (filled disc done, half disc in progress, diamond review, triangle waiting, ring to-do, square on hold) beside plain text. Numerals are tabular and small, sounding-like, aligned in fixed columns that never move between tables. Gantt axis is a chart-border graticule of alternating black and white scale segments with a bearing line for today.

STORY: The manager opens the page and sees the exceptions first, trusts the numbers because they align, expands a ticket's comments in place, and leaves with the overview text copied.

FIRST VIEWPORT: Chart-blue band full width: brand left, seven tabs, refresh icon right, active tab marked by a white underline. Below, a slim toolbar: member jump links left, the two panel actions right. Left column (about two thirds): the first member's sheet with name, open count, an inline allocation line of project shares, then the finished and in-progress tables at 13px with symbol-and-text status and tabular dates. Right column (320px): the gantt sheet with graticule axis and one row per ticket, sticky and scrolling inside itself. The primary action is the weekly overview button in the toolbar.

FORM: Admiralty chart, assigned candidate 6 of 7 on my ordered list; seed key 7c32a7eb. Fused disciplines: from the airport sign system, the loudest colour carries exactly one meaning; from the ticket wallet, closed work is cancelled in place rather than removed; from the split-flap board, column grid is fixed across tables.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
