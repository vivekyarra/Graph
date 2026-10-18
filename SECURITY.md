# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 0.1.x | :white_check_mark: |

---

## Security Architecture & Invariants

MAELIN is built from the ground up with defensive security principles:

1. **Authenticated Operator Boundary**:
   * Remote production deployments enforce `MAELIN_OPERATOR_TOKEN`.
   * Graph read/write endpoints require `x-maelin-operator-token` headers evaluated via constant-time comparison (`hmac.compare_digest`) to prevent timing side-channel attacks.
   * Public evaluation deployments (`MAELIN_PUBLIC_DEMO=1`) grant tokenless inspection strictly to isolated synthetic demo tenants (`alpha`, `beta`). Custom tenant creation or topology imports always require operator tokens.

2. **Strict MCP Isolation for LLMs**:
   * LLMs cannot execute raw Cypher queries, modify graph structures directly, or interact with underlying infrastructure.
   * Agent operations are strictly restricted to typed, read-only Model Context Protocol (MCP) tool invocations.

3. **Tenant Graph Namespace Isolation**:
   * All database queries scope dynamically to `maelin_{tenant}_*` with strict alphanumeric input validation (`^[a-z][a-z0-9_-]{0,31}$`).
   * No query can traverse or join across different tenant namespaces.

4. **Disposable Clone Execution**:
   * All remediation simulations execute on temporary database clones generated via `Graph.copy()` with unique randomized IDs (`maelin_{tenant}_sim_{uuid}`).
   * Clones are cleaned up immediately in `try...finally` blocks, ensuring zero mutation of persistent operational data.

---

## Reporting a Vulnerability

If you discover a security vulnerability within MAELIN, please do not file a public issue. Instead, report it privately via email:

* **Contact**: `kittusontineni@gmail.com`
* **Subject**: `[SECURITY VULNERABILITY] MAELIN - <Brief Description>`

Please include:
- A description of the vulnerability and its potential impact.
- Step-by-step reproduction instructions or a minimal proof-of-concept.
- Any proposed mitigations or patches.

We acknowledge receipt of reports within 24 hours and aim to coordinate a resolution within 7 business days.
