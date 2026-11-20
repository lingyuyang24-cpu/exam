import React, { useEffect, useState } from "react";

export default function RunElapsed({ run }) {
  const [now, setNow] = useState(Date.now);
  const { started_at: startedAt, finished_at: finishedAt, status } = run;

  useEffect(() => {
    if (status !== "running" || !startedAt || finishedAt) return;

    // Read the clock rather than counting ticks: background tabs can be throttled.
    const update = () => setNow(Date.now());
    update();
    const timer = window.setInterval(update, 1000);
    window.addEventListener("focus", update);
    document.addEventListener("visibilitychange", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
      document.removeEventListener("visibilitychange", update);
    };
  }, [startedAt, finishedAt, status]);

  if (!startedAt) return null;
  const milliseconds =
    (finishedAt ? Date.parse(finishedAt) : now) - Date.parse(startedAt);
  if (!Number.isFinite(milliseconds)) return null;
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const label =
    seconds < 60
      ? `${seconds} 秒`
      : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;

  return (
    <span
      className="elapsed"
      role="timer"
      aria-live="off"
      aria-label={`执行时长：${label}`}
    >
      {label}
    </span>
  );
}
