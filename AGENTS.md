# EvoNext implementation instructions

Implement the product, not a copy of the previous implementation. Read README, docs/rebuild/README.md, docs/rebuild/03_ARCHITECTURE.md, docs/rebuild/08_SKILLS_RUNTIME_AND_PIPELINE.md and docs/ROADMAP.md before making changes. The full PRD/contracts and original acceptance IDs are now in docs/rebuild; current implementation evidence is only in docs/ACCEPTANCE.md.

**Cross-repo UI ownership override (approved 2026-11-14): EvoLoop owns ALL frontend code and business UI, including Viewer/Case/Correction/Evaluation/Recovery/Teacher/Verification/Skill Workshop pages. Do not add frontend features, UI routes, or a second SPA in EvoNext. Existing `web/` is transitional source code to port back and DELETE after EvoLoop integration and acceptance. Continue implementing algorithms, domain services, API/CLI/Worker, schemas, and backend tests in EvoNext. Older instructions mentioning React or a user-facing path refer to EvoLoop as the UI consumer, not a requirement to build one here.**

1. Preserve OpenCUA-shaped source JSON and the existing offline profile. Validate a view without serializing defaults back into source evidence. Unknown fields, long string IDs, source versions including zero, raw output, dispatch and observed results must survive interchange.
2. Mongo owns trajectory facts, MinIO owns bytes, PG owns explicitly introduced control records. Do not replace these technologies or migrate legacy data as a side effect of startup. Never modify legacy collections directly.
3. A Snapshot is a frozen package identity, not a new meaning of Task/Trial/Review. Byte hash, semantic input hash, source revision and human review status are different concepts.
4. ZIP/file interchange must be lossless. HTTP compatibility must name its supported profile and report transformations, unknowns and unverified readback. Never claim that the complete old API is emulated.
5. No paid model calls, device execution, training, deployment or production writes in ordinary tests. Enabling an adapter is not authorization for every operation.
6. Use mature tools: FastAPI, Pydantic, React, official persistence clients, SQLAlchemy/Alembic, Celery and Langfuse. No second scheduler, generic workflow platform, custom tracing backend, broad ORM facade or speculative plugin marketplace.
7. Each slice must work through API/CLI and a user-facing path where relevant. Do not add empty feature modules or success-returning stubs to satisfy a checklist.
8. Machine judgment, human review, candidate generation, execution, adoption and training eligibility retain separate authority. Failure does not automatically mean weight training or Skill generation.
9. Changes to raw evidence create a new source/revision; corrections cannot rewrite original dispatch/results. A resumed trial must obtain new evidence, not paste a previous suffix after a changed action.
10. No private source, real data or credentials in this public repository. Synthetic fixtures are explicitly named. Never copy old deployment settings or entire historical design archives here.
11. Run pytest, compileall, lint and the frontend build when available. Report unavailable checks separately. Add real-service tests only for isolated resources with explicit configuration; never turn missing dependencies into a passing mock test.
12. Keep one current roadmap and one compatibility contract. Record exceptions in a scoped ADR, not another parallel global plan. Complete a working slice, then stop expanding its infrastructure.

13. Follow the first-class feature layout inside src/evonext. Runtime consumes contracts.skills, never Workshop internals. Workshop does not execute tools or award evaluation/adoption authority. Do not create top-level generic Python packages named skills/runtime or put skill assets back under offline.
14. Paid calls use providers.gateway with durable PostgreSQL receipts, stable operation/repetition identity and an explicit enable switch. Sending/unknown is not permission to retry; received responses are saved before parsing. Never run a real model merely to verify a refactor.
15. Policy files are trusted reviewed configuration, not uploaded executable templates. Git is the policy editing source; a future Langfuse publication bridge must pin versions rather than create two independent latest definitions.
16. AIHOT/OpenClaw ideas are mapped in ADR-001. Do not copy their whole product, default immediate Skill activation or news scoring into GUI success/eligibility. The current templates and linkage checks are not independent semantic validation.
