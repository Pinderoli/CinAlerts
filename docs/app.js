const CHAIN_ORDER = ["odeon", "cineworld", "vue", "picturehouse", "everyman", "curzon"];
const VISIBLE_VENUES = 3;
const VISIBLE_TIMES = 6;

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem("cinalerts:" + k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("cinalerts:" + k, JSON.stringify(v)); } catch {} },
};

const state = {
  q: "",
  age: store.get("age", 1),
  mine: store.get("mine", false),
  myCinemas: new Set(store.get("cinemas", [])),
  chains: new Set(),
  genres: new Set(),
};

let data, cinemas, cinemaById;

const dayFmt = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });
function fmtTime(iso) {
  const d = new Date(iso);
  return `${dayFmt.format(d)} ${iso.slice(11, 16)}`;
}

function chainName(c) { return data.chains[c]?.name ?? c; }

async function load() {
  const [r, c] = await Promise.all([fetch("data/reruns.json"), fetch("data/cinemas.json")]);
  data = await r.json();
  cinemas = await c.json();
  cinemaById = Object.fromEntries(cinemas.map((c) => [c.id, c]));

  $("#updated").textContent = `Updated ${new Date(data.generated).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })}`;
  $("#age").value = String(state.age);
  $("#mine").checked = state.mine;

  const chains = CHAIN_ORDER.filter((c) => data.chains[c] || cinemas.some((x) => x.chain === c));
  $("#chains").innerHTML = chains.map((c) => {
    const down = data.chains[c] && !data.chains[c].ok;
    return `<button class="chip${down ? " down" : ""}" data-chain="${c}" aria-pressed="false" title="${down ? "Not updated in the latest scan" : ""}">${esc(chainName(c))}</button>`;
  }).join("");
  const genres = [...new Set(data.films.flatMap((f) => f.genres))].sort();
  $("#genres").innerHTML = genres.map((g) => `<button class="chip" data-genre="${esc(g)}" aria-pressed="false">${esc(g)}</button>`).join("");

  const failed = Object.entries(data.chains).filter(([, s]) => !s.ok).map(([c]) => chainName(c));
  $("#status").textContent = failed.length ? `Couldn't update: ${failed.join(", ")}` : `All ${Object.keys(data.chains).length} chains scanned`;

  updatePickCount();
  render();
  if (location.hash) focusFilm(decodeURIComponent(location.hash.slice(1)));
}

function filmMatches(f) {
  if (state.q && !(f.title + " " + f.listed_as.join(" ")).toLowerCase().includes(state.q)) return false;
  if (f.age_years != null && f.age_years < state.age) return false;
  if (f.age_years == null && state.age > 1) return false;
  if (state.genres.size && !f.genres.some((g) => state.genres.has(g))) return false;
  return true;
}

function venueMatches(cid) {
  const c = cinemaById[cid];
  if (!c) return false;
  if (state.chains.size && !state.chains.has(c.chain)) return false;
  if (state.mine && !state.myCinemas.has(cid)) return false;
  return true;
}

function render() {
  // Showings are local UK times without an offset; compare as strings in the same format.
  const now = new Date();
  const nowLocal = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  const out = [];
  let shownVenues = 0;
  for (const f of data.films) {
    if (!filmMatches(f)) continue;
    const venues = Object.entries(f.showings)
      .filter(([cid]) => venueMatches(cid))
      .map(([cid, shows]) => [cid, shows.filter(([t]) => t >= nowLocal)])
      .filter(([, shows]) => shows.length);
    if (!venues.length) continue;
    venues.sort((a, b) => (state.myCinemas.has(b[0]) - state.myCinemas.has(a[0])) || a[1][0][0].localeCompare(b[1][0][0]));
    shownVenues += venues.length;
    out.push(filmCard(f, venues));
  }
  $("#films").innerHTML = out.join("") || `<p class="empty">${state.mine && !state.myCinemas.size ? "Choose some cinemas first." : "Nothing matches these filters right now."}</p>`;
  $("#summary").textContent = out.length ? `${out.length} film${out.length === 1 ? "" : "s"} across ${shownVenues} cinema showing${shownVenues === 1 ? "" : "s"} in the next ${data.days_ahead} days` : "";
}

function filmCard(f, venues) {
  const poster = f.poster ? `<img class="poster" loading="lazy" src="${esc(f.poster)}" alt="">` : `<div class="poster"></div>`;
  const age = f.age_years != null ? `<span class="tag age">${Math.floor(f.age_years)} yr${Math.floor(f.age_years) === 1 ? "" : "s"}</span>` : `<span class="tag age">Re-release</span>`;
  const title = f.imdb ? `<a href="https://www.imdb.com/title/${esc(f.imdb)}/" target="_blank" rel="noopener">${esc(f.title)}</a>` : esc(f.title);
  const rows = venues.map(([cid, shows], i) => venueRow(cid, shows, i >= VISIBLE_VENUES)).join("");
  const more = venues.length > VISIBLE_VENUES ? `<button class="more" data-more>+ ${venues.length - VISIBLE_VENUES} more cinemas</button>` : "";
  return `<article class="film" id="${esc(f.key)}">
    ${poster}
    <div>
      <h3>${title}${f.year ? ` <span style="color:var(--muted)">(${f.year})</span>` : ""}</h3>
      <div class="meta">${age}${f.genres.map((g) => `<span class="tag">${esc(g)}</span>`).join("")}</div>
      <div class="venues">${rows}${more}</div>
    </div>
  </article>`;
}

function venueRow(cid, shows, hidden) {
  const c = cinemaById[cid];
  const times = shows.slice(0, VISIBLE_TIMES).map(([t, url]) => `<a href="${esc(url || c.url)}" target="_blank" rel="noopener">${fmtTime(t)}</a>`).join("");
  const extra = shows.length > VISIBLE_TIMES ? `<a href="${esc(c.url)}" target="_blank" rel="noopener">+${shows.length - VISIBLE_TIMES}</a>` : "";
  return `<div class="venue"${hidden ? " hidden" : ""}>
    <div class="venue-name">${esc(chainName(c.chain))} · <b>${esc(c.name)}</b>${state.myCinemas.has(cid) ? " ★" : ""}</div>
    <div class="times">${times}${extra}</div>
  </div>`;
}

function focusFilm(key) {
  const el = document.getElementById(key);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "start" });
  el.classList.add("flash");
}

// Cinema picker
function renderCinemaList() {
  const q = $("#cinema-search").value.trim().toLowerCase();
  const html = [];
  for (const chain of CHAIN_ORDER) {
    const list = cinemas.filter((c) => c.chain === chain && (!q || `${c.name} ${c.city}`.toLowerCase().includes(q)));
    if (!list.length) continue;
    html.push(`<h4>${esc(chainName(chain))}</h4>`);
    for (const c of list) {
      const city = c.city && !c.name.toLowerCase().includes(c.city.toLowerCase()) ? ` <small>${esc(c.city)}</small>` : "";
      html.push(`<label><input type="checkbox" value="${esc(c.id)}"${state.myCinemas.has(c.id) ? " checked" : ""}> ${esc(c.name)}${city}</label>`);
    }
  }
  $("#cinema-list").innerHTML = html.join("") || `<p class="empty">No cinemas match.</p>`;
}

function updatePickCount() {
  $("#pick-count").textContent = state.myCinemas.size ? `(${state.myCinemas.size})` : "";
}

function configSnippet() {
  const ids = [...state.myCinemas].sort();
  const lines = ids.map((id) => `  "${id}",  # ${chainName(cinemaById[id]?.chain)} ${cinemaById[id]?.name ?? ""}`);
  return `cinemas = [\n${lines.join("\n")}\n]`;
}

$("#search").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
$("#age").addEventListener("change", (e) => { state.age = Number(e.target.value); store.set("age", state.age); render(); });
$("#mine").addEventListener("change", (e) => { state.mine = e.target.checked; store.set("mine", state.mine); render(); });

document.addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (chip) {
    const set = chip.dataset.chain ? state.chains : state.genres;
    const val = chip.dataset.chain ?? chip.dataset.genre;
    set.has(val) ? set.delete(val) : set.add(val);
    chip.setAttribute("aria-pressed", set.has(val));
    render();
  }
  if (e.target.matches("[data-more]")) {
    e.target.parentElement.querySelectorAll(".venue[hidden]").forEach((v) => (v.hidden = false));
    e.target.remove();
  }
});

$("#pick").addEventListener("click", () => {
  $("#cinema-search").value = "";
  $("#config-out").hidden = true;
  renderCinemaList();
  $("#picker").showModal();
});
$("#cinema-search").addEventListener("input", renderCinemaList);
$("#cinema-list").addEventListener("change", (e) => {
  const id = e.target.value;
  e.target.checked ? state.myCinemas.add(id) : state.myCinemas.delete(id);
  store.set("cinemas", [...state.myCinemas]);
  updatePickCount();
  render();
});
$("#clear").addEventListener("click", () => {
  state.myCinemas.clear();
  store.set("cinemas", []);
  updatePickCount();
  renderCinemaList();
  render();
});
$("#copy").addEventListener("click", async () => {
  const text = configSnippet();
  $("#config-out").textContent = text;
  $("#config-out").hidden = false;
  try { await navigator.clipboard.writeText(text); $("#copy").textContent = "Copied"; } catch { $("#copy").textContent = "Copy from below"; }
  setTimeout(() => ($("#copy").textContent = "Copy for config.toml"), 2000);
});
window.addEventListener("hashchange", () => focusFilm(decodeURIComponent(location.hash.slice(1))));

load().catch((err) => {
  $("#films").innerHTML = `<p class="empty">Couldn't load listings: ${esc(err.message)}</p>`;
});
