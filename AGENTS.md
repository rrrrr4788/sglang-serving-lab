# Repository guide

Read [README.md](README.md), [docs/README.md](docs/README.md) and
[docs/architecture.md](docs/architecture.md) before changing deployment behavior.
Implementation milestones live in [docs/platform-roadmap.md](docs/platform-roadmap.md).

## Local collaboration context

If present, read `.private/learning/WORKFLOW.md`, `.private/learning/learning-plan.md`
and `.private/learning/WORKING-MEMORY.md` before continuing local work. They preserve
the owner's collaboration preferences and current checkpoint. These ignored files
are optional local context; a fresh clone uses the public engineering docs.
Keep personal learning progress and course notes in `.private/`, not public docs.

## Engineering constraints

- Preserve existing edits, live services and unrelated Docker/Kubernetes projects.
- Kubernetes commands must name the intended kubeconfig/context and use the project
  namespace for namespaced operations. Do not rely on the default context for mutations.
- Keep .env, kubeconfig, credentials, caches and private requests out of Git/tool output.
  Do not publish unauthenticated inference or management endpoints.
- Pin images/Charts before use. Distinguish selected design, checked-in configuration,
  simulation and actual runtime evidence.
- The selected stack is kind/K3s, SGLang/official Gateway, Traefik,
  Prometheus/Grafana and KEDA-managed HPA; revisit for concrete implementation needs.
- Keep Compose as the single-GPU baseline. CPU mock results do not prove real GPU
  scheduling, TP performance, autoscaling, HA or production readiness.
- Checks must match the change. Document edits need link/content checks, not service
  restarts or inference requests. Record material verification limits.
- Follow the user's authorized scope for implementation, runtime actions, paid cloud
  resources and commit/push. Architecture docs do not authorize purchasing resources.

## Release documentation languages

Release-facing README, presentation, architecture, reproduction, acceptance, operations,
roadmap and index guides must have English and Simplified Chinese counterparts listed
in docs/languages.json. Update both together; keep commands, claims and verification
limits aligned. Follow docs/documentation.md and run scripts/check_repository.py.
Historical source reports/archives may remain in their original language with a
paired evidence summary; never translate private credentials or personal notes into Git.
