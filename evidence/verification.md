# 验证记录

此文件随实际验证更新。截图和记录来自真实运行的应用；模型运行状态单独列出。

## 已完成

- 2026-11-20：本机 Docker 成功构建应用镜像；CLI 最终固定为 `@openai/codex@0.114.0`，原因与沙箱检查见下。
- 2026-11-20：React/Vite 生产构建通过。
- 2026-11-20：后端验证 14 项通过，覆盖会话续接、快照、并发、幂等、失败判定、停止、超时、上传、路径保护、凭据边界、SSE、重启处理和代理转发。输出见 [backend-tests.txt](backend-tests.txt)。测试使用显式标记的进程替身，不调用模型。
- 2026-11-20：浏览器已检查桌面三栏布局、窄屏文件面板默认收起、任务模板填入以及 API 未配置提示。
- 2026-11-20：Docker 页面已通过 1366×900 桌面和 390×844 手机宽度检查，浏览器控制台无 error；截图为 [桌面](screenshots/workbench-desktop.jpg) 和 [手机](screenshots/workbench-mobile.jpg)。
- 2026-11-20：浏览器实际上传两份演示材料，打开 Markdown 预览，完成文件下载，并在刷新页面后确认两份材料仍存在。截图见 [材料预览](screenshots/material-preview.jpg)。
- 2026-11-20：Docker 容器健康检查通过；`/healthz` 返回 `status=ok, configured=false, cli_available=true`，明确表示尚未配置上游 API。
- 2026-11-20：通过 Docker 应用 HTTP API 创建会话、上传并下载文件；执行 `docker compose restart app` 后，同一会话可读取，文件 SHA256 一致。见 [重启前](runtime-before-restart.json)、[重启后](runtime-after-restart.json)。此项验证文件和数据库持久化，不代表正在执行的 CLI 进程能够恢复。
- 2026-11-20：Codex 0.171.0 默认 Bubblewrap 在当前 Docker 限制下无法创建用户命名空间，其 legacy 后端仍要求 Bubblewrap。改为固定 Codex 0.114.0，实际通过 Landlock + seccomp 正反向验证：工作目录写入成功，写入 `/home/agent/outside-probe.txt` 得到 PermissionError。容器保持非 root、无额外 capabilities、no-new-privileges；未修改宿主机配置。此沙箱测试不调用模型。
- 最终镜像运行 `codex --version` 返回 `codex-cli 0.114.0`，容器为 healthy；沙箱结果见 [sandbox-test.txt](sandbox-test.txt)，可用 `scripts/sandbox_probe.py` 在容器内复现。

## 待提供配置后验证

- 平台 `linext-5.3-luna` 与实际 API 地址的 Responses/工具调用兼容性。
- 真实代码开发任务及其后续修改、测试和成果。
- 真实材料分析任务及统计口径变更后的独立数字核验。
- 真实运行期间多会话切换、刷新，以及容器重启后的历史访问。

没有把待完成项记为通过，也没有预填真实 Agent 的回复或成果。
