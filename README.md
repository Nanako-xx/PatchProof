# PatchProof

PatchProof is a Python CLI debugging agent that proposes verified patch suggestions.

It reproduces a pytest failure, investigates with a bounded read-only agent, generates a unified diff, reviews it, verifies it in a temporary copy, and writes reports.

```bash
patchproof run ./examples/buggy_calculator --test "pytest -q"
```

The original project is not modified.
