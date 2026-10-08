# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person: the engineering manager who runs the team's weekly review. They sit at a desktop, usually once a week and in short check-ins between, with Jira open in another tab. The job is to see what each person actually has open, what is overdue or stalled, and what finished, then turn that into a weekly progress overview that is pasted into a document for the team. The page itself is rarely shown to anyone else.

## Product Purpose

work-radar reads Jira and answers three questions without clicking through boards one by one: what does each person have open, what has been sitting too long, and how long does work take here. Success is a weekly review done from one screen per question, with the overview text produced in minutes.

## Positioning

It is a manager's own scanner, not a team dashboard. It also holds one thing Jira cannot: a local tracking list of important work that has not been ticketed yet, which appears next to the ticketed work it competes with.

## Operating Context

- Runs locally as a FastAPI app; Jira is the data source, the tracking list, member roster and notes are local JSON files.
- Every report page does a live round trip to Jira, so pages can take a few seconds to load. A manual refresh re-fetches.
- Content is Traditional Chinese with English ticket keys, summaries and names mixed in.
- Real people and ticket content are on screen. Screenshots and examples must not leave the machine.

## Capabilities and Constraints

- Seven pages: 個人工作量 (per-person boards, gantt, strategy note, weekly overview generator), 追蹤事項, 團隊風險, 專案盤查, 個人週報, 單號查詢, 成員管理.
- Per ticket: expandable comments, parent link, status, priority, due date, last update. Overdue and not-yet-started-but-dated rows are flagged for the whole row.
- Data density is a requirement: many tickets must be visible on one page. Scan speed outranks decoration.
- Existing Chinese terminology stays unless a change is clearly clearer.
- Single-process app with no static file mount; styles, scripts and icons ship inside the templates.

## Product Principles

- Scan first: the page should answer "what needs me" before it asks me to read.
- Exceptions lead: overdue, unassigned and untracked work come before routine work.
- Nothing is hidden that a decision needs; detail expands in place.
- Honest about latency: every action that waits on Jira says so.
- Quiet by default, so a flagged row is the loudest thing on the page.
