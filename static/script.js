"use strict";

let page = 1;
let animeList = [];
let visibleAnime = [];
let view = "all";
let loading = false;
let catalogError = false;
let activeQuery = "";
let hasMore = true;
const PAGE_SIZE = 25;
const favorites = new Set();
const favoriteDetails = new Map();

const $ = (id) => document.getElementById(id);
const grid = $("grid"), pageNum = document.querySelectorAll(".page"), prev = document.querySelectorAll(".prev"), next = document.querySelectorAll(".next"), modal = $("modal"), modalContent = $("modal-content");
const pagination = document.querySelectorAll(".pagination-top, .pagination-bottom");
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
const validId = (id) => (typeof id === "number" || typeof id === "string") && String(id).trim() !== "" && Number.isSafeInteger(Number(id)) && Number(id) > 0;

function storageNotice(message) {
    $("storage-notice").textContent = message;
    $("storage-notice").hidden = false;
}

function readStoredArray(key) {
    try {
        const value = JSON.parse(localStorage.getItem(key) || "[]");
        return Array.isArray(value) ? value : [];
    } catch {
        return [];
    }
}

function animeDetails(anime) {
    return {
        id: Number(anime.id),
        title: anime.title,
        image_url: typeof anime.image_url === "string" ? anime.image_url : "",
        score: Number.isFinite(anime.score) ? anime.score : null,
        episodes: Number.isInteger(anime.episodes) && anime.episodes >= 0 ? anime.episodes : null,
        genres: Array.isArray(anime.genres) ? anime.genres.filter((genre) => typeof genre === "string") : [],
        synopsis: typeof anime.synopsis === "string" ? anime.synopsis : "",
    };
}

for (const id of readStoredArray("favoriteAnimeIds")) {
    if (validId(id)) favorites.add(Number(id));
}
for (const anime of readStoredArray("favoriteAnimeDetails")) {
    if (!anime || !validId(anime.id)) continue;
    const id = Number(anime.id);
    favorites.add(id);
    if (typeof anime.title === "string" && anime.title.trim()) {
        favoriteDetails.set(id, animeDetails(anime));
    }
}

function saveFavorites() {
    try {
        localStorage.setItem("favoriteAnimeIds", JSON.stringify([...favorites]));
        localStorage.setItem("favoriteAnimeDetails", JSON.stringify([...favoriteDetails.values()]));
    } catch {
        storageNotice("Your favorites are available for this visit, but couldn't be saved. Changes may not survive a refresh.");
    }
}

function render() {
    pagination.forEach((controls) => { controls.hidden = view === "favorites"; });
    $("all-anime").setAttribute("aria-pressed", String(view === "all"));
    $("favorites").setAttribute("aria-pressed", String(view === "favorites"));
    pageNum.forEach((label) => { label.textContent = `Page ${page}`; });
    prev.forEach((button) => { button.disabled = loading || page <= 1; });
    next.forEach((button) => { button.disabled = loading || (activeQuery && !hasMore); });
    visibleAnime = view === "favorites"
        ? [...favorites].map((id) => favoriteDetails.get(id) || { id, title: `Saved anime #${id}`, unresolved: true })
        : animeList;
    if (view === "all" && (loading || catalogError)) {
        grid.innerHTML = loading ? "<p>Loading...</p>" : `<div class="empty-state"><p>${activeQuery ? "We couldn’t run that search." : "We couldn’t load the catalog."} Please try again.</p><button id="retry" type="button">Try again</button></div>`;
        if (catalogError && !loading) $("retry").onclick = () => (activeQuery ? search(activeQuery, page) : load(page));
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
        <div class="card" onclick="openModal(${i})">
          <div class="poster">
            ${a.image_url ? `<img src="${escapeHtml(a.image_url)}" alt="${escapeHtml(a.title)}" loading="lazy">` : ""}
            <span class="score-badge"><span class="star">★</span> ${escapeHtml(a.score ?? "N/A")}</span>
            <button class="favorite-btn${favorites.has(a.id) ? " favorited" : ""}" type="button" aria-pressed="${favorites.has(a.id)}" aria-label="${favorites.has(a.id) ? "Remove from favorites" : "Add to favorites"}" onclick="addToFavorites(event, this, ${i})">${favorites.has(a.id) ? "♥" : "♡"}</button>
          </div>
          <div class="card-body">
            <h3>${escapeHtml(a.title)}</h3>
            <p>${a.unresolved ? "Browse the catalog to restore details." : episodeLabel(a)}</p>
          </div>
        </div>
    `).join("");
}

async function load(p) {
    loading = true;
    catalogError = false;
    render();
    try {
        const res = await fetch(`/api/catalog/top?page=${p}&limit=${PAGE_SIZE}`);
        if (!res.ok) throw new Error("Catalog unavailable");
        const json = await res.json();
        animeList = (Array.isArray(json.data) ? json.data : [])
            .filter((a) => a && validId(a.id) && typeof a.title === "string")
            .map(animeDetails);
        page = p;
        let resolved = false;
        for (const anime of animeList) {
            if (favorites.has(anime.id)) {
                favoriteDetails.set(anime.id, anime);
                resolved = true;
            }
        }
        if (resolved) saveFavorites();
    } catch {
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
    render();
    try {
        const res = await fetch(`/api/catalog/search?q=${encodeURIComponent(q)}&page=${p}&limit=${PAGE_SIZE}`);
        if (!res.ok) throw new Error("Search unavailable");
        const json = await res.json();
        animeList = (Array.isArray(json.data) ? json.data : [])
            .filter((a) => a && validId(a.id) && typeof a.title === "string")
            .map(animeDetails);
        page = p;
        // AniList sends no "is there another page" flag through this response,
        // so a full page is the signal that it is worth trying the next one.
        hasMore = animeList.length === PAGE_SIZE;
    } catch {
        catalogError = true;
    } finally {
        loading = false;
        render();
    }
}

function setView(selectedView) {
    view = selectedView;
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

window.addToFavorites = (event, btn, i) => {
    event.stopPropagation();
    const anime = visibleAnime[i];
    if (favorites.has(anime.id)) {
        favorites.delete(anime.id);
        favoriteDetails.delete(anime.id);
    } else {
        favorites.add(anime.id);
        favoriteDetails.set(anime.id, animeDetails(anime));
    }
    saveFavorites();
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

window.openModal = (i) => {
    const a = visibleAnime[i];
    const genres = a.genres || [];
    const genreTokens = genres.length
        ? genres.map((g) => `<span class="chip">${escapeHtml(g)}</span>`).join("")
        : '<span class="chip">No genres listed</span>';
    modalContent.innerHTML = `
        <div class="modal-header">
            ${a.image_url ? `<img class="modal-cover" src="${escapeHtml(a.image_url)}" alt="${escapeHtml(a.title)}">` : ""}
            <div class="modal-heading">
                <h2>${escapeHtml(a.title)}</h2>
                <div class="modal-stats">
                    <span><span class="star">★</span> ${escapeHtml(a.score ?? "N/A")}</span>
                    <span>${episodeLabel(a)}</span>
                </div>
                <div class="modal-genres">${genreTokens}</div>
            </div>
        </div>
        <div class="modal-synopsis">
            <h3>Synopsis</h3>
            <p>${escapeHtml(a.unresolved ? "Details for this older favorite will be restored when you visit its catalog page." : a.synopsis || "No synopsis available.")}</p>
        </div>
    `;
    modal.classList.remove("hidden");
};

$("close").onclick = () => modal.classList.add("hidden");
modal.onclick = (e) => { if (e.target === modal) modal.classList.add("hidden"); };
prev.forEach((button) => { button.onclick = () => page > 1 && (activeQuery ? search(activeQuery, page - 1) : load(page - 1)); });
next.forEach((button) => { button.onclick = () => (activeQuery ? search(activeQuery, page + 1) : load(page + 1)); });
$("all-anime").onclick = () => setView("all");
$("favorites").onclick = () => setView("favorites");

function runSearch() {
    const q = $("search").value.trim();
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
