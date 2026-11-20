# 验证记录

最终验收日期：2026-11-20。截图和记录来自真实运行的应用。完整机器可读结果见 [acceptance-summary.json](real/acceptance-summary.json)。

## 已完成

- 2026-11-20：本机 Docker 成功构建应用镜像；CLI 最终固定为 `@openai/codex@0.114.0`，原因与沙箱检查见下。
- 2026-11-20：React/Vite 生产构建通过。
- 2026-11-20：后端验证 16 项通过，覆盖会话续接、快照、并发、幂等、失败判定、停止、超时、上传、路径保护、凭据边界、SSE、重启处理和代理转发。输出见 [backend-tests.txt](backend-tests.txt)。测试使用显式标记的进程替身，不调用模型。
- 2026-11-20：浏览器已检查桌面三栏布局、窄屏文件面板默认收起、任务模板填入以及 API 未配置提示。
- 2026-11-20：Docker 页面已通过 1366×900 桌面和 390×844 手机宽度检查，浏览器控制台无 error；截图为 [桌面](screenshots/workbench-desktop.jpg) 和 [手机](screenshots/workbench-mobile.jpg)。
- 2026-11-20：浏览器实际上传两份演示材料，打开 Markdown 预览，完成文件下载，并在刷新页面后确认两份材料仍存在。截图见 [材料预览](screenshots/material-preview.jpg)。
- 2026-11-20：初始未配置凭据时，Docker 容器健康检查通过；`/healthz` 返回 `status=ok, configured=false, cli_available=true`，明确表示尚未配置上游 API。
- 2026-11-20：通过 Docker 应用 HTTP API 创建会话、上传并下载文件；执行 `docker compose restart app` 后，同一会话可读取，文件 SHA256 一致。见 [重启前](runtime-before-restart.json)、[重启后](runtime-after-restart.json)。此项验证文件和数据库持久化，不代表正在执行的 CLI 进程能够恢复。
- 2026-11-20：Codex 0.171.0 默认 Bubblewrap 在当前 Docker 限制下无法创建用户命名空间，其 legacy 后端仍要求 Bubblewrap。改为固定 Codex 0.114.0，实际通过 Landlock + seccomp 正反向验证：工作目录写入成功，写入 `/home/agent/outside-probe.txt` 得到 PermissionError。容器保持非 root、无额外 capabilities、no-new-privileges；未修改宿主机配置。此沙箱测试不调用模型。
- 最终镜像运行 `codex --version` 返回 `codex-cli 0.114.0`，容器为 healthy；沙箱结果见 [sandbox-test.txt](sandbox-test.txt)，可用 `scripts/sandbox_probe.py` 在容器内复现。

## 真实平台联调与最终验收

- 已接通平台 `linext-5.3-luna` Responses API。关闭平台不支持的托管网页搜索后，真实 CLI 读取 CSV、执行 Python 并生成 JSON，独立核验合计为 15。见 [probe-verification.json](probe-verification.json)。
- 代码首轮出现上游 `max_output_tokens` 断流，后达到 600 秒时限；应用正确标记 `timed_out` 并保存 4 个代码文件的部分快照。在原会话续接后已成功交付，成果 ZIP 中的 9 项 unittest 已在清空凭据环境的 Docker 沙箱中独立运行通过，另验证缺失值和重复行数字；旧尝试见 `real/code_1-attempt-1-trace.json`。
- 材料分析第一轮已成功，独立 Decimal 核对为华东 4040、华北 4200、华南 3680（合计 11920）。见 [work_1-verification.json](real/work_1-verification.json)。第二轮也成功完成，独立核对为华东 2760、华北 4200、华南 2560（合计 9520），见 [work_2-verification.json](real/work_2-verification.json)。
- 真实运行中已在浏览器切换两会话、刷新并恢复任务状态；实际点击下载成果 ZIP，文件 SHA256 与 API 产物一致。见 [浏览器下载核验](real/browser-download-verification.json)。最终执行 `docker compose restart app` 后，两会话全部消息、CLI 会话 ID、任务状态、工作文件和 6 份 ZIP 的 SHA256 均一致，见 [restart-verification.json](real/restart-verification.json)。

- 去重追加任务也曾达到原 600 秒时限，保留记录和部分成果，续接后成功完成。实际默认时限据此调整为 1200 秒；不会回写旧任务的超时状态。
- 最终代码成果已在清空上游凭据的 Docker 环境下，经 Codex Linux 沙箱独立运行全部 **21 项 unittest**；额外检验缺失值、精确重复行、保留首行、原文件 SHA256 不变和拒绝覆盖输入文件，全部通过。见 [独立测试](real/code_2-independent-tests.txt)、[断言结果](real/code_2-verification.json)。基础版本独立运行 **9 项 unittest** 通过。
- 四个目标任务最终均为 `succeeded`，真实 CLI 续接标志及相同线程 ID 已核验。初始两个任务并行执行约 309 秒。两次超时尝试原样保留。
- 最终镜像构建记录见 [docker-build-final.txt](docker-build-final.txt)，`/healthz` 为 `status=ok, configured=true, cli_available=true`。浏览器重启刷新后控制台无 error，截图见 [最终开发成果](screenshots/06-final-code-delivery.jpg)。

所有真实任务均通过应用 API 调用实际 Codex CLI 和平台模型。自动测试的 16 项应用测试使用显式测试替身；真实代码成果的 9 / 21 项测试直接执行模型生成的代码，两者不混用。
