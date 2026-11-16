# LangChain Migration & Provider-Agnostic LLM Architecture Report

## 1. Executive Summary
The **Agentic Task Manager** AI interpretation pipeline has been migrated from direct Google Gemini SDK calls (`google-genai` / `genai.Client`) to **LangChain** with a **Provider-Agnostic LLM Architecture**.

The system now supports runtime and configuration-based switching between multiple LLM providers (including **Google Gemini** as the default and **OpenAI**) while strictly preserving:
- All human-in-the-loop approval safeguards and SHA-256 payload integrity hashing.
- Dynamic tool discovery and the official Model Context Protocol (MCP) Trello tool execution pipeline.
- Persistent conversational history in MongoDB Atlas.
- Full backwards compatibility for existing imports, client adapters, and API endpoints (`POST /api/v1/ai/interpret`).
- **100% test pass rate**: 112 passing backend unit and integration tests (12 new tests added for the provider architecture).
- **Verified live execution**: Verified live structured output extraction using LangChain's `ChatGoogleGenerativeAI` with model `gemini-3.5-flash-lite`.

---

## 2. Architecture Overview

### Core Abstractions (`backend/app/ai/`)
The new centralized AI provider subsystem is located in `backend/app/ai/`:

1. **`model_config.py`**:
   - `LLMProviderType`: Enum supporting `GOOGLE` and `OPENAI`.
   - `ProviderConfig`: Typed configuration class reading provider settings (`LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY`, `OPENAI_API_KEY`, `LLM_TEMPERATURE`, `LLM_TIMEOUT`, `LLM_MAX_TOKENS`).
2. **`llm_provider.py`**:
   - `BaseLLMProvider`: Abstract base class defining `is_configured()`, `generate_text()`, and `generate_structured(prompt, schema_cls)`.
   - `GoogleGenAIProvider`: Implements `ChatGoogleGenerativeAI` from `langchain-google-genai`. Uses LangChain's `.with_structured_output()` to guarantee structured Pydantic output.
   - `OpenAIProvider`: Implements `ChatOpenAI` from `langchain-openai`. Uses `.with_structured_output()` for schema validation.
   - `LLMConfigurationError` and `LLMExecutionError`: Specialized domain exceptions.
3. **`provider_factory.py`**:
   - `LLMProviderFactory`: Registry-based factory that instantiates provider classes based on provider name or configuration.
   - Supports runtime registration of new providers.
4. **`prompts.py`**:
   - Defines system instructions, dynamic tool schema context serialization, and LangChain `ChatPromptTemplate` integration.
5. **`schemas.py`**:
   - Defines provider-agnostic aliases (`IntentOutput = GeminiIntentOutput`) and exports `AIInterpretRequest` and `AIInterpretResponse`.
6. **`service.py` (`AIService`)**:
   - Primary service orchestrating intent interpretation via LangChain.
   - Implements `interpret_command(command, discovered_tools)`.
   - Dynamically validates suggested tools against discovered tools.
   - Retains deterministic fallback interpreter for offline environments and automated test suites.
   - Provides `switch_provider(provider_type)` for dynamic runtime switching.

---

## 3. Backwards Compatibility & Integration Adapter

To ensure zero regressions across existing code and test suites:
- [`backend/app/integrations/gemini/service.py`](file:///home/pulse06/Desktop/Agentic_task/agentic-task-manager/backend/app/integrations/gemini/service.py) acts as an adapter delegating to `AIService`.
- Existing unit tests that instantiate `GeminiService(client=mock_client)` continue to pass seamlessly without modifications to existing test harnesses.
- [`backend/app/api/v1/endpoints/ai.py`](file:///home/pulse06/Desktop/Agentic_task/agentic-task-manager/backend/app/api/v1/endpoints/ai.py) seamlessly routes requests through the LangChain provider pipeline without API contract modifications.

---

## 4. Provider Configuration

The environment configuration in [`backend/app/core/config.py`](file:///home/pulse06/Desktop/Agentic_task/agentic-task-manager/backend/app/core/config.py) and [`backend/.env.example`](file:///home/pulse06/Desktop/Agentic_task/agentic-task-manager/backend/.env.example) now supports:

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `google` | Active LLM provider (`google` or `openai`) |
| `LLM_MODEL` | `gemini-3.5-flash-lite` | Active model identifier (or `gpt-4o-mini` when using OpenAI) |
| `GEMINI_API_KEY` | *(Set in .env)* | Google Gemini API Key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Backwards-compatible model fallback |
| `OPENAI_API_KEY` | *(Optional)* | OpenAI API Key |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `LLM_TIMEOUT` | `60` | Request timeout in seconds |
| `LLM_MAX_TOKENS` | `None` | Optional token generation limit |

### Provider Switching Example:
To switch the application to OpenAI:
```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

---

## 5. Verification Evidence

### Automated Backend Tests
```
============================= test session starts ==============================
platform linux -- Python 3.10.12, pytest-9.2.0, pluggy-1.7.0
rootdir: /home/pulse06/Desktop/Agentic_task/agentic-task-manager/backend
configfile: pytest.ini
plugins: asyncio-1.4.1.post1, anyio-4.16.0, langsmith-0.14.17
asyncio: mode=auto, debug=False
collected 112 items

tests/integration/test_ai_interpret_api.py .
tests/integration/test_approval_api.py ...
tests/integration/test_auth.py ...
tests/integration/test_auth_flow_verification.py .
tests/integration/test_health.py .....
tests/integration/test_mcp_api.py ..
tests/integration/test_phase7a_conversational_agent.py ....
tests/integration/test_tools_api.py .
tests/integration/test_trello_mcp_integration.py ..
tests/integration/test_users.py .
tests/test_config.py ...
tests/test_db_lifecycle.py .
tests/test_health.py ...
tests/unit/test_approval_service.py .........
tests/unit/test_config.py ..
tests/unit/test_exceptions.py .......
tests/unit/test_gemini_service.py ......
tests/unit/test_llm_provider.py ............
tests/unit/test_mcp_client.py .....
tests/unit/test_mcp_server.py ....
tests/unit/test_security.py ......
tests/unit/test_tool_discovery.py .....
tests/unit/test_tool_executor.py .
tests/unit/test_tool_registry.py ....
tests/unit/test_trello_client.py .............
tests/unit/test_trello_mcp_tools.py .........

============================= 112 passed in 8.28s ==============================
```

### Live LangChain Gemini Invocation
```python
# Live execution via LangChain ChatGoogleGenerativeAI:
Provider: google
Model: gemini-3.5-flash-lite
Live LangChain Output: {
    'intent': 'create_card',
    'entity': 'card',
    'parameters': {'name': 'Verify LangChain Live', 'list': 'To Do'},
    'suggested_tool_id': 'trello_create_card',
    'requires_clarification': False,
    'clarification_message': None,
    'confidence': 1.0
}
```

### Frontend Production Build
```
> agentic-task-manager-frontend@1.0.0 build
> tsc && vite build

dist/index.html                   0.85 kB │ gzip:   0.48 kB
dist/assets/index-Bw7v4_SZ.css   40.74 kB │ gzip:   7.04 kB
dist/assets/index-DAq8Q15c.js   364.43 kB │ gzip: 101.16 kB
✓ built in 7.10s
```

---

## 6. Summary of Files Changed & Created

| Path | Status | Purpose |
|---|---|---|
| `backend/app/ai/__init__.py` | Created | Central package exports for AI subsystem |
| `backend/app/ai/model_config.py` | Created | Provider config & settings loader |
| `backend/app/ai/llm_provider.py` | Created | BaseLLMProvider, GoogleGenAIProvider, OpenAIProvider |
| `backend/app/ai/provider_factory.py` | Created | Factory for provider instantiation & registry |
| `backend/app/ai/prompts.py` | Created | Prompt definitions & LangChain ChatPromptTemplate |
| `backend/app/ai/schemas.py` | Created | Provider-agnostic intent and request/response schemas |
| `backend/app/ai/service.py` | Created | Unified AIService with structured output & fallback |
| `backend/tests/unit/test_llm_provider.py` | Created | 12 unit tests for LangChain provider architecture |
| `backend/app/integrations/gemini/service.py` | Modified | Backwards-compatible adapter delegating to AIService |
| `backend/app/core/config.py` | Modified | LLM provider settings (`LLM_PROVIDER`, `LLM_MODEL`, etc.) |
| `backend/requirements.txt` | Modified | Added LangChain dependencies |
| `backend/.env.example` | Modified | Documented provider settings template |
| `backend/tests/conftest.py` | Modified | Clean test isolation for LLM configurations |

