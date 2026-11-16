# Agentic Task Manager

An enterprise-grade, privacy-first Agentic Task Management Platform combining **FastAPI**, **React 18**, **MongoDB Atlas**, **LangChain**, **Google Gemini & OpenAI**, **Model Context Protocol (MCP)**, **Microsoft Presidio**, and **Trello**.

The platform provides intelligent conversational task orchestration with **guaranteed zero Personally Identifiable Information (PII) leakage** to external LLMs, dynamic tool discovery across hundreds of tools, and a strict **Human-in-the-Loop (HITL) two-phase approval workflow** for all mutating actions.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                        React 18 + Vite Frontend                        │
│             (Conversational Chat + Live Trello Approval Cards)         │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ HTTP / REST API
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          FastAPI Backend                               │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 1. Microsoft Presidio Engine + spaCy (Local PII Masking)         │  │
│  │    • Indian PAN, Aadhaar, Passport, Phone, Email, Person         │  │
│  │    • Deterministic In-Memory Placeholders: [PERSON_1], etc.      │  │
│  │    • Request-Scoped RAM Mapping (Zero MongoDB / Log persistence) │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     ▼                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 2. Hybrid Tool Discovery (Keyword + Weighted Semantic Ranker)    │  │
│  │    • Dynamically selects top-K tools from MongoDB Tool Registry  │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     ▼                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 3. LangChain Outbound Boundary Inspection (Fail-Closed)          │  │
│  │    • Validates complete serialized prompt against PII leakage    │  │
│  │    • Cross-sanitizes multi-turn MongoDB conversation history     │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     ▼                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 4. External LLM Provider (Sanitized Prompts Only)                │  │
│  │    • Primary: Google Gemini (gemini-3.5-flash-lite via LangChain)│  │
│  │    • Fallback: OpenAI (gpt-4o-mini via LangChain)                │  │
│  │    • Offline: Deterministic Heuristic Pattern Interpreter        │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     ▼                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 5. Local In-Memory Restoration Engine                            │  │
│  │    • Replaces [PERSON_1] -> "Sourabh Mishra" in backend RAM      │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     ▼                                  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 6. Human-in-the-Loop (HITL) Two-Phase Approval Engine            │  │
│  │    • Generates PENDING Action Draft for human confirmation       │  │
│  └──────────────────────────────────┬───────────────────────────────┘  │
│                                     ▼ (Upon Human Confirmation)        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ 7. Model Context Protocol (MCP) Execution Engine                 │  │
│  │    • Trello MCP Server & Tool Adapter via Async HTTPX            │  │
│  │    • Live Mutation: Create, Move, Assign Member, Delete Card     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Core Technologies, Models & Libraries

### 1. AI & Machine Learning Models
* **Google Gemini (`gemini-3.5-flash-lite` / `gemini-1.5-flash`)**: Primary cloud LLM for structured intent parsing and parameter extraction via LangChain `ChatGoogleGenerativeAI`.
* **OpenAI (`gpt-4o-mini`)**: Fallback cloud LLM provider via LangChain `ChatOpenAI`.
* **spaCy (`en_core_web_sm`)**: Small local Named Entity Recognition (NER) model running on CPU inside Microsoft Presidio to detect entities locally.

### 2. Frameworks & Foundations
* **Backend**: Python 3.10+, **FastAPI**, **Pydantic v2**, **Pydantic Settings**, **Uvicorn**, **Motor** (Async MongoDB Driver).
* **AI Orchestration**: **LangChain** (`langchain-core`, `langchain-google-genai`, `langchain-openai`).
* **Privacy & Security**: **Microsoft Presidio** (`presidio-analyzer`, `presidio-anonymizer`) + custom regex recognizers for Indian identities.
* **Tool Standard**: **Model Context Protocol (MCP)** (`mcp` SDK) with streamable HTTP and stdio transports.
* **Frontend**: **React 18**, **Vite**, **TypeScript**, **Tailwind CSS**, **Lucide React**, **Axios**.
* **Authentication**: **Argon2** password hashing (`argon2-cffi`), **JWT** access tokens (`pyjwt`), single-use rotating refresh tokens in MongoDB Atlas.

---

## PII Masking & Privacy Architecture

The platform enforces strict bank-grade privacy invariants before any prompt reaches an external provider:

1. **Local Detection & Deterministic Placeholders**:
   * Analyzes incoming commands with Microsoft Presidio + Custom Indian Recognizers (`IN_PAN`, `IN_AADHAAR`, `IN_PASSPORT`, `IN_PHONE`).
   * Substitutes sensitive values with deterministic indexed placeholders (`[PERSON_1]`, `[EMAIL_ADDRESS_1]`, `[PHONE_NUMBER_1]`, `[IN_PAN_1]`).
   * Repeated entities receive the exact same placeholder within the request.
2. **Request-Scoped In-Memory Mapping**:
   * The mapping table (`{"[PERSON_1]": "Sourabh Mishra"}`) is stored **strictly in RAM** inside the request lifecycle.
   * **Zero Database Persistence**: Mappings are never stored in MongoDB or disk.
   * **Zero Log Leakage**: Raw values and mapping dictionaries are strictly excluded from logs.
3. **Multi-Turn History Cross-Sanitization**:
   * When pulling prior chat history from MongoDB, history is sanitized using accumulated request mappings (case-insensitively with regex word boundaries `\b`).
   * Prevents prior turns (e.g., lowercase names in history) from leaking into the prompt.
4. **Provider Boundary Security Verification**:
   * Right before `ainvoke()` in `GoogleGenAIProvider` and `OpenAIProvider`, the complete serialized prompt is inspected.
   * If any unmasked PII is detected, the request immediately blocks (**Fail-Closed**) with `PIIMaskingError`.
5. **Local Restoration**:
   * When the LLM returns structured parameters referencing placeholders, `restore_dict()` recursively swaps placeholders back to real values in memory before presenting the preview to the user.

---

## Dynamic Tool Registry & MCP Architecture

### 1. Dynamic Tool Registry (`app/tool_registry/`)
Supports scaling from 10 to 500+ tools without hardcoding tools into the AI agent:
* **MongoDB Storage**: Tools are stored in the `tools` collection with unique indexes on `tool_id`.
* **Rich Metadata**: Each tool defines `tool_id`, `name`, `description`, `category`, `keywords`, `synonyms`, `capabilities`, `input_schema` (JSON Schema), and `approval_required`.

### 2. Hybrid Tool Discovery Engine (`app/tool_discovery/`)
* **Metadata Filter**: Drops disabled tools and enforces Role-Based Access Control (`ADMIN`, `MANAGER`, `EMPLOYEE`).
* **Weighted Keyword Matcher**: Tokenizes query and computes relevance across synonyms (4.0x), names (3.0x), keywords (2.5x), capabilities (2.0x), and descriptions (0.8x).
* **Top-K Selection**: Injects only the top 5 relevant tool definitions into the LLM prompt, keeping prompt tokens small and context clean.

### 3. Model Context Protocol (MCP) Server (`app/mcp_server/`)
* Standardized tool server exposing vetted Trello tools:
  * `trello_create_card`: Create task card with title, description, due date, list, and assign member.
  * `trello_update_card`: Update existing card title, description, due date, or assign new member.
  * `trello_move_card`: Move card between columns (`To Do`, `Doing`, `In-Review`, `Testing`, `Done`).
  * `trello_delete_card`: Permanently delete card (`DELETE /1/cards/{id}`) with archive fallback.
  * `trello_search_cards` & `trello_list_cards`: Query live cards by keyword or list name.
  * `trello_create_list`: Create new columns on the board.

---

## Human-in-the-Loop (HITL) Two-Phase Approval Workflow

To prevent unintended mutations on production boards:

1. **Phase 1: Draft Creation (Intent Stage)**
   * When the AI interprets a mutating command (`create_card`, `move_card`, `update_card`, `delete_card`), it creates a `PENDING` action document in MongoDB Atlas with a unique ID (`ACT-PREV-XXXXXXXX`) and a 30-minute TTL.
   * Returns a structured preview card in the chat UI with extracted parameters.
   * **Zero live mutations occur during this phase.**
2. **Phase 2: Execution (Approval Stage)**
   * The user clicks **Confirm** (or types `"confirm"` / `"yes"` / `"proceed"`).
   * The backend validates the action ID, verifies state is `PENDING`, and triggers the vetted MCP tool executor.
   * Live Trello mutation executes and returns the live card URL and execution result.
   * The user can also **Edit** parameters or **Cancel** the draft at any time.

---

## Project Structure

```text
agentic-task-manager/
├── backend/
│   ├── app/
│   │   ├── ai/                        # LangChain Multi-Provider & Heuristic AI Service
│   │   │   ├── llm_provider.py        # GoogleGenAIProvider & OpenAIProvider boundary
│   │   │   ├── prompts.py             # Structured interpretation prompt templates
│   │   │   ├── provider_factory.py    # Runtime provider factory
│   │   │   ├── schemas.py             # Pydantic structured output models
│   │   │   └── service.py             # AIService.interpret_command pipeline
│   │   ├── approvals/                 # Two-phase human approval engine
│   │   ├── chat/                      # MongoDB conversation history repository
│   │   ├── core/                      # Config, logging, security, and exceptions
│   │   │   ├── config.py              # Pydantic Settings & environment validation
│   │   │   └── logging.py             # SensitiveDataFilter (Trello key/token redaction)
│   │   ├── integrations/
│   │   │   ├── gemini/                # Google GenAI client & schemas
│   │   │   └── trello/                # Async REST client for Trello API v1
│   │   ├── mcp_server/                # Model Context Protocol tools & server
│   │   ├── privacy/                   # Microsoft Presidio PII Masking Pipeline
│   │   │   ├── recognizers/           # Indian PAN, Aadhaar, Passport, Phone recognizers
│   │   │   ├── schemas.py             # DetectedEntity, PIIMaskResult schemas
│   │   │   ├── service.py             # PIIService (Masking & Local Restoration)
│   │   │   └── terminal_logger.py     # Privacy-safe terminal logging & boundary auditor
│   │   ├── tool_discovery/            # Hybrid keyword + semantic search engine
│   │   ├── tool_executor/             # Vetted tool registry & MCP execution adapters
│   │   ├── tool_registry/             # Dynamic MongoDB tool definitions & seeders
│   │   └── main.py                    # FastAPI application entrypoint & lifespan
│   ├── scripts/
│   │   └── demo_pii_masking.py        # Safe 10-stage terminal demonstration script
│   └── tests/                         # Pytest test suite (143 unit & integration tests)
├── frontend/
│   ├── src/
│   │   ├── components/                # Chat, Approval Cards, Task Preview, Board View
│   │   ├── context/                   # Auth & WebSocket / State providers
│   │   └── App.tsx                    # Main interactive UI
│   └── package.json
├── docker-compose.yml                 # Multi-service Docker configuration
└── README.md                          # Documentation
```

---

## Installation & Setup Guide

### Prerequisites
* Python 3.10+
* Node.js 18+ and npm
* MongoDB Atlas cluster or local MongoDB 7.0+ instance
* Trello Account with API Key and Token ([Trello Developer Portal](https://trello.com/power-ups/admin))
* Google Gemini API Key ([Google AI Studio](https://aistudio.google.com/)) or OpenAI API Key

---

### Step 1: Clone and Configure Environment

```bash
cd agentic-task-manager
cp .env.example .env
```

Edit your `.env` file:

```env
# Application Settings
APP_NAME="Agentic Task Manager"
APP_ENV=development
DEBUG=true
PORT=8000
FRONTEND_URL=http://localhost:3000

# MongoDB Configuration
MONGODB_URL=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/agentic_task_manager?retryWrites=true&w=majority

# JWT Authentication
JWT_SECRET_KEY=your-super-secure-random-jwt-key-min-32-chars-long
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# Bootstrap Admin User (Auto-created on first startup)
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=AdminSecurePassword123!
BOOTSTRAP_ADMIN_NAME="System Administrator"

# LLM Configuration (LangChain)
LLM_PROVIDER=google                     # "google" or "openai"
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-3.5-flash-lite
OPENAI_API_KEY=your-openai-api-key     # Optional fallback

# PII Protection & Logging
PII_MASKING_ENABLED=true
PII_MASKING_THRESHOLD=0.5
PII_TERMINAL_LOGGING=true              # Displays verification stages in Uvicorn terminal

# Trello Integration
TRELLO_API_KEY=your-trello-api-key
TRELLO_TOKEN=your-trello-user-token
TRELLO_BOARD_ID=your-trello-board-id
```

---

### Step 2: Backend Setup

```bash
# Navigate to backend
cd backend

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Download required spaCy NLP model for Presidio
python3 -m spacy download en_core_web_sm

# Start FastAPI server with Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend starts at `http://localhost:8000`. Swagger documentation is available at `http://localhost:8000/docs`.

---

### Step 3: Frontend Setup

```bash
# Navigate to frontend in a new terminal
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```

The React frontend starts at `http://localhost:3000`.

---

## Verifying the PII Masking Pipeline

### 1. Interactive Terminal Demonstration
Run the deterministic synthetic data demonstration script:

```bash
cd backend
python3 scripts/demo_pii_masking.py
```

This runs through 10 distinct security stages:
* **Stage 1**: Synthetic command input.
* **Stage 2**: Presidio PII entity detection and confidence scores.
* **Stage 3**: Deterministic masking and placeholder generation.
* **Stage 4**: Outbound request boundary interception.
* **Stage 5**: Security assertions (negative leak verification).
* **Stage 6**: Mocked response parsing.
* **Stage 7**: Local parameter restoration.
* **Stage 8**: Multi-turn conversation history sanitization.
* **Stage 9**: Fail-closed analyzer engine crash simulation.
* **Stage 10**: Executive audit summary.

### 2. Automated Test Suite
Run the 143 automated backend tests:

```bash
cd backend
pytest
```

---

## Natural Language Commands Reference

| Intent | Example User Prompt in Chat UI | Target Tool |
| :--- | :--- | :--- |
| **Create Card** | `"Create a task card Full Stack due date 21 November 2026 and add member Sourabh Mishra"` | `trello_create_card` |
| **Assign Member** | `"On Register Page card add member Sourabh Mishra"` | `trello_update_card` |
| **Move Card** | `"Move backend card to Testing list"` | `trello_move_card` |
| **Delete Card** | `"Delete card Person 1"` | `trello_delete_card` |
| **List Cards** | `"Show cards in the To Do list"` | `trello_search_cards` |
| **Workload Report** | `"Show employee workload analytics"` | `report_get_workload` |
| **Confirm Action** | `"Confirm"` or `"Yes, proceed"` | `confirm_action` |
| **Cancel Action** | `"Cancel"` or `"Reject"` | `cancel_action` |

---

## Security Invariants Checklist

* [x] **Zero Cloud PII Leakage**: Raw personal data (names, emails, phones, PAN, Aadhaar) never reaches Google Gemini or OpenAI.
* [x] **No In-Database Mapping Storage**: Placeholder mapping dictionaries exist only in temporary RAM during request execution.
* [x] **Fail-Closed Execution**: If PII masking or security inspection fails, outbound LLM requests are blocked immediately.
* [x] **Redacted Terminal Logs**: HTTP request logs scrub Trello credentials (`?key=[REDACTED]&token=[REDACTED]`) and bearer tokens.
* [x] **Two-Phase Human Confirmation**: Destructive or mutating board actions require explicit user approval before execution.

---

## License

Enterprise Proprietary & Confidential. All rights reserved.
