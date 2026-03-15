import { useCallback, useEffect, useState } from "react";
import "./index.css";
import type { AgentCard } from "./lib/types";
import { AgentInfo } from "./components/AgentInfo";
import { ChatView } from "./components/ChatView";
import { TasksView } from "./components/TasksView";

const INITIAL_POLL = (() => {
  try {
    const p = new URLSearchParams(window.location.search);
    const v = parseInt(p.get("poll") || "", 10);
    if (v > 0) return v * 1000;
  } catch { /* ignore */ }
  return 1000;
})();

export function App() {
  const [card, setCard] = useState<AgentCard | null>(null);
  const [cardError, setCardError] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "tasks">("chat");
  const [pollInterval, setPollInterval] = useState(INITIAL_POLL);

  useEffect(() => {
    (async () => {
      try {
        const resp = await fetch("/.well-known/agent-card.json");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        setCard(await resp.json());
      } catch (err) {
        setCardError(err instanceof Error ? err.message : String(err));
      }
    })();
  }, []);

  const switchView = useCallback((v: "chat" | "tasks") => setView(v), []);

  return (
    <div className="app">
      <div className="header">
        <div className="header-left">
          <h1>a2akit Debug UI</h1>
          <div className="tabs">
            <button
              className={`tab${view === "chat" ? " active" : ""}`}
              onClick={() => switchView("chat")}
            >
              Chat
            </button>
            <button
              className={`tab${view === "tasks" ? " active" : ""}`}
              onClick={() => switchView("tasks")}
            >
              Tasks
            </button>
          </div>
        </div>
        <span className="badge">Experimental</span>
      </div>
      <div className="main">
        <AgentInfo card={card} error={cardError} />
        <div className="panel-right">
          {view === "chat" ? (
            <ChatView card={card} />
          ) : (
            <TasksView
              card={card}
              active={view === "tasks"}
              pollInterval={pollInterval}
              onPollIntervalChange={setPollInterval}
            />
          )}
        </div>
      </div>
      <div className="footer">
        <span>a2akit v{"{{VERSION}}"}</span>
        <span>
          Agent Card:{" "}
          <a href="/.well-known/agent-card.json" target="_blank" rel="noopener">
            /.well-known/agent-card.json
          </a>
        </span>
      </div>
    </div>
  );
}
