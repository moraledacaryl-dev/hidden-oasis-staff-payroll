# Security header ownership

Hidden Oasis Staff Payroll has two HTTP security boundaries. They are intentionally split so application deployments do not silently replace edge policy.

## Next.js application

`apps/web/next.config.ts` owns browser policy that must be present on application responses:

- `Content-Security-Policy`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Referrer-Policy`
- `Permissions-Policy`
- `Cross-Origin-Opener-Policy`
- `Cross-Origin-Resource-Policy`
- removal of the `X-Powered-By` framework disclosure (`poweredByHeader: false`)

The CSP deliberately permits only same-origin application resources, with `data:`/`blob:` images for QR and generated-image rendering and inline script/style compatibility required by the current Next.js application. It blocks object embedding and third-party framing and constrains forms, workers, fonts, images, and network connections.

## Nginx public HTTPS edge

The production reverse proxy for `staff.hiddenoasis.app` owns transport and host policy:

- redirect/reject plain HTTP in favor of HTTPS;
- serve only the canonical `staff.hiddenoasis.app` host for this application;
- emit `Strict-Transport-Security` on HTTPS responses;
- terminate TLS and maintain the production certificate;
- proxy application traffic only to the loopback Staff Payroll listeners.

HSTS is intentionally an edge responsibility because it is meaningful only after TLS termination and must not depend on a Next.js process being reached.

## Production acceptance

Every production deployment that changes either boundary must verify the public endpoint, not only localhost. Acceptance must assert:

1. HTTPS responds successfully.
2. `Strict-Transport-Security` is present at the public edge.
3. `Content-Security-Policy` is present on the public application response.
4. `X-Powered-By` is absent.
5. `X-Content-Type-Options`, `X-Frame-Options`, and `Referrer-Policy` remain present.
6. The canonical production hostname is used.

Do not weaken CSP or transport policy merely to make a browser smoke pass. Fix the specific resource requirement and keep the smallest required source allowance.
