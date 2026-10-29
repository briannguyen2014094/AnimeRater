const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

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
    let account = null;
    let failSave = false;
    let expire = false;
    const saved = new Map();
    const calls = [];
    const context = vm.createContext({
        document: { getElementById: element, querySelectorAll: () => [], addEventListener() {}, body: { dataset: {} } },
        window: { scrollTo() {}, location: { hash: "" } }, URLSearchParams,
        localStorage: {
            getItem: (key) => key === "favoriteAnimeIds" ? "[99]" : null,
            setItem() { throw new Error("Favorites must not use localStorage"); },
        },
        fetch: async (url, options = {}) => {
            calls.push({ url, options });
            const response = (status, data) => ({ status, ok: status < 400, json: async () => data });
            if (url === "/api/auth/me") return response(401, {});
            if (url.startsWith("/api/catalog/")) return response(200, { data: [{ id: 1, title: "Cowboy Bebop" }] });
            if (url === "/api/ratings") return response(200, { data: [] });
            if (url.startsWith("/api/favorites")) {
                if (!account || expire) return response(401, {});
                const favorites = saved.get(account) || [];
                if (!options.method) return response(200, { data: favorites });
                if (failSave) throw new Error("Offline");
                if (options.method === "POST") saved.set(account, [JSON.parse(options.body)]);
                if (options.method === "DELETE") saved.set(account, []);
                return response(204, {});
            }
            throw new Error(`Unexpected URL: ${url}`);
        },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/ratings/library.js"), "utf8"), context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/script.js"), "utf8"), context);
    await new Promise(setImmediate);
    return {
        evaluate: (code) => vm.runInContext(code, context), calls, saved, element,
        async login(name) { account = name; await vm.runInContext(`setAuthState(${JSON.stringify(name)})`, context); },
        failSave() { failSave = true; }, expire() { expire = true; },
        click: () => vm.runInContext('window.addToFavorites({ stopPropagation() {} }, document.getElementById("heart"), 0)', context),
    };
}

test("guests cannot load legacy favorites or save anime and receive a login prompt", async () => {
    const ui = await browser();
    assert.equal(ui.evaluate("favorites.size"), 0);
    await ui.click();
    assert.match(ui.element("auth-notice").textContent, /Log in or sign up/);
    assert.equal(ui.calls.filter(({ url }) => url.startsWith("/api/favorites")).length, 0);
});

test("favorites save through the API, survive login, and stay isolated between accounts", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.click();
    assert.equal(ui.evaluate("favorites.has(1)"), true);
    await ui.evaluate("setAuthState(null)");
    assert.equal(ui.evaluate("favorites.size"), 0);
    await ui.login("second");
    assert.equal(ui.evaluate("favorites.size"), 0);
    await ui.login("first");
    assert.equal(ui.evaluate("favorites.has(1)"), true);
    await ui.click();
    assert.equal(ui.evaluate("favorites.size"), 0);
    assert.equal(ui.saved.get("first").length, 0);
});

test("failed writes never show an unsaved favorite as saved", async () => {
    const ui = await browser();
    await ui.login("first");
    ui.failSave();
    await ui.click();
    assert.equal(ui.evaluate("favorites.size"), 0);
    assert.match(ui.element("storage-notice").textContent, /Couldn't save/);
});

test("an expired session clears favorites and prompts for login", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.click();
    ui.expire();
    await ui.click();
    assert.equal(ui.evaluate("currentUsername"), null);
    assert.equal(ui.evaluate("favorites.size"), 0);
    assert.match(ui.element("auth-notice").textContent, /Log in or sign up/);
});
