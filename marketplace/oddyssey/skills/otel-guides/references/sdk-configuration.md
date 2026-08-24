# OpenTelemetry SDK Configuration

Official docs root: https://opentelemetry.io/docs/languages/sdk-configuration/
Links ending in `index.md` return the page as raw markdown; links without it are redirects to external resources (registry, examples, API references).

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [General SDK Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/general/index.md) | Cross-language environment variables for core SDK behavior: `OTEL_SERVICE_NAME` (sets `service.name`, defaults to `unknown_service`), `OTEL_RESOURCE_ATTRIBUTES` (key=value resource attributes), `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` (sampler selection and args, default `parentbased_always_on`), and related propagator/log/attribute-limit settings. | Use this as the default knob set for identity (service name/resource attributes) and sampling in any instrumentation plan, regardless of target language. |
| [OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/index.md) | Cross-language environment variables for the OTLP exporter: `OTEL_EXPORTER_OTLP_ENDPOINT` (single base endpoint for all signals, default `http://localhost:4317` gRPC / `http://localhost:4318` HTTP) and its per-signal overrides `OTEL_EXPORTER_OTLP_{TRACES,METRICS,LOGS}_ENDPOINT`, plus protocol, headers, timeout, and compression settings. | Use this to point any SDK at a collector/backend — set one shared endpoint via `OTEL_EXPORTER_OTLP_ENDPOINT`, or override per signal when traces/metrics/logs must go to different destinations. |
| [Declarative Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/declarative-configuration/index.md) | A YAML-file-based alternative to environment variables (loaded via `OTEL_CONFIG_FILE`), useful for large configs or options not exposed as env vars. Schema is stable; `/development`-suffixed parts are experimental, and only Java currently supports it in practice. | Only reach for this when env vars are insufficient (e.g. many options, non-Java-only rollout) — check language support before assuming an SDK can consume the YAML file. |

## Planning notes

- These environment variables are cross-language by design (per the OpenTelemetry spec) — they are the primary knobs an instrumentation plan sets regardless of which language SDK is used, though actual per-variable support varies by language (see the linked environment-variable compliance matrix).
- `OTEL_SERVICE_NAME` and `OTEL_RESOURCE_ATTRIBUTES` establish resource identity; if `service.name` is set in both, `OTEL_SERVICE_NAME` wins.
- A subprocess-driven CLI inherits the parent's environment, so an instrumented CLI exports under the *parent application's* `OTEL_SERVICE_NAME` (observed with the Claude Code CLI): give every instrumented CLI the plan spawns a distinct `OTEL_SERVICE_NAME` in the subprocess environment, or its telemetry lands under the wrong service.
- `OTEL_EXPORTER_OTLP_ENDPOINT` is the single variable to set for "send everything to my collector" setups; use the signal-specific `_TRACES_`/`_METRICS_`/`_LOGS_ENDPOINT` variants only when signals must be routed differently.
- Declarative (YAML) configuration is still experimental/limited in language support — default to environment-variable configuration for a new instrumentation plan unless the target is Java or the env-var surface is genuinely insufficient.
