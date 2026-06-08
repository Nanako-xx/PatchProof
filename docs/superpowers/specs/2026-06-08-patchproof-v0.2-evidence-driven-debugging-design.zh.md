# PatchProof v0.2：基于 Bug 证据的自动修复设计

日期：2026-06-08
分支：patchproof-v0.2

## 1. 目标

v0.1 的核心模式是：用户提供一个 pytest 命令，PatchProof 跑测试，读取失败输出，然后让 agent 调查、生成 patch、审查、在临时目录里验证。

v0.2 要把这个模式升级成更接近真实工程 agent 的模式：

**用户不一定知道测试命令，也不一定给 pytest 输出。用户可能直接发报错文本、日志文件、截图，或者同时提供测试命令。PatchProof 需要先把这些输入统一理解成结构化的 Bug 证据，再让 agent 修复。**

v0.2 的目标是：

1. 支持多种 Bug 证据输入：`--bug-text`、`--bug-log`、`--bug-image`、`--test`。
2. 把所有输入统一整理成结构化的 `BugEvidence`。
3. 所有文本类证据都先经过确定性的 traceback/log 解析，再交给 LLM agent 推理。
4. `InvestigatorAgent` 和 `PatchAgent` 不再只依赖 pytest 输出，而是基于 `BugEvidence` 工作。
5. 修完以后优先使用用户给的 `--test` 验证；如果用户没给，则只在安全白名单内自动寻找 Python 测试命令。
6. 报告里必须明确区分：已验证、未复现、未验证建议，不允许把“patch 能应用”说成“bug 已修好”。

## 2. v0.2 暂时不做什么

v0.2 不执行任意 shell 命令。

也就是说，v0.2 暂时不会自动执行：

```text
make deploy
npm run xxx
项目自定义脚本
CI 里发现的未知命令
README 里写的未知命令
LLM 自己建议的任意命令
```

这些能力放到后续版本。做之前需要先研究 Codex / Claude Code 这类工具为什么敢让 agent 执行命令，包括：

1. 如何让用户确认权限。
2. 如何识别危险命令。
3. 如何限制工作目录。
4. 如何处理网络访问。
5. 如何避免泄露密钥和环境变量。
6. 如何防止删除、部署、发布、数据库迁移等高风险操作。
7. 如何处理长时间运行的命令。
8. 如何把风险用用户能看懂的方式展示出来。

v0.2 也不做多语言通用 agent。当前项目是 Python-first，所以 v0.2 先聚焦 Python traceback、Python 日志、Python 测试命令。

## 3. CLI 形式

v0.1 已有命令继续保留：

```powershell
patchproof run ./project --test "pytest -q"
```

v0.2 新增：

```powershell
patchproof run ./project --bug-text "Traceback ..."
patchproof run ./project --bug-log .\error.log
patchproof run ./project --bug-image .\error.png
patchproof run ./project --bug-log .\error.log --test "pytest -q"
patchproof run ./project --bug-image .\error.png --test "pytest -q"
```

输入规则：

1. `--test`、`--bug-text`、`--bug-log`、`--bug-image` 至少要提供一个。
2. 可以同时提供多个证据来源。
3. 如果用户提供了 `--test`，它是最可信的验证命令。
4. 如果用户提供了 `--bug-image`，但当前模型不支持图片输入，PatchProof 要提前失败，并提示用户改用 `--bug-text` 或 `--bug-log`。

## 4. 证据处理流程

v0.2 的关键变化是：**所有 bug 输入都走统一的 evidence pipeline。**

文本输入：

```text
--bug-text
-> TextEvidenceReader
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence
```

日志文件：

```text
--bug-log
-> LogFileEvidenceReader
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence
```

截图：

```text
--bug-image
-> VisionTextExtractor
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence
```

测试输出：

```text
--test output
-> TracebackParser / LogParser
-> BugEvidenceBuilder
-> BugEvidence
```

这里有一个重要边界：

**VisionTextExtractor 只负责把截图里的可见错误文本提取出来，不直接生成最终 BugEvidence。**

也就是说：

```text
图片
-> 视觉模型提取原始错误文本
-> 再交给 TracebackParser / LogParser
-> 再生成 BugEvidence
```

这样做的好处是：文件、行号、异常类型、stack frames、日志信号这些结构化信息，优先由确定性 parser 提取，而不是完全交给 LLM 猜。

## 5. 数据模型

建议新增或扩展这些模型：

```python
class EvidenceSourceType(str, Enum):
    TEST_OUTPUT = "test_output"
    BUG_TEXT = "bug_text"
    BUG_LOG = "bug_log"
    BUG_IMAGE = "bug_image"


class BugEvidenceSource(BaseModel):
    source_type: EvidenceSourceType
    label: str
    path: Path | None = None
    raw_text: str


class LogSignal(BaseModel):
    level: str | None = None
    message: str
    file_path: str | None = None
    line_number: int | None = None


class BugEvidence(BaseModel):
    sources: list[BugEvidenceSource]
    raw_text: str
    traceback_summary: TracebackSummary
    log_signals: list[LogSignal] = []
    suspected_files: list[str] = []
    entrypoint_files: list[str] = []
    summary: str
```

其中：

1. `sources` 表示 bug 证据来自哪里，比如用户粘贴文本、日志文件、截图、pytest 输出。
2. `raw_text` 是合并后的原始错误文本。
3. `traceback_summary` 复用 v0.1 已有的 traceback 结构。
4. `log_signals` 存储日志里解析出的 ERROR、WARNING、文件名、行号等信息。
5. `suspected_files` 表示可能需要修改的源码文件。
6. `entrypoint_files` 表示可能用于复现问题的入口文件，比如测试文件、example、script。

重点区别：

```text
suspected_files = 可能要修的源码文件
entrypoint_files = 可能要重新运行来复现/验证的入口
```

agent 不能简单地“跑被修改的源码文件”，而是要尽量通过测试文件、脚本、CLI 等入口验证行为。

## 6. Orchestrator 流程

v0.2 的主流程：

```text
1. 收集用户输入的 bug 证据。
2. 如果用户提供了 --test，先运行 baseline test。
3. 把所有文本输出解析成 BugEvidence。
4. 如果没有 bug 证据，并且 baseline test 通过，则返回 not_reproduced。
5. InvestigatorAgent 根据 BugEvidence 读代码、定位根因。
6. PatchAgent 根据 BugEvidence、调查结果、代码上下文生成 patch。
7. ReviewerAgent 审查 patch。
8. 在临时 workspace 应用 patch。
9. VerificationPlanner 规划验证命令。
10. VerificationRunner 只运行允许范围内的验证命令。
11. 写 report.md 和 report.json。
```

如果 `--test` 失败，它的输出会成为一个证据来源。

如果 `--test` 通过，但用户同时提供了 `--bug-text`、`--bug-log` 或 `--bug-image`，PatchProof 可以继续基于这些证据调查，但报告里不能说“用户提供的测试已经复现了问题”。

如果用户没有提供 `--test`，PatchProof 仍然可以调查和生成 patch。最终状态取决于是否找到了安全范围内的验证命令。

## 7. Agent Prompt 调整

`InvestigatorAgent` 不应该再只接收 `TestRunResult`，而应该接收 `BugEvidence`。

调查 prompt 里要包含：

1. 证据来源。
2. 解析出的异常类型和错误信息。
3. traceback stack frames。
4. 可能的复现入口文件。
5. 可能的源码问题文件。
6. 日志信号。
7. 如果有 baseline test result，也一起提供。

`PatchAgent` 也要接收 `BugEvidence`，并且要说明 patch 如何解决这个 parsed failure。

v0.1 的 retry 思路保留：

1. patch 应用失败，反馈给 `PatchAgent` 重新生成 patch。
2. 验证失败，反馈给 `InvestigatorAgent` 重新调查。

## 8. VerificationPlanner：怎么判断修没修好

v0.2 的自动验证是受限的，不做无限制命令探索。

验证优先级：

```text
1. 用户提供了 --test
   -> 直接用用户给的命令，可信度最高

2. traceback 里出现了测试文件入口
   -> 跑这个具体测试文件

3. traceback 或 patch 指向源码文件
   -> 找覆盖这些源码文件的相关测试

4. 找不到精准测试
   -> 跑项目默认 Python 测试命令

5. 没有行为验证命令
   -> 只检查 patch 能否应用，必要时做 Python 语法检查
   -> 最终状态标记为 unverified
```

v0.2 自动允许的命令只有：

```text
pytest <test-file-or-dir> -q
python -m pytest <test-file-or-dir> -q
python -m unittest
python -m unittest discover
```

不在白名单内的命令不自动执行，只记录到报告里，说明“发现了候选命令，但 v0.2 安全策略不允许自动执行”。

这里的核心原则是：

```text
源码文件是要修的对象
测试文件 / 脚本 / CLI 才是复现或验证入口
```

所以如果 traceback 指向：

```text
src/patchproof/tools/traceback_parser.py
```

agent 不应该直接跑：

```powershell
pytest src/patchproof/tools/traceback_parser.py
```

而应该尽量找：

```text
tests/**/test_traceback_parser.py
tests/**/*traceback*.py
```

然后跑：

```powershell
pytest tests/unit/test_traceback_parser.py -q
```

## 9. 源码文件如何匹配测试文件

v0.2 第一版先用简单、确定性的规则。

例子：

```text
src/patchproof/tools/traceback_parser.py
-> tests/**/test_traceback_parser.py
-> tests/**/test_tools.py
-> tests/**/*traceback*.py

src/patchproof/core/orchestrator.py
-> tests/**/test_orchestrator.py
-> tests/**/*orchestrator*.py
```

如果匹配到多个测试，优先跑最具体的测试文件。

如果修完后这些测试仍然失败，失败输出会成为新的证据，进入 retry loop。

## 10. 状态和报告

v0.2 报告必须明确区分这些状态：

1. `verified`  
   patch 已在临时目录应用，并且允许范围内的验证命令通过。

2. `not_reproduced`  
   用户提供的测试命令在修复前就已经通过，而且没有其他 bug 证据足以继续修复。

3. `unverified`  
   patch 已生成并能在临时目录应用，但没有行为级验证命令通过，或者没有找到可运行的行为验证命令。

4. `stopped`  
   因为证据不足、patch 被 reviewer 拒绝、命令不安全、超过 retry 限制等原因停止。

报告里要包含：

1. 用户提供了哪些证据。
2. 如果是图片，视觉模型提取出了什么文本。
3. 解析出的 traceback frames 和 exception。
4. suspected files 和 entrypoint files。
5. 实际运行了哪些验证命令。
6. 哪些候选命令因为不在 v0.2 白名单里被跳过。
7. 最终状态和原因。

报告不能把“patch 能 apply”或“语法检查通过”包装成“bug 已修好”。

## 11. 安全规则

v0.2 自动验证必须保守：

1. 不执行 `Makefile`、`package.json`、CI config、README、注释或模型输出里的未知命令。
2. 不执行 deploy、publish、install、migration、delete、网络访问、任意 shell 命令。
3. 所有验证都在临时 patched workspace 里运行。
4. 命令必须有超时。
5. 继续保持 v0.1 原则：patch 尝试不直接修改用户原项目。

## 12. 测试计划

新增单元测试：

1. CLI 校验：至少提供一个证据输入。
2. `--bug-text` 能收集证据。
3. `--bug-log` 能读取日志证据。
4. `--bug-image` 在模型不支持图片时能给出明确失败。
5. 使用 fake model 测试 VisionTextExtractor。
6. pasted text、log、image-extracted text 都能走 traceback parser。
7. `BugEvidenceBuilder` 能合并多个证据来源。
8. VerificationPlanner 优先选择用户给的 `--test`。
9. VerificationPlanner 能选择 traceback 里的测试入口。
10. VerificationPlanner 能把源码文件匹配到测试文件。
11. VerificationPlanner 会跳过不安全命令。

新增集成测试：

1. 只传 `--test` 时保持 v0.1 行为。
2. 只传 `--bug-text` 且无 `--test` 时，可以生成 unverified patch。
3. `--bug-log --test` 可以完成 verified patch。
4. `--bug-image` 可以通过 fake vision 提取文本，再进入 traceback parser。
5. 验证失败会作为 retry evidence 反馈给 investigator。

## 13. 验收标准

v0.2 完成的标准：

1. v0.1 现有测试全部通过。
2. CLI 支持 text、log、image、test 四类 bug 证据。
3. 所有证据类型都能生成结构化 `BugEvidence`。
4. 图片输入一定是先提取文本，再 traceback/log 解析。
5. Investigator 和 Patcher 基于 `BugEvidence` 工作。
6. 验证优先使用 `--test`，其次使用受限自动 Python 验证。
7. 不安全命令会被跳过并写入报告。
8. 报告明确区分 verified patch 和 unverified suggestion。
