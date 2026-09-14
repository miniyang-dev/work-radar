# work-radar

Scans Jira for stalled work, per-person workload, and delivery metrics —
built to answer "what does this person actually have open," "what's been
sitting too long," and "how long does work actually take here," without
clicking through Jira's UI board by board.

A CLI and a local web UI both run on the same logic (see Architecture).

## Architecture

Hexagonal (ports & adapters), so the business logic never imports Jira:

```
domain/          Entities (Issue, Person, Status, StatusTransition, TrackingItem)
                 + Protocols (IssueRepository, IssueHistoryRepository,
                 StatusCatalogRepository, PersonRepository, MemberRepository,
                 TrackingItemRepository). No dependencies, no I/O.
application/     Use cases: EpicReportService, WorkloadReportService,
                 StaleIssueFinder, TeamRiskScanner/TeamRiskReportService,
                 CycleTimeCalculator/CycleTimeReportService, WeeklyReportService,
                 TrackingListService. Depend only on domain Protocols.
infrastructure/  Jira REST API adapter: HTTP client, cloud-id resolution,
                 JSON->domain mappers, and the repository implementations.
cli/             Composition root #1: wires infrastructure into application
                 services, plus text presenters for terminal output.
web/             Composition root #2 (FastAPI): same application services,
                 rendered as HTML via Jinja2 templates instead of text.
```

Swapping Jira for another tracker means writing a new adapter under
`infrastructure/` that satisfies the Protocols in `domain/ports.py` —
nothing in `application/` or `domain/` changes. Same story for adding a
third "driver" alongside cli/ and web/ (a Slack bot, say).

## Getting started

Five steps from a fresh clone to a working page. Python 3.9+.

**1. Install**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip        # don't skip: see below
pip install -e ".[dev,web]"
```

The pip upgrade is not boilerplate. This project has no `setup.py`, so an
editable install needs PEP 660 support, and the pip that ships inside a
fresh Python 3.9 venv (21.2.4) predates it — without the upgrade the
install fails with *"a pyproject.toml file was found, but editable mode
currently requires a setuptools-based build"*.

**2. Check it works — before touching any credentials**

```bash
python3 -m pytest
```

All tests must pass. They need no Jira account, no `.env` and no network:
`tests/conftest.py` pins placeholder Jira settings for the whole suite. If
this is green, the install is fine and anything that breaks later is
configuration, not code.

**3. Get a Jira API token**

Atlassian account settings -> Security -> API tokens -> **"Create API token
with scopes"**. Grant only read scopes — this tool never writes to Jira:
`read:jira-work`, `read:jira-user`, `read:issue.changelog:jira`,
`read:project:jira`, `read:comment:jira`.

**4. Point it at your Jira**

```bash
cp .env.example .env
```

Then fill in all three values:

```
JIRA_EMAIL=you@example.com          # the account the token belongs to
JIRA_API_TOKEN=your-api-token       # from step 3
JIRA_DOMAIN=your-domain.atlassian.net   # host only, no https://
```

**Optional settings**

Both take comma-separated project keys and both are empty by default,
because they name *your* projects:

```
AUDIT_PROJECT_KEYS=ABC,DEF      # which projects 專案盤查 (/audit) scans
OVERVIEW_PROJECT_RANK=ABC,DEF   # project priority order in the weekly overview
```

The local JSON stores can be relocated with `MEMBER_STORE_PATH`,
`TRACKING_STORE_PATH` and `OVERVIEW_NOTE_PATH`; by default they sit under
`data/`.

**5. Start the web UI**

```bash
uvicorn work_radar.web.app:app --reload --port 8000
```

Open <http://127.0.0.1:8000>, go to **成員管理 (`/members`)**, search a
colleague by name and add them. **Do this first** — every other page is
driven by that roster, so until it has someone in it 個人工作量 and 團隊風險
are empty by design, not broken.

That roster (and the 追蹤事項 list, and the saved overview note) is stored
as JSON under `data/`, which is gitignored — you start with an empty one,
and nothing is ever written back to Jira.

### If a page comes up empty

The first two are much more likely than a bug:

- **個人工作量 / 甘特圖 empty, but the roster has people** — the "進行中"
  split matches status *names* containing `running` or `reviewing`
  (`_ACTIVE_STATUS_KEYWORDS`, `application/workload_report.py`). If your
  workflow says "In Progress", edit that tuple. It fails silently because
  a name that matches nothing is indistinguishable from having no active
  work.
- **Start dates missing in the Gantt chart** — `START_DATE_FIELD` in
  `infrastructure/jira/mappers.py` is `customfield_10015`. That is Jira
  Cloud's usual "Start date" id, but it is per-site; check yours at
  `/rest/api/3/field`.
- **專案盤查 says no projects are configured** — that page audits whatever
  `AUDIT_PROJECT_KEYS` lists (see Optional settings below). There is no
  default because the keys name your projects, not anyone else's.
- **The weekly overview orders projects oddly** — set
  `OVERVIEW_PROJECT_RANK` to your own priority order; anything unlisted
  sorts after it, alphabetically.
- **Urgency scores look flat** — the scoring in
  `application/project_audit.py` knows a `P0..P3` scheme and Jira's stock
  Highest..Lowest. Another scheme falls through to a neutral weight.

## Usage — CLI

```bash
work-radar epic ABC-123                      # Epic status + child issue breakdown
work-radar workload "Alice"                  # a person's open issues + cross-project allocation
work-radar stale "Alice" --days 14           # that person's open issues stuck 14+ days
work-radar risk ABC,DEF --stale-days 14      # team-wide: overdue / unassigned / stale issues
work-radar cycle-time ABC --window-days 90   # lead time & cycle time for recently-done issues
work-radar weekly "Alice" --window-days 7    # what a person completed / touched / is stuck on
```

## Usage — Web UI

You do not need any of this to run work-radar — step 5 of Getting started
is enough. This is just how it is deployed on the original author's
machine, kept here as a worked example.

The server runs permanently as a macOS user LaunchAgent
(`~/Library/LaunchAgents/com.example.work-radar-web.plist`), started at
login and restarted automatically if it dies — so http://127.0.0.1:8000
is simply always up, and `.claude/launch.json` attaches to it rather
than starting a second copy. It runs **without** `--reload`, so restart
it by hand after changing code:

```bash
launchctl kickstart -k gui/$(id -u)/com.example.work-radar-web
```

Logs land in `~/Library/Logs/work-radar-web.log` (and `.err.log`). To run
a throwaway instance on another port instead:

```bash
uvicorn work_radar.web.app:app --reload --port 8001
```

The web UI has diverged from the CLI's six flat reports into something more opinionated about *not* making you
type things. Tab order is the display order in `base.html`'s `<nav class="tabs">`, and the landing page's card
list in `index.html` is a second hand-kept copy of it — adding a page means editing both:

- **個人工作量 (workload)** — no input at all: every roster member gets a
  board, and each board reads top to bottom as four sections.
  - **重要但尚未開票** — follow-ups from 追蹤事項 that were routed to this
    member (see that page below). It leads because it is the only thing
    on the page Jira knows nothing about, and among thirty tickets it
    would otherwise be lost. Hidden entirely when empty — an exception
    block, not a standing section.
  - **本週已完成** — what this member finished since Monday, most recent
    first, with a 完成時間 column. Completion is read from
    `statusCategoryChangedDate`, not `updated` (which also matches a
    ticket closed months ago that someone merely commented on this week)
    and not `resolutiondate` (empty on any workflow that reaches Done
    without setting a resolution).
  - **進行中** — issues whose status name contains "Running"/"Reviewing",
    soonest due date first.
  - **庫存區** — everything else, collapsed. It now shows the due date,
    and a row that has one is tinted: red once the date has passed, amber
    while it is still ahead. Nothing here has been started, so a date on
    one of these rows is a commitment already running down, and a red one
    is late without ever having been picked up.

  A Gantt chart alongside groups each member's rows under their name on a
  **three-week** axis — last week plus the next two, with today marked by
  a vertical line. It reaches into the past on purpose: an overdue or
  just-finished span is only legible if the axis has room to draw it, and
  seven days back always covers the current week's Monday (six at the
  most, on a Sunday).

  Each bar spans that issue's own **start date to its due date**, so a
  three-day task reads as three days sitting where it falls rather than as
  a bar stretching back to today. Jira's due date is inclusive — work runs
  through the end of that day — so 09/07~09/09 is three days wide and a
  same-day task is one day wide rather than zero. Start date comes from
  Jira's own field, falling back to the creation date when it is unset.
  Colours: **green** for work finished this week, **red** for overdue,
  amber for still running, dashed for no due date at all, and an arrow
  where the due date runs past the right edge. The green bars are the one
  case whose right end is what *happened* rather than what was planned —
  they end at the actual completion time, so a ticket delivered early
  reads shorter than its due date promised, and a late one reads longer.
  The dashed case tends to dominate wherever due dates are optional, which
  the chart shows honestly rather than papering over.
- **單號查詢 (`/epic`)** — look up any single issue key and see its
  status plus its children's breakdown; not actually restricted to
  Epics (`EpicReportService` just does `get_issue` + `find_children`),
  hence the more accurate name.
- **個人週報** — still takes a person, now via a roster dropdown
  (auto-submits) *or* a free-text Jira name search, both wired into the
  same form so switching one doesn't clobber the other. 待處理偵測 (stale)
  was dropped from the web UI — CLI-only now (`work-radar stale`).
- **團隊風險 (`/risk`)** — no project keys to type either, and scoped
  to *people*, not projects: only the roster members' own open issues
  are scanned for overdue/stale. "無人認領" (unassigned) always comes up
  empty here on purpose — an unassigned issue can't belong to a tracked
  member, so that category only makes sense in a project-wide scan,
  which this isn't.
- **專案盤查 (`/audit`)** — the project-scoped counterpart to `/risk`:
  everything the projects in `AUDIT_PROJECT_KEYS` *took in* over a window
  (近 3 個月 / 半年 / 一年),
  windowed on `created` rather than `updated`, because "what came in
  this quarter" is a different question from "what was touched
  recently". Closed issues are included — the audit reports the whole
  intake, with the finished ones collapsed into a `<details>` — and the
  open ones are ranked by a composite urgency score rather than by
  Jira's priority field. That score exists because priority alone
  doesn't discriminate: on a backlog where nearly every ticket carries
  the same middle priority, sorting by it produces a flat list.
  Overdue days outweigh priority,
  which outweighs days-since-update, which outweighs being unassigned;
  every row shows the reasons in words next to its 危急/高/中/低 label,
  so the number is auditable rather than magic. Two priority schemes
  are mapped (P0..P3 and stock Highest..Lowest), since Jira sites differ
  on which they use. Above the list sits a stats row: intake, open,
  done rate, overdue, P0/P1, unassigned, no-due-date, past the stall
  threshold (which the 待處理門檻 control sets), and median staleness.
  Those gap counts were briefly three tables of their own — a mistake
  worth recording, since the reasoning looked sound: the tickets that
  rot are the undated, unassigned ones. But on a backlog where due
  dates are rarely set, nearly every open issue falls into at least one
  gap bucket, so the section printed the ranked list a second time and
  added nothing. The rows already say it better where they are, in an
  urgency column reading "140 天未更新、無人認領".
  Counts belong on the page; the same rows twice don't. The list can
  also be grouped by assignee or issue type, with groups ordered by
  their most urgent member rather than alphabetically.
- **追蹤事項 (`/tracking`)** — the one page with no tracker behind it
  at all: a hand-kept list of things to follow up on that Jira has no
  ticket for — what you promised in a meeting, the decision you're
  waiting on someone to make. Each item carries a description, status
  (待處理/進行中/等待回覆/已完成/已擱置), an owner (suggested from the
  roster but free-typed, so 客戶 or 法務 work too), a priority, a
  follow-up date, a link, and a 備註 log — notes are appended rather
  than overwritten, each stamped with the time it was written, so the
  rounds of chasing stay readable. A URL inside a note renders as a
  short label (`docs.google.com/spreadsheets/d/…`) with the full address
  kept in the link: a pasted share URL has no spaces in it, so printing
  it in full cannot wrap and dragged the whole table into a horizontal
  scrollbar.

  One more field, **顯示在個人工作量**, picks a roster member (or nobody,
  the default). Set it and the item also appears at the top of that
  person's workload board under 重要但尚未開票. It is deliberately separate
  from the owner field above: that one is free text and often names someone
  outside the team, while this has to match a roster member exactly for
  the item to route anywhere. Only items still being chased show up
  there — mark one 已完成 or 已擱置 and it leaves the workload page on its
  own, because a closed follow-up is no longer work waiting for a ticket.

  Sorted by that date ascending,
  which puts anything overdue at the top for free and sinks undated
  items to the bottom; closed items collapse into a `<details>` at the
  end. `created_at` survives every edit while `updated_at` advances, so
  "how long has this sat untouched" stays answerable. Stored at
  `data/tracking_items.json` (overridable via `TRACKING_STORE_PATH`).
  Because nothing here reads Jira — neither the owner suggestions nor the
  顯示在個人工作量 picker, both of which go straight to the local roster
  file — **this is the only page that renders fully with no Jira
  credentials configured**.
- **成員管理 (`/members`)** — curate that roster: search Jira by name
  once, add/rename/remove. Stored locally as JSON at
  `data/members.json` under the repo root (overridable via
  `MEMBER_STORE_PATH`), never synced back to Jira. Defaults are anchored
  to the project root rather than the process's working directory, so
  starting the server from elsewhere still finds the same roster.
- Cycle time is CLI-only now (`work-radar cycle-time`) — dropped from
  the web UI as a page nobody was clicking through a browser for.

Every issue key everywhere is a link straight to that issue in Jira
(opens in a new tab), and a "💬 留言" toggle under each row lazily
fetches that issue's comments on demand (one request per issue, only
when expanded — not fetched up front for every row). `.claude/launch.json`
already points at this for Claude Code's preview panel.

## How cycle time / weekly reports actually work

Jira's changelog only records a status **name** at each transition (e.g.
"Running / 執行中"), never its category. To classify a transition as
"in progress" or "done" without guessing from the name string, work-radar
fetches each project's full status scheme from
`/rest/api/3/project/{key}/statuses` (`StatusCatalogRepository`) and uses
that as the name->category lookup — this is also why `resolutiondate`
isn't used for lead time: a visibly-Done issue can carry
`resolutiondate: null` (it is only set when the workflow sets a
resolution), so completion time is derived from the changelog instead.

`weekly` pulls every touched issue's history in one batched search
(`expand=changelog`, whose embedded copy carries an issue's most recent
history entries — plenty for a days-long window), falling back to
per-issue requests if a deployment ignores the expand.

`cycle-time` still makes one changelog request per issue on top of the
initial search: it needs the *full* paginated history to find the last
transition into Done, so the embedded copy isn't good enough. Fine for
tens-to-low-hundreds of issues, not sized for a multi-year backfill.

Roster-wide pages (workload, risk) fetch every member's open issues in a
single `assignee in (...)` query rather than one query per member.

## Tests

```bash
python3 -m pytest
```

Every use case is tested against in-memory fakes of the domain Protocols —
no network access and no Jira credentials needed. `tests/conftest.py` pins
placeholder Jira settings for the whole suite, so the result is the same on
every machine: with a `.env`, without one, or with someone else's. A test
that needs the host in an assertion takes the `jira_domain` fixture rather
than writing one in. Jira JSON parsing (including the two different
changelog response shapes) is tested separately in
`tests/infrastructure/test_mappers.py`, the repository adapters against a
recording fake HTTP client in `tests/infrastructure/test_repositories.py`
(request-path encoding, JQL quoting, the parent-link fallback, batching),
and the FastAPI handlers themselves through `TestClient` in
`tests/web/test_routes.py` — all without network access.

The presenters get their own files where the arithmetic is easy to get
subtly wrong: `tests/web/test_gantt_view.py` pins where every kind of bar
starts and how wide it is (including the inclusive-due-date rule and a
span whose dates are the wrong way round), and
`tests/web/test_tracking_view.py` covers note-link shortening — a link in
the middle of a Chinese sentence, trailing punctuation, and a short URL
that should be left alone.

## License

MIT — see [LICENSE](LICENSE).
