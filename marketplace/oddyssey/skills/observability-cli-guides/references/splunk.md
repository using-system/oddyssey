# Splunk — `splunk` CLI (+ REST API); Splunk Observability Cloud — API/SignalFlow

Official docs: https://help.splunk.com/, https://dev.splunk.com/observability/
`help.splunk.com` and `dev.splunk.com` are HTML-only (no raw-markdown
mirror); `docs.splunk.com` — the older doc host, still linked from many
search results — returns HTTP 403 to non-browser clients (`curl`, this
tool's fetcher) even though the pages exist, so every link below uses the
`help.splunk.com` mirror instead, which serves the same content and returns
200.

Splunk Enterprise/Cloud Platform (the log-search product, SPL) and Splunk
Observability Cloud (the former SignalFx product: metrics/traces/RUM) are
**separate products** with separate CLIs, APIs, and auth — covered in two
halves below.

## Setup

| Topic | Link | What to do with it |
| --- | --- | --- |
| `splunk` CLI basics | [About the CLI](https://help.splunk.com/en/data-management/splunk-enterprise-admin-manual/9.4/administer-splunk-enterprise-with-the-command-line-interface-cli/about-the-cli) | The `splunk` binary ships with every Enterprise/Cloud instance (`$SPLUNK_HOME/bin/splunk`); run it locally on the instance or remotely with `-uri`. Log in interactively once (`splunk login`) or pass `-auth user:pass` per command. |
| CLI search syntax | [Syntax for searches in the CLI](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-in-the-cli/syntax-for-searches-in-the-cli) | `./splunk search '<SPL>' -maxout 100 -output table\|json\|csv\|rawdata`. Remote: add `-uri https://<host>:8089`. `-earliest_time`/`-latest_time` set the window; `-preview true` streams partial results; `-detach true` runs async. |
| `btool` (config inspection) | [Use btool to troubleshoot configurations](https://help.splunk.com/en/splunk-enterprise/administer/troubleshoot/10.2/first-steps/use-btool-to-troubleshoot-configurations) | `splunk btool <conf> list [--debug] [--app=<app>]` — shows the merged, layered view of a single `.conf` file across all apps/default/local. Not a query tool; useful when a search or index isn't behaving as its `.conf` files suggest. |
| Support/debug CLI tools | [Command line tools for use with Support](https://help.splunk.com/en/splunk-enterprise/administer/troubleshoot/9.4/contact-splunk-support/command-line-tools-for-use-with-support) | Catalog of `splunk diag`, `splunk btool`, `splunk cmd`, etc. — reach for this when triaging a broken instance rather than a search itself. |
| Current context & connection probe | (rows above) | The splunk CLI has no whoami surface: the "context" a preflight displays is the target (`-uri`) and user the mission provides, and the cheapest connection probe is any trivial authenticated call from the rows above — e.g. a `splunk search` with `-maxout 1`, or the REST search-jobs call below. |
| REST API basics (search jobs) | [Creating searches using the REST API](https://help.splunk.com/en/splunk-enterprise/leverage-rest-apis/rest-api-tutorials/10.0/rest-api-tutorials/creating-searches-using-the-rest-api) | Management port `8089`. `curl -k -u admin:changeme https://localhost:8089/services/search/jobs/ -d search="search sourcetype=access_* earliest=-7d"` returns XML with a `<sid>` (search ID) — the base pattern for every SPL-over-HTTP call below. |
| Auth tokens (bearer, no per-request login) | [Use authentication tokens](https://help.splunk.com/en/splunk-enterprise/administer/manage-users-and-security/9.3/authenticate-into-the-splunk-platform-with-tokens/use-authentication-tokens) | Mint a token once (Splunk Web or `/services/authorization/tokens`), then `curl -H "Authorization: Bearer <token>" -X GET https://<host>:8089/<endpoint>` — avoids sending username/password on every call; works for both REST calls and CLI `-auth` in newer versions. |
| Splunk Cloud admin CLI (config, not search) | [Administer Splunk Cloud Platform using the ACS CLI](https://help.splunk.com/en/splunk-cloud-platform/administer/admin-config-service-manual/10.5.2605/administer-splunk-cloud-platform-using-the-admin-config-service-acs-cli) | `acs` is a separate, Cloud-only CLI for self-service admin tasks (IP allow lists, indexes, HEC tokens). It does not run searches — don't confuse it with `splunk search`. |
| Observability Cloud tokens | [Org access tokens](https://help.splunk.com/en/splunk-observability-cloud/administer/authentication-and-security/authentication-tokens/org-access-tokens), [API access tokens](https://help.splunk.com/en/splunk-observability-cloud/administer/authentication-and-security/authentication-tokens/api-access-tokens) | Org (access) tokens are long-lived, org-scoped, sent as `X-SF-Token` on data-plane/query calls; API access tokens are shorter-lived and user-scoped, needed for endpoints requiring admin/user identity. Pick org tokens for scripts/automation. |
| Observability Cloud API map | [Splunk Observability Cloud API endpoint overview](https://dev.splunk.com/observability/docs/apibasics/api_list/), [Retrieve data basics](https://dev.splunk.com/observability/docs/apibasics/retrieve_data_basics) | Landing pages for the full REST surface (metrics, traces, detectors, dashboards) — start here before hunting for a specific endpoint. |

## Query by signal

| Signal | How | Link | Notes |
| --- | --- | --- | --- |
| Logs (discovery: indexes) | `./splunk search '\| eventcount summarize=false index=*' -output table` | [eventcount command](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/10.4/search-commands/eventcount) | Generating command (leading pipe, must come first). `summarize=false` splits the counts per index and adds the `provider`/`server` columns, so it doubles as "which indexes exist and which of them actually hold events"; add `report_size=true` for `size_bytes`. Run it before any `search index=…` rather than guessing an index name. |
| Logs (SPL, CLI) | `./splunk search 'search index=main error \| head 20' -output json` | [Syntax for searches in the CLI](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/9.4/search-in-the-cli/syntax-for-searches-in-the-cli) | Logs/events are SPL's native, first-class object — no special command needed, just `search ...`. Real-time variant is `splunk rtsearch`. |
| Logs (SPL, REST/curl) | `curl -k -u admin:pw https://localhost:8089/services/search/jobs/ -d search="search sourcetype=access_* earliest=-7d"` → poll/export | [Creating searches using the REST API](https://help.splunk.com/en/splunk-enterprise/leverage-rest-apis/rest-api-tutorials/10.0/rest-api-tutorials/creating-searches-using-the-rest-api), [Export data using the REST API](https://help.splunk.com/en/splunk-enterprise/search/search-manual/10.4/export-search-results/export-data-using-the-splunk-rest-api) | POST creates a job (`sid`); GET `.../jobs/<sid>/results/` (blocking search must finish first) or `.../jobs/export` (streams as it runs) with `-d output_mode=json\|csv\|xml`. |
| Metrics (discovery: metric names) | `./splunk search '\| mcatalog values(metric_name) WHERE index=*' -output table` | [mcatalog command](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/10.4/internal-commands/mcatalog) | Generating command (leading pipe). Lists the distinct `metric_name` values across the metric indexes — the discovery step before `mstats`. Same default-index trap as `mstats`: without `WHERE index=` it only reads the role's default metrics indexes. `values(<dimension>)` with `WHERE … AND metric_name=<name>` lists a metric's dimension values. Requires the `list_metrics_catalog` capability on the role. |
| Metrics (SPL, `mstats`) | `./splunk search '\| mstats avg(cpu.usage) WHERE index=metrics_idx span=1m'` | [mstats command](https://help.splunk.com/en/splunk-enterprise/search/spl-search-reference/10.4/search-commands/mstats) | Report-generating command: it takes a **leading pipe and must be the first command** in the search (unless `append=true`) — `search \| mstats …` is invalid. Runs against dedicated metric indexes, not event indexes; if no `index=` is given it only searches the caller's *default* metrics indexes (returns nothing if none are set) — always pass `WHERE index=` explicitly or `index=*` for "search everything". Group with a `BY` clause, which must come **after** `WHERE` (`\| mstats avg(cpu.usage) WHERE index=metrics_idx BY host span=1m`); time-bucket needs an explicit `span=`. |
| Traces / APM | No SPL command — Splunk APM (part of Observability Cloud) is a separate product with its own UI-first workflow; ingest and single-trace download are documented, bulk trace *search/query* from a terminal is not. | [Introduction to Splunk APM](https://help.splunk.com/en/splunk-observability-cloud/monitor-application-performance/introduction-to-splunk-apm), [Download traces](https://help.splunk.com/en/splunk-observability-cloud/monitor-application-performance/manage-services-spans-and-traces-in-splunk-apm/download-traces) | Documented programmatic path is narrow: [Download APM traces API](https://dev.splunk.com/observability/reference/api/trace_id/latest) fetches one trace by trace ID as JSON (8 MB cap, multi-segment traces need concatenating). There is no documented SPL/DQL-style query language over span data from a terminal. |
| Metrics (Observability Cloud, streaming) | SignalFlow program over REST/WebSocket, e.g. `curl -X POST "https://stream.<REALM>.signalfx.com/v2/signalflow/start" -H "X-SF-Token: <token>" -H 'Content-Type: application/json' -d '{"program":"data(\"cpu.utilization\").publish()"}'` | [Analyze data using SignalFlow](https://dev.splunk.com/observability/docs/signalflow), [SignalFlow methods](https://dev.splunk.com/observability/docs/signalflow/methods) | SignalFlow is the query/analytics language for metric time series in Observability Cloud — a Python-like DSL, not SPL. No packaged CLI ships it; the closest terminal tool is the [`signalflow-client-python`](https://github.com/signalfx/signalflow-client-python) library, which bundles an example script invoked as `python <script>.py --stream-endpoint https://stream.<realm>.signalfx.com <token> "<program>"` — that's a sample runner, not an installable CLI binary. |
| Profiles | No terminal query surface for stack traces — AlwaysOn Profiling (Splunk APM) collects them continuously but is explored in the UI flame graph; its **memory** metrics are ordinary Observability Cloud metrics, so those *are* reachable via SignalFlow. | [AlwaysOn Profiling](https://help.splunk.com/en/splunk-observability-cloud/monitor-application-performance/alwayson-profiling), [Memory profiling metrics](https://help.splunk.com/en/splunk-observability-cloud/monitor-application-performance/alwayson-profiling/memory-profiling-metrics) | AlwaysOn Profiling "continuously collects stack traces" and correlates them to APM spans; the documented way to read them is "explore stack traces directly from APM" and the flame graph — no REST/CLI endpoint for stack traces is documented. Memory profiling additionally "exposes memory metrics for your application, which you can use to build charts and dashboards" (the exact set is language-dependent: Java, Node.js, .NET) — query those with the SignalFlow row above. Splunk Enterprise/Cloud Platform (SPL) has no profiles signal at all. |
| Ingest metrics/traces/events (Observability Cloud) | `curl` to the ingest REST/gRPC endpoints | [Send traces, metrics and events](https://dev.splunk.com/observability/reference/api/ingest_data/latest), [Send APM traces](https://dev.splunk.com/observability/docs/apm/send_traces/) | Write path, not query — useful when bypassing the OTel Collector. Trace ingest is `POST /v2/trace` or `/v2/trace/otlp`; gRPC endpoint is `ingest.<realm>.observability.splunkcloud.com:443`; both need `X-SF-Token`. |

## Planning notes

- `docs.splunk.com` blocks non-browser `curl`/fetch requests (HTTP 403) even
  though its pages are otherwise identical to `help.splunk.com`, which
  returns 200 — link this skill's readers to `help.splunk.com` exclusively
  to avoid broken-looking links in automated checks (verified 2026-08).
- Splunk Enterprise/Cloud (SPL, `splunk` CLI) and Splunk Observability
  Cloud (SignalFlow, APM) are billed, documented, and authenticated as
  **separate products** — a Splunk Enterprise auth token/`Api-Token`-style
  credential does not work against `dev.splunk.com`'s Observability Cloud
  endpoints, which want `X-SF-Token` org access tokens instead.
- Signal coverage gap: traces in Observability Cloud have no SPL/DQL-style
  terminal query surface — only single-trace-by-ID download (8 MB cap,
  UI-first) is documented. This is a real gap versus the logs (`search`)
  and metrics (`mstats` / SignalFlow) stories, both of which support
  free-form filtering and aggregation from a terminal.
- `mstats`, `mcatalog`, and `eventcount` are all **generating** commands:
  they take a leading pipe and must be the first command in the search.
  `search | mstats …` does not parse. In both `mstats` and `mcatalog` the
  `WHERE` clause precedes `BY`/`GROUPBY`; `span=` exists only on `mstats`
  (`mcatalog` cannot group by time at all) and may sit anywhere between
  clauses (per the fetched command pages, verified 2026-08).
- Profiles coverage is UI-first: AlwaysOn Profiling has no documented
  stack-trace query API or CLI, so from a terminal the only profiling
  data reachable is the memory metrics it exports (via SignalFlow). Record
  this as a telemetry gap rather than reporting "no profiling exists".
- `mstats` silently returns nothing if the caller's role has no default
  metrics index and the query omits `index=` — worth calling out
  explicitly in any generated `mstats` query, since the failure mode looks
  like "no data" rather than an error.
- The Splunk Cloud `acs` CLI is a distinct, admin-only tool (index/HEC/IP
  allow-list management) and must not be confused with `splunk search` —
  it has no search or query capability at all.
