// Browser regression fixture: no polling, backend, model or production data.
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import RunElapsed from "../src/RunElapsed.jsx";

function Fixture() {
  const [run, setRun] = useState({ status: "queued" });
  const [mounted, setMounted] = useState(true);
  const start = (offset = 0) =>
    setRun({
      status: "running",
      started_at: new Date(Date.now() - offset).toISOString(),
      finished_at: null,
    });
  return (
    <main
      style={{
        padding: 32,
        fontFamily: "sans-serif",
        color: "#172033",
        lineHeight: 2,
      }}
    >
      <h1>执行时长组件验证</h1>
      <p>测试夹具，不调用模型；任务执行时父组件没有轮询或事件更新。</p>
      <p>
        状态：<strong>{run.status}</strong> · 时长：
        {mounted && <RunElapsed run={run} />}
      </p>
      <button onClick={() => start()}>开始任务</button>{" "}
      <button onClick={() => start(58000)}>跨分钟任务</button>{" "}
      <button
        onClick={() =>
          setRun({
            ...run,
            status: "succeeded",
            finished_at: new Date().toISOString(),
          })
        }
      >
        完成任务
      </button>{" "}
      <button
        onClick={() =>
          setRun({
            ...run,
            status: "cancelled",
            finished_at: new Date().toISOString(),
          })
        }
      >
        停止任务
      </button>{" "}
      <button onClick={() => setRun({ status: "queued" })}>排队任务</button>{" "}
      <button onClick={() => setMounted(!mounted)}>
        {mounted ? "离开会话" : "返回会话"}
      </button>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<Fixture />);
