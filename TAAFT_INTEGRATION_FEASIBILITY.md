# TAAFT Integration Feasibility

Date: 2026-11-08
Decision: **NO-GO for automated TAAFT operation** until prior written consent is
obtained from the provider. The adapter is implemented and gated, not enabled.

## What was reviewed

- Provider Terms of Service: https://theresanaiforthat.com/terms/ (last updated
  2026-03-19, as displayed at review time).
- The existing `taaft_agent.py`, which logs into the site through a browser
  profile, drives the generator UI, polls internal endpoints, downloads clips and
  automatically extends them.
- The new platform requirement for multi-user, isolated, production operation.

## Relevant prohibitions (paraphrased)

The Terms of Service restrict, among other things:

1. Automated access, scraping, crawling or harvesting of the service without prior
   written consent.
2. Circumventing or attempting to circumvent security, authentication, rate limits
   or access controls.
3. Automated, bulk or repetitive engagement with the service.
4. Using the service in ways that damage, overload or interfere with it.

The exact wording and scope can change. This is a product/legal assessment, not
legal advice.

## Why the original agent conflicts

`taaft_agent.py` is unattended browser automation of a logged-in account. It
submits generations, polls internal JSON, downloads media and repeats this per
scene. Even where a human owns the account, this is automated access and automated
engagement at a scale the provider's terms do not authorize. Wrapping it in a
multi-user SaaS would multiply the conduct and require sharing or automating
multiple accounts, which is not acceptable without explicit permission.

## Technical risks even with permission

- UI/API drift breaks selectors and internal endpoints without notice.
- Per-account concurrency limits make one active workflow per account essential.
- Provider quotas and credit accounting must be respected and surfaced to users.
- Browser automation of authenticated sessions is fragile and hard to sandbox.
- Long-running generations conflict with ephemeral/sleeping free hosts.
- Download URLs and cookies are secrets; isolation and encryption are mandatory.

## Current implementation

- `agent/providers/taaft.py` contains the ported adapter, including login session
  hydration, submit, extend, poll, download and account/quota checks.
- The adapter throws `ProviderDisabledError` with a clear message unless
  `TAAFT_ENABLED=true` (cloud) or `TAAFT_LOCAL_ENABLED=1` (local agent) **and** a
  per-user session exists.
- Project creation with `provider="taaft"` returns HTTP 409 while
  `TAAFT_ENABLED=false`.
- `TAAFT_ENABLED` defaults to `false` in `.env.example` and settings.
- Provider sessions are encrypted at rest with Fernet and hydrated only inside a
  worker process with a temporary file; they are never logged or shared.

## Path to a lawful, supported integration

1. Contact the provider and request **prior written authorization** for automated
   multi-user integration, describing volume, rate limits, account model, storage
   and attribution.
2. If an official API or partner program exists, integrate against it instead of
   the UI. Replace the Playwright adapter with an HTTP client implementing the
   same `VideoProvider` contract.
3. Obtain written confirmation on: automated access, per-user accounts, concurrent
   jobs, media retention, and whether resale/SaaS use is permitted.
4. Keep the existing gate. Enable only for authorized environments and accounts.
5. Add provider-specific quotas, backoff, kill switches and audit logging before
   enabling for any user.

## Recommended alternatives now

- Use the simulated provider for development and demos (real MP4 output, clearly
  labelled).
- Integrate a provider with a documented public API and terms that permit this use.
- Keep local execution available for operators who already have lawful access to a
  generation tool, without shipping unauthorized automation.

## Decision record

- Automated TAAFT access: **prohibited without prior written consent**.
- Platform default: simulated provider.
- TAAFT code: present, isolated, encrypted-session aware, **disabled by default**.
- No attempt is made to bypass logins, paywalls, quotas or bot protections.
