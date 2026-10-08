"use strict";

let page = 1;
let animeList = [];
let visibleAnime = [];
let view = "all";
let loading = false;
let catalogError = false;
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
    next.forEach((button) => { button.disabled = loading; });
    visibleAnime = view === "favorites"
        ? [...favorites].map((id) => favoriteDetails.get(id) || { id, title: `Saved anime #${id}`, unresolved: true })
        : animeList;
    if (view === "all" && (loading || catalogError)) {
        grid.innerHTML = loading ? "<p>Loading...</p>" : '<div class="empty-state"><p>We couldn’t load the catalog. Please try again.</p><button id="retry" type="button">Try again</button></div>';
        if (catalogError && !loading) $("retry").onclick = () => load(page);
        return;
    }
    if (view === "favorites" && !favorites.size) {
        grid.innerHTML = '<div class="empty-state"><h2>No favorites yet</h2><p>Save anime with the heart button to find them here.</p><button id="browse-anime" type="button">Browse anime</button></div>';
        $("browse-anime").onclick = () => { setView("all"); $("all-anime").focus(); };
        return;
    }
    grid.innerHTML = visibleAnime.map((a, i) => `
        <div class="card" onclick="openModal(${i})">
          <div class="poster">
            ${a.image_url ? `<img src="${escapeHtml(a.image_url)}" alt="${escapeHtml(a.title)}">` : ""}
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
        const res = await fetch(`/api/catalog/top?page=${p}&limit=25`);
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

function setView(selectedView) {
    view = selectedView;
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
prev.forEach((button) => { button.onclick = () => page > 1 && load(page - 1); });
next.forEach((button) => { button.onclick = () => load(page + 1); });
$("all-anime").onclick = () => setView("all");
$("favorites").onclick = () => setView("favorites");

load(1);
