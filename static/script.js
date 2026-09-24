"use strict";

let page = 1;
let animeList = [];

const $ = (id) => document.getElementById(id);
const grid = $("grid"), pageNum = $("page"), prev = $("prev"), next = $("next"), modal = $("modal"), modalContent = $("modal-content");

async function load(p) {
    grid.innerHTML = "<p>Loading...</p>";
    const res = await fetch(`/api/catalog/top?page=${p}&limit=25`);
    const json = await res.json();
    
    animeList = json.data || [];
    page = p;
    pageNum.textContent = `Page ${page}`;
    prev.disabled = page <= 1;

    grid.innerHTML = animeList.map((a, i) => `
        <div class="card" onclick="openModal(${i})">
        <img src="${a.image_url || ''}" alt="${a.title}">
        <div class="card-body">
            <h3>${a.title}</h3>
            <p>Score: ${a.score} | Eps: ${a.episodes}</p>
        </div>
        </div>
    `).join("");
}

window.openModal = (i) => {
    const a = animeList[i];
    modalContent.innerHTML = `
        <h2>${a.title}</h2>
        <p><strong>Genres:</strong> ${a.genres.join(", ") || "None"}</p>
        <p style="margin-top:10px; font-size:0.9rem; line-height:1.4;">${a.synopsis}</p>
    `;
    modal.classList.remove("hidden");
};

$("close").onclick = () => modal.classList.add("hidden");
modal.onclick = (e) => { if (e.target === modal) modal.classList.add("hidden"); };
prev.onclick = () => page > 1 && load(page - 1);
next.onclick = () => load(page + 1);

load(1);