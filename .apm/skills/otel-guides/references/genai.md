# OpenTelemetry Generative AI

Official docs root: https://github.com/open-telemetry/semantic-conventions-genai/tree/main/docs/gen-ai
The GenAI conventions left the main `semantic-conventions` repository and live in their own,
`open-telemetry/semantic-conventions-genai`; the main registry keeps only the deprecated names.
Every link below is a GitHub page — swap `github.com/.../blob/main/` for
`raw.githubusercontent.com/.../main/` to fetch the raw markdown — and every fact in this file
was read at revision `94f432d7126f5884d30a2cdde6f4e89908ebb6fd` (2026-09-03). The whole
document set is **Development** status: re-fetch the page before quoting a name in a plan.

| Section | What it covers | What to do with it |
| --- | --- | --- |
| [README](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/README.md) | The index: five signal pages (events, exceptions, metrics, model spans, agent spans), four provider pages (Anthropic, Azure AI Inference, AWS Bedrock, OpenAI), and the Model Context Protocol page. | Open first to see which pages exist at the current revision — providers and agent conventions are still being added. |
| [Model spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-spans.md) | The client span for every model operation — inference, embeddings, retrievals, fetch response, memory, execute tool — with its attribute table, the `gen_ai.operation.name` value list, and the "Capturing instructions, inputs, and outputs" section that sets the content-capture policy. Span name `{gen_ai.operation.name} {gen_ai.request.model}`, kind `CLIENT`. | The page that names a model call; read its attribute table when reading a trace (which attributes are Required, Recommended, Opt-In) and its capture section before deciding whether prompts and completions go into telemetry. |
| [Metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-metrics.md) | Client instruments (`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, `gen_ai.client.operation.time_to_first_chunk`, `gen_ai.client.operation.time_per_output_chunk`), model-server instruments (`gen_ai.server.request.duration`, `gen_ai.server.time_per_output_token`, `gen_ai.server.time_to_first_token`), and the workflow, agent (`gen_ai.invoke_agent.duration`, `.inference_calls`, `.tool_calls`) and tool (`gen_ai.execute_tool.duration`) histograms, each with its advised bucket boundaries. | Use to plan the per-model RED reading (calls, tokens, latency) and to check what a library already emits before adding a histogram by hand. |
| [Events](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-events.md) | `gen_ai.client.inference.operation.details` (requirement level Opt-In: chat history and parameters as a log event, independent from the trace) and `gen_ai.evaluation.result`; notes that events are not yet available in every language. | Open when content capture must land in logs rather than on span attributes, or when evaluation scores are part of the plan. |
| [Agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-agent-spans.md) | Create agent, invoke agent (client and internal), invoke workflow, plan, and execute tool spans, extending the model spans; `invoke_agent {gen_ai.agent.name}` is the span name, `gen_ai.agent.name` Conditionally Required. | The page for an agent loop: how the loop, its model calls and its tool calls nest, and which attributes tie them to one `gen_ai.conversation.id`. |
| [Exceptions](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/gen-ai-exceptions.md) | The `gen_ai.client.operation.exception` event (severity WARN) carrying `exception.type`, `exception.message`, `exception.stacktrace` for API errors, rate limits, timeouts. | Use when planning how a failed model call is recorded, next to `error.type` on the span. |
| [Model Context Protocol](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/mcp.md) | MCP client and server spans and four duration metrics (`mcp.client.operation.duration`, `mcp.server.operation.duration`, `mcp.client.session.duration`, `mcp.server.session.duration`); `mcp.method.name` Required; context propagation over JSON-RPC; stdio and streamable-HTTP examples. Explicitly preferred over the RPC and HTTP conventions for MCP traffic. | Open when the service is an MCP client or server — a tool call through MCP is an `execute_tool` operation with `mcp.method.name` next to it. |
| [Anthropic](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/anthropic.md) | Inference and embedding spans plus metrics for the Anthropic API; `gen_ai.provider.name` MUST be `anthropic`. | Open when the code calls Anthropic directly, to pin the provider-specific attributes. |
| [OpenAI](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/openai.md) | Inference, embeddings and fetch-response spans plus metrics; `gen_ai.provider.name` MUST be `openai`. | Same, for the OpenAI API — and for the OpenAI-compatible platforms an OpenAI SDK instrumentation reaches. |
| [AWS Bedrock](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/aws-bedrock.md) | Bedrock spans extending the model spans, with guardrail attributes (`aws.bedrock.guardrail.id`); `gen_ai.provider.name` MUST be `aws.bedrock`. | Same, for Bedrock through the AWS SDKs. |
| [Azure AI Inference](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/azure-ai-inference.md) | Inference and embedding spans plus metrics; `gen_ai.provider.name` MUST be `azure.ai.inference`. | Same, for the Azure AI Inference (Foundry) endpoints. |
| [LLM call examples](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/non-normative/examples-llm-calls.md) (non-normative) | Worked telemetry for a simple chat completion, multimodal input and output, tool calls (functions and built-in), system instructions, reasoning, multiple choices; the simple chat completion is shown three ways — content capture disabled, on span attributes, and on event attributes. | Read one example before reading a real trace: it shows what a compliant span looks like and what changes when content capture is on. |
| [models.py](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/docs/gen-ai/non-normative/models.py) (non-normative) | The Python (pydantic) reference models of the structured content — system instructions, input/output messages, tool definitions, retrieval documents, memory records — that generate the JSON schemas under `model/gen-ai/`. | Use when hand-coding or validating a `gen_ai.input.messages` / `gen_ai.output.messages` payload; the JSON schemas it generates are the normative shape. |
| [Deprecated names](https://github.com/open-telemetry/semantic-conventions/blob/main/docs/registry/attributes/gen-ai.md) (main registry) | The main repository's registry keeps the retired attributes with their replacements: `gen_ai.system` → `gen_ai.provider.name`, `gen_ai.usage.prompt_tokens` → `gen_ai.usage.input_tokens`, `gen_ai.usage.completion_tokens` → `gen_ai.usage.output_tokens`. | Use to read telemetry from an older instrumentation, and to translate a stored report that used the old names. |

## Hard facts (revision `94f432d`, 2026-09-03)

The minimum to detect and read GenAI telemetry without opening a link. Requirement levels
are those of the inference span.

| Attribute | Level | What it carries |
| --- | --- | --- |
| `gen_ai.operation.name` | Required | The operation: `chat`, `text_completion`, `embeddings`, `generate_content`, `execute_tool`, `invoke_agent`, `invoke_workflow`, `retrieval`, `create_agent`, `plan`, `fetch_response`, the memory operations |
| `gen_ai.provider.name` | Required | The provider: `openai`, `anthropic`, `aws.bedrock`, `azure.ai.inference`, `gcp.gen_ai`, `gcp.vertex_ai`, ... (replaces the removed `gen_ai.system`) |
| `gen_ai.request.model` | Conditionally Required (if available) | The model requested — the per-model pivot of an observation |
| `gen_ai.response.model` | Recommended | The model that actually answered (`gpt-4-0613` for a `gpt-4` request) |
| `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | Recommended | Prompt and completion token counts, integers |
| `gen_ai.conversation.id` | Conditionally Required | The session or thread — what groups the spans of one agent conversation |
| `gen_ai.agent.name`, `gen_ai.tool.name` | Conditionally Required on agent and tool spans | The agent invoked, the tool executed |
| `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.definitions` | Opt-In | The content — never emitted unless the user opts in |

The two client metrics, both histograms:

- `gen_ai.client.token.usage` — unit `{token}`. Required: `gen_ai.operation.name`,
  `gen_ai.provider.name`, `gen_ai.token.type` (values `input` and `output`, so one histogram
  carries both counts). Conditionally Required: `gen_ai.request.model` (if available),
  `server.port` (if `server.address` is set). Recommended: `gen_ai.response.model`,
  `server.address`. No `error.type`.
- `gen_ai.client.operation.duration` — unit `s`. Required: `gen_ai.operation.name`.
  Conditionally Required: `error.type` (if the operation ended in an error),
  `gen_ai.provider.name` (if the operation involves a call to a GenAI provider),
  `gen_ai.request.model` (if available), `server.port` (if `server.address` is set).
  Recommended: `gen_ai.response.model`, `server.address`.
- Token counts come from the provider: an instrumentation that cannot efficiently obtain them
  MAY let the user enable offline token counting and otherwise MUST NOT report the usage
  metric — a plan promising token usage for a streaming call has to check that the SDK returns
  usage on the stream. When a system reports both used and billable tokens, billable tokens
  are the ones reported.

Content capture — instructions, inputs and outputs are sensitive and often large, so
instrumentations SHOULD NOT capture them by default and SHOULD offer an opt-in. The three
patterns the spans page names:

1. The default: record nothing.
2. Record the content on the `gen_ai.system_instructions`, `gen_ai.input.messages` and
   `gen_ai.output.messages` attributes — for pre-production, or storage that complies with
   the privacy rules that apply.
3. Store the content externally and record references on the span — the pattern the page
   recommends in production.

The opt-in switch the spec cites as an example, and the official Python instrumentations
implement, is `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`: `no_content` (the
default), `span_only`, `event_only`, `span_and_event`. The official Python packages expose the
external-storage pattern through `OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK=upload` with
`OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH`.

## Instrumentation libraries

An instrumentation library first, never hand-coded `gen_ai` attributes. Every row was verified
on 2026-09-05 against the linked package page and the package's registry entry (PyPI, npm,
Maven Central) — a package marked unreleased has no registry entry. The official Python packages now live in the
`open-telemetry/opentelemetry-python-genai` repository; the copies left in
`opentelemetry-python-contrib` only receive security patches. Anything not listed here is
unverified — check the language registry and the contrib repository before promising it.

| Ecosystem | SDK / framework | Package | Docs |
| --- | --- | --- | --- |
| Python | `openai` (and the OpenAI-compatible platforms reached through it) | `opentelemetry-instrumentation-genai-openai` — replaces the deprecated `opentelemetry-instrumentation-openai-v2` (security patches only, breaking changes on migration) | [README](https://github.com/open-telemetry/opentelemetry-python-genai/blob/main/instrumentation/opentelemetry-instrumentation-genai-openai/README.rst) |
| Python | `anthropic` | `opentelemetry-instrumentation-genai-anthropic` | [README](https://github.com/open-telemetry/opentelemetry-python-genai/blob/main/instrumentation/opentelemetry-instrumentation-genai-anthropic/README.rst) |
| Python | `google-genai` (Gemini API) | `opentelemetry-instrumentation-google-genai` | [README](https://github.com/open-telemetry/opentelemetry-python-genai/blob/main/instrumentation/opentelemetry-instrumentation-google-genai/README.rst) |
| Python | `google-cloud-aiplatform` (Vertex AI) | The contrib `opentelemetry-instrumentation-vertexai` is deprecated with no replacement planned; the PyPI project of that name is OpenLLMetry's package | [README](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation-genai/opentelemetry-instrumentation-vertexai/README.rst) |
| Python | `boto3` / `botocore` (Bedrock Runtime) | `opentelemetry-instrumentation-botocore` — its Bedrock Runtime extension covers Converse and ConverseStream for every model, InvokeModel and InvokeModelWithResponseStream only for Titan, Nova and Claude models; `opentelemetry-instrumentation-genai-bedrock` is an unreleased skeleton | [README](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/main/instrumentation/opentelemetry-instrumentation-botocore/README.rst) |
| Python | `langchain` / LangGraph | `opentelemetry-instrumentation-genai-langchain` — hooks LangChain's callback manager; workflow, agent and tool spans | [README](https://github.com/open-telemetry/opentelemetry-python-genai/blob/main/instrumentation/opentelemetry-instrumentation-genai-langchain/README.rst) |
| Python | `openai-agents` | `opentelemetry-instrumentation-genai-openai-agents` | [Repository index](https://github.com/open-telemetry/opentelemetry-python-genai#released-instrumentations) |
| Python | `llama-index-core` | The official `opentelemetry-instrumentation-genai-llama-index` is an unreleased skeleton (agent and tool spans only; model calls left to the provider SDK instrumentation) — use OpenLLMetry's `opentelemetry-instrumentation-llamaindex` or OpenLIT | [README](https://github.com/open-telemetry/opentelemetry-python-genai/blob/main/instrumentation/opentelemetry-instrumentation-genai-llama-index/README.rst) |
| Python | Any provider or framework (OpenAI, Anthropic, Bedrock, Vertex AI, Gemini, LangChain, LangGraph, LlamaIndex, OpenAI Agents, vector DBs) | OpenLLMetry — `traceloop-sdk` (`Traceloop.init()`) or its individual `opentelemetry-instrumentation-<name>` packages; logs prompts and completions **by default**, `TRACELOOP_TRACE_CONTENT=false` disables it | [Getting started](https://traceloop.com/docs/openllmetry/getting-started-python) · [Privacy](https://www.traceloop.com/docs/openllmetry/privacy/traces) |
| Python | Any provider or framework (50+ integrations: LangChain, LlamaIndex, CrewAI, OpenAI Agents, Claude Agent SDK, MCP, vector DBs, ...) | OpenLIT — `openlit` (`openlit.init()`); OpenTelemetry-native, follows the `gen_ai.*` conventions | [Docs](https://docs.openlit.io/) · [README](https://github.com/openlit/openlit#readme) |
| JavaScript | Vercel AI SDK (`ai`) | Built in: install `@ai-sdk/otel` and call `registerTelemetry(new OpenTelemetry())` once; every AI SDK call then emits `gen_ai.*` spans (`invoke_agent {modelId}` root, `gen_ai.usage.*_tokens`, ...). Inputs and outputs are recorded **by default** — `recordInputs: false` / `recordOutputs: false` per call, `isEnabled: false` to opt a call out | [Telemetry](https://ai-sdk.dev/docs/ai-sdk-core/telemetry) |
| JavaScript | `openai` (>=4.19.0 <7) | `@opentelemetry/instrumentation-openai` (js-contrib) | [README](https://github.com/open-telemetry/opentelemetry-js-contrib/blob/main/packages/instrumentation-openai/README.md) |
| JavaScript | `langchain` | The js-contrib `@opentelemetry/instrumentation-langchain` is unreleased (its `package.json` is `private`, npm has no such package) — use OpenLLMetry JS's `@traceloop/instrumentation-langchain` or OpenLIT | [README](https://github.com/open-telemetry/opentelemetry-js-contrib/blob/main/packages/instrumentation-langchain/README.md) |
| JavaScript | Any provider or framework (OpenAI, Azure OpenAI, Anthropic, Cohere, Vertex AI, Bedrock, LangChain, LlamaIndex, vector DBs) | OpenLLMetry JS — `@traceloop/node-server-sdk` or the individual `@traceloop/instrumentation-<name>` packages | [Getting started](https://traceloop.com/docs/openllmetry/getting-started-ts) · [README](https://github.com/traceloop/openllmetry-js#readme) |
| Java | OpenAI Java SDK 1.1+ | `io.opentelemetry.instrumentation:opentelemetry-openai-java-1.1` (an `-alpha` artifact on Maven Central) — wrap the client with `OpenAITelemetry.builder(openTelemetry).build().wrap(client)`; also covered by the Java agent | [README](https://github.com/open-telemetry/opentelemetry-java-instrumentation/blob/main/instrumentation/openai/openai-java-1.1/library/README.md) |

### Detecting GenAI usage

The manifest names that route to a row above (the names the rows were verified with on
2026-09-05) — the presence of one is the signal that a service makes model calls, whatever
its HTTP surface looks like:

- Python (`pyproject.toml`, `requirements*.txt`, `uv.lock`): `openai`, `anthropic`,
  `google-genai`, `google-cloud-aiplatform`, `boto3` with a `bedrock-runtime` client,
  `langchain`, `langgraph`, `llama-index`, `openai-agents`, `traceloop-sdk`, `openlit`.
- JavaScript (`package.json`): `ai` and `@ai-sdk/*`, `openai`, `langchain` and `@langchain/*`,
  `@traceloop/node-server-sdk`.
- Java (`pom.xml`, `build.gradle`): `com.openai:openai-java`.

## Planning notes

A snapshot verified on 2026-09-05 against the pages above; the fetched page always wins.

- **Library first.** Detect the SDK in the dependency manifest, pick its row above, and let
  the library emit the `gen_ai` spans and metrics. Hand-code only what no library covers:
  - **cost** — no convention attribute exists for it; derive it from
    `gen_ai.client.token.usage` (or the span's token attributes) and a price per model kept
    outside the application, or record it under an application namespace;
  - **the agent loop** when the framework has no instrumentation — `invoke_agent` and
    `execute_tool` spans per the agent-spans page, sharing one `gen_ai.conversation.id`.
- Content capture is an open decision of every GenAI plan: the convention's default is off,
  and turning it on is a privacy and volume decision the user takes, not the plan. Two
  libraries in the table invert that default (OpenLLMetry, the Vercel AI SDK) — a plan that
  adopts them names the switch that turns content off, or states that content stays on and
  why.
- Everything here is Development: names move (`gen_ai.system` became
  `gen_ai.provider.name`, `prompt_tokens` / `completion_tokens` became `input_tokens` /
  `output_tokens`), and an instrumentation may emit the convention version it was built
  against rather than the current one — read the version a package declares and the
  attributes it actually sends before writing a query.
- The per-model reading of an observation pivots on `gen_ai.request.model` (what was asked)
  and `gen_ai.response.model` (what answered), split by `gen_ai.operation.name` and
  `gen_ai.provider.name`; the agent reading pivots on `gen_ai.conversation.id`, counting the
  model calls and `execute_tool` spans under each `invoke_agent` (the
  `gen_ai.invoke_agent.inference_calls` and `gen_ai.invoke_agent.tool_calls` histograms when a
  framework emits them).
- A stack ingests `gen_ai.*` attributes like any other attribute; querying them is the
  backend's business — the stack's reference in the observability CLI guides carries the
  query surface, this file only the names.
- The stable attributes the pages reuse (`error.type`, `server.address`, `server.port`,
  `exception.*`) come from the main semantic conventions — open the semantic conventions
  reference for those.
