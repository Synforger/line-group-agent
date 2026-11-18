# Security Policy

## Reporting a vulnerability

Use **GitHub Security Advisories private vulnerability reporting** to
disclose security issues responsibly:

1. Open https://github.com/Synforger/line-group-agent/security/advisories/new
2. Fill in the affected version + reproduction + impact estimate
3. Maintainer will acknowledge within 7 days

Do not file public Issues or PRs for security-relevant findings. Public
discussion only after a fix has shipped and end users have had time to
update.

If GitHub access is unavailable, reach `@Synforger` via the
contact channel listed in the repo's README.

## Supported versions

| version | supported |
|---|---|
| main (= rolling release) | ✅ active |
| tagged releases (= v0.x) | ⚠️ best effort (= no formal LTS) |
| forks / mirrors | ❌ out of scope |

This is a personal project; there is no enterprise LTS. Security fixes
land on `main` and the next tagged release. Pin to a specific tag if
your environment requires reproducibility.

## Threat model

line-group-agent runs on one operator's machine and is reached by the LINE
Platform through an HTTPS entry the operator puts in front of it.

- The server binds to loopback (`127.0.0.1`) by default and serves one endpoint,
  `POST /line/webhook`. A request is accepted only when its `X-Line-Signature`
  is the HMAC-SHA256 of the raw body under the channel secret (compared in
  constant time); the body is size-capped before that. Anyone who holds the
  channel secret can send events as LINE would.
- Messages of the groups in `allowed_group_ids` are stored in plain text under
  `state_dir`, and the recent ones are sent to the Claude API when the bot is
  mentioned. Members of those groups should know this. Events of other groups
  are dropped; only their group id is logged.
- Group messages are untrusted input. They reach the model inside an envelope
  and the system text tells it to read them as data. The model's tools are
  limited to web search, web page reading and a search over the same group's
  record; it has no tool that writes, books, pays or reaches the host. Only the
  text inside `<reply>…</reply>` is sent, and only to the group it was asked in.
  A member can still steer what the bot says in that group.
- Web page reading only fetches URLs that already appeared in the
  conversation (a rule of the Claude API), so a page cannot make the bot fetch a
  URL it made up.
- Secrets live in files named by the configuration, are read once at start and
  are never logged. Logs hold no message text, tokens or signatures. Settings
  come only from the configuration file: credential, address, proxy and tracing
  variables in the environment have no effect.
- Spending is capped by the monthly limit in the configuration; a spend limit
  on the API key's workspace is the second guard.

## In scope

- Authentication / authorization flaws (= when applicable)
- Sensitive data leakage (= secrets in logs / errors / responses)
- Path traversal / SSRF / RCE in the agent's own code paths
- Group content making the agent reveal data of another group, its secrets,
  or anything outside its state folder
- Dependency vulnerabilities surfaced by `task audit`

## Out of scope

- Issues in upstream dependencies that are already disclosed
  (= report those upstream; this repo will pick up the fix on next bump)
- Best-practice nudges with no concrete exploit path
- Vulnerabilities only reproducible with privileged local access
  (= `sudo` / root) — those imply the threat model has already failed
- Cosmetic / DoS-via-resource-exhaustion in dev-mode tools

## Audit log

The maintainer runs `task audit` (= `pip-audit` + `npm audit` +
`cargo audit` + `gitleaks` + `anon-scan` aggregated) at least every
6 months. Findings + resolutions are tracked here:

| date | findings | resolution |
|---|---|---|
| 2026-11-18 | (initial) | first release, no findings |

## Upstream redirect

When a vulnerability originates in a transitive dependency, the
disclosure goes to the upstream maintainer first. This repo only
contains the integration layer; the offending logic lives elsewhere
and should be patched there.
