"use strict";

let page = 1;
let animeList = [];
let visibleAnime = [];
let view = "all";
let loading = false;
let catalogError = false;
let errorMessage = "";
let activeQuery = "";
let hasMore = true;
const PAGE_SIZE = 25;
const favorites = new Set();
const favoriteDetails = new Map();
let currentUsername = null;
let authVersion = 0;
let favoritesReady = false;
let favoriteSaving = false;
let favoritesRequest = 0;

const $ = (id) => document.getElementById(id);
const grid = $("grid"), pageNum = document.querySelectorAll(".page"), prev = document.querySelectorAll(".prev"), next = document.querySelectorAll(".next"), modal = $("modal"), modalContent = $("modal-content");
const pagination = document.querySelectorAll(".pagination-top, .pagination-bottom");
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const validId = (id) => (typeof id === "number" || typeof id === "string") && String(id).trim() !== "" && Number.isSafeInteger(Number(id)) && Number(id) > 0;

function storageNotice(message) {
    $("storage-notice").textContent = message;
    $("storage-notice").hidden = false;
}

function animeDetails(anime) {
    return {
        id: Number(anime.id),
        // the AniList id, used to fetch the synopsis the list payloads leave out
        anilist_id: Number.isSafeInteger(Number(anime.anilist_id)) && Number(anime.anilist_id) > 0 ? Number(anime.anilist_id) : null,
        title: anime.title,
        image_url: typeof anime.image_url === "string" ? anime.image_url : "",
        score: Number.isFinite(anime.score) ? anime.score : null,
        episodes: Number.isInteger(anime.episodes) && anime.episodes >= 0 ? anime.episodes : null,
        genres: Array.isArray(anime.genres) ? anime.genres.filter((genre) => typeof genre === "string") : [],
        synopsis: typeof anime.synopsis === "string" ? anime.synopsis : "",
    };
}

async function loadFavorites(version = authVersion) {
    const request = ++favoritesRequest;
    try {
        const res = await authFetch("/api/favorites");
        if (version !== authVersion || request !== favoritesRequest) return;
        if (res.status === 401) {
            await setAuthState(null);
            return;
        }
        if (!res.ok) throw new Error("Favorites unavailable");
        const json = await res.json();
        if (version !== authVersion || request !== favoritesRequest) return;
        favorites.clear();
        favoriteDetails.clear();
        for (const anime of json.data) {
            if (!anime || !validId(anime.id)) continue;
            const id = Number(anime.id);
            favorites.add(id);
            if (typeof anime.title === "string" && anime.title.trim()) {
                favoriteDetails.set(id, animeDetails(anime));
            }
        }
        favoritesReady = true;
        $("storage-notice").hidden = true;
    } catch {
        if (version !== authVersion || request !== favoritesRequest) return;
        storageNotice("Couldn't load your favorites. Select Favorites to try again.");
    }
    render();
}

function scrollToTop() {
    window.scrollTo(0, 0);
}

// The API distinguishes a temporary throttle (503 + Retry-After) from a real
// upstream fault (502), so say which one happened instead of a generic failure.
async function describeFailure(res) {
    try {
        const body = await res.json();
        if (res.status === 503) {
            const retry = res.headers.get("retry-after");
            return retry
                ? `AniList is rate limiting requests right now. Try again in about ${retry} seconds.`
                : "AniList is rate limiting requests right now. Try again in a moment.";
        }
        return typeof body.detail === "string" && body.detail
            ? body.detail
            : "Something went wrong talking to AniList.";
    } catch {
        return "Something went wrong talking to AniList.";
    }
}

function renderFavoriteCount() {
    $("favorites").textContent = `Favorites (${favorites.size})`;
}

function render() {
    pagination.forEach((controls) => { controls.hidden = view !== "all"; });
    grid.setAttribute("aria-busy", String(view === "ratings" ? ratingsLoading : loading));
    $("all-anime").setAttribute("aria-pressed", String(view === "all"));
    $("favorites").setAttribute("aria-pressed", String(view === "favorites"));
    $("my-ratings").setAttribute("aria-pressed", String(view === "ratings"));
    $("ratings-controls").hidden = view !== "ratings";
    $("search").placeholder = view === "ratings" ? "Search your rated anime..." : "Search anime...";
    $("ratings-status").textContent = view === "ratings" && !ratingsLoading && !ratingsError && ratingsReady
        ? `${filteredRatings().length} rated anime` : "";
    renderFavoriteCount();
    pageNum.forEach((label) => { label.textContent = `Page ${page}`; });
    prev.forEach((button) => { button.disabled = loading || page <= 1; });
    next.forEach((button) => { button.disabled = loading || !hasMore; });
    visibleAnime = view === "favorites"
        ? [...favorites].map((id) => favoriteDetails.get(id) || { id, title: `Saved anime #${id}`, unresolved: true })
        : view === "ratings" ? filteredRatings() : animeList;
    if (view === "ratings" && (ratingsLoading || ratingsError || !ratingsReady)) {
        grid.innerHTML = ratingsLoading
            ? '<p class="empty-state" role="status">Loading your rated anime…</p>'
            : `<div class="empty-state"><p role="alert">${escapeHtml(ratingsError || "Your ratings have not loaded.")}</p><button id="ratings-retry" type="button">Try again</button></div>`;
        if (!ratingsLoading) $("ratings-retry").onclick = () => loadPersonalRatings(true);
        return;
    }
    if (view === "ratings" && !visibleAnime.length) {
        grid.innerHTML = ratedAnime.length
            ? '<div class="empty-state"><h2>No matching titles</h2><p>Try another title or clear your search.</p><button id="ratings-clear" type="button">Clear search</button></div>'
            : '<div class="empty-state"><h2>No ratings yet</h2><p>Open an anime and choose Your rating to start your list.</p><button id="browse-anime" type="button">Browse anime</button></div>';
        if (ratedAnime.length) $("ratings-clear").onclick = () => { ratingsQuery = ""; $("search").value = ""; render(); $("search").focus(); };
        else $("browse-anime").onclick = () => { setView("all"); $("all-anime").focus(); };
        return;
    }
    if (view === "all" && catalogError) {
        const fallback = activeQuery ? "We couldn’t run that search. Please try again." : "We couldn’t load the catalog. Please try again.";
        grid.innerHTML = `<div class="empty-state"><p>${escapeHtml(errorMessage || fallback)}</p><button id="retry" type="button">Try again</button></div>`;
        $("retry").onclick = () => (activeQuery ? search(activeQuery, page) : load(page));
        return;
    }
    // While paging, keep the cards already on screen. Replacing them with a one-line
    // "Loading..." message collapses the page height and reads as a full-site flash.
    if (view === "all" && loading && !visibleAnime.length) {
        grid.innerHTML = "<p>Loading...</p>";
        return;
    }
    if (view === "favorites" && !favoritesReady) {
        grid.innerHTML = '<div class="empty-state"><p>Your favorites are not loaded yet. Select Favorites to try again.</p></div>';
        return;
    }
    if (view === "favorites" && !favorites.size) {
        grid.innerHTML = '<div class="empty-state"><h2>No favorites yet</h2><p>Save anime with the heart button to find them here.</p><button id="browse-anime" type="button">Browse anime</button></div>';
        $("browse-anime").onclick = () => { setView("all"); $("all-anime").focus(); };
        return;
    }
    if (view === "all" && activeQuery && !visibleAnime.length) {
        // nothing on page 1 means the query found nothing
        if (page > 1) {
            grid.innerHTML = '<div class="empty-state"><h2>No more results</h2><p>That was the last page for this search.</p><button id="search-back" type="button">Previous page</button></div>';
            $("search-back").onclick = () => search(activeQuery, page - 1);
        } else {
            grid.innerHTML = '<div class="empty-state"><h2>No results</h2><p>Nothing matched that search. Try a different title.</p><button id="clear-search" type="button">Clear search</button></div>';
            $("clear-search").onclick = () => { $("search").value = ""; activeQuery = ""; load(1); };
        }
        return;
    }
    grid.innerHTML = visibleAnime.map((a, i) => `
        <article class="card" onclick="openModal(${i})">
          <div class="poster">
            ${a.image_url ? `<img src="${escapeHtml(a.image_url)}" alt="${escapeHtml(a.title)}" loading="lazy">` : ""}
            <span class="score-badge">AniList: <span class="star">★</span> ${escapeHtml(a.score ?? "N/A")}</span>
            <button class="favorite-btn${favorites.has(a.id) ? " favorited" : ""}" type="button" aria-pressed="${favorites.has(a.id)}" aria-label="${favorites.has(a.id) ? "Remove from favorites" : "Add to favorites"}" onclick="addToFavorites(event, this, ${i})">${favorites.has(a.id) ? "♥" : "♡"}</button>
          </div>
          <div class="card-body">
            <h3><button class="anime-title" id="anime-${ratingId(a)}" type="button" onclick="event.stopPropagation(); openModal(${i})">${escapeHtml(a.title)}</button></h3>
            <p class="personal-rating">Your rating: ${escapeHtml(cardRating(a))}</p>
            <p>${a.unresolved ? "Anime details are unavailable." : episodeLabel(a)}</p>
          </div>
        </article>
    `).join("");
}

async function load(p) {
    loading = true;
    catalogError = false;
    errorMessage = "";
    // only on an actual page change, so a refresh keeps the position the browser restored
    if (p !== page) scrollToTop();
    render();
    try {
        const res = await fetch(`/api/catalog/top?page=${p}&limit=${PAGE_SIZE}`);
        if (!res.ok) {
            errorMessage = await describeFailure(res);
            throw new Error(errorMessage);
        }
        const json = await res.json();
        animeList = (Array.isArray(json.data) ? json.data : [])
            .filter((a) => a && validId(a.id) && typeof a.title === "string")
            .map(animeDetails);
        page = p;
        hasMore = json.has_next_page ?? (animeList.length === PAGE_SIZE);
        for (const anime of animeList) {
            if (favorites.has(anime.id)) {
                favoriteDetails.set(anime.id, anime);
            }
        }
    } catch {
        // a network failure has no server message, so the friendly fallback stands
        catalogError = true;
    } finally {
        loading = false;
        render();
    }
}

async function search(q, p = 1) {
    activeQuery = q;
    loading = true;
    catalogError = false;
    errorMessage = "";
    scrollToTop();
    render();
    try {
        const res = await fetch(`/api/catalog/search?q=${encodeURIComponent(q)}&page=${p}&limit=${PAGE_SIZE}`);
        if (!res.ok) {
            errorMessage = await describeFailure(res);
            throw new Error(errorMessage);
        }
        const json = await res.json();
        animeList = (Array.isArray(json.data) ? json.data : [])
            .filter((a) => a && validId(a.id) && typeof a.title === "string")
            .map(animeDetails);
        page = p;
        // has_next_page comes straight from AniList's pageInfo; the length check is
        // only a fallback for a response that does not carry it
        hasMore = json.has_next_page ?? (animeList.length === PAGE_SIZE);
    } catch {
        // a network failure has no server message, so the friendly fallback stands
        catalogError = true;
    } finally {
        loading = false;
        render();
    }
}

function setView(selectedView) {
    if (selectedView === "favorites" && !requireFavoriteAccount()) return;
    if (selectedView === "ratings" && !currentUsername) {
        openAuthModal();
        showAuthNotice("Log in or sign up to see your ratings.");
        return;
    }
    view = selectedView;
    $("search").value = view === "ratings" ? ratingsQuery : activeQuery;
    if (selectedView === "ratings" && !ratingsReady) loadPersonalRatings(true);
    if (selectedView === "favorites" && !favoritesReady) loadFavorites();
    if (selectedView === "all" && activeQuery) {
        // "All Anime" means the catalog, so leave search mode behind
        activeQuery = "";
        load(1);
        return;
    }
    render();
}

function episodeLabel(a) {
    return a.episodes == null ? "? episodes" : `${a.episodes} ${a.episodes === 1 ? "episode" : "episodes"}`;
}

function requireFavoriteAccount() {
    if (currentUsername) return true;
    openAuthModal();
    showAuthNotice("Log in or sign up to save anime to your account.");
    return false;
}

window.addToFavorites = async (event, btn, i) => {
    event.stopPropagation();
    if (!requireFavoriteAccount() || favoriteSaving) return;
    if (!favoritesReady) {
        await loadFavorites();
        return;
    }
    const anime = visibleAnime[i];
    const removing = favorites.has(anime.id);
    const version = authVersion;
    favoriteSaving = true;
    btn.disabled = true;
    try {
        const res = await authFetch(removing ? `/api/favorites/${anime.id}` : "/api/favorites", {
            method: removing ? "DELETE" : "POST",
            ...(removing ? {} : { body: JSON.stringify(animeDetails(anime)) }),
        });
        if (version !== authVersion) return;
        if (res.status === 401) {
            await setAuthState(null);
            requireFavoriteAccount();
            return;
        }
        if (!res.ok) throw new Error("Save failed");
        $("storage-notice").hidden = true;
    } catch {
        if (version === authVersion) storageNotice("Couldn't save your favorite. Please try again.");
        return;
    } finally {
        favoriteSaving = false;
        btn.disabled = false;
    }
    if (removing) {
        favorites.delete(anime.id);
        favoriteDetails.delete(anime.id);
    } else {
        favorites.add(anime.id);
        favoriteDetails.set(anime.id, animeDetails(anime));
    }
    renderFavoriteCount();
    if (view === "favorites") {
        render();
        const buttons = grid.querySelectorAll(".favorite-btn");
        (buttons[Math.min(i, buttons.length - 1)] || $("browse-anime") || $("favorites")).focus();
    } else {
        const isFav = favorites.has(anime.id);
        btn.classList.toggle("favorited", isFav);
        btn.textContent = isFav ? "♥" : "♡";
        btn.setAttribute("aria-label", isFav ? "Remove from favorites" : "Add to favorites");
        btn.setAttribute("aria-pressed", String(isFav));
    }
};

let synopsisToken = 0;
let modalAnimeId = null;
let modalAnime = null;
let modalReturnId = null;
let ratingRequest = 0;
let ratingState = {};
const RATING_LABELS = ["Masterpiece", "Great", "Very Good", "Good", "Fine", "Average", "Bad", "Very Bad", "Horrible", "Appalling"];

function renderRating() {
    const panel = $("modal-rating");
    if (modalAnimeId === null || !panel) return;
    if (!currentUsername) {
        panel.innerHTML = '<h3>Your rating</h3><p>Log in to rate this anime.</p><button id="rating-login" type="button">Log in</button>';
        $("rating-login").onclick = openAuthModal;
        return;
    }
    const busy = ratingState.loading || ratingState.saving;
    panel.innerHTML = `
        <h3>Your rating</h3>
        <p>${!ratingState.loaded ? "Your rating has not loaded." : ratingState.value == null ? "Not rated yet" : `${ratingState.value}/10`}</p>
        <form id="rating-form" novalidate>
            <label for="rating-input">Choose a rating</label>
            <div class="rating-controls">
                <select id="rating-input" required ${busy || !ratingState.loaded ? "disabled" : ""}>
                    <option value="">Select</option>
                    ${RATING_LABELS.map((label, index) => {
                        const value = 10 - index;
                        return `<option value="${value}" ${Number(ratingState.draft) === value ? "selected" : ""}>(${value}) ${label}</option>`;
                    }).join("")}
                </select>
                <button type="submit" ${busy || !ratingState.loaded ? "disabled" : ""}>Save rating</button>
                <button id="rating-remove" type="button" ${busy || ratingState.value == null ? "disabled" : ""}>Remove rating</button>
            </div>
        </form>
        <p role="status">${escapeHtml(ratingState.loading ? "Loading your rating…" : ratingState.saving ? "Saving…" : ratingState.message || "")}</p>
        <p class="auth-error" role="alert" ${ratingState.error ? "" : "hidden"}>${escapeHtml(ratingState.error)}</p>
        ${!ratingState.loaded && !busy ? '<button id="rating-retry" type="button">Try again</button>' : ""}
    `;
    $("rating-form").onsubmit = (event) => { event.preventDefault(); saveRating(false); };
    $("rating-remove").onclick = () => saveRating(true);
    if (!ratingState.loaded && !busy) $("rating-retry").onclick = loadRating;
}

async function loadRating() {
    const request = ++ratingRequest;
    const version = authVersion;
    const animeId = modalAnimeId;
    ratingState = { loading: !!currentUsername };
    renderRating();
    if (!currentUsername || animeId === null) return;
    try {
        const res = await authFetch(`/api/ratings/${animeId}`);
        if (request !== ratingRequest || version !== authVersion) return;
        if (res.status === 401) return await setAuthState(null);
        if (!res.ok) throw new Error("Rating unavailable");
        const data = await res.json();
        if (request !== ratingRequest || version !== authVersion) return;
        ratingState = { value: data.rating, draft: data.rating, loaded: true };
    } catch {
        if (request !== ratingRequest || version !== authVersion) return;
        ratingState = { error: "Couldn't load your rating. Please try again." };
    }
    renderRating();
}

async function saveRating(removing) {
    if (!currentUsername || !ratingState.loaded || ratingState.saving) return;
    ratingState.draft = $("rating-input").value;
    const rating = Number(ratingState.draft);
    if (!removing && (!String(ratingState.draft).trim() || !Number.isInteger(rating) || rating < 1 || rating > 10)) {
        ratingState.error = "Enter a whole number from 1 to 10.";
        ratingState.message = "";
        renderRating();
        return;
    }
    const request = ++ratingRequest;
    const version = authVersion;
    const anime = modalAnime;
    ratingState.saving = true;
    ratingState.error = "";
    ratingState.message = "";
    renderRating();
    try {
        const res = await authFetch(`/api/ratings/${modalAnimeId}`, {
            method: removing ? "DELETE" : "PUT",
            ...(removing ? {} : { body: JSON.stringify({ rating }) }),
        });
        if (version !== authVersion) return;
        if (res.status === 401) return await setAuthState(null);
        if (!res.ok) throw new Error("Save failed");
        updateLibraryRating(anime, removing ? null : rating);
        if (request !== ratingRequest) return;
        ratingState.value = removing ? null : rating;
        ratingState.draft = ratingState.value;
        ratingState.message = removing ? "Rating removed." : "Rating saved.";
    } catch {
        if (request !== ratingRequest || version !== authVersion) return;
        ratingState.error = removing ? "Couldn't remove your rating. Please try again." : "Couldn't save your rating. Please try again.";
    }
    if (request !== ratingRequest || version !== authVersion) return;
    ratingState.saving = false;
    renderRating();
    $("rating-input").focus();
}

function closeAnimeModal() {
    modal.classList.add("hidden");
    modalAnimeId = null;
    ($(modalReturnId) || $(view === "ratings" ? "my-ratings" : view === "favorites" ? "favorites" : "all-anime")).focus();
    ++ratingRequest;
    ++synopsisToken;
}

function setSynopsisText(token, text) {
    if (token !== synopsisToken) return;
    const slot = $("modal-synopsis-text");
    if (slot) slot.textContent = text;
}

async function loadSynopsis(a) {
    if (a.synopsis) return;

    const token = ++synopsisToken;

    if (!a.anilist_id) {
        setSynopsisText(token, a.unresolved
            ? "Details for this older favorite will be restored when you visit its catalog page."
            : "No synopsis available.");
        return;
    }

    try {
        const res = await fetch(`/api/catalog/anime/${a.anilist_id}`);
        if (!res.ok) throw new Error("Details unavailable");
        const json = await res.json();
        a.synopsis = typeof json.synopsis === "string" ? json.synopsis : "";
        setSynopsisText(token, a.synopsis || "No synopsis available.");
    } catch {
        setSynopsisText(token, "We couldn't load the synopsis. Please try again.");
    }
}

window.openModal = (i) => {
    const a = visibleAnime[i];
    modalAnime = a;
    modalReturnId = `anime-${ratingId(a)}`;
    modalAnimeId = ratingId(a);
    const genres = a.genres || [];
    const genreTokens = genres.length
        ? genres.map((g) => `<span class="chip">${escapeHtml(g)}</span>`).join("")
        : '<span class="chip">No genres listed</span>';
    const pendingSynopsis = a.unresolved
        ? "Details for this older favorite will be restored when you visit its catalog page."
        : "Loading synopsis…";
    modalContent.innerHTML = `
        <div class="modal-header">
            ${a.image_url ? `<img class="modal-cover" src="${escapeHtml(a.image_url)}" alt="${escapeHtml(a.title)}">` : ""}
            <div class="modal-heading">
                <h2>${escapeHtml(a.title)}</h2>
                <div class="modal-stats">
                    <span>AniList score: <span class="star">★</span> ${escapeHtml(a.score ?? "N/A")}</span>
                    <span>${episodeLabel(a)}</span>
                </div>
                <div class="modal-genres">${genreTokens}</div>
            </div>
        </div>
        <section id="modal-rating" class="modal-rating" aria-label="Your rating"></section>
        <div class="modal-synopsis">
            <h3>Synopsis</h3>
            <p id="modal-synopsis-text">${escapeHtml(a.synopsis || pendingSynopsis)}</p>
        </div>
    `;
    modal.classList.remove("hidden");
    $("close").focus();
    loadRating();
    loadSynopsis(a);
};

$("close").onclick = closeAnimeModal;
modal.onclick = (e) => { if (e.target === modal) closeAnimeModal(); };
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) closeAnimeModal();
    if (event.key === "Tab" && !modal.classList.contains("hidden") && authModal.classList.contains("hidden")) {
        const controls = [...modal.querySelectorAll('button:not(:disabled), select:not(:disabled)')];
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
});
prev.forEach((button) => { button.onclick = () => page > 1 && (activeQuery ? search(activeQuery, page - 1) : load(page - 1)); });
next.forEach((button) => { button.onclick = () => (activeQuery ? search(activeQuery, page + 1) : load(page + 1)); });
$("all-anime").onclick = () => setView("all");
$("favorites").onclick = () => setView("favorites");
$("my-ratings").onclick = () => setView("ratings");
$("ratings-sort").onchange = () => { ratingsSort = $("ratings-sort").value; render(); };

function runSearch() {
    const q = $("search").value.trim();
    if (view === "ratings") { ratingsQuery = q; render(); return; }
    view = "all";
    if (!q) {
        // an empty box means "show me the catalog", not "search for nothing"
        activeQuery = "";
        load(1);
        return;
    }
    search(q);
}

$("search-btn").onclick = runSearch;
$("search").addEventListener("keydown", (event) => {
    if (event.key === "Enter") runSearch();
});

load(1);
const BG_THEMES = ["navy", "aurora", "sunset", "forest"]
const settingsModal = $("settings-modal");

function applyTheme(theme) {
    const chosen = BG_THEMES.includes(theme) ? theme : "navy";
    document.body.dataset.theme = chosen;
    document.querySelectorAll(".bg-option").forEach((btn) => {
        btn.setAttribute("aria-pressed", String(btn.dataset.bg === chosen));
    });
}

function saveTheme(theme) {
    try {
        localStorage.setItem("bgTheme", theme);
    } catch {
        storageNotice("Your settings are active for this visist, but couldn't be saved. Changes may not be saved after refreshing");
    }
}

let storedTheme = "navy";
try { storedTheme = localStorage.getItem("bgTheme") || "navy"; } catch {}
applyTheme(storedTheme);

$("settings-btn").onclick = () => settingsModal.classList.remove("hidden");
$("settings-close"). onclick = () => settingsModal.classList.add("hidden");
settingsModal.onclick = (e) => { if (e.target === settingsModal)
settingsModal.classList.add("hidden"); };
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !settingsModal.classList.contains("hidden")) {
        settingsModal.classList.add("hidden")
    }
});
document.querySelectorAll(".bg-option").forEach((btn) => {
      btn.onclick = () => { applyTheme(btn.dataset.bg); saveTheme(btn.dataset.bg); };
});
/* ---- Authentication UI ---- */
  const authModal = $("auth-modal");
  let authMode = "login";
  let resetToken = "";
  
  // Backend requires this header on POSTs; cookies carry the session.
async function authFetch(path, options = {}) {
    return fetch(path, {
        credentials: "same-origin",
        ...options,
        headers: {
            "Content-Type": "application/json",
            "X-Requested-With": "AnimeRater",
            ...options.headers,
        },
    });
}

function showAuthError(message = "") {
    $("auth-error").textContent = message;
    $("auth-error").hidden = !message;
}

async function setAuthState(username) {
    currentUsername = username || null;
    const version = ++authVersion;
    resetRatings();
    if (modalAnimeId !== null) loadRating();
    favorites.clear();
    favoriteDetails.clear();
    favoritesReady = false;
    $("storage-notice").hidden = true;
    const loggedIn = Boolean(username);
    if (loggedIn) $("account-name").textContent = username;
    $("account").hidden = !loggedIn;
    $("login-btn").hidden = loggedIn;
    if (!loggedIn && view !== "all") view = "all";
    render();
    if (loggedIn) await Promise.all([loadFavorites(version), loadPersonalRatings(view === "ratings")]);
}

function setAuthMode(mode) {
    authMode = mode;
    const signup = mode === "signup";
    const forgot = mode === "forgot";
    const reset = mode === "reset";
    const email = mode === "email";
    const titles = { login: "Log in", signup: "Sign up", forgot: "Forgot password", reset: "Reset password", email: "Recovery email" };
    $("auth-form").reset();
    $("auth-title").textContent = titles[mode];
    $("auth-submit").textContent = forgot ? "Send reset link" : email ? "Save recovery email" : titles[mode];
    $("auth-username-field").hidden = reset || email;
    $("auth-username").required = !reset && !email;
    $("auth-email-field").hidden = !signup && !email;
    $("auth-email").required = signup || email;
    $("auth-password-field").hidden = forgot;
    $("auth-password").required = !forgot;
    $("auth-password").minLength = signup || reset ? 12 : 1;
    $("auth-confirm-field").hidden = !reset;
    $("auth-confirm").required = reset;
    $("auth-forgot-btn").hidden = mode !== "login";
    $("auth-switch-text").textContent = mode === "login" ? "Don't have an account?" : "Back to";
    $("auth-switch-btn").textContent = signup ? "Log in" : "Sign up";
    if (forgot || reset || email) $("auth-switch-btn").textContent = "Log in";
    $("auth-password").setAttribute("autocomplete", signup || reset ? "new-password" : "current-password");
    $("auth-notice").hidden = true;
    showAuthError();
}

function showAuthNotice(message) {
    $("auth-notice").textContent = message;
    $("auth-notice").hidden = false;
}

function openAuthModal() {
    $("auth-form").reset();
    setAuthMode("login");
    authModal.classList.remove("hidden");
    $("auth-username").focus();
}

function closeAuthModal() {
    authModal.classList.add("hidden");
    $("auth-form").reset();
    resetToken = "";
    showAuthError();
}

// Mirror the backend's validation rules so users get instant feedback.
function credentialError(username, password) {
    if (!["reset", "email"].includes(authMode) && !/^[A-Za-z0-9_]{3,30}$/.test(username)) {
        return "Username must be 3–30 characters: letters, numbers, or underscores.";
    }
    if (authMode === "forgot") return "";
    if (["signup", "reset"].includes(authMode) && password.length < 12) {
        return "Password must be at least 12 characters.";
    }
    if (password.length < 1 || password.length > 128) {
        return "Please enter your password.";
    }
    return "";
}

// POST credentials to one of the auth endpoints; returns an error string or "".
async function postCredentials(path, username, password, email) {
    return postAuth(path, { username, password, email });
}

async function postAuth(path, body) {
    const res = await authFetch(path, {
        method: "POST",
        body: JSON.stringify(body),
    });
    if (res.ok) return "";
    if (res.status === 409) return "That username is already taken.";
    try {
        const detail = (await res.json()).detail;
        return typeof detail === "string" ? detail : "Please check the fields and try again.";
    }
    catch { return "Something went wrong. Please try again."; }
}

async function submitAuth(event) {
    event.preventDefault();
    const username = $("auth-username").value.trim();
    const password = $("auth-password").value;

    const invalid = credentialError(username, password);
    if (invalid) return showAuthError(invalid);
    if (["signup", "email"].includes(authMode) && !$("auth-email").checkValidity()) {
        return showAuthError("Please enter a valid recovery email.");
    }
    if (authMode === "reset" && password !== $("auth-confirm").value) {
        return showAuthError("The passwords do not match.");
    }

    $("auth-submit").disabled = true;
    showAuthError();
    try {
        if (authMode === "forgot") {
            const error = await postAuth("/api/auth/forgot-password", { username });
            if (error) return showAuthError(error);
            showAuthNotice("If this account has a recovery email, a reset link will be sent. Check your inbox and spam folder. Links expire in 30 minutes; wait a minute before requesting another.");
            return;
        }
        if (authMode === "reset") {
            const error = await postAuth("/api/auth/reset-password", { token: resetToken, password });
            if (error) return showAuthError(error);
            resetToken = "";
            await setAuthState(null);
            setAuthMode("login");
            showAuthNotice("Password updated. Log in with your new password.");
            return;
        }
        if (authMode === "email") {
            const error = await postAuth("/api/auth/recovery-email", { email: $("auth-email").value.trim(), password });
            if (error) return showAuthError(error);
            $("auth-password").value = "";
            showAuthNotice("Recovery email saved.");
            return;
        }
        if (authMode === "signup") {
            const signupError = await postCredentials("/api/auth/register", username, password, $("auth-email").value.trim());
            if (signupError) return showAuthError(signupError);
        }
        const loginError = await postCredentials("/api/auth/login", username, password);
        if (loginError) return showAuthError(loginError);
        closeAuthModal();
        await setAuthState(username);
    } catch {
        showAuthError("Could not reach the server. Please try again.");
    } finally {
        $("auth-submit").disabled = false;
    }
}

async function logout() {
    try {
        const res = await authFetch("/api/auth/logout", { method: "POST" });
        if (!res.ok) throw new Error("Logout failed");
        await setAuthState(null);
    } catch {
        storageNotice("Couldn't log out. Please try again.");
    }
}

// Reflect any existing session on load.
async function refreshAuthState() {
    try {
        const res = await authFetch("/api/auth/me");
        if (res.ok) return setAuthState((await res.json()).username);
    } catch {}
    await setAuthState(null);
}

$("login-btn").onclick = openAuthModal;
$("logout-btn").onclick = logout;
$("auth-close").onclick = closeAuthModal;
$("auth-form").onsubmit = submitAuth;
$("auth-switch-btn").onclick = () => setAuthMode(authMode === "login" ? "signup" : "login");
$("auth-forgot-btn").onclick = () => { setAuthMode("forgot"); $("auth-username").focus(); };
$("recovery-email-btn").onclick = () => {
    setAuthMode("email");
    authModal.classList.remove("hidden");
    $("auth-email").focus();
};
authModal.onclick = (e) => { if (e.target === authModal) closeAuthModal(); };

refreshAuthState();

// Fragments are not sent to the server or included in HTTP referrers.
const resetParams = new URLSearchParams(window.location.hash.slice(1));
if (resetParams.has("reset_token")) {
    resetToken = resetParams.get("reset_token");
    history.replaceState(null, "", window.location.pathname + window.location.search);
    setAuthMode("reset");
    authModal.classList.remove("hidden");
    $("auth-password").focus();
}
