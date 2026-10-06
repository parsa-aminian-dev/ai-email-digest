# Architecture

The system is designed as a modular pipeline:

1. Email collection
   - Connector adapters fetch new mail from providers such as Gmail.
2. Preprocessing
   - Normalize headers, strip HTML, redact PII, and remove noise.
3. Rule evaluation
   - Deterministic rules assign categories, priorities, and urgency.
4. LLM summarization
   - A model adapter creates concise summaries without exposing unnecessary content.
5. Digest assembly
   - Compute categories, highlights, and action items into a final digest.
6. Storage and retention
   - Persist metadata and filtered content according to configured retention policies.

## Major components

- `src/digest/providers/`: Email provider interfaces and Gmail integration
- `src/digest/preprocessing/`: Redaction and sanitization
- `src/digest/rules/`: Deterministic rule engine
- `src/digest/llm/`: Prompt templates and LLM adapters
- `src/digest/pipeline/`: Orchestration and job scheduling
- `src/digest/storage/`: Repositories, models, retention logic
- `src/digest/config/`: Settings and validation
