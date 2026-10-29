"use strict";

// Ratings are keyed by AniList ID, unlike favorites which use the catalog ID.
const personalRatings = new Map();
let ratedAnime = [];
let ratingsReady = false;
let ratingsLoading = false;
let ratingsError = "";
let ratingsRequest = 0;
let ratingsQuery = "";
let ratingsSort = "highest";

function ratingId(anime) {
    return Number(anime.anilist_id || anime.id);
}

async function loadPersonalRatings(library = false) {
    const request = ++ratingsRequest;
    const version = authVersion;
    ratingsLoading = true;
    ratingsError = "";
    render();
    try {
        const res = await authFetch(library ? "/api/ratings/library" : "/api/ratings");
        if (version !== authVersion || request !== ratingsRequest) return;
        if (res.status === 401) return await setAuthState(null);
        if (!res.ok) throw new Error("Ratings unavailable");
        const json = await res.json();
        if (version !== authVersion || request !== ratingsRequest) return;
        personalRatings.clear();
        for (const row of json.data) {
            personalRatings.set(library ? ratingId(row) : row.anime_id, row.rating);
        }
        if (library) {
            ratedAnime = json.data;
            ratingsReady = true;
        }
    } catch {
        if (version !== authVersion || request !== ratingsRequest) return;
        ratingsError = "Couldn't load your ratings. Please try again.";
    } finally {
        if (version === authVersion && request === ratingsRequest) {
            ratingsLoading = false;
            render();
        }
    }
}

function filteredRatings() {
    return ratedAnime.filter((anime) => anime.title.toLowerCase().includes(ratingsQuery.toLowerCase()))
        .sort((a, b) => {
            const difference = (personalRatings.get(ratingId(b)) || 0) - (personalRatings.get(ratingId(a)) || 0);
            return (ratingsSort === "title" ? 0 : ratingsSort === "lowest" ? -difference : difference)
                || a.title.localeCompare(b.title) || ratingId(a) - ratingId(b);
        });
}

function cardRating(anime) {
    if (!currentUsername) return "Log in to rate";
    const rating = personalRatings.get(ratingId(anime));
    if (rating != null) return `${rating}/10`;
    if (ratingsLoading) return "Loading…";
    if (ratingsError) return "Unavailable";
    return "Not rated";
}

function updateLibraryRating(anime, value) {
    // Invalidate a list read that started before this successful mutation.
    ++ratingsRequest;
    const needsReload = ratingsLoading;
    if (ratingsLoading) ratingsReady = false;
    ratingsLoading = false;
    if (value == null) {
        personalRatings.delete(ratingId(anime));
        ratedAnime = ratedAnime.filter((row) => ratingId(row) !== ratingId(anime));
    } else {
        personalRatings.set(ratingId(anime), value);
        if (!ratedAnime.some((row) => ratingId(row) === ratingId(anime))) ratedAnime.push(anime);
    }
    render();
    if (needsReload || (view === "ratings" && !ratingsReady)) loadPersonalRatings(view === "ratings");
}

function resetRatings() {
    ++ratingsRequest;
    personalRatings.clear();
    ratedAnime = [];
    ratingsReady = false;
    ratingsLoading = false;
    ratingsError = "";
    ratingsQuery = "";
}
