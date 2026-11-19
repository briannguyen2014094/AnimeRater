const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const settle = () => new Promise(setImmediate);

async function browser() {
    const elements = new Map();
    const element = (id) => {
        if (!elements.has(id)) elements.set(id, {
            hidden: true, value: "", textContent: "", innerHTML: "",
            classList: { add() {}, remove() {}, toggle() {}, contains() { return true; } },
            setAttribute() {}, addEventListener() {}, focus() {}, reset() {},
            querySelectorAll() { return []; },
        });
        return elements.get(id);
    };
    const catalog = [
        { id: 1, anilist_id: 101, title: "Known total", episodes: 12, synopsis: "Synopsis" },
        { id: 2, anilist_id: 202, title: "Unknown total", episodes: null, synopsis: "Synopsis" },
    ];
    const calls = [];
    const accounts = new Map();
    let account;
    let holdWrite;
    const context = vm.createContext({
        document: { getElementById: element, querySelectorAll: () => [], addEventListener() {}, body: { dataset: {} } },
        window: { scrollTo() {}, location: { hash: "" } }, URLSearchParams,
        localStorage: { getItem: () => null },
        fetch: async (url, options = {}) => {
            calls.push({ url, options });
            const response = (status, data) => ({ status, ok: status < 400, json: async () => data });
            if (url === "/api/auth/me") return response(401, {});
            if (url.startsWith("/api/catalog/")) return response(200, { data: catalog });
            if (url === "/api/favorites" || url === "/api/ratings") return response(200, { data: [] });
            if (url.startsWith("/api/ratings/")) return response(200, { rating: null });
            const entries = accounts.get(account);
            if (url === "/api/watchlist") return response(200, { data: [...entries.values()] });
            const [, id, progress] = url.match(/^\/api\/watchlist\/(\d+)(\/progress)?$/);
            const anime = catalog.find((item) => item.anilist_id === Number(id));
            if (holdWrite) await holdWrite;
            if (options.method === "DELETE") {
                entries.delete(id);
                return response(204);
            }
            const entry = { ...entries.get(id) };
            if (progress) {
                entry.episodes_watched = options.method === "POST" ? entry.episodes_watched + 1
                    : JSON.parse(options.body).episodes_watched;
            } else {
                Object.assign(entry, anime, { status: JSON.parse(options.body).status });
                entry.episodes_watched ??= 0;
            }
            entries.set(id, entry);
            return response(200, entry);
        },
    });
    const evaluate = (code) => vm.runInContext(code, context);
    for (const file of ["ratings/library.js", "script.js"]) {
        evaluate(fs.readFileSync(path.join(__dirname, "../static", file), "utf8"));
    }
    await settle();
    return {
        element, evaluate, calls,
        async login(name) {
            account = name;
            if (!accounts.has(name)) accounts.set(name, new Map());
            await evaluate(`setAuthState(${JSON.stringify(name)})`);
        },
        async open(index) { evaluate(`window.openModal(${index})`); await settle(); },
        async submit(form) { element(form).onsubmit({ preventDefault() {} }); await settle(); },
        pauseWrite() {
            let release;
            holdWrite = new Promise((resolve) => { release = resolve; });
            return () => { holdWrite = null; release(); };
        },
    };
}

test("the watchlist guides guests and has a browse action when empty", async () => {
    const ui = await browser();
    ui.element("my-watchlist").onclick();
    assert.match(ui.element("auth-notice").textContent, /Log in or sign up to see your watchlist/);
    await ui.open(0);
    assert.match(ui.element("modal-watchlist").innerHTML, /Log in to track this anime/);
    assert.equal(ui.calls.some(({ url }) => url === "/api/watchlist"), false);
    await ui.login("viewer");
    ui.evaluate("closeAnimeModal()");
    ui.element("my-watchlist").onclick();
    assert.match(ui.element("grid").innerHTML, /Your watchlist is empty/);
    ui.element("browse-anime").onclick();
    assert.equal(ui.evaluate("view"), "all");
});

test("the details dialog tracks progress and watchlist cards regroup and update", async () => {
    const ui = await browser();
    await ui.login("viewer");
    await ui.open(0);
    ui.element("watchlist-status-input").value = "watching";
    await ui.submit("watchlist-status-form");
    assert.match(ui.element("modal-watchlist").innerHTML, /0 \/ 12 episodes/);
    await ui.element("watchlist-increment").onclick();
    assert.match(ui.element("modal-watchlist").innerHTML, /1 \/ 12 episodes/);
    const count = ui.element("watchlist-count");
    count.value = "13";
    count.valueAsNumber = 13;
    await ui.submit("watchlist-progress-form");
    assert.match(ui.element("modal-watchlist").innerHTML, /whole number from 0 to 12/);
    assert.equal(ui.calls.some(({ url, options }) => url.endsWith("/progress") && options.method === "PUT"), false);
    count.value = "12";
    count.valueAsNumber = 12;
    await ui.submit("watchlist-progress-form");
    assert.match(ui.element("modal-watchlist").innerHTML, /id="watchlist-increment" type="button" disabled/);
    assert.match(ui.element("modal-watchlist").innerHTML, /value="watching" selected/);
    assert.ok(ui.calls.some(({ url }) => url === "/api/watchlist/101/progress"));

    await ui.open(1);
    ui.element("watchlist-status-input").value = "plan_to_watch";
    await ui.submit("watchlist-status-form");
    ui.evaluate("closeAnimeModal()");
    ui.element("my-watchlist").onclick();
    const grid = ui.element("grid");
    assert.match(grid.innerHTML, /Plan to Watch.*Unknown total.*0 watched.*Watching.*Known total.*12 \/ 12 episodes/s);
    await ui.open(1);
    ui.element("watchlist-status-input").value = "completed";
    await ui.submit("watchlist-status-form");
    assert.match(grid.innerHTML, /Completed.*12 \/ 12 episodes/s);
    assert.doesNotMatch(grid.innerHTML, /id="watchlist-watching"/);
    await ui.element("watchlist-remove").onclick();
    assert.doesNotMatch(grid.innerHTML, /Known total/);
});

test("a pending write from a previous account cannot populate the current watchlist", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.open(0);
    const releaseWrite = ui.pauseWrite();
    ui.element("watchlist-status-input").value = "dropped";
    ui.element("watchlist-status-form").onsubmit({ preventDefault() {} });
    await ui.login("second");
    releaseWrite();
    await settle();
    assert.match(ui.element("modal-watchlist").innerHTML, /Add to watchlist/);
    ui.element("my-watchlist").onclick();
    assert.match(ui.element("grid").innerHTML, /Your watchlist is empty/);
});
