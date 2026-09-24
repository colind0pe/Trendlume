# Security Policy

Trendlume prioritizes software security. Because automated video generation handles external AI credentials, local browser rendering, and social platform publishing sessions, please review the system's operational and architectural boundaries below.

---

## ⚠️ Architectural Scope & Security Boundaries

When deploying or using Trendlume, keep the following security constraints in mind:

1. **No Built-in Multi-User Authentication**:
   - Trendlume is designed as a **single-user creator workbench for local or trusted private networks**.
   - It **does not include user authentication, multi-tenant isolation, or role-based access control (RBAC)**. Anyone who can reach the web port (default `3000`) or the backend API (default `8000`) can view and modify configured API keys, inspect task history, and trigger publishing jobs.
   - **Never expose this project directly to the public internet**. If remote access is required, restrict access using a private network (e.g., Tailscale, WireGuard) or place it behind a reverse proxy enforcing authentication (e.g., HTTP Basic Auth, OAuth2-Proxy).

2. **Credential Storage & Encryption**:
   - All external API keys and publishing credentials saved via the Web Settings UI are encrypted at rest in SQLite using symmetric AES/Fernet encryption via the `CREDENTIAL_ENCRYPTION_KEY` environment variable.
   - Secrets are masked (`mask_secret`) before appearing in application logs, error traces, or task snapshots.
   - Never commit `.env` files containing real production keys to version control.

3. **Local Code & Media Execution**:
   - Dynamic video templates are rendered inside a sandboxed headless Chromium instance managed by Playwright.
   - Audio/video stitching and subtitle burn-in are executed locally via FFmpeg. File operations are strictly scoped to `data/` and temporary cache paths.

---

## Supported Versions

We provide security updates and patches for the current release stream:

| Version | Supported | Notes |
| :--- | :---: | :--- |
| `0.3.x` (main) | ✅ | Active development and current release baseline |
| `< 0.3.0` | ❌ | Early development prototypes; please upgrade |

---

## Reporting a Vulnerability

If you discover a security issue (specifically credential leakage, cipher flaws, SSRF, or unintended command execution), **do not open a public GitHub issue**.

Please report security issues privately:

1. **Email**: Send detailed findings to `colin0921@outlook.com`.
2. **Include in your report**:
   - Description of the vulnerability and potential impact
   - Step-by-step reproduction instructions or Proof of Concept (PoC)
   - Environment details (Docker Compose vs. local source, OS version)
   - Suggested remediation or patch (if available)

### Response Timeline

- **Acknowledgement**: We aim to acknowledge receipt of security reports within **48 hours**.
- **Assessment & Fix**: Confirmed issues will be evaluated and patched within **7 to 14 business days**, depending on severity.
- **Coordinated Disclosure**: We request that vulnerability details remain confidential until a fix has been released with reasonable upgrade time for users.
