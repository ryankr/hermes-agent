import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";


const entry = new URL("../plugins/work-portfolio/dashboard/dist/index.js", import.meta.url);

async function loadPortfolioPlugin({ data = null } = {}) {
  const registered = [];
  const h = () => null;
  const sdk = {
    React: { createElement: h },
    components: { Card: "Card", CardContent: "CardContent", Badge: "Badge", Button: "Button" },
    hooks: {
      useCallback: (fn) => fn,
      useEffect: () => {},
      useState: () => [data, () => {}],
    },
    fetchJSON: () => Promise.resolve(data),
  };
  const window = {
    __HERMES_PLUGIN_SDK__: sdk,
    __HERMES_PLUGINS__: { register: (...args) => registered.push(args) },
  };
  vm.runInNewContext(await readFile(entry, "utf8"), { window });
  return { registered };
}

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
  const { registered } = await loadPortfolioPlugin({ data });

  assert.equal(registered.length, 1);
  assert.equal(registered[0][0], "work-portfolio");
  assert.equal(typeof registered[0][1], "function");
}

await main();
console.log("work portfolio dashboard plugin contract: ok");