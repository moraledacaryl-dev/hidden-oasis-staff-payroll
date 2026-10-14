# npm security audits during production deployment

Production deployment runs `npm audit --omit=dev --audit-level=high` as a **blocking** check. This includes the dependencies used by the deployed Next.js application. A high or critical finding in that dependency graph prevents deployment.

The separate `npm audit --audit-level=high` scans all dependencies, including developer tooling. Its findings are printed but do not independently block a production release. Lint, typecheck, build, Python tests, production preflight, and staged activation checks still remain mandatory.

## Accepted development-only finding (2026-10-14)

- Advisory: `GHSA-vfj7-8cjw-p6xm`, `braces <=3.0.3` (high; recursive brace-pattern stack exhaustion).
- Observed dependency path: `eslint-config-next -> @next/eslint-plugin-next -> fast-glob -> micromatch -> braces`.
- `braces` is used by lint tooling; the vulnerable pattern expansion is not called by the production application. The deployment's strict production-only audit checks this boundary on every release.
- As of 2026-10-14, the advisory has **no published patched release**. Do not apply `npm audit fix --force`: its suggested major ESLint configuration downgrade does not provide a patched `braces`.
- Reassess on every dependency upgrade. Remove this acceptance when the lint toolchain drops `braces` or a patched version is published.

## Remaining runtime advisory

`next@15.5.24` has a moderate SSG/ISR cache-poisoning advisory (GHSA-4jqv-mc3x-m676). `next@15.5.27` is the patched 15.x release. Upgrade Next.js **and** regenerate `package-lock.json` together, then run the full CI/browser suite before shipping that separate change. Moderate findings are below the existing high-severity deployment gate; this is not a waiver of any high/critical production advisory.

Do not silently suppress audit output, and do not downgrade the production-only severity threshold.
