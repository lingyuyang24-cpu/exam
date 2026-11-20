import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Layers3,
  Plus,
  MessageSquare,
  Code2,
  FileText,
  Paperclip,
  Square,
  Check,
  CircleAlert,
  X,
  Download,
  FolderOpen,
  ChevronDown,
  ChevronRight,
  Clock3,
  LoaderCircle,
  Settings2,
  PanelRightClose,
  PanelRightOpen,
  Terminal,
  Pencil,
  File,
  Upload,
  Search,
  Sparkles,
  Package,
  ExternalLink,
  Menu,
  CircleCheck,
  CirclePause,
  BookOpen,
  Copy,
  CheckCheck,
} from "lucide-react";
import "./style.css";

const STATUS = {
  queued: "排队中",
  running: "执行中",
  succeeded: "已完成",
  failed: "执行失败",
  cancelled: "已停止",
  timed_out: "已超时",
  interrupted: "已中断",
};
const ACTIVE = new Set(["queued", "running"]);
const templates = [
  {
    icon: Code2,
    color: "violet",
    title: "从想法到代码",
    subtitle: "开发工具、修复问题，让代码实际运行。",
    label: "开发一个小工具",
    prompt:
      "请在 project 目录开发一个 Python CSV 数据质量检查工具，检查缺失值和重复行，输出 JSON 报告。提供 README 和自动化测试，并实际运行测试。",
  },
  {
    icon: FileText,
    color: "amber",
    title: "让材料变得清晰",
    subtitle: "分析数据、提炼重点，整理可用的报告。",
    label: "分析工作材料",
    prompt:
      "请分析 uploads 中的材料，计算关键指标、提炼结论和待办事项，在 outputs 目录生成 report.md 和 summary.csv。注明数据口径和材料来源，并验证关键数字。",
  },
];

async function api(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : `请求未成功 (${res.status})`,
    );
  }
  return res.json();
}
const time = (value) =>
  value
    ? new Date(value).toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";
const bytes = (value) =>
  value < 1024
    ? `${value} B`
    : value < 1048576
      ? `${(value / 1024).toFixed(1)} KB`
      : `${(value / 1048576).toFixed(1)} MB`;
function StatusIcon({ status, size = 14 }) {
  const Icon =
    status === "running" || status === "queued"
      ? LoaderCircle
      : status === "succeeded"
        ? CircleCheck
        : status === "cancelled"
          ? CirclePause
          : CircleAlert;
  return <Icon size={size} className={ACTIVE.has(status) ? "spin" : ""} />;
}
function Markdown({ children }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
        }}
      >
        {children || ""}
      </ReactMarkdown>
    </div>
  );
}

function Trace({ run, events, onLoad }) {
  const [open, setOpen] = useState(ACTIVE.has(run.status));
  const [diagnostics, setDiagnostics] = useState(false);
  const commands = new Map();
  const changes = [];
  let plan = [];
  for (const e of events || []) {
    if (e.type === "command")
      commands.set(e.payload.item_id || e.id, e.payload);
    if (e.type === "file.change")
      for (const f of e.payload.changes || [])
        if (!changes.includes(f.path)) changes.push(f.path);
    if (e.type === "plan") plan = e.payload.items || [];
  }
  const logs = (events || []).filter((e) =>
    ["diagnostic", "error", "warning"].includes(e.type),
  );
  const elapsed = run.started_at
    ? Math.max(
        0,
        Math.round(
          (new Date(run.finished_at || Date.now()) - new Date(run.started_at)) /
            1000,
        ),
      )
    : 0;
  return (
    <div className={`trace status-${run.status}`}>
      <button
        className="trace-heading"
        onClick={() => {
          if (!open) onLoad(run.id);
          setOpen(!open);
        }}
        aria-expanded={open}
      >
        <StatusIcon status={run.status} />
        <strong>{STATUS[run.status]}</strong>
        <span>
          {commands.size
            ? `${commands.size} 次命令执行`
            : run.status === "queued"
              ? "等待可用执行位"
              : "Agent 工作记录"}
        </span>
        {elapsed > 0 && (
          <span className="elapsed">
            {elapsed < 60
              ? `${elapsed} 秒`
              : `${Math.floor(elapsed / 60)} 分 ${elapsed % 60} 秒`}
          </span>
        )}
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {run.error && (
        <div className="run-error">
          <CircleAlert size={14} />
          <span>{run.error}</span>
        </div>
      )}
      {open && (
        <div className="trace-body">
          {plan.length > 0 && (
            <div className="plan-list">
              {plan.map((item, i) => (
                <div key={i}>
                  {item.completed ? (
                    <Check size={13} />
                  ) : (
                    <span className="plan-circle" />
                  )}
                  <span>{item.text}</span>
                </div>
              ))}
            </div>
          )}
          {[...commands.entries()].map(([id, c]) => (
            <details key={id} className="command-detail">
              <summary>
                <Terminal size={13} />
                <code>{c.command}</code>
                <span
                  className={
                    c.exit_code === 0
                      ? "exit-ok"
                      : c.exit_code != null
                        ? "exit-failed"
                        : ""
                  }
                >
                  {c.exit_code != null
                    ? `exit ${c.exit_code}`
                    : c.status === "in_progress"
                      ? "运行中"
                      : c.status}
                </span>
              </summary>
              <pre>{c.output || "命令尚无输出。"}</pre>
            </details>
          ))}
          {changes.length > 0 && (
            <div className="changed-files">
              <FileText size={13} />
              <span>
                已修改 {changes.slice(0, 6).join("、")}
                {changes.length > 6 ? ` 等 ${changes.length} 个文件` : ""}
              </span>
            </div>
          )}
          {!commands.size && !changes.length && !logs.length && (
            <p className="trace-empty">
              {ACTIVE.has(run.status)
                ? "助手正在准备工作，执行事件会显示在这里。"
                : "本轮没有命令执行记录。"}
            </p>
          )}
          <div className="trace-footer">
            <a href={`/api/runs/${run.id}/trace`} download>
              <Download size={12} />
              下载执行记录
            </a>
            {logs.length > 0 && (
              <button onClick={() => setDiagnostics(!diagnostics)}>
                {diagnostics ? "收起" : "查看"}诊断 ({logs.length})
              </button>
            )}
          </div>
          {diagnostics && (
            <pre className="diagnostics">
              {logs.map((e) => e.payload.message).join("\n")}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

function App() {
  const [config, setConfig] = useState(null),
    [sessions, setSessions] = useState([]),
    [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null),
    [files, setFiles] = useState([]),
    [traces, setTraces] = useState({});
  const [draft, setDraft] = useState(""),
    [busy, setBusy] = useState(false),
    [uploading, setUploading] = useState(false);
  const [search, setSearch] = useState(""),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [panel, setPanel] = useState(() => window.innerWidth >= 1100),
    [sidebar, setSidebar] = useState(false),
    [tab, setTab] = useState("files");
  const [preview, setPreview] = useState(null),
    [settingsOpen, setSettingsOpen] = useState(false),
    [editing, setEditing] = useState(false),
    [title, setTitle] = useState("");
  const inputRef = useRef(),
    uploadRef = useRef(),
    bottomRef = useRef(),
    selectedRef = useRef(null),
    drafts = useRef({}),
    requestId = useRef(null);
  const activeRun = detail?.runs.find((r) => ACTIVE.has(r.status));
  const ready = config?.configured && config?.cli_available;

  const loadSessions = useCallback(async () => {
    const rows = await api("/api/sessions");
    setSessions(rows);
    return rows;
  }, []);
  const loadDetail = useCallback(async (sid) => {
    if (!sid) return;
    const [data, listed] = await Promise.all([
      api(`/api/sessions/${sid}`),
      api(`/api/sessions/${sid}/files`),
    ]);
    if (selectedRef.current === sid) {
      setDetail(data);
      setFiles(listed);
    }
    return data;
  }, []);
  const selectSession = useCallback((sid) => {
    drafts.current[selectedRef.current || ""] = inputRef.current?.value || "";
    selectedRef.current = sid;
    setSelected(sid);
    setDetail(null);
    setFiles([]);
    setPreview(null);
    setEditing(false);
    setSidebar(false);
    setError("");
    setDraft(drafts.current[sid] || "");
    requestId.current = null;
    localStorage.setItem("agent-desk-session", sid);
  }, []);
  const newSession = useCallback(async () => {
    try {
      const s = await api("/api/sessions", {
        method: "POST",
        body: JSON.stringify({ title: "新会话" }),
      });
      await loadSessions();
      selectSession(s.id);
    } catch (e) {
      setError(e.message);
    }
  }, [loadSessions, selectSession]);
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [cfg, rows] = await Promise.all([
          api("/api/config"),
          loadSessions(),
        ]);
        if (!mounted) return;
        setConfig(cfg);
        const saved = localStorage.getItem("agent-desk-session");
        if (rows.length)
          selectSession(rows.some((s) => s.id === saved) ? saved : rows[0].id);
        else await newSession();
      } catch (e) {
        setError(`无法连接工作台：${e.message}`);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);
  useEffect(() => {
    if (selected) loadDetail(selected).catch((e) => setError(e.message));
  }, [selected, loadDetail]);
  useEffect(() => {
    const timer = setInterval(() => {
      loadSessions().catch(() => {});
      if (selectedRef.current) loadDetail(selectedRef.current).catch(() => {});
    }, 4000);
    return () => clearInterval(timer);
  }, [loadSessions, loadDetail]);
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(""), 3500);
      return () => clearTimeout(timer);
    }
  }, [toast]);
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [detail?.messages.length, activeRun?.id]);
  const loadTrace = useCallback(async (rid) => {
    try {
      const data = await api(`/api/runs/${rid}/trace`);
      setTraces((old) => ({ ...old, [rid]: data.events }));
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => {
    if (!activeRun) return;
    const rid = activeRun.id;
    const stream = new EventSource(`/api/runs/${rid}/events`);
    stream.onmessage = (e) => {
      const event = JSON.parse(e.data);
      setTraces((old) => {
        const previous = old[rid] || [];
        return previous.some((x) => x.id === event.id)
          ? old
          : { ...old, [rid]: [...previous, event] };
      });
      if (event.type === "run.status" && !ACTIVE.has(event.payload.status)) {
        loadDetail(selectedRef.current).catch(() => {});
        loadSessions().catch(() => {});
      }
    };
    stream.addEventListener("stream.end", () => {
      stream.close();
      loadDetail(selectedRef.current).catch(() => {});
    });
    return () => stream.close();
  }, [activeRun?.id, loadDetail, loadSessions]);

  async function send() {
    if (!draft.trim() || busy || activeRun) return;
    if (!ready) {
      setSettingsOpen(true);
      return;
    }
    setBusy(true);
    setError("");
    const sid = selected;
    try {
      requestId.current ||= crypto.randomUUID();
      await api(`/api/sessions/${sid}/messages`, {
        method: "POST",
        body: JSON.stringify({ content: draft, request_id: requestId.current }),
      });
      if (selectedRef.current === sid) setDraft("");
      drafts.current[sid] = "";
      requestId.current = null;
      await Promise.all([loadDetail(sid), loadSessions()]);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function cancel() {
    if (!activeRun) return;
    try {
      await api(`/api/runs/${activeRun.id}/cancel`, { method: "POST" });
      await loadDetail(selected);
    } catch (e) {
      setError(e.message);
    }
  }
  async function uploadFiles(list) {
    if (!selected || !list.length) return;
    setUploading(true);
    setError("");
    const sid = selected;
    try {
      for (const file of list) {
        const data = new FormData();
        data.append("file", file);
        await api(`/api/sessions/${sid}/uploads`, {
          method: "POST",
          body: data,
        });
      }
      await loadDetail(sid);
      setToast(`已上传 ${list.length} 份材料`);
      setPanel(true);
      setTab("files");
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
      if (uploadRef.current) uploadRef.current.value = "";
    }
  }
  async function openFile(file) {
    try {
      const content = await api(
        `/api/sessions/${selected}/file?path=${encodeURIComponent(file.path)}`,
      );
      setPreview({ ...file, ...content });
    } catch (e) {
      setError(e.message);
    }
  }
  async function rename() {
    setEditing(false);
    if (!title.trim() || title === detail?.session.title) return;
    try {
      await api(`/api/sessions/${selected}`, {
        method: "PATCH",
        body: JSON.stringify({ title: title.trim() }),
      });
      await Promise.all([loadDetail(selected), loadSessions()]);
    } catch (e) {
      setError(e.message);
    }
  }
  const lastLiveMessage = (traces[activeRun?.id] || [])
    .filter((e) => e.type === "agent.message")
    .at(-1)?.payload.text;
  const displayed = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase()),
  );
  const inputs = files.filter((f) => f.category === "input"),
    outputs = files.filter((f) => f.category === "output");
  const hasMessages = !!detail?.messages.length;
  return (
    <div className={`app ${panel ? "" : "panel-closed"}`}>
      <aside className={`sidebar ${sidebar ? "mobile-open" : ""}`}>
        <div className="brand">
          <div className="brand-symbol">
            <Layers3 size={22} />
          </div>
          <span>Agent Desk</span>
          <span className="brand-beta">BETA</span>
        </div>
        <button className="new-session" onClick={newSession}>
          <Plus size={18} />
          新建会话<span>⌘ K</span>
        </button>
        <label className="search">
          <Search size={15} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜索会话"
            aria-label="搜索会话"
          />
        </label>
        <div className="sidebar-section">
          <span>我的工作</span>
          <span>{sessions.length}</span>
        </div>
        <nav className="session-list" aria-label="会话列表">
          {displayed.map((s) => (
            <button
              className={`session ${selected === s.id ? "selected" : ""}`}
              key={s.id}
              onClick={() => selectSession(s.id)}
            >
              <MessageSquare size={16} />
              <div>
                <strong>{s.title}</strong>
                <span>
                  {ACTIVE.has(s.status)
                    ? STATUS[s.status]
                    : s.preview
                      ? s.preview.slice(0, 26)
                      : "准备开始新的工作"}
                </span>
              </div>
              {ACTIVE.has(s.status) && (
                <LoaderCircle size={13} className="spin" />
              )}
            </button>
          ))}
          {!displayed.length && (
            <p className="sidebar-empty">没有找到相关会话</p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace-label">
            <span className="workspace-avatar">W</span>
            <div>
              <strong>个人工作空间</strong>
              <span>文件与记录自动保存</span>
            </div>
            <button
              className="icon-button"
              aria-label="工作台设置"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings2 size={16} />
            </button>
          </div>
        </div>
      </aside>
      {sidebar && (
        <button
          className="sidebar-shade"
          aria-label="关闭导航"
          onClick={() => setSidebar(false)}
        />
      )}
      <main className="main">
        <header className="topbar">
          <div className="title-wrap">
            <button
              className="icon-button mobile-menu"
              aria-label="打开导航"
              onClick={() => setSidebar(true)}
            >
              <Menu size={20} />
            </button>
            <span className="breadcrumb">工作台</span>
            <span className="slash">/</span>
            {editing ? (
              <input
                className="rename-input"
                autoFocus
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                onBlur={rename}
                onKeyDown={(e) => {
                  if (e.key === "Enter") e.currentTarget.blur();
                  if (e.key === "Escape") {
                    setEditing(false);
                  }
                }}
                maxLength={80}
              />
            ) : (
              <button
                className="session-title"
                onClick={() => {
                  setTitle(detail?.session.title || "新会话");
                  setEditing(true);
                }}
                title="重命名会话"
              >
                {detail?.session.title || "新会话"}
                <Pencil size={12} />
              </button>
            )}
          </div>
          <div className="topbar-right">
            <button
              className={`connection ${ready ? "ready" : ""}`}
              onClick={() => setSettingsOpen(true)}
            >
              <span />
              {ready ? "Agent 已就绪" : "等待 API 配置"}
            </button>
            <span className="header-divider" />
            <button
              className="icon-button"
              aria-label={panel ? "收起文件面板" : "展开文件面板"}
              onClick={() => setPanel(!panel)}
            >
              {panel ? (
                <PanelRightClose size={18} />
              ) : (
                <PanelRightOpen size={18} />
              )}
            </button>
          </div>
        </header>
        <div className="conversation" key={selected}>
          {!hasMessages ? (
            <div className="welcome">
              <div className="welcome-mark">
                <Layers3 size={29} />
                <span className="welcome-spark">
                  <Sparkles size={13} />
                </span>
              </div>
              <div className="eyebrow">一个工作台，无限种可能</div>
              <h1>把想法，交给行动。</h1>
              <p className="welcome-subtitle">
                写代码、读材料、做分析。
                <br className="small-break" /> 交给助手，也随时回来继续。
              </p>
              <div className="starter-grid">
                {templates.map((t) => (
                  <button
                    key={t.title}
                    className="starter-card"
                    onClick={() => {
                      setDraft(t.prompt);
                      inputRef.current?.focus();
                    }}
                  >
                    <div className={`template-icon ${t.color}`}>
                      <t.icon size={21} />
                    </div>
                    <h2>{t.title}</h2>
                    <p>{t.subtitle}</p>
                    <span>
                      {t.label}
                      <Plus size={13} />
                    </span>
                  </button>
                ))}
              </div>
              <div className="welcome-note">
                <Clock3 size={14} />
                进展随时可见，成果自动保存
              </div>
            </div>
          ) : (
            <div className="messages">
              {detail.messages.map((m) => (
                <React.Fragment key={m.id}>
                  <article className={`message ${m.role}`}>
                    <div className="message-avatar">
                      {m.role === "user" ? "你" : <Layers3 size={17} />}
                    </div>
                    <div className="message-content">
                      <div className="message-meta">
                        <strong>{m.role === "user" ? "你" : "Agent"}</strong>
                        <time>{time(m.created_at)}</time>
                        {m.role === "assistant" && (
                          <span className="assistant-label">Codex</span>
                        )}
                      </div>
                      {m.role === "user" ? (
                        <div className="user-text">{m.content}</div>
                      ) : (
                        <Markdown>{m.content}</Markdown>
                      )}
                    </div>
                  </article>
                  {m.role === "user" &&
                    detail.runs
                      .filter((r) => r.id === m.run_id)
                      .map((r) => (
                        <Trace
                          key={r.id}
                          run={r}
                          events={traces[r.id]}
                          onLoad={loadTrace}
                        />
                      ))}
                </React.Fragment>
              ))}
              {activeRun && lastLiveMessage && (
                <article className="message assistant live">
                  <div className="message-avatar">
                    <Layers3 size={17} />
                  </div>
                  <div className="message-content">
                    <div className="message-meta">
                      <strong>Agent</strong>
                      <span className="assistant-label">正在工作</span>
                    </div>
                    <Markdown>{lastLiveMessage}</Markdown>
                  </div>
                </article>
              )}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
        <div className="composer-area">
          {error && (
            <div className="error-banner" role="alert">
              <CircleAlert size={16} />
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="关闭错误"
                onClick={() => setError("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {inputs.length > 0 && (
            <div className="attached-summary">
              <Paperclip size={13} />
              <span>本会话已有 {inputs.length} 份材料</span>
              <button
                onClick={() => {
                  setPanel(true);
                  setTab("files");
                }}
              >
                查看材料
              </button>
            </div>
          )}
          <div
            className={`composer ${activeRun ? "is-working" : ""}`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              uploadFiles([...e.dataTransfer.files]);
            }}
          >
            <textarea
              ref={inputRef}
              aria-label="给助手的任务"
              placeholder={
                activeRun
                  ? "助手正在执行，你可以先写好下一步要求…"
                  : hasMessages
                    ? "继续提出要求，助手会接着完成…"
                    : "告诉助手你想完成什么，或先上传一些材料…"
              }
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                requestId.current = null;
              }}
              onKeyDown={(e) => {
                if (
                  e.key === "Enter" &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing
                ) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <div className="composer-toolbar">
              <div className="composer-tools">
                <button
                  className="icon-button attach-button"
                  aria-label="上传材料"
                  onClick={() => uploadRef.current?.click()}
                  disabled={uploading || !!activeRun}
                >
                  {uploading ? (
                    <LoaderCircle className="spin" size={18} />
                  ) : (
                    <Paperclip size={18} />
                  )}
                </button>
                <span className="tool-divider" />
                <button
                  className="model-label"
                  onClick={() => setSettingsOpen(true)}
                >
                  <span className="model-icon">✳</span>
                  {config?.model || "linext-5.3-luna"}
                  <ChevronDown size={12} />
                </button>
              </div>
              {activeRun ? (
                <button className="stop-button" onClick={cancel}>
                  <Square size={12} fill="currentColor" />
                  停止任务
                </button>
              ) : (
                <button
                  className="send-button"
                  onClick={send}
                  disabled={!draft.trim() || busy || uploading}
                >
                  {busy ? (
                    <LoaderCircle size={15} className="spin" />
                  ) : (
                    <Sparkles size={15} />
                  )}
                  发送
                </button>
              )}
            </div>
          </div>
          <div className="composer-caption">
            <span>
              {activeRun
                ? "任务在后台运行，离开页面后仍会继续。"
                : "Enter 发送 · Shift + Enter 换行"}
            </span>
            <span>由真实 Agent CLI 执行</span>
          </div>
        </div>
      </main>
      {panel && (
        <aside className="file-panel">
          <div className="panel-heading">
            <div>
              <FolderOpen size={18} />
              <h2>工作文件</h2>
            </div>
            <button
              className="icon-button"
              aria-label="关闭文件面板"
              onClick={() => setPanel(false)}
            >
              <X size={16} />
            </button>
          </div>
          <div className="panel-tabs">
            <button
              className={tab === "files" ? "active" : ""}
              onClick={() => setTab("files")}
            >
              文件<span>{files.length}</span>
            </button>
            <button
              className={tab === "artifacts" ? "active" : ""}
              onClick={() => setTab("artifacts")}
            >
              成果<span>{detail?.artifacts.length || 0}</span>
            </button>
          </div>
          <div className="panel-scroll">
            {tab === "files" ? (
              <>
                <button
                  className="upload-zone"
                  onClick={() => uploadRef.current?.click()}
                  disabled={uploading || !!activeRun}
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    e.preventDefault();
                    uploadFiles([...e.dataTransfer.files]);
                  }}
                >
                  <div className="upload-symbol">
                    {uploading ? (
                      <LoaderCircle className="spin" size={19} />
                    ) : (
                      <Upload size={19} />
                    )}
                  </div>
                  <strong>
                    {uploading ? "正在上传…" : "点击或拖入工作材料"}
                  </strong>
                  <span>文本、CSV、JSON、代码 · 最大 10 MB</span>
                </button>
                {inputs.length > 0 && (
                  <div className="file-group">
                    <h3>
                      上传材料 <span>{inputs.length}</span>
                    </h3>
                    {inputs.map((f) => (
                      <FileRow key={f.path} file={f} onOpen={openFile} />
                    ))}
                  </div>
                )}
                {outputs.length > 0 && (
                  <div className="file-group">
                    <h3>
                      工作成果 <span>{outputs.length}</span>
                    </h3>
                    {outputs.map((f) => (
                      <FileRow key={f.path} file={f} onOpen={openFile} />
                    ))}
                  </div>
                )}
                {!files.length && (
                  <div className="files-empty">
                    <div className="empty-file-illustration">
                      <FileText size={29} strokeWidth={1.3} />
                      <span>
                        <Plus size={12} />
                      </span>
                    </div>
                    <strong>每一份成果，都在这里</strong>
                    <p>
                      上传的材料和助手生成的文件
                      <br />
                      会自动整理到当前会话。
                    </p>
                  </div>
                )}
              </>
            ) : detail?.artifacts.length ? (
              <div className="artifact-list">
                {detail.artifacts.map((a, i) => (
                  <div className="artifact-card" key={a.id}>
                    <div className="artifact-icon">
                      <Package size={20} />
                    </div>
                    <strong>
                      第 {detail.artifacts.length - i} 轮成果
                      {a.partial ? " · 部分完成" : ""}
                    </strong>
                    <p>
                      {time(a.created_at)} · {bytes(a.size)} · ZIP
                    </p>
                    <a href={`/api/artifacts/${a.id}/download`} download>
                      <Download size={14} />
                      下载成果包
                    </a>
                    <span className="artifact-hash" title={a.sha256}>
                      SHA256 {a.sha256.slice(0, 12)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="files-empty">
                <Package size={34} strokeWidth={1.2} />
                <strong>等待第一份成果</strong>
                <p>
                  任务结束后，生成的文件会
                  <br />
                  保存为独立的成果包。
                </p>
              </div>
            )}
          </div>
          <div className="panel-footer">
            <Layers3 size={14} />
            <span>文件仅属于当前会话</span>
          </div>
        </aside>
      )}
      <input
        ref={uploadRef}
        type="file"
        multiple
        hidden
        accept={config?.upload_extensions?.join(",")}
        onChange={(e) => uploadFiles([...e.target.files])}
      />
      {toast && (
        <div className="toast" role="status">
          <CircleCheck size={16} />
          {toast}
        </div>
      )}
      {preview && (
        <div className="modal-backdrop" onClick={() => setPreview(null)}>
          <section
            className="preview-modal"
            role="dialog"
            aria-modal="true"
            aria-label="文件预览"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <div>
                <FileText size={18} />
                <strong>{preview.name}</strong>
                <span>{bytes(preview.size)}</span>
              </div>
              <div>
                <a
                  className="text-button"
                  href={`/api/sessions/${selected}/download?path=${encodeURIComponent(preview.path)}`}
                  download
                >
                  <Download size={15} />
                  下载
                </a>
                <button
                  className="icon-button"
                  aria-label="关闭预览"
                  onClick={() => setPreview(null)}
                >
                  <X size={19} />
                </button>
              </div>
            </header>
            <div className="preview-body">
              {preview.name.endsWith(".md") ? (
                <Markdown>{preview.content}</Markdown>
              ) : (
                <pre>{preview.content}</pre>
              )}
              {preview.truncated && (
                <p className="preview-notice">
                  仅预览前 256 KB，下载可查看完整内容。
                </p>
              )}
            </div>
            <footer>{preview.path}</footer>
          </section>
        </div>
      )}
      {settingsOpen && (
        <div className="modal-backdrop" onClick={() => setSettingsOpen(false)}>
          <section
            className="settings-modal"
            role="dialog"
            aria-modal="true"
            aria-label="工作台配置"
            onClick={(e) => e.stopPropagation()}
          >
            <header>
              <h2>工作台配置</h2>
              <button
                className="icon-button"
                aria-label="关闭配置"
                onClick={() => setSettingsOpen(false)}
              >
                <X size={19} />
              </button>
            </header>
            <div className={`config-state ${ready ? "configured" : ""}`}>
              <StatusIcon status={ready ? "succeeded" : "failed"} size={20} />
              <div>
                <strong>
                  {ready ? "Agent 已准备就绪" : "等待模型 API 配置"}
                </strong>
                <p>
                  {ready
                    ? "任务由服务端 Codex CLI 执行。"
                    : "在服务端 .env 中配置地址和密钥，然后重启应用。"}
                </p>
              </div>
            </div>
            <dl>
              <div>
                <dt>执行引擎</dt>
                <dd>
                  Codex CLI {config?.cli_available ? "· 已安装" : "· 未检测到"}
                </dd>
              </div>
              <div>
                <dt>当前模型</dt>
                <dd>{config?.model}</dd>
              </div>
              <div>
                <dt>同时执行</dt>
                <dd>{config?.concurrency || 2} 个任务 · 每会话串行</dd>
              </div>
              <div>
                <dt>单次时限</dt>
                <dd>
                  {Math.floor((config?.timeout_seconds || 600) / 60)} 分钟
                </dd>
              </div>
            </dl>
            {!ready && (
              <pre>
                AGENT_API_KEY=你的密钥{"\n"}AGENT_BASE_URL=平台 API 地址{"\n"}
                AGENT_MODEL={config?.model || "linext-5.3-luna"}
              </pre>
            )}
            <p className="settings-note">
              密钥只保存在服务端。关闭网页不会停止任务；重启服务会将执行中的任务标为中断，已有文件仍保留。
            </p>
            <button
              className="settings-done"
              onClick={() => setSettingsOpen(false)}
            >
              知道了
            </button>
          </section>
        </div>
      )}
      <KeyboardShortcut onNew={newSession} />
    </div>
  );
}
function FileRow({ file, onOpen }) {
  const code = /\.(py|js|ts|html|css|jsx|tsx)$/.test(file.name);
  return (
    <button className="file-row" onClick={() => onOpen(file)} title={file.path}>
      <div className={`file-type ${code ? "code" : ""}`}>
        {code ? <Code2 size={17} /> : <FileText size={17} />}
      </div>
      <div>
        <strong>{file.name}</strong>
        <span>
          {bytes(file.size)} · {file.path.split("/").slice(0, -1).join("/")}
        </span>
      </div>
      <ChevronRight size={13} />
    </button>
  );
}
function KeyboardShortcut({ onNew }) {
  useEffect(() => {
    const handler = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        onNew();
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onNew]);
  return null;
}
createRoot(document.getElementById("root")).render(<App />);
