"use strict";

let page = 1;
let animeList = [];
const favorites = new Set(JSON.parse(localStorage.getItem("favoriteAnimeIds") || "[]"));

const $ = (id) => document.getElementById(id);
const grid = $("grid"), pageNum = document.querySelectorAll(".page"), prev = document.querySelectorAll(".prev"), next = document.querySelectorAll(".next"), modal = $("modal"), modalContent = $("modal-content");

async function load(p) {
    grid.innerHTML = "<p>Loading...</p>";
    const res = await fetch(`/api/catalog/top?page=${p}&limit=25`);
    const json = await res.json();
    
    animeList = json.data || [];
    page = p;
    pageNum.forEach((label) => { label.textContent = `Page ${page}`; });
    prev.forEach((button) => { button.disabled = page <= 1; });

     grid.innerHTML = animeList.map((a, i) => `
        <div class="card" onclick="openModal(${i})">
        <div class="poster">
          <img src="${a.image_url || ''}" alt="${a.title}">
          <span class="score-badge"><span class="star">★</span> ${a.score ?? "N/A"}</span>
            <button class="favorite-btn${favorites.has(a.id) ? " favorited" : ""}" type="button" aria-label="${favorites.has(a.id) ? "Remove from favorites" : "Add to favorites"}" onclick="addToFavorites(event, this, ${i})">${favorites.has(a.id) ? "♥" : "♡"}</button>
        </div>
      <div class="card-body">
          <h3>${a.title}</h3>
          <p>${a.episodes == null ? "? episodes" : `${a.episodes} ${a.episodes === 1 ? "episode" : "episodes"}`}</p>
      </div>
      </div>
  `).join("");
}
window.addToFavorites = (event, btn, i) => {
      event.stopPropagation();
      const isFav = btn.classList.toggle("favorited");
      btn.textContent = isFav ? "♥" : "♡";
      btn.setAttribute("aria-label", isFav ? "Remove from favorites" : "Add to favorites");
  
      const anime = animeList[i];
  };

window.addToFavorites = (event, btn, i) => {
    event.stopPropagation();
    const anime = animeList[i];
    if (favorites.has(anime.id)) favorites.delete(anime.id);
    else favorites.add(anime.id);
    localStorage.setItem("favoriteAnimeIds", JSON.stringify([...favorites]));
    const isFav = favorites.has(anime.id);
    btn.classList.toggle("favorited", isFav);
    btn.textContent = isFav ? "♥" : "♡";
    btn.setAttribute("aria-label", isFav ? "Remove from favorites" : "Add to favorites");
};

window.openModal = (i) => {
    const a = animeList[i];
        const episodeLabel = a.episodes == null
      ? "? episodes"
      : `${a.episodes} ${a.episodes === 1 ? "episode" : "episodes"}`;
      const genreTokens = a.genres.length
          ? a.genres.map((g) => `<span class="chip">${g}</span>`).join("")
          : `<span class="chip">No genres listed</span>`;
    


      modalContent.innerHTML = `
          <div class="modal-header">
              <img class="modal-cover" src="${a.image_url || ''}" alt="${a.title}">
              <div class="modal-heading">
                  <h2>${a.title}</h2>
                 <div class="modal-stats">
                    <span><span class="star">★</span> ${a.score ?? "N/A"}</span>
                    <span>${episodeLabel}</span>
                </div>
                <div class="modal-genres">${genreTokens}</div>
              </div>
          </div>
  
          
  
          <div class="modal-synopsis">
              <h3>Synopsis</h3>
              <p>${a.synopsis || "No synopsis available."}</p>
          </div>
      `;
    modal.classList.remove("hidden");
};

$("close").onclick = () => modal.classList.add("hidden");
modal.onclick = (e) => { if (e.target === modal) modal.classList.add("hidden"); };
prev.forEach((button) => { button.onclick = () => page > 1 && load(page - 1); });
next.forEach((button) => { button.onclick = () => load(page + 1); });

load(1);
