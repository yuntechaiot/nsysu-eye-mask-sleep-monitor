# Independent EGM audit and fixes

Status: initial findings addressed; final regression and audit recorded in the delivery report.

The installed EGM plugin and native fresh-context agent tool were available. Read `skills/egm-review-loop/SKILL.md`, `docs/codex.md`, the readiness/codebase personas and readiness standard. Applied the personas to independent read-only audits. This is not a claim that the full interactive review-loop achieved two clean rounds. The user's explicit instruction was to continue authorized implementation and validation through a working local version.

## Readiness audit

Reviewer `egm_readiness` read the target design and supplied source files. It reported one Blocker and seven Major documentation gaps: schema/import contracts, webhook/API details, target-date and interval rules, durable retry accounting, production read-only SQL permissions, session protocol, exact file boundaries/checkpoints, and concrete acceptance cases. All were classified **PROPOSE FIX** and resolved by executable schema/service definitions, the appended contracts in `LINE_IMPLEMENTATION.md`, `LINE_SETUP.md`, and the acceptance evidence map. No critique was silently counted as a clean review.

## Code audit

The reviewer read `reminders.py`, `reminder_routes.py`, SQLite schema, `workspace.js`, auth bridge HTML/Python, `dashboard_flow.py`, preview and acceptance providers. It reported five Major implementation defects; no confirmed auth bypass or Blocker.

| ID | Finding | Resolution and verification |
|---|---|---|
| code-1 | One captured clock could send a late recipient outside the grace window | Re-read server clock per job, after blocking snapshot and immediately before HTTP; `test_slow_snapshot_cannot_send_after_grace` |
| code-2 | One batch transaction could erase earlier accepted results and crash attempt counts | Durable immutable intent, durable attempt/60s uncertain lease, then per-job dispatch/result; crash, concurrency and later-source-failure tests |
| code-3 | Cached bridge sessions and one-direction updates could leave stale refresh tokens | Fresh nonce handshake takes precedence, periodic source/origin-checked reconciliation, `session_updated` backend adoption and identity-cache invalidation; actual cross-origin Streamlit browser test |
| code-4 | Dashboard logout did not clear private website state or invalidate outstanding requests | Shared local sign-out clears generation, history, exports, names, QR title/image/link/cache; registered component-frame logout broadcast; browser logout assertion |
| code-5 | Acceptance mode could still call production Platform.login | Explicit DisabledPlatform injected into acceptance renderer; no production factory selected and outbound API calls blocked during browser test |

Every finding was **PROPOSE FIX** and implemented in the authorized local worktree. There are no accepted-but-hidden findings in these two reports. Additional privacy hardening removes query strings from local access logs. The formal backend remains disabled until explicitly provisioned; tests never substitute success in the production factory.

## Fresh final audit and regression fixes

A second fresh-context reviewer, egm_final, read the complete service/session flows, schemas and documentation. It found three further Major defects, all classified PROPOSE FIX and addressed:

| ID | Finding | Fix and evidence |
|---|---|---|
| final-1 | A pending export response could repopulate records and reopen the dialog after logout | openExport captures authGeneration/user and discards stale responses; downloadCSV requires a current session; actual local logout runs immediately. Two JavaScript race/control tests pass. |
| final-2 | A follow near midnight lost its welcome because diary same-day rules applied to all jobs | Same-target-day guard now applies only to diary jobs; welcomes retain the elapsed ten-minute grace across midnight. Controlled-clock regression passes. |
| final-3 | A later 5xx could erase an earlier unknown send result | SQLite explicit v2 migration adds durable uncertainty. Dispatch intent persists uncertainty; later failures cannot clear it, and expired unknown work remains uncertain_final. Timeout-then-5xx, permanent-failure-after-timeout and crash tests pass. |

The final reviewer confirmed no LIFF identity bypass, private snapshot exposure, unstable retry key or rolled-back durable attempt counts in the reviewed implementation. It did not run tests or write files. The main agent applied the three fixes and ran the final regression. The final audit itself reported these findings; it is not represented as a clean review or full-loop convergence.
