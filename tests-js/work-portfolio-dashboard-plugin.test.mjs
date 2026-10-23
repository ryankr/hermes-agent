import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";


const entry = new URL("../plugins/work-portfolio/dashboard/dist/index.js", import.meta.url);

async function loadPortfolioPlugin({ fetchJSON }) {
  const registered = [];
  const state = [];
  const effects = [];
  let hook = 0;
  let tree = null;
  const h = (type, props, ...children) => ({ type, props: props || {}, children: children.flat() });
  const sdk = {
    React: { createElement: h },
    components: { Card: "Card", CardContent: "CardContent", Badge: "Badge", Button: "Button" },
    hooks: {
      useCallback: (fn) => fn,
      useEffect: (fn) => effects.push(fn),
      useState: (initial) => {
        const index = hook++;
        if (!(index in state)) state[index] = initial;
        return [state[index], (value) => { state[index] = value; }];
      },
    },
    fetchJSON,
  };
  const window = {
    __HERMES_PLUGIN_SDK__: sdk,
    __HERMES_PLUGINS__: { register: (...args) => registered.push(args) },
  };
  vm.runInNewContext(await readFile(entry, "utf8"), { window });
  function expand(node) {
    if (node == null || typeof node === "string" || typeof node === "number") return node;
    if (typeof node.type === "function") return expand(node.type({ ...node.props, children: node.children }));
    return { ...node, children: node.children.map(expand) };
  }
  function render() {
    hook = 0;
    tree = expand(registered[0][1]());
    return tree;
  }
  function text(node) {
    if (node == null) return "";
    if (typeof node === "string" || typeof node === "number") return String(node);
    return node.children.map(text).join("");
  }
  function find(node, predicate) {
    if (node && typeof node === "object" && predicate(node)) return node;
    if (node && typeof node === "object") {
      for (const child of node.children) {
        const result = find(child, predicate);
        if (result) return result;
      }
    }
    return null;
  }
  return { registered, effects, render, text, find };
}

const flush = () => new Promise((resolve) => setImmediate(resolve));

async function main() {
  const data = {
    outcome: "complete",
    current_board: "default",
    boards: [{
      slug: "alpha",
      counts: { running: 2 },
      focus: {
        running: { tasks: [{ id: "t1", title: "first", status: "running", priority: 1 }], truncated: true },
      },
    }],
  };
  const successful = await loadPortfolioPlugin({
    fetchJSON: (endpoint) => {
      assert.equal(endpoint, "/api/plugins/kanban/overview");
      return Promise.resolve(data);
    },
  });

  assert.equal(successful.registered.length, 1);
  assert.equal(successful.registered[0][0], "work-portfolio");
  successful.render();
  successful.effects[0]();
  await flush();
  assert.match(successful.text(successful.render()), /Work Portfolio/);
  assert.match(successful.text(successful.render()), /first/);

  let retries = 0;
  const unavailable = await loadPortfolioPlugin({
    fetchJSON: () => {
      retries += 1;
      return Promise.reject({ status: 404, message: "Not Found" });
    },
  });
  unavailable.render();
  unavailable.effects[0]();
  await flush();
  let rendered = unavailable.render();
  assert.match(unavailable.text(rendered), /requires the Kanban dashboard plugin to be enabled/i);
  assert.match(unavailable.text(rendered), /Not Found/);
  const retry = unavailable.find(rendered, (node) => node.type === "Button" && unavailable.text(node) === "Retry");
  assert.ok(retry, "unavailable state exposes a retry control");
  await retry.props.onClick();
  assert.equal(retries, 2);

  const serverFailure = await loadPortfolioPlugin({
    fetchJSON: () => Promise.reject({ status: 503, message: "Service Unavailable" }),
  });
  serverFailure.render();
  serverFailure.effects[0]();
  await flush();
  assert.doesNotMatch(serverFailure.text(serverFailure.render()), /requires the Kanban dashboard plugin to be enabled/i);
  assert.match(serverFailure.text(serverFailure.render()), /Service Unavailable/);
}

await main();
console.log("work portfolio dashboard plugin contract: ok");