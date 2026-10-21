# Architecture

## Generation and refinement

```mermaid
flowchart TD
    U[User request and age] --> I["Intake prompt: validated brief"]
    I --> P["Planner: category arc, techniques, and craft plan"]
    I --> D[Decline with explanation]
    P --> W["Writer prompt: initial story"]
    W --> R[Review current draft]
    R --> M[Code metrics]
    R --> S["Safety: verdict and concise reason"]
    R --> Q["Quality: six ratings and grounded craft evidence"]
    M --> C[Deterministic controller]
    S --> C
    Q --> C
    C -->|Pass all gates| O[Accepted story and inspection page]
    C -->|Deficits and budget remaining| E["Editor prompt: paragraph replacements"]
    E --> V[Review candidate with same checks]
    V --> G[Compare candidate with incumbent]
    G -->|Measured regression| B[Rollback and stop]
    G -->|Improvement| C
    B --> F[Return eligible incumbent or no story]
    C -->|Budget or plateau| F
```

`StoryEngine.run` controls the workflow. Safety and quality run concurrently by default, without seeing each other's verdict, and join before acceptance. Each LLM call uses the required model. JSON mode supplies syntax, Pydantic validates the contract, and `review_validation.py` grounds quality citations against the story. One repair is permitted by default. Incomplete reviews cannot pass acceptance.

## User feedback

```mermaid
flowchart TD
    A[Accepted story] --> U[User change]
    U --> I[Rebuild brief with feedback ledger]
    I --> R[Reevaluate incumbent against new brief]
    R --> E[Patch requested change]
    E --> V[Review and compare under new brief]
    V -->|Accepted| N[Commit new session story]
    V -->|Failed| K[Keep previous session state]
    N --> U
```

The ledger is bounded. New age/length requests are interpreted by intake. The old story's scores are invalid for the new brief and are recomputed. Session history is committed only after acceptance. A requested change may still fail; if the reevaluated incumbent passes, it can survive an operational edit failure with a visible warning.

## Boundaries

- Each stage receives the fields it needs; prompts and stories are data, never executable instructions or tool calls.
- Local code controls retries, iteration limits, retention, output release and artifacts.
- Concurrency is limited to the two review calls for the current draft.
- Budgets count actual transport attempts, including retries and JSON repair, using a lock shared by concurrent reviewers.
- No result is released when its required review is missing. A previously eligible incumbent can survive a later operational failure only within its current evaluated request.
