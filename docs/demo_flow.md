# PatchProof Demo Flow

## 真实模型演示

1. 确认 `.env` 或环境变量里已经配置模型：

```bash
PATCHPROOF_PROVIDER=openai_compatible
PATCHPROOF_MODEL=your-model-id
PATCHPROOF_BASE_URL=https://your-provider.example.com/v1
PATCHPROOF_API_KEY=your-api-key
```

2. 展示原始项目失败：

```bash
cd examples/buggy_calculator
pytest -q
```

3. 回到仓库根目录，运行 PatchProof：

```bash
patchproof run ./examples/buggy_calculator --test "pytest -q"
```

4. 打开 `report.md`，重点讲这几部分：

- baseline failure evidence;
- read-only investigation hypothesis;
- generated patch diff;
- independent review;
- temporary-copy verification;
- beginner-friendly explanation.

5. 确认原始项目没有被修改：

```bash
git diff -- examples/buggy_calculator
```

## 无 API 验证路径

自动化测试使用 fake LLM，可以稳定验证核心流程，不依赖网络、API key 或模型输出波动：

```bash
pytest tests/integration/test_orchestrator_happy_path.py -q
```

这个测试覆盖：

- 复现 `buggy_calculator` 的 pytest 失败；
- InvestigatorAgent 通过只读 ReAct 工具定位代码；
- PatchAgent 生成 unified diff；
- ReviewerAgent 通过审查；
- patch 应用到临时副本；
- 临时副本里同一条 pytest 命令通过；
- 原始项目保持不变；
- 写出 Markdown 和 JSON 报告。
