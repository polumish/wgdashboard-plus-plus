# WGDashboard Backup — Ideal Redesign (Design Spec)

**Status:** Draft for review (authored autonomously 2026-07-17; Sergiy asleep — decisions taken with documented alternatives, revisit any you disagree with).
**Scope:** The in-app WGDashboard **application-level** backup feature (configs + database + settings), on prod VM 4001 (`10.0.50.15`, MariaDB). Complementary to, not a replacement for, Proxmox/PBS VM-level backups.

---

## 0. Implementation status

- **P2 (PBS off-host DR): DONE & verified 2026-07-18.** proxmox-backup-client 4.2.2 on VM 4001; scoped PBS user+token `wgdash@pbs!vm4001` (role DatastorePowerUser on `pbs-data`); client-side encryption key + token in Vaultwarden folder `WGDashboard`; `/usr/local/bin/pbs-backup.sh` (mysqldump minus heavy tables + `/etc/wireguard` + ini, encrypted) driven by a nightly systemd timer (23:31 UTC); **failure alerting** via systemd `OnFailure` → email (app SMTP) — tested, delivered. First backup + **restore round-trip verified** (restored `Vano_Golubka.conf` matches live; 58 tables; heavy tables absent). Snapshot group `host/wg-dashboard`.
  - **Deferred (safe follow-up):** automated retention/prune. Client-side group prune needs `Datastore.Prune` (privsep) and a datastore-wide prune-job would touch the cluster's VM backups — so retention should be done via a dedicated `wg-dashboard` **namespace** + namespace-scoped prune/verify jobs (namespace creation needs root on PBS). Non-urgent: each backup is ~160 KB.
- **P1/P3/P4:** not started (design below).

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

### P2 — Off-host DR via existing PBS  *(ship second; biggest risk reducer)*
**Decision — target: the existing Proxmox Backup Server `pbs-vs10` (94.130.207.10), datastore `pbs-data`, file-level backups via `proxmox-backup-client`.** Sergiy's call (2026-07-18) and the right one: no new cost, same DC, already ZFS raidz2 + AES, and PBS natively provides dedup, incremental, retention (prune), scheduled **verify**, and **email notifications on failure** — which also covers most of P1's observability *for free, at the PBS layer, independent of WGDashboard's own (fragile) scheduler*. Feasibility confirmed 2026-07-18: VM 4001 reaches `pbs:8007`; PBS is 4.2.3 with one datastore `pbs-data`; only gap is the client package isn't installed yet. Alternatives (rejected/secondary): dedicated Hetzner Storage Box + restic (new cost + creds, no reuse), rsync/rclone (no dedup/encryption/retention).

- **What to back up:** the *live source state*, not the app's own backup dirs — i.e. `/etc/wireguard/*.conf` + a fresh **DB dump** (`mysqldump`, heavy `*_transfer`/`*_history_endpoint` excluded) written to a staging dir + `wg-dashboard.ini`. PBS stores this as a `host/wg-dashboard` backup (`.pxar` + `.blob`), deduped and encrypted. This makes PBS a first-class, granular, off-VM backup of the actual system — restorable file-by-file without touching the VM image.
- **Driver:** a small, self-contained systemd **timer** on VM 4001 running a `pbs-backup.sh` (pre-dump DB → `proxmox-backup-client backup`), **independent of the WGDashboard app scheduler** (the fragile part we don't want in the critical path). Optionally the app also triggers an ad-hoc PBS run after big changes, but the timer is the guarantee.
- **Auth & encryption:** a PBS **API token** scoped by ACL to a `wg-dashboard` namespace/backup-id (least privilege, not root); client-side **encryption key**; both stored in **Vault** (referenced by id, never in the ini/plaintext). PBS repo string `token@pbs!tokenid@94.130.207.10:pbs-data`, `--ns wg-dashboard`.
- **Retention & verify:** PBS prune job (e.g. keep-daily 14 / keep-weekly 8 / keep-monthly 6) + a weekly verify job on the namespace. Configured on PBS, visible in its task log/UI.
- **Observability for free:** PBS email notifications on backup/verify failure (configure PBS notification target to `sergey.karlovskij@volia-software.com`). This is the durable "did last night's backup succeed?" signal — no app code needed. The in-app health panel (P1) can *also* read the last PBS run via the client for a single pane, but PBS alone already prevents another silent 2-month outage.
- **Restore path:** `proxmox-backup-client restore host/wg-dashboard/<snap> <file> <dest>` → drop `.conf` back / import the SQL dump. Granular (one config) or full.
- **Prereq install (needs your OK — prod change):** add the Proxmox no-subscription repo (or just the `proxmox-backup-client` package) on VM 4001.
- **Tests:** `pbs-backup.sh` dry-run builds the staging set (configs + non-heavy dump + ini) correctly; a restore round-trip against a scratch PBS namespace; the timer failing (PBS unreachable) alerts via PBS + is recorded, and never impacts the running VPN.

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

Revised after the PBS decision — PBS gives off-host DR **and** failure-notification with almost no app code, so it now leads:

1. **P2 PBS off-host backup** — ~1 session (+ your OK to install the client & make PBS token/namespace). Delivers DR *and* the "did it run?" alert (PBS email) in one move. **Do this first.**
2. **P1 In-app observability** — ~1 session. Now smaller: a durable ledger + health panel + stop-swallowing-errors; PBS already covers the critical alert, so this is the single-pane nicety and covers the app's *own* internal snapshots.
3. **P3 Storage/retention** — ~1 session. Fixes the "500 MB" number properly (local tier can be small since PBS holds the long history).
4. **P4 Restore verification/UX** — ~1 session (PBS verify covers off-host integrity; this adds app-side restore-tests + UI).

## 8. Decisions taken here (change any you dislike)

- **Off-host target: DECIDED — existing PBS `pbs-vs10`, datastore `pbs-data`, file-level via `proxmox-backup-client`** (Sergiy 2026-07-18). Alts rejected: Hetzner Storage Box + restic, rsync/rclone.
- **PBS driver:** standalone systemd timer (independent of the app scheduler). Alt: app-triggered only (rejected — keeps the fragile scheduler in the DR path).
- **Alert channel:** **PBS-native email** for the off-host layer (primary) + existing WGDashboard SMTP for the in-app layer (P1). Alt: Matrix/webhook later.
- **PBS auth:** scoped API token + client-side encryption key, both in Vault. Alt: root token (rejected — least privilege).
- **PBS retention:** keep-daily 14 / weekly 8 / monthly 6 + weekly verify (starting point, tune later).
- **Local cap:** `max_storage_gb=5` and ≤60 % free disk; long history lives on PBS. Alt: keep MB-based but disk-aware.
- **Traffic history:** excluded from recovery backups (PBS + app); optional DB trim (default off). Alt: keep full.
- **Restore-test cadence:** monthly to a scratch schema (app) + PBS weekly verify (off-host). Alt: weekly / on-demand only.

## 9. Immediate low-risk quick wins (can precede the full plan, on your OK)

- Raise `max_storage_mb` on prod now (e.g., 5000) so nothing self-deletes even before P3 — one config line + restart. *(Not done — prod change awaiting your OK.)*
- One-off orphan cleanup of the 12 manifest-less global dirs on prod (frees space, de-clutters UI).

## 10. What's left needing your OK (all prod-infra changes)

Off-host target is **decided (PBS)**; no design questions block progress. To *implement* P2 I need your go on these prod changes (I'll snapshot/confirm each):
1. Install `proxmox-backup-client` on VM 4001 (Proxmox no-subscription repo or the single package).
2. On PBS `pbs-vs10`: create a scoped API token + a `wg-dashboard` namespace/ACL, and a prune+verify job. (PBS is prod infra — your confirm.)
3. Generate a client-side encryption key → store key + token in Vault.
4. Deploy the `pbs-backup.sh` + systemd timer on VM 4001; run the first backup; verify a restore round-trip.
5. Point PBS notifications at your email.

Everything up to here (design) is done. Say "go P2" and I'll prepare the exact commands + do it step by step with your confirmations.
