# Load test types

Official docs: https://grafana.com/docs/k6/latest/testing-guides/test-types/

Six documented types (verified 2026-08 - an easy miscount, five is a
common wrong answer that drops breakpoint):

| Type | What it answers | Shape |
| --- | --- | --- |
| **Smoke** | Does the system work at all, minimal load? | 1-2 VUs, short duration - a sanity check before anything bigger. |
| **Average-load** (often called "load") | How does the system behave under expected, everyday traffic? | Steady VUs at the expected concurrency, sustained duration. |
| **Stress** | Where does the system start to degrade under above-normal load? | Ramp VUs beyond expected traffic until latency/errors climb. |
| **Soak** | Does the system degrade over a long sustained run (leaks, resource exhaustion)? | Moderate, steady load held for a long duration (hours). |
| **Spike** | Does the system survive a sudden, sharp traffic burst? | Fast ramp to a high VU count, brief hold, fast ramp down. |
| **Breakpoint** | What's the system's actual capacity ceiling? | Continuously increasing load until the system breaks. |

Picking one is a **human decision** (see authoring-inputs.md) - it
encodes what the caller actually wants to learn, which this skill or
the authoring agent cannot infer from the service alone.
