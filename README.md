# PatchProof

PatchProof is a Python CLI debugging agent that proposes verified patch suggestions.

It reproduces a pytest failure, investigates with a bounded read-only agent, generates a unified diff, reviews it, verifies it in a temporary copy, and writes reports. The original project is not modified.

PatchProof uses a bounded feedback loop. A patch application error is returned to PatchAgent so it can generate a corrected replacement patch. If the patch applies but pytest still fails, the new test evidence is returned to InvestigatorAgent before the next patch is generated. Every attempt is preserved in the reports, and the default maximum is three patch attempts.

## Quick Start

Install the package in editable mode:

```bash
python -m pip install -e ".[dev]"
```

Configure an OpenAI-compatible model provider:

```bash
PATCHPROOF_PROVIDER=openai_compatible
PATCHPROOF_MODEL=your-model-id
PATCHPROOF_BASE_URL=https://your-provider.example.com/v1
PATCHPROOF_API_KEY=your-api-key
PATCHPROOF_MAX_PATCH_ATTEMPTS=3
```

Run PatchProof against a local pytest project:

```bash
patchproof run ./examples/buggy_calculator --test "pytest -q"
```

PatchProof writes `report.md` and `report.json` in the current working directory.

## Local Verification

The automated tests use a fake LLM client, so they do not require network access, API keys, or model stability.

```bash
pytest -q
```

If a global pytest plugin causes startup hangs, disable plugin autoload:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; $env:PYTHONDONTWRITEBYTECODE='1'; python -m pytest -q -p no:cacheprovider
```

## Why These Technology Choices?

- **CLI first:** keeps the MVP focused on a developer workflow that can be tested and demoed from the terminal.
- **Hand-written orchestrator:** the top-level flow is a fixed safety-critical state machine, so v0.1 does not need LangGraph yet.
- **Classified retry routing:** patch-format and application failures return to PatchAgent, while new pytest failures return to InvestigatorAgent.
- **Bounded ReAct only for investigation:** code exploration benefits from iterative read-only tool calls, while patch review and verification should stay gated.
- **Pydantic:** validates structured LLM output before downstream steps use it.
- **pytest:** matches the first target use case: Python projects with reproducible test failures.
- **git apply:** uses a mature patch application tool instead of a hand-written patch applier.
- **OpenAI-compatible adapter:** supports DeepSeek-style APIs now while leaving room for GPT, Claude, Qwen, and other providers later.

## 面试讲法

PatchProof 的重点不是“又做了一个会改代码的 Agent”，而是把调试流程拆成可验证的工程闭环：

1. 先复现失败，避免 Agent 在没有证据时乱修。
2. InvestigatorAgent 只能调用只读工具，最多做有限次代码调查。
3. PatchAgent 只输出 unified diff，不直接改原项目。
4. ReviewerAgent 独立审查 patch，降低单个模型自我确认的风险。
5. Patch 只应用到临时副本里，再跑同一条 pytest 命令验证。
6. 最后输出报告，包含证据、patch、验证结果和初学者解释。

v1 选择手写 orchestrator，是因为当前流程固定、可测试、风险边界清晰。v2 再迁移到 LangGraph，会更适合加入多轮重试、分支决策和更复杂的 agent graph。
