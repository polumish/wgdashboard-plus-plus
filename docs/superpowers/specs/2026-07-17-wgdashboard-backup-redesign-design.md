# WGDashboard Backup — Ideal Redesign (Design Spec)

**Status:** Draft for review (authored autonomously 2026-07-17; Sergiy asleep — decisions taken with documented alternatives, revisit any you disagree with).
**Scope:** The in-app WGDashboard **application-level** backup feature (configs + database + settings), on prod VM 4001 (`10.0.50.15`, MariaDB). Complementary to, not a replacement for, Proxmox/PBS VM-level backups.

---

## 1. Why this document exists

This session found the app-level backup silently broken for ~2 months: scheduled global snapshots were created nightly and immediately deleted by rotation (each ~492 MB > `max_storage_mb=500`), while the UI showed only 2 stale manual snapshots. We shipped two fixes (heavy-table exclusion → snapshots ~0.3 MB; "never delete the newest snapshot"; plus a client-portal backup hook). Those stopped the bleeding. This spec is about making the whole feature **trustworthy, disaster-proof, efficient, and easy to restore** — not just un-broken.

## 2. Current architecture (as-is)

- **Two levels.** *Global snapshots* (`backups/global/…`) = all `.conf` + full DB dump (`wgdashboard.sql`) + JSON exports + `wg-dashboard.ini`, with a `manifest.json` (sha256 checksums, trigger, size). *Per-config backups* (`backups/per-config/<cfg>/…`) = one config's `.conf` + its tables, event-triggered before peer/config changes.
- **Scheduler** (`BackupScheduler`, a daemon thread): checks daily/weekly/monthly schedules every 60 s; event-driven per-config backups with debounce + cooldown. State (`_last_scheduled`, `_last_pre_change`) is **in-memory only**.
- **Rotation** (`enforceRotation`): per-trigger keep limits (daily 7 / weekly 4 / monthly 3) + a total-size cap `max_storage_mb`. Manual snapshots never auto-deleted.
- **Heavy tables** (`*_transfer`, `*_history_endpoint`, ~400 MB of append-only traffic accounting) are dumped once into a shared `transfer_dump.sql`, and (as of this session) excluded from each snapshot's full dump.
- **Restore** (`restoreFromSnapshot`): integrity-checks checksums, creates a `restore_point` snapshot first, then restores selected components (configs / full DB / settings / per-table JSON). Per-config restore + full-DB restore exist.
- **API surface** exists and is fairly complete: `/api/backup/global/{list,details,create,delete,download,restore}`, `/api/backup/config/{list,create,delete,download,restore}`, `/api/backup/restore/status`.
- **SMTP** is configured (`m.half.net.ua`, `vpn@half.net.ua`) via `EmailSender.send()` — usable for alerting.

## 3. Problems remaining (the gap to "ideal")

1. **No observability / trust.** Failures are swallowed (`_schedule_loop` `except: pass`; `createGlobalSnapshot` returns `{status:False}` unlogged). Nothing surfaces *last successful backup*, *last failure*, or *"backups are healthy"*. This is why a 2-month outage went unnoticed. **Highest-impact gap.**
2. **No off-host copy (no DR).** Every backup lives on the same VM 4001 disk. Lose the VM/disk/filesystem and the app-level backups die with it. Violates 3-2-1. **Highest-risk gap.**
3. **Arbitrary storage cap.** `max_storage_mb=500` is not disk-aware (disk is 32 GB, ~24 GB free) and was the root of the deletion bug. The UI presents it as "500 MB available", which is misleading.
4. **Orphaned snapshot dirs.** 12 of 14 global dirs lack a valid `manifest.json` (leftovers from the failed-then-half-deleted snapshots). They consume space and are invisible to the UI listing (`_read_snapshot_list` only counts valid manifests).
5. **In-memory scheduler state.** `_last_scheduled` is rebuilt from disk on restart (`_recover_last_scheduled`) but keyed off snapshot `type`; a restart storm or a listing edge can double-fire or skip. No durable "last run" ledger.
6. **No restore verification.** Integrity checks exist, but nobody ever *test-restores*. A backup you've never restored is a hypothesis, not a backup.
7. **Heavy-table policy is implicit.** `*_transfer`/`*_history_endpoint` (~400 MB, growing) are traffic accounting. They inflate the shared dump and are rarely needed for recovery. No retention/trim policy; no explicit decision on whether they're restore-critical.
8. **UI is thin.** No health panel, the global page shows only manual snapshots when scheduled ones vanish, no "last backup / next backup / off-host status".

## 4. Goals / non-goals

**Goals:** (a) You can *see at a glance* that backups are working and *get alerted* when they aren't. (b) At least one backup copy lives **off VM 4001**, encrypted, with its own retention. (c) Storage limits are disk-aware and self-cleaning. (d) Restores are periodically *proven*, not assumed.

**Non-goals:** Replacing PBS/Proxmox VM-level DR (that stays as the full-machine layer — this is granular app-level). Backing up traffic history forever. Multi-region active-active. Backing up secrets in plaintext anywhere they aren't already.

## 5. Design — four pillars (phased sub-projects)

Each pillar is independently shippable and independently valuable. Recommended order P1 → P2 → P3 → P4 (trust before durability before efficiency before polish).

### P1 — Observability & trust  *(ship first; cheap, high value)*
- **Durable backup ledger.** A small `BackupEvents` table (or `backup_state.json`): per run `{scope, trigger, started_at, finished_at, status, size, error, off_host_status}`. Written by `BackupManager` on every create/rotate. Source of truth for "last success/failure", survives restarts, replaces the fragile in-memory recovery.
- **Stop swallowing errors.** `_schedule_loop` and `_run_scheduled` log at ERROR with the exception; `createGlobalSnapshot` failures are recorded to the ledger.
- **Health endpoint + UI panel.** `GET /api/backup/health` → `{last_global_success, last_per_config_success, consecutive_failures, next_scheduled, oldest/newest, total_size, disk_free, off_host: {...}, status: green|amber|red}`. Settings → Backup shows this at the top.
- **Alerting.** On N consecutive scheduled failures or "no successful global backup in > daily_interval × 1.5", email via the existing `EmailSender` (to `sergey.karlovskij@volia-software.com` / configurable). Amber/red also shown in UI. *Decision:* email only for v1 (SMTP already works); webhook/Matrix optional later.
- **Tests:** ledger written on success/failure; health computes green/amber/red from fixtures; alert fires exactly once per failure streak (debounced).

### P2 — Off-host DR  *(ship second; biggest risk reducer)*
- **Replicate each snapshot off VM 4001**, encrypted, with independent retention. The app creates the local snapshot, then pushes it to a remote repo.
- **Decision — tool: `restic`** to an off-host repository. Rationale: content-addressed dedup (tiny snapshots stay tiny; heavy dumps dedup well), built-in AES encryption, built-in retention (`forget --keep-daily/weekly/monthly`), `check` for integrity, and simple restore. Alternatives considered: *borg* (also great, but restic's multi-backend + single static binary is easier on a minimal VM), *rsync/rclone* (no dedup/encryption/retention — rejected), *push into PBS* (PBS is block/VM-oriented; app-file granularity is awkward).
- **Decision — target: Hetzner Storage Box (SFTP/rest-server) or the existing PBS host `pbs-vs10` as an SFTP restic repo.** Recommend a **dedicated Hetzner Storage Box** (cheap, same DC region, off the Proxmox cluster so a cluster-wide failure doesn't take it out). Alternative: restic REST server on `pbs-vs10` (reuses existing hardware/ZFS). *This is the one choice I'd most want your confirmation on — it has a small recurring cost and a credential.* Second copy to homelab (ph0 NFS over WG) is a cheap optional third leg for true 3-2-1.
- **Integration:** a `RemoteReplicator` module invoked after each successful snapshot (and on a schedule for catch-up). Restic repo password + target creds live in **Vault** (referenced by id, never in the ini/plaintext). Health panel shows last off-host success + repo `check` result.
- **Restore path:** `restic restore` to a scratch dir → feed into existing `restoreFromSnapshot`. No new restore logic, just a fetch step.
- **Tests:** replicate → list on remote → restore round-trip on a scratch repo (local restic repo in tests, no network); failure of the remote never breaks the local backup (best-effort, recorded).

### P3 — Storage & retention (disk-aware, self-cleaning)  *(ship third)*
- **Replace `max_storage_mb=500`** with a disk-aware cap: `min(configured_gb, free_disk * fraction)` — *decision default:* `max_storage_gb=5` **and** never exceed 60 % of free disk, whichever is smaller; the local tier only needs a short window because P2 holds the long history off-host. Keep a small local N (e.g., daily 7 / weekly 4) locally, long retention lives in restic.
- **Orphan cleanup.** On startup and after each rotation, remove `backups/global/*` and `per-config/*` dirs that lack a valid `manifest.json` **and** are older than a grace period (so an in-progress snapshot isn't nuked). Fixes the 12 leftovers. Logged + counted (no silent truncation).
- **Heavy-table policy.** *Decision:* keep `*_transfer`/`*_history_endpoint` **out of the per-snapshot dump** (already done) and **out of restic** by default; the shared `transfer_dump.sql` remains as an on-box convenience only. Add an optional `trim_transfer_days` (default off) to prune traffic history older than N days at the DB level — reduces DB bloat (the ~400 MB) that also slows other operations. Traffic history is analytics, not recovery-critical; document that restoring won't include it.
- **UI:** show "local: N snapshots, X MB of cap; off-host: M snapshots, retained 90d; disk free: Y GB" instead of a bare "500 MB".
- **Tests:** cap computed from fake free-disk; orphan cleanup respects grace period; trim removes only rows older than N days.

### P4 — Restore UX & periodic verification  *(ship last; polish + assurance)*
- **Scheduled restore-test** (monthly): restore the newest global snapshot's DB into a **scratch schema** (`wgdashboard_verify`), run a sanity query (row counts, a known config present), record pass/fail to the ledger + health. This turns "we have backups" into "restores are proven".
- **UI restore flow:** one-click restore with an explicit component picker (already supported by `restoreFromSnapshot`), a clear "a restore point was created first" confirmation, and progress via `/api/backup/restore/status`.
- **Download/verify:** surface integrity status per snapshot in the list.
- **Tests:** restore-test detects a deliberately-corrupted dump; UI status transitions.

## 6. Component boundaries (so it stays maintainable)

- `BackupManager` — create/list/delete/restore + checksums (exists; add ledger writes, orphan cleanup, disk-aware cap helper).
- `BackupScheduler` — timing only (exists; add ledger + logging; read "last run" from ledger not memory).
- `RemoteReplicator` — **new**; owns restic invocation + off-host health; knows nothing about scheduling.
- `BackupHealth` — **new**; pure read-model that computes the health object from the ledger + disk + replicator status. Feeds the API/UI.
- `BackupAlerter` — **new**; consumes health, sends debounced email. Isolated so alert policy changes don't touch the manager.

Each is independently testable with fakes; no cross-talk beyond the ledger + health read-model.

## 7. Recommended order & rough effort

1. **P1 Observability** — ~1 focused session. Immediate: you'd *know* the state. *Do this first even if nothing else.*
2. **P2 Off-host DR** — ~1–2 sessions + your decision on target/cost. Biggest risk reducer.
3. **P3 Storage/retention** — ~1 session. Also finally fixes the "500 MB" number properly.
4. **P4 Restore verification/UX** — ~1 session.

## 8. Decisions taken here (change any you dislike)

- **Alert channel:** email via existing SMTP (v1). Alt: Matrix/webhook later.
- **Off-host tool:** restic. Alt: borg.
- **Off-host target:** dedicated Hetzner Storage Box (recommended) vs restic-REST on `pbs-vs10` (reuse). **← needs your pick (cost + creds).**
- **Local cap:** `max_storage_gb=5` and ≤60 % free disk; long history off-host. Alt: keep MB-based but disk-aware.
- **Traffic history:** excluded from recovery backups; optional DB trim (default off). Alt: keep full.
- **Restore-test cadence:** monthly to a scratch schema. Alt: weekly / on-demand only.

## 9. Immediate low-risk quick wins (can precede the full plan, on your OK)

- Raise `max_storage_mb` on prod now (e.g., 5000) so nothing self-deletes even before P3 — one config line + restart. *(Not done — prod change awaiting your OK.)*
- One-off orphan cleanup of the 12 manifest-less global dirs on prod (frees space, de-clutters UI).

## 10. Open question for you (only one that blocks P2)

Off-host target: **Hetzner Storage Box (new, ~€3–4/mo, isolated)** or **restic-REST repo on the existing `pbs-vs10`** (no new cost, but shares fate with that box)? Everything else has a sensible default and can proceed.
