import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const entry = new URL("../plugins/kanban/dashboard/dist/index.js", import.meta.url);

async function loadEditor(fetchJSON) {
  const state = [];
  let hook = 0;
  const h = (type, props, ...children) => ({ type, props: props || {}, children: children.flat() });
  const hooks = {};
  const window = {
    __HERMES_KANBAN_TEST_HOOKS__: hooks,
    __HERMES_PLUGIN_SDK__: {
      React: { createElement: h, Component: class {} },
      components: { Card: "Card", CardContent: "CardContent", Badge: "Badge", Button: "button", Input: "input" },
      hooks: {
        useState: (initial) => {
          const index = hook++;
          if (!(index in state)) state[index] = initial;
          return [state[index], (value) => { state[index] = typeof value === "function" ? value(state[index]) : value; }];
        },
        useEffect: () => {}, useCallback: (fn) => fn, useMemo: (fn) => fn(), useRef: (value) => ({ current: value }),
      },
      utils: { cn: (...values) => values.filter(Boolean).join(" "), timeAgo: () => "" },
      fetchJSON,
    },
    __HERMES_PLUGINS__: { register: () => {} },
  };
  vm.runInNewContext(await readFile(entry, "utf8"), { window, URLSearchParams, Promise, console });
  assert.equal(typeof hooks.SourceUrlEditor, "function", "bundle exposes the guarded editor test hook");
  assert.equal(typeof hooks.patchTask, "function", "bundle exposes the guarded patch test hook");
  const find = (node, predicate) => {
    if (node && typeof node === "object" && predicate(node)) return node;
    if (node && typeof node === "object") for (const child of node.children) {
      const result = find(child, predicate);
      if (result) return result;
    }
    return null;
  };
  const text = (node) => node == null ? "" : (typeof node === "string" ? node : node.children.map(text).join(""));
  const render = (onPatch, sourceUrl = "") => {
    hook = 0;
    return hooks.SourceUrlEditor({ task: { id: "task-7", source_url: sourceUrl }, onPatch });
  };
  return { hooks, find, text, render };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

async function main() {
  const requests = [];
  const editor = await loadEditor((url, options) => {
    requests.push({ url, options });
    return Promise.resolve({ task: { source_url: "https://acme.slack.com/archives/C123/p456" } });
  });
  const patch = (body, options) => editor.hooks.patchTask("task-7", "alpha", body).catch((error) => options.onError(error.message));
  let tree = editor.render(patch);
  editor.find(tree, (node) => node.type === "input").props.onChange({ target: { value: " https://acme.slack.com/archives/C123/p456 " } });
  tree = editor.render(patch);
  editor.find(tree, (node) => node.type === "button" && editor.text(node) === "Save").props.onClick();
  await flush();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/plugins/kanban/tasks/task-7?board=alpha");
  assert.equal(requests[0].options.method, "PATCH");
  assert.equal(requests[0].options.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(requests[0].options.body), { source_url: "https://acme.slack.com/archives/C123/p456" });

  tree = editor.render(patch, "https://acme.slack.com/archives/C123/p456");
  editor.find(tree, (node) => node.type === "button" && editor.text(node) === "Clear").props.onClick();
  await flush();
  assert.deepEqual(JSON.parse(requests[1].options.body), { clear_source_url: true });
  const related = editor.find(tree, (node) => node.type === "a" && editor.text(node) === "Open related Slack");
  assert.equal(related.props.href, "https://acme.slack.com/archives/C123/p456");
  assert.equal(related.props.target, "_blank");
  assert.equal(related.props.rel, "noopener noreferrer");

  const rejected = await loadEditor(() => Promise.reject(new Error('422: {"detail":"source_url must be an approved Slack URL"}')));
  const rejectedPatch = (body, options) => rejected.hooks.patchTask("task-7", "alpha", body).catch((error) => options.onError(error.message));
  tree = rejected.render(rejectedPatch);
  rejected.find(tree, (node) => node.type === "input").props.onChange({ target: { value: "https://evil.example/" } });
  tree = rejected.render(rejectedPatch);
  rejected.find(tree, (node) => node.type === "button" && rejected.text(node) === "Save").props.onClick();
  await flush();
  tree = rejected.render(rejectedPatch);
  const error = rejected.find(tree, (node) => node.props.role === "alert");
  assert.ok(error, "rejected source URL renders a field-level alert");
  assert.match(rejected.text(error), /source_url must be an approved Slack URL/);
}

await main();
console.log("kanban Slack source editor contract: ok");
