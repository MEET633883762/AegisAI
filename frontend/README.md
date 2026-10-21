# AegisAI Dashboard — Phase 12

A read-only frontend for visualizing simulator evidence, Red/Blue execution, metrics, XAI decision traces, adaptive knowledge patches, and threat-intelligence context.

## Security boundary
The dashboard has no action-execution controls and cannot bypass the controller. Threat-intelligence content is rendered as untrusted data and escaped before insertion into the DOM.

## Scope
- Overview metrics
- Red/Blue execution timeline
- Structured XAI traces (no hidden chain-of-thought)
- Adaptive knowledge patches
- Threat-intelligence context
- Responsive layout
- Deterministic local demo data

The authoritative project architecture prefers React/Vite for the eventual full frontend. This phase keeps the dashboard dependency-free so the research prototype remains reproducible in an offline environment; API/database integration is intentionally deferred.

## Load a local website assessment

Run `python scripts/check_demo_site.py` while the local demo site is running. The checker writes profile-specific files under `results/`, preserving the baseline and hardened assessments. Open `frontend/index.html` and choose one report or both reports in the **Website Header Assessment** section. Loading both shows how many baseline findings were resolved. The browser parses reports locally, validates their schema and fixed loopback target, and escapes report values before display. The dashboard is read-only and does not execute remediation actions.
