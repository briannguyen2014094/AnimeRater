"use strict";

let currentPage = 1;
const $ = (id) => document.getElementById(id);
const grid = $("anime-grid");
const indicator = $("page-indicator");
const prevBtn = $("prev-btn");
const nextBtn = $("next-btn");

async function loadPage(page) {
    grid.innerHTML = "<p>Loading anime...</p>";

    try {
        const res = await fetch(`/api/catalog/top?page=${page}&limit=25`);
        const { data } = await res.json();

        if (!data?.length) {
            grid.innerHTML = "<p>No anime records found or API is unavailable.</p>";
            return;
        }

        currentPage = page;
        indicator.textContent = `Page ${currentPage}`;
        prevBtn.disabled = currentPage <= 1;

        grid.innerHTML = data.map((anime) => `
        <div class="anime-card">
            <img src="${anime.image_url || "https://via.placeholder.com/225x320?text=No+Image"}" alt="${anime.title}" loading="lazy" />
            <div class="card-content">
            <h3>${anime.title}</h3>
            <p class="episodes">Episodes: ${anime.episodes || "?"}</p>
            </div>
        </div>
        `).join("");
    } catch (err) {
        grid.innerHTML = `<p>Error loading catalog: ${err.message}</p>`;
    }
}

prevBtn.onclick = () => currentPage > 1 && loadPage(currentPage - 1);
nextBtn.onclick = () => loadPage(currentPage + 1);

loadPage(1);