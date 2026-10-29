const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

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
    let account = null;
    let fail = false;
    let expire = false;
    let pauseNext = false;
    let resume;
    const saved = new Map();
    const calls = [];
    const context = vm.createContext({
        document: { getElementById: element, querySelectorAll: () => [], addEventListener() {}, body: { dataset: {} } },
        window: { scrollTo() {}, location: { hash: "" } }, URLSearchParams,
        localStorage: { getItem() { return null; }, setItem() { throw new Error("Ratings must use the API"); } },
        fetch: async (url, options = {}) => {
            calls.push({ url, options });
            const response = (status, data) => ({ status, ok: status < 400, json: async () => data });
            if (url === "/api/auth/me") return response(401, {});
            if (url.startsWith("/api/catalog/")) return response(200, {
                data: [1, 2].map((id) => ({ id, anilist_id: id, title: `Anime ${id}`, score: 8.9, synopsis: "Synopsis" })),
            });
            if (url === "/api/favorites") return response(200, { data: [] });
            if (url === "/api/ratings" || url === "/api/ratings/library") {
                const owner = account;
                const rows = [...saved].filter(([key]) => key.startsWith(`${owner}:`)).map(([key, rating]) => {
                    const id = Number(key.split(":")[1]);
                    return url.endsWith("library") ? { id: id + 100, anilist_id: id, title: `Anime ${id}`, score: 8.9, rating } : { anime_id: id, rating };
                });
                if (pauseNext) { pauseNext = false; await new Promise((resolve) => { resume = resolve; }); }
                if (!owner || expire) return response(401, {});
                if (fail) throw new Error("Offline");
                return response(200, { data: rows });
            }
            if (url.startsWith("/api/ratings/")) {
                const owner = account;
                const id = Number(url.split("/").pop());
                const key = `${owner}:${id}`;
                const value = saved.get(key) ?? null;
                if (pauseNext) {
                    pauseNext = false;
                    await new Promise((resolve) => { resume = resolve; });
                }
                if (!owner || expire) return response(401, {});
                if (fail) throw new Error("Offline");
                if (options.method === "PUT") saved.set(key, JSON.parse(options.body).rating);
                if (options.method === "DELETE") saved.delete(key);
                return response(200, { anime_id: id, rating: value });
            }
            throw new Error(`Unexpected URL: ${url}`);
        },
    });
    const evaluate = (code) => vm.runInContext(code, context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../static/ratings/library.js"), "utf8"), context);
    evaluate(fs.readFileSync(path.join(__dirname, "../static/script.js"), "utf8"));
    await settle();
    return {
        evaluate, calls, saved, element,
        async login(name) { account = name; await evaluate(`setAuthState(${JSON.stringify(name)})`); await settle(); },
        async open(index = 0) { evaluate(`window.openModal(${index})`); await settle(); },
        async save(value) { element("rating-input").value = value; await evaluate("saveRating(false)"); },
        remove: () => evaluate("saveRating(true)"),
        fail(value = true) { fail = value; }, expire() { expire = true; },
        pause() { pauseNext = true; },
        async resume() { resume(); await settle(); },
    };
}

test("guests see login guidance and AniList scores stay separate from personal ratings", async () => {
    const ui = await browser();
    await ui.open();
    assert.match(ui.element("modal-content").innerHTML, /AniList score:.*8.9/);
    assert.match(ui.element("modal-rating").innerHTML, /Your rating.*Log in to rate/s);
    assert.equal(ui.calls.filter(({ url }) => url.startsWith("/api/ratings/")).length, 0);
});

test("rating creation, editing, removal, reopening, and account switching use the API", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.open();
    assert.match(ui.element("modal-rating").innerHTML, /Not rated yet/);
    const dropdown = ui.element("modal-rating").innerHTML;
    assert.match(dropdown, /<select id="rating-input"/);
    assert.match(dropdown, /<option value="">Select<\/option>/);
    assert.equal((dropdown.match(/<option /g) || []).length, 11);
    assert.match(dropdown, /\(10\) Masterpiece/);
    assert.match(dropdown, /\(1\) Appalling/);
    await ui.save("10");
    assert.equal(ui.saved.get("first:1"), 10);
    assert.match(ui.element("modal-rating").innerHTML, /10\/10.*Rating saved/s);
    await ui.save("1");
    await ui.open();
    assert.equal(ui.evaluate("ratingState.value"), 1);
    assert.match(ui.element("modal-rating").innerHTML, /<option value="1" selected>\(1\) Appalling/);
    await ui.login("second");
    assert.equal(ui.evaluate("ratingState.value"), null);
    await ui.save("5");
    await ui.login("first");
    assert.equal(ui.evaluate("ratingState.value"), 1);
    await ui.remove();
    assert.match(ui.element("modal-rating").innerHTML, /Rating removed/);
    await ui.open();
    assert.equal(ui.evaluate("ratingState.value"), null);
    assert.equal(ui.saved.get("second:1"), 5);
    assert.equal(ui.evaluate("visibleAnime[0].score"), 8.9);
    const write = ui.calls.find(({ options }) => options.method === "PUT");
    assert.equal(write.options.headers["X-Requested-With"], "AnimeRater");
    assert.equal(write.options.credentials, "same-origin");
});

test("invalid input and failed writes preserve the saved rating and show errors", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.open();
    await ui.save("7");
    const count = ui.calls.length;
    for (const value of ["", "0", "11", "1.5", "invalid"]) {
        await ui.save(value);
        assert.match(ui.element("modal-rating").innerHTML, /Enter a whole number/);
    }
    assert.equal(ui.calls.length, count);
    ui.fail();
    await ui.save("8");
    assert.equal(ui.evaluate("ratingState.value"), 7);
    assert.equal(ui.evaluate("ratingState.draft"), "8");
    assert.match(ui.evaluate("ratingState.error"), /Couldn't save/);
    await ui.remove();
    assert.equal(ui.evaluate("ratingState.value"), 7);
    assert.match(ui.evaluate("ratingState.error"), /Couldn't remove/);
    ui.fail(false);
    await ui.save("8");
    assert.equal(ui.evaluate("ratingState.value"), 8);
});

test("failed loads offer retry and session expiry clears the personal rating", async () => {
    const ui = await browser();
    await ui.login("first");
    ui.fail();
    await ui.open();
    assert.match(ui.evaluate("ratingState.error"), /Couldn't load/);
    assert.match(ui.element("modal-rating").innerHTML, /Try again/);
    assert.notEqual(ui.evaluate("ratingState.loaded"), true);
    ui.fail(false);
    await ui.element("rating-retry").onclick();
    await ui.save("6");
    ui.expire();
    await ui.remove();
    assert.equal(ui.evaluate("currentUsername"), null);
    assert.match(ui.element("modal-rating").innerHTML, /Log in to rate/);
});

test("late reads cannot overwrite another anime or a closed modal", async () => {
    const ui = await browser();
    await ui.login("first");
    ui.saved.set("first:1", 9);
    ui.saved.set("first:2", 4);
    ui.pause();
    await ui.open();
    await ui.open(1);
    await ui.resume();
    assert.equal(ui.evaluate("ratingState.value"), 4);
    ui.pause();
    await ui.open();
    ui.evaluate("closeAnimeModal()");
    await ui.open(1);
    await ui.resume();
    assert.equal(ui.evaluate("ratingState.value"), 4);
});

test("late writes cannot put the previous account's rating into the current modal", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.open();
    ui.pause();
    const save = ui.save("9");
    assert.equal(ui.evaluate("ratingState.saving"), true);
    await ui.login("second");
    await ui.resume();
    await save;
    assert.equal(ui.evaluate("ratingState.value"), null);
    assert.equal(ui.saved.get("first:1"), 9);
});


test("My Ratings includes off-page anime, searches titles, and sorts personal scores", async () => {
    const ui = await browser();
    ui.saved.set("first:23", 3);
    ui.saved.set("first:7", 10);
    ui.saved.set("first:11", 6);
    await ui.login("first");
    ui.evaluate('setView("ratings")');
    await settle();
    assert.equal(ui.evaluate('visibleAnime.map(ratingId).join(",")'), "7,11,23");
    assert.match(ui.element("grid").innerHTML, /Your rating: 10\/10/);
    assert.match(ui.element("grid").innerHTML, /AniList:.*8.9/);
    ui.element("ratings-sort").value = "lowest";
    ui.element("ratings-sort").onchange();
    assert.equal(ui.evaluate('visibleAnime.map(ratingId).join(",")'), "23,11,7");
    ui.element("search").value = "ANIME 11";
    ui.evaluate("runSearch()");
    assert.equal(ui.evaluate("visibleAnime.length"), 1);
    assert.equal(ui.evaluate("ratingId(visibleAnime[0])"), 11);
    ui.element("search").value = "missing";
    ui.evaluate("runSearch()");
    assert.match(ui.element("grid").innerHTML, /No matching titles/);
    ui.element("ratings-clear").onclick();
    assert.equal(ui.evaluate("visibleAnime.length"), 3);
    await ui.open();
    await ui.save("9");
    assert.equal(ui.evaluate('visibleAnime.map(ratingId).join(",")'), "11,23,7");
    await ui.remove();
    assert.equal(ui.evaluate('visibleAnime.map(ratingId).join(",")'), "11,7");
    await ui.login("second");
    assert.match(ui.element("grid").innerHTML, /No ratings yet/);
});

test("My Ratings handles loading, retry, and stale account responses", async () => {
    const ui = await browser();
    ui.evaluate('setView("ratings")');
    assert.equal(ui.evaluate("view"), "all");
    ui.saved.set("first:1", 8);
    await ui.login("first");
    ui.pause();
    ui.evaluate('setView("ratings")');
    assert.match(ui.element("grid").innerHTML, /Loading your rated anime/);
    await ui.login("second");
    await ui.resume();
    assert.match(ui.element("grid").innerHTML, /No ratings yet/);
    ui.fail();
    await ui.evaluate("loadPersonalRatings(true)");
    assert.match(ui.element("grid").innerHTML, /Couldn&#39;t load your ratings/);
    ui.fail(false);
    await ui.element("ratings-retry").onclick();
    assert.match(ui.element("grid").innerHTML, /No ratings yet/);
});

test("cards and lists update when a rating save finishes after closing the modal", async () => {
    const ui = await browser();
    await ui.login("first");
    await ui.open();
    ui.pause();
    const save = ui.save("9");
    ui.evaluate("closeAnimeModal()");
    await ui.resume();
    await save;
    assert.match(ui.element("grid").innerHTML, /Your rating: 9\/10/);
    ui.evaluate('setView("ratings")');
    await settle();
    assert.equal(ui.evaluate("visibleAnime.length"), 1);
});
