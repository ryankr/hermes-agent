/** Read-only Kanban Work Portfolio dashboard plugin. */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const registry = window.__HERMES_PLUGINS__;
  if (!SDK || !registry || typeof registry.register !== "function") return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge, Button } = SDK.components;
  const { useCallback, useEffect, useState } = SDK.hooks;
  const API = "/api/plugins/kanban/overview";
  const FOCUS = ["running", "blocked", "review", "scheduled", "ready"];

  function TaskCard(props) {
    const task = props.task;
    return h("li", { className: "space-y-1 rounded border p-2" },
      h("strong", null, task.title),
      h("div", { className: "text-xs text-muted-foreground" },
        `${task.status} · priority ${task.priority}`,
        task.assignee ? ` · ${task.assignee}` : ""),
      h("code", { className: "text-xs" }, task.id));
  }

  function Board(props) {
    const board = props.board;
    return h(Card, { className: "mb-4" }, h(CardContent, { className: "p-4" },
      h("h2", { className: "text-lg font-semibold" }, board.name || board.slug),
      h("p", { className: "mb-3 text-sm text-muted-foreground" },
        `Board: ${board.slug}${board.project_id ? ` · Project: ${board.project_id}` : ""}`),
      h("div", { className: "mb-3 flex flex-wrap gap-2", "aria-label": "Task counts" },
        Object.keys(board.counts || {}).map(function (status) {
          return h(Badge, { key: status, variant: "secondary" }, `${status}: ${board.counts[status]}`);
        })),
      FOCUS.map(function (status) {
        const focus = (board.focus && board.focus[status]) || { tasks: [], truncated: false };
        const tasks = focus.tasks || [];
        if (!tasks.length && !focus.truncated) return null;
        return h("section", { key: status, className: "mb-3", "aria-label": `${status} tasks` },
          h("h3", { className: "text-sm font-medium capitalize" }, status),
          h("ul", { className: "space-y-2", "aria-label": `${status} focus cards` },
            tasks.map(function (task) { return h(TaskCard, { key: task.id, task: task }); })),
          focus.truncated ? h("p", { className: "mt-2 text-xs text-muted-foreground", role: "status" },
            `Additional ${status} tasks are not shown.`) : null);
      })));
  }

  function WorkPortfolio() {
    const [data, setData] = useState(null);
    const [error, setError] = useState("");
    const load = useCallback(function () {
      setError("");
      return SDK.fetchJSON(API).then(setData).catch(function (err) {
        setError(err && err.message ? err.message : "Could not load portfolio overview.");
      });
    }, []);
    useEffect(function () { load(); }, [load]);
    if (error) return h("section", { role: "alert", className: "p-4" }, error);
    if (!data) return h("p", { className: "p-4", "aria-live": "polite" }, "Loading portfolio overview…");
    return h("main", { className: "p-4", "aria-labelledby": "work-portfolio-title" },
      h("div", { className: "mb-4 flex items-center justify-between gap-3" },
        h("div", null,
          h("h1", { id: "work-portfolio-title", className: "text-xl font-semibold" }, "Work Portfolio"),
          h("p", { className: "text-sm text-muted-foreground" },
            `Snapshot: ${data.outcome}; current board: ${data.current_board}`)),
        h(Button, { type: "button", onClick: load }, "Refresh")),
      data.failures && data.failures.length ? h("section", { role: "status", className: "mb-4" },
        h("h2", { className: "font-medium" }, "Unavailable boards"),
        h("ul", null, data.failures.map(function (failure) {
          return h("li", { key: failure.board }, `${failure.board}: ${failure.message}`);
        }))) : null,
      (data.boards || []).map(function (board) { return h(Board, { key: board.slug, board: board }); }));
  }

  registry.register("work-portfolio", WorkPortfolio);
}());
