## PR Description
<!-- Briefly describe the problem this PR solves or the feature it introduces. Reference related issues (e.g. Closes #123). -->

### Type of Change
- [ ] 🐛 Bug Fix
- [ ] ✨ New Feature
- [ ] 🔌 New Provider Integration
- [ ] 🎨 Code Refactor / Performance Improvement
- [ ] 📝 Documentation Update
- [ ] 🧪 Tests & Quality Assurance

---

## 🏛️ Architectural Checklist
Please confirm that your changes adhere to Trendlume's core design rules:

- [ ] **Protocol Contracts**: Any external AI or platform interaction strictly implements its Protocol under `src/providers/`, and business logic contains **no** `if provider == "xxx"` branching.
- [ ] **Retry & Masking**: Remote network calls use `@retry_async`, and credentials are masked via `mask_secret()` before logging.
- [ ] **Lightweight Architecture**: **No** external persistent dependencies (Redis, Celery, Kafka, PostgreSQL, MinIO) are introduced.
- [ ] **Storage Abstraction**: All file reading and writing is routed through `StorageService`, without scattered raw `open()` calls.
- [ ] **Database Migrations**: If `src/models/` was changed, an auto-generated Alembic migration script is included under `alembic/versions/`.

---

## 🧪 Verification Checklist

Ensure all local quality checks pass cleanly before submitting:

### Backend Checks
- [ ] `cd backend && uv run ruff check src` (Lint checks passed)
- [ ] `cd backend && uv run ruff format --check src` (Formatting verified)
- [ ] `cd backend && uv run --extra dev pytest ../tests -q` (Automated test suite passed)

### Frontend Checks
- [ ] `cd frontend && npm run typecheck` (TypeScript type check passed)
- [ ] `cd frontend && npm run build` (Production build succeeds)

---

## Testing Evidence
<!-- Describe how you verified your changes, or paste terminal outputs / screenshots demonstrating success. -->
```text

```
