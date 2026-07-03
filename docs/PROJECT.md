# Auto Sentinel — Project Context & Status

> 项目上下文 + 进度快照。**维护规则：每次代码 PR 落地，顺手更新「当前状态」段和涉及的决策段。**
> 权威进度以 `git log` / `specs/<sprint>/tasks.md` 的 `[X]` / `DEBT.md` 为准，本文件是快照 + 上下文入口。
> 矩阵全局上下文见 `~/Repo/PORTFOLIO.md`（本地文件，不入库）。

---

## 当前状态（快照 2026-07-03）

- ✅ **Sprint 5（Real LLM Integration）完成**：`specs/005-real-llm-integration/tasks.md` 68/68 全部 `[X]`，
  main 停在 PR #16（Sprint 5 wrap-up docs）。README 已更新为 Sprint 5 real-run quickstart。
- 🔄 进行中：`feat/langfuse-real-trace-script` 分支（T068 real-trace 冒烟脚本，已 push，待 PR/merge）——
  这是与项目 4（LLMOps Dashboard）Phase 2 对接的第一步。
- 🔑 `ARK_API_KEY` 已在本地 `.env` 配置（矩阵中唯一已配 key 的项目）。
- ⚠️ 高优先级已知问题见 `DEBT.md`：**fix-artifact ↔ Verifier 执行格式不匹配**（code 类修复多以
  SyntaxError 挂掉沙盒验证）+ **benchmark `resolved` 定义过宽**（0.98 的 resolution_rate 度量的是
  pipeline 完成率而非修复验证通过率，需 re-baseline）。
- 下一步锚点：Sprint 6（v1 single-agent pipeline 退役、broad CI——目前只有 scenario-authorship gate 在跑）。

---

## 项目是什么

故障自动响应系统：输入报错日志 → 自动分析、写修复代码、安全审查、Docker 沙盒验证，全程无人介入。
6 个 agent 用 LangGraph 编排，agent 间只走 state channel（AST 静态分析在 CI 强制，非口头约定）。

| Agent | 职责 | 真实 LLM |
|-------|------|----------|
| Diagnosis | 解析 stack trace，分类错误 | ✅ |
| Supervisor | 路由到对应 specialist | ✅ |
| CodeFixer | CODE / SECURITY / UNKNOWN | ✅ |
| InfraSRE | INFRA / CONFIG | ✅ |
| SecurityReviewer | 所有 fix 必经 SAFE/HIGH_RISK 审查 | ✅（reasoning model） |
| **Verifier** | Docker 沙盒跑测试，唯一允许 import docker | ❌ 保持确定性（exit code 判定） |

HIGH_RISK 触发 LangGraph `interrupt()`，PostgresSaver 支持跨进程 `Command(resume=...)` 恢复。

## 方法论

**SDD (Spec Kit)**：Constitution 项目级一次立项（现为 v2.2.0），每个 Sprint 必走
/specify → /plan → /tasks → /implement，不可跳过。Constitution v2.2.0 的 Principle VII
（LLM Provider Boundary & Cost Governance）：VII.1 Provider Isolation（AST 强制 SDK import
仅限 `src/auto_sentinel/llm/`）/ VII.2 Cost Guard 不可绕过 / VII.3 Trace Propagation 强制 /
VII.4 Model Routing 声明式。

## Sprint 5 关键决策（已落地）

- **模型路由（3 endpoint × 6 agent，单网关火山方舟）**：Supervisor/Verifier → Doubao-1.5-lite-32k；
  Diagnosis/CodeFixer/InfraSRE → Doubao-Seed-2.0-pro；SecurityReviewer → GLM-4.7（reasoning，
  经火山方舟代理，非智谱官方网关）。OpenAI SDK + base_url 指向 Ark，单一 `ARK_API_KEY`。
  路由配置在 `config/model_routing.yaml`（声明式，不在 agent 内硬编码）。
- **原生货币计量**：cost 按模型计费货币记账（Ark 系全 CNY），零汇率换算，数据结构带 currency 字段。
  Sprint 5 预算 ¥150，CostGuard 超阈值抛 `CostGuardError`，`cost_exhausted_node` + `_guarded`
  wrapper 经条件边确定性中止。GLM-4.7 单价按 ¥3/¥14 主档记（输出 >200，三档见 pricing 注释）。
- **trace_id 单一来源**：trace_id == job_id == `secrets.token_hex(16)`（32-hex，OTel 兼容），
  incident 入口一次生成，经 state channel 透传，LLMTracer 不自生成。
- **env-gated checkpointer**：`AUTOSENTINEL_CHECKPOINTER_DSN` 设了走 PostgresSaver（durable），
  没设走 MemorySaver（hermetic）。`build_multi_agent_graph(agents=)` 是测试注入缝（D2）。
- **SC-013 / SECURITY 子集（T066 真跑后修订）**：030/031/033 重标 SAFE（gate 判 fix artifact 而非
  incident）；032/034/035（涉密类）加确定性 secret/credential 关键词 override 强制 HIGH_RISK +
  GLM 调用失败时 fail-safe HIGH_RISK。HIGH_RISK 子集现为 032/034/035，SC-013=0 由确定性机制保证。
- **benchmark fixture**：`data/benchmark/*.json` 为显式 tracked authored data（`git add -f`），
  ground truth 人工标注，AI 不得自生成自验证。

## 技术栈

LangGraph / OpenAI SDK（base_url→火山方舟）/ Docker SDK / Pydantic v2 / PostgreSQL（checkpointer）/
Langfuse（自托管，项目 4）/ pytest 100% branch coverage / GitHub Actions（目前仅 scenario-authorship
gate，broad CI 见 DEBT.md）/ uv

## 跨项目依赖

- **项目 4 LLMOps Dashboard**：`llmops_dashboard` 作为可选 tracing extra，`set_cost_breakdown`
  签名两仓已对齐（keyword-only，currency 默认 CNY）。T068 冒烟脚本验证真实 trace 进 Langfuse。
- **项目 3 DevContext MCP**：Phase 2 将通过 HTTP 调用本项目（`analyze_error_log` 等 3 个 tool）。
