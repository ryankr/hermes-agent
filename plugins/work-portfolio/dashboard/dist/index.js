/** Read-only Kanban Work Portfolio dashboard plugin. */
(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const registry = window.__HERMES_PLUGINS__;
  if (!SDK || !registry || typeof registry.register !== "function") return;
  const { React } = SDK;
  const h = React.createElement;
  const { Card, CardContent, Badge, Button } = SDK.components;
  const { useCallback, useEffect, useRef, useState } = SDK.hooks;
  const API = "/api/plugins/kanban/overview";
  const FOCUS = ["running", "blocked", "review", "scheduled", "ready"];

  function errorDetails(err) {
    return err && err.message ? err.message : "Could not load portfolio overview.";
  }

  function missingKanbanPlugin(err) {
    return !!err && Number(err.status) === 404;
  }

  function TaskCard(props) {
    const task = props.task;
    const progress = task.progress && Number.isFinite(task.progress.done) && Number.isFinite(task.progress.total)
      ? ` · ${task.progress.done}/${task.progress.total}` : "";
    return h("li", { className: "space-y-1 rounded border p-2" },
      h("button", { type: "button", className: "w-full text-left", onClick: props.onSelect },
        h("strong", null, task.title),
        h("div", { className: "text-xs text-muted-foreground" },
          `${task.status} · priority ${task.priority}${progress}`,
          task.assignee ? ` · ${task.assignee}` : ""),
        h("code", { className: "text-xs" }, task.id)),
    );
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
            tasks.map(function (task) { return h(TaskCard, { key: task.id, task: task, onSelect: function () { props.onSelect(task, board.slug); } }); })),
          focus.truncated ? h("p", { className: "mt-2 text-xs text-muted-foreground", role: "status" },
            `Additional ${status} tasks are not shown.`) : null);
      })));
  }

  function TaskDetail(props) {
    if (!props.selection) return null;
    const task = props.detail && props.detail.task;
    const children = props.detail && props.detail.child_results || [];
    return h("section", { role: "dialog", "aria-modal": "true", "aria-label": "Task details", className: "mb-4 rounded border p-4" },
      h("div", { className: "flex items-center justify-between gap-3" },
        h("h2", { className: "text-lg font-semibold" }, "Task details"),
        h(Button, { type: "button", onClick: props.onClose }, "Close")),
      props.loading ? h("p", { role: "status" }, "Loading task details…") : null,
      props.error ? h("p", { role: "alert" }, "Task details are unavailable. ", props.error) : null,
      task ? h("div", { className: "space-y-2" },
        h("h3", null, task.title),
        h("p", { className: "text-sm text-muted-foreground" },
          `Board: ${props.selection.board} · ${task.status} · priority ${task.priority}${task.assignee ? ` · ${task.assignee}` : ""}`),
        h("section", null, h("h4", null, "Description"), h("pre", { className: "whitespace-pre-wrap" }, task.body || "No description recorded.")),
        h("section", null, h("h4", null, "Result / latest summary"), h("pre", { className: "whitespace-pre-wrap" }, task.result || task.latest_summary || "No result recorded.")),
        task.source_url
          ? h("a", { href: task.source_url, target: "_blank", rel: "noopener noreferrer" }, "Open related Slack")
          : h("p", { className: "text-sm text-muted-foreground" }, "Slack source not recorded"),
        h("section", null, h("h4", null, "Direct child tasks"),
          children.length ? h("ul", null, children.map(function (child) {
            return h("li", { key: child.id }, `${child.title} · ${child.status}${child.latest_summary ? ` · ${child.latest_summary}` : ""}`);
          })) : h("p", { className: "text-sm text-muted-foreground" }, "No direct child tasks."))) : null);
  }

  function WorkPortfolio() {
    const [data, setData] = useState(null);
    const [error, setError] = useState(null);
    const [selection, setSelection] = useState(null);
    const [detail, setDetail] = useState(null);
    const [detailError, setDetailError] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const detailRequestRef = useRef(0);
    const load = useCallback(function () {
      setError(null);
      return SDK.fetchJSON(API).then(setData).catch(function (err) {
        setError({ details: errorDetails(err), kanbanPluginMissing: missingKanbanPlugin(err) });
      });
    }, []);
    useEffect(function () { load(); }, [load]);
    const selectTask = useCallback(function (task, board) {
      const request = ++detailRequestRef.current;
      setSelection({ id: task.id, board: board });
      setDetail(null);
      setDetailError(null);
      setDetailLoading(true);
      SDK.fetchJSON(`/api/plugins/kanban/tasks/${encodeURIComponent(task.id)}?board=${encodeURIComponent(board)}`)
        .then(function (response) {
          if (detailRequestRef.current === request) setDetail(response);
        })
        .catch(function (err) {
          if (detailRequestRef.current === request) setDetailError(errorDetails(err));
        })
        .finally(function () {
          if (detailRequestRef.current === request) setDetailLoading(false);
        });
    }, []);
    const closeDetail = useCallback(function () {
      detailRequestRef.current += 1;
      setSelection(null); setDetail(null); setDetailError(null); setDetailLoading(false);
    }, []);
    if (error) return h("section", { role: "alert", className: "p-4" },
      h("h1", { className: "text-lg font-semibold" }, "Work Portfolio cannot load"),
      error.kanbanPluginMissing
        ? h("p", null, "Work Portfolio requires the Kanban dashboard plugin to be enabled.")
        : h("p", null, "The portfolio overview request failed. Check the error details and try again."),
      h("details", { className: "mt-2" },
        h("summary", null, "Technical details"),
        h("pre", { className: "mt-2 whitespace-pre-wrap" }, error.details)),
      h(Button, { type: "button", className: "mt-3", onClick: load }, "Retry"));
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
      h(TaskDetail, { selection: selection, detail: detail, error: detailError, loading: detailLoading, onClose: closeDetail }),
      (data.boards || []).map(function (board) { return h(Board, { key: board.slug, board: board, onSelect: selectTask }); }));
  }

  registry.register("work-portfolio", WorkPortfolio);
}());
