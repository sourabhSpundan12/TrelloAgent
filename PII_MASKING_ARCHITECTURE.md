# PII Detection and Masking Architecture

## 1. Overview and Security Architecture

The **Agentic Task Manager** incorporates a zero-trust privacy and Personally Identifiable Information (PII) protection layer. This layer ensures that sensitive user and organizational data is identified and masked **before** any conversational prompt, history, or context is transmitted to external Large Language Model (LLM) providers (such as Google Gemini or OpenAI via LangChain).

```
                      [ User Input / Task Command ]
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │       PIIService Layer        │
                   │   (Presidio + spaCy NER)      │
                   └───────────────┬───────────────┘
                                   │
               Detects PII & generates deterministic tokens
                    (e.g., [PERSON_1], [EMAIL_1])
                                   │
         ┌─────────────────────────┴────────────────────────┐
         │                                                  │
         ▼                                                  ▼
┌─────────────────────────┐                      ┌───────────────────────────┐
│ External LLM Boundary   │                      │ Request-Scoped Isolation  │
│  (Gemini / OpenAI via   │                      │ Mapping:                  │
│       LangChain)        │                      │ {"[PERSON_1]": "Rahul V"} │
│                         │                      │ (Never sent to LLM,       │
│ Receives ONLY Sanitized │                      │  never persisted globally)│
│ Prompts & Placeholders  │                      └─────────────┬─────────────┘
└───────────┬─────────────┘                                    │
            │ Returns structured intent                        │
            ▼                                                  │
┌─────────────────────────┐                                    │
│   GeminiIntentOutput    │                                    │
│ (parameters contain     │                                    │
│    placeholders)        │                                    │
└───────────┬─────────────┘                                    │
            │                                                  │
            └──────────────────────┬───────────────────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │  Local Parameter Restoration  │
                   │ (Replaces placeholders using  │
                   │   local request map only)     │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │ Human-in-the-Loop Action Card │
                   │  & Confirmed MCP Trello Exec  │
                   └───────────────────────────────┘
```

---

## 2. Core Components and Frameworks

- **Microsoft Presidio Analyzer (`presidio-analyzer`)**: Detects standard and custom PII entities via rule-based patterns, regular expressions, and context keywords.
- **Microsoft Presidio Anonymizer (`presidio-anonymizer`)**: Anonymizes text using configurable operators.
- **spaCy NLP (`en_core_web_sm`)**: Provides named-entity recognition (NER) for `PERSON` and `LOCATION` entities, loaded offline via a local `NlpEngineProvider`.
- **Custom Indian Recognizers**: Custom pattern recognizers for Indian identities and phone numbers.
- **LangChain Unified AIService Integration**: Outbound prompt sanitization and local parameter restoration.

---

## 3. Supported PII Entities

### Standard Entities
| Entity Type | Description | Pattern / Extraction Mechanism |
| :--- | :--- | :--- |
| `PERSON` | Individual names | spaCy NER (`PERSON` label) with smart action verb & tech vocabulary filters |
| `EMAIL_ADDRESS` | Email addresses | RFC-compliant email regex + offline domain parser |
| `PHONE_NUMBER` | Phone numbers | International format + custom Indian mobile recognizers |
| `LOCATION` | Cities, regions, countries | spaCy NER (`GPE` / `LOC` labels) |
| `IP_ADDRESS` | IPv4 and IPv6 addresses | Presidio built-in IP recognizer |
| `URL` | Web and internal links | Presidio standard URL patterns |
| `CREDIT_CARD` | Credit card numbers | Luhn checksum verification |
| `IBAN_CODE` | International bank account numbers | Presidio IBAN recognizer |
| `US_SSN` | US Social Security Numbers | SSA-compliant format (excluding dummy test sequences) |

### Custom Indian Recognizers
| Entity Type | Pattern & Rules | Context Requirements & False-Positive Prevention |
| :--- | :--- | :--- |
| `PHONE_NUMBER` (Indian) | `(?:\+91[\-\s]?\|91[\-\s])[6-9]\d{9}` or bare `\b[6-9]\d{9}\b` | Bare 10-digit numbers require context keywords (`call`, `mobile`, `phone`, `whatsapp`, `contact`) to exceed threshold (0.5), preventing ordinary 10-digit database IDs or task metrics from false-positive masking. |
| `IN_PAN` | `\b[A-Z]{5}[0-9]{4}[A-Z]\b` | Boosted by keywords (`pan`, `pan card`, `income tax`, `taxpayer`). |
| `IN_AADHAAR` | `(?<![\d\-])[2-9]\d{3}[\s\-]\d{4}[\s\-]\d{4}(?![\-\d])` | 12 digits, formatted 4-4-4 or continuous with context keywords (`aadhaar`, `uidai`, `identity card`). Negative lookarounds prevent false matches on 16-digit credit cards. |
| `IN_PASSPORT` | `\b[A-Z][1-9]\d{6}\b` (8 chars) | Indian passport structure boosted by keywords (`passport`, `travel document`, `visa`). |

---

## 4. Privacy & Security Guarantees

1. **Request-Scoped Isolation**:
   - Every execution of `PIIService.mask_text()` instantiates a distinct, isolated `PIIMaskResult`.
   - The mapping (e.g. `{"[PERSON_1]": "Rahul Sharma"}`) exists **only** in the local invocation stack of `AIService.interpret_command`.
   - Mappings are never stored in global variables, class singletons, or shared caches across async requests.
2. **Zero Outbound Exposure**:
   - Neither the original PII nor the mapping dictionary is ever included in the prompt payload sent to Google Gemini or OpenAI.
   - PII is never logged in application logs.
3. **Fail-Closed Architecture**:
   - If PII detection or anonymization encounters any failure (e.g., analyzer error, missing model, unexpected exception), the system **fails closed**: it raises `PIIMaskingError` (HTTP 500, code `PII_MASKING_FAILED`) and blocks the LLM call completely. It never silently passes unmasked data.
4. **Deterministic Deduplication**:
   - If the same sensitive value appears multiple times within a prompt (e.g. "Assign card to Rahul Sharma and notify Rahul Sharma"), it receives the same placeholder (`[PERSON_1]`) throughout the prompt.
5. **Preservation of Task Management Terms**:
   - Standard task operations (such as "Move Login API card to IN_PROGRESS") preserve technical keywords (`api`, `login`, `card`, `backend`) and action verbs (`move`, `create`, `list`) without false-positive tagging as person names.
   - Relative deadlines (`tomorrow`, `next week`, `Friday`) are excluded from `DATE_TIME` masking so that task scheduling functions normally.

---

## 5. Configuration Options

Configured via environment variables in `.env`:

```bash
# Enable or disable PII masking (default: true)
PII_MASKING_ENABLED=true

# Provider implementation (default: presidio)
PII_MASKING_PROVIDER=presidio

# Minimum confidence threshold for entity acceptance (default: 0.5)
PII_MASKING_THRESHOLD=0.5

# Configurable list of entities to detect
PII_MASKING_ENTITIES=["PERSON","EMAIL_ADDRESS","PHONE_NUMBER","LOCATION","IP_ADDRESS","URL","CREDIT_CARD","IBAN_CODE","US_SSN","IN_PAN","IN_AADHAAR","IN_PASSPORT"]
```

---

## 6. End-to-End Walkthrough Example

### User Input
```text
"Create a task to onboard Rahul Sharma, email him at rahul.sharma@example.com and call on mobile 9876543210. His PAN is ABCDE1234F."
```

### 1. PII Detection & Sanitization
- Detected:
  - `Rahul Sharma` -> `[PERSON_1]`
  - `rahul.sharma@example.com` -> `[EMAIL_ADDRESS_1]`
  - `9876543210` (with `mobile` context) -> `[PHONE_NUMBER_1]`
  - `ABCDE1234F` -> `[IN_PAN_1]`
- Masked Text:
  ```text
  "Create a task to onboard [PERSON_1], email him at [EMAIL_ADDRESS_1] and call on mobile [PHONE_NUMBER_1]. His PAN is [IN_PAN_1]."
  ```

### 2. LLM Prompt & Processing (Google Gemini / OpenAI via LangChain)
- The external LLM receives the prompt containing **only** the masked text.
- The LLM responds with structured parameters:
  ```json
  {
    "intent": "create_card",
    "entity": "card",
    "parameters": {
      "name": "Onboard [PERSON_1]",
      "desc": "Contact: [EMAIL_ADDRESS_1], Phone: [PHONE_NUMBER_1], PAN: [IN_PAN_1]"
    }
  }
  ```

### 3. Local Parameter Restoration
- `AIService` locally restores parameters using the isolated request mapping:
  ```json
  {
    "name": "Onboard Rahul Sharma",
    "desc": "Contact: rahul.sharma@example.com, Phone: 9876543210, PAN: ABCDE1234F"
  }
  ```
- Restored parameters are presented to the user in the preview card for explicit confirmation before any Trello card creation occurs.

---

## 7. Verification and Testing

Run unit and integration tests with pytest:

```bash
# Run PII unit test suite
pytest tests/unit/test_pii_service.py -v

# Run entire backend test suite
pytest -v
```

