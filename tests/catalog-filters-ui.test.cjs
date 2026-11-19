const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const settle = () => new Promise(setImmediate);
const response = (data) => ({ ok: true, json: async () => data });
const catalogPage = (id) => response({
    data: [{ id, title: `Anime ${id}` }],
    has_next_page: true,
});

async function browser() {
    const elements = new Map();
    function element(id) {
        if (!elements.has(id)) elements.set(id, {
            value: "", innerHTML: "",
            classList: { add() {}, remove() {}, toggle() {}, contains() { return true; } },
            setAttribute() {}, addEventListener() {}, focus() {},
        });
        return elements.get(id);
    }
    const calls = [];
    let catalogResponse = () => catalogPage(1);
    const context = vm.createContext({
        document: {
            getElementById: element,
            querySelectorAll: (selector) => [".prev", ".next"].includes(selector) ? [element(selector)] : [],
            addEventListener() {}, body: { dataset: {} },
        },
        window: { scrollTo() {}, location: { hash: "" } },
        localStorage: { getItem() { return null; } }, URLSearchParams,
        fetch: async (url) => {
            if (url === "/api/auth/me") return { ok: false, status: 401 };
            const request = new URL(url, "http://localhost");
            assert.match(request.pathname, /^\/api\/catalog\//);
            calls.push({ endpoint: request.pathname, ...Object.fromEntries(request.searchParams) });
            return catalogResponse();
        },
    });
    for (const script of ["ratings/library.js", "script.js"]) {
        vm.runInContext(fs.readFileSync(path.join(__dirname, "../static", script), "utf8"), context);
    }
    await settle();
    return {
        element, calls,
        replyWith(handler) { catalogResponse = handler; },
        evaluate: (code) => vm.runInContext(code, context),
        change(id, value) {
            const control = element(id);
            control.value = value;
            return control.onchange();
        },
    };
}

test("filters combine with a title, keep their values on paging and retry, and reset the page", async () => {
    const ui = await browser();
    assert.equal(ui.calls.at(-1).endpoint, "/api/catalog/top");
    await ui.change("filter-genre", "Sci-Fi");
    assert.deepEqual(ui.calls.at(-1), {
        endpoint: "/api/catalog/search", page: "1", limit: "25", genre: "Sci-Fi",
    });
    ui.element("search").value = "Cowboy Bebop";
    await ui.change("filter-year", "1998");
    await ui.change("filter-format", "TV");
    const criteria = {
        endpoint: "/api/catalog/search", page: "1", limit: "25",
        q: "Cowboy Bebop", genre: "Sci-Fi", year: "1998", format: "TV",
    };
    assert.deepEqual(ui.calls.at(-1), criteria);

    ui.replyWith(() => { throw new Error("Offline"); });
    await ui.element(".next").onclick();
    const secondPage = { ...criteria, page: "2" };
    assert.deepEqual(ui.calls.at(-1), secondPage);
    ui.replyWith(() => catalogPage(2));
    await ui.element("retry").onclick();
    assert.deepEqual(ui.calls.at(-1), secondPage);
    assert.match(ui.element("grid").innerHTML, /Anime 2/);

    ui.element("search").value = "Space";
    await ui.element("search-btn").onclick();
    assert.deepEqual(ui.calls.at(-1), { ...criteria, q: "Space" });
    await ui.element(".next").onclick();
    await ui.change("filter-genre", "Action");
    assert.deepEqual(ui.calls.at(-1), { ...criteria, q: "Space", genre: "Action" });
    await ui.element(".next").onclick();
    await ui.element("clear-filters").onclick();
    assert.deepEqual(ui.calls.at(-1), {
        endpoint: "/api/catalog/search", page: "1", limit: "25", q: "Space",
    });
    assert.equal(ui.element("clear-filters").disabled, true);
});

test("filter controls stay in All Anime and stale results cannot replace a filtered empty state", async () => {
    const ui = await browser();
    let resolveOld;
    ui.replyWith(() => new Promise((resolve) => { resolveOld = resolve; }));
    const oldRequest = ui.change("filter-genre", "Action");
    ui.replyWith(() => response({ data: [], has_next_page: false }));
    await ui.change("filter-genre", "Comedy");
    resolveOld(catalogPage(9));
    await oldRequest;
    assert.match(ui.element("grid").innerHTML, /No anime matched these filters/);
    assert.equal(ui.element(".next").disabled, true);

    ui.evaluate('currentUsername = "test"; ratingsReady = true; favoritesReady = true;');
    ui.element("my-ratings").onclick();
    assert.equal(ui.element("catalog-filters").hidden, true);
    ui.element("favorites").onclick();
    assert.equal(ui.element("catalog-filters").hidden, true);
    ui.element("all-anime").onclick();
    assert.equal(ui.element("catalog-filters").hidden, false);
    assert.equal(ui.element("filter-genre").value, "Comedy");
});
