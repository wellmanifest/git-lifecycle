# Git lifecycle logic flow

```mermaid
sequenceDiagram
    participant M as Model / caller
    participant P as GBNF parser
    participant V as Schema + policy gate
    participant C as URI Process / CQRS controller
    participant G as Git repository
    participant R as Receipt store
    M->>P: typed transition request
    P->>V: closed AST
    V->>V: resolve state, authorization and opaque refs
    V->>C: one authorized command
    C->>G: bounded Git effect
    G-->>C: observed state and HEAD
    C->>R: redacted idempotent receipt
    R-->>M: receipt reference
```

For a new repository the first effect is `seed-baseline`. The gate requires an
unborn `HEAD`, no implementation, no remote, a published governance lock, an
exact seed-profile allowlist and a passing secret scan. The controller creates
one local commit, reads the resulting SHA and uses it as the delivery base.
Every implementation edit happens afterwards.

State mismatch, an unknown reference, repeated idempotency key with different
content, foreign dirty data or any request field outside the schema rejects
before a Git effect. Trusted merge and release evidence is resolved by protected
infrastructure; it cannot be created by a model request.
