// Library view: search and filters, cover grid or sortable table, endless scrolling and bulk edit.
import { api } from "../api.js";
import { store } from "../store.js";
import { icon } from "../icons.js";
import {
  authorsLine,
  editionLabel,
  esc,
  fmtDate,
  statusLabel,
} from "../format.js";
import { bookCard, formatBadges, rowThumb, statusBadge, seriesText } from "../components.js";
import { emptyState, toast } from "../ui.js";
import { openAddDialog, openBulkDialog } from "../forms.js";
import { navigate } from "../router.js";

const PAGE_SIZE = 48;
const SORTS = [
  ["title", "Title"],
  ["author", "Author"],
  ["series", "Series"],
  ["added", "Recently added"],
  ["status", "Status"],
  ["genre", "Genre"],
];

function option(value, label, selected) {
  return `<option value="${esc(value)}" ${selected ? "selected" : ""}>${esc(label)}</option>`;
}

export async function libraryView(main, params, search) {
  const subgenreValues = await api
    .suggestions("subgenre", "")
    .then((result) => result.values)
    .catch(() => []);
  const state = {
    q: search.get("q") || "",
    genre: search.get("genre") || "",
    subgenre: search.get("subgenre") || "",
    status: search.get("status") || "",
    edition: search.get("edition") || "",
    review: search.get("review") === "1",
    sort: search.get("sort") || "title",
    direction: search.get("direction") || (search.get("sort") === "added" ? "desc" : "asc"),
    view: search.get("view") === "table" ? "table" : "grid",
  };
  if (!SORTS.some(([value]) => value === state.sort)) state.sort = "title";
  if (!["asc", "desc"].includes(state.direction)) state.direction = "asc";
  if (state.subgenre && !subgenreValues.some((value) => value.toLowerCase() === state.subgenre.toLowerCase())) {
    subgenreValues.push(state.subgenre);
  }
  const subgenreOptions = [...new Set(subgenreValues)].sort((a, b) => a.localeCompare(b));
  const genres = [...store.genres];
  if (state.genre && !genres.some((value) => value.toLowerCase() === state.genre.toLowerCase())) {
    genres.push(state.genre);
  }

  main.innerHTML = `
    <header class="page-head">
      <div>
        <h1>Library</h1>
        <p class="subtitle">Every book in your collection.</p>
      </div>
    </header>
    <div class="toolbar">
      <div class="toolbar-row">
        <div class="search-field">
          ${icon("search", 18)}
          <input class="input" id="lib-search" type="search" autocomplete="off" placeholder="Search title, author, series, narrator, description" value="${esc(state.q)}">
        </div>
        <div class="view-switch" role="group" aria-label="View">
          <button type="button" id="view-grid" title="Cover grid">${icon("grid", 17)}</button>
          <button type="button" id="view-table" title="Table">${icon("table", 17)}</button>
        </div>
      </div>
      <div class="toolbar-row">
        <select class="input filter-select" id="filter-genre" aria-label="Genre">
          ${option("", "All genres", !state.genre)}
          ${genres.map((genre) => option(genre, genre, state.genre.toLowerCase() === genre.toLowerCase())).join("")}
        </select>
        <select class="input filter-select" id="filter-subgenre" aria-label="Subgenre">
          ${option("", "All subgenres", !state.subgenre)}
          ${subgenreOptions.map((value) => option(value, value, state.subgenre.toLowerCase() === value.toLowerCase())).join("")}
        </select>
        <select class="input filter-select" id="filter-status" aria-label="Status">
          ${option("", "Any status", !state.status)}
          ${["unread", "read", "didnt_finish"].map((value) => option(value, statusLabel(value), state.status === value)).join("")}
        </select>
        <select class="input filter-select" id="filter-edition" aria-label="Edition">
          ${option("", "All formats", !state.edition)}
          ${option("ebook", "Ebook", state.edition === "ebook")}
          ${option("audiobook", "Audiobook", state.edition === "audiobook")}
        </select>
        <button type="button" class="chip chip-toggle ${state.review ? "active" : ""}" id="filter-review">${icon("alert", 13)} Needs review</button>
        <select class="input filter-select" id="sort-select" aria-label="Sort">
          ${SORTS.map(([value, label]) => option(value, label, state.sort === value)).join("")}
        </select>
      </div>
      <div class="filter-chips" id="active-filters"></div>
    </div>
    <div class="result-count" id="result-count"></div>
    <div id="library-results"></div>
    <div class="sentinel" id="sentinel"></div>
    <div class="end-note" id="end-note"></div>
    <div id="bulk-bar"></div>
  `;

  const results = main.querySelector("#library-results");
  const countElement = main.querySelector("#result-count");
  const endNote = main.querySelector("#end-note");
  const bulkRoot = main.querySelector("#bulk-bar");
  const searchInput = main.querySelector("#lib-search");
  const genreSelect = main.querySelector("#filter-genre");
  const subgenreSelect = main.querySelector("#filter-subgenre");
  const statusSelect = main.querySelector("#filter-status");
  const editionSelect = main.querySelector("#filter-edition");
  const reviewToggle = main.querySelector("#filter-review");
  const sortSelect = main.querySelector("#sort-select");
  const sentinel = main.querySelector("#sentinel");
  const gridButton = main.querySelector("#view-grid");
  const tableButton = main.querySelector("#view-table");

  let items = [];
  let total = 0;
  let offset = 0;
  let loading = false;
  let done = false;
  let generation = 0;
  let selectAll = null;
  const selected = new Set();

  const hasFilters = () =>
    Boolean(state.q || state.genre || state.subgenre || state.status || state.edition || state.review);

  const syncURL = () => {
    const paramsObject = new URLSearchParams();
    if (state.q) paramsObject.set("q", state.q);
    if (state.genre) paramsObject.set("genre", state.genre);
    if (state.subgenre) paramsObject.set("subgenre", state.subgenre);
    if (state.status) paramsObject.set("status", state.status);
    if (state.edition) paramsObject.set("edition", state.edition);
    if (state.review) paramsObject.set("review", "1");
    if (state.sort !== "title") paramsObject.set("sort", state.sort);
    const defaultDirection = state.sort === "added" ? "desc" : "asc";
    if (state.direction !== defaultDirection) paramsObject.set("direction", state.direction);
    if (state.view === "table") paramsObject.set("view", "table");
    const text = paramsObject.toString();
    history.replaceState(null, "", `/library${text ? `?${text}` : ""}`);
  };

  const syncControls = () => {
    genreSelect.value = state.genre;
    subgenreSelect.value = state.subgenre;
    statusSelect.value = state.status;
    editionSelect.value = state.edition;
    sortSelect.value = state.sort;
    reviewToggle.classList.toggle("active", state.review);
    gridButton.classList.toggle("active", state.view === "grid");
    tableButton.classList.toggle("active", state.view === "table");
    if (searchInput.value !== state.q) searchInput.value = state.q;
  };

  const buildFilterChips = () => {
    const container = main.querySelector("#active-filters");
    const chips = [];
    if (state.q) chips.push(["q", `Search: ${state.q}`]);
    if (state.genre) chips.push(["genre", state.genre]);
    if (state.subgenre) chips.push(["subgenre", state.subgenre]);
    if (state.status) chips.push(["status", statusLabel(state.status)]);
    if (state.edition) chips.push(["edition", editionLabel(state.edition)]);
    if (state.review) chips.push(["review", "Needs review"]);
    container.innerHTML = chips
      .map(
        ([key, label]) =>
          `<span class="chip accent">${esc(label)}<button type="button" data-clear="${key}" aria-label="Clear ${esc(label)}">${icon("x", 12)}</button></span>`
      )
      .join("");
    container.querySelectorAll("[data-clear]").forEach((button) => {
      button.addEventListener("click", () => {
        const key = button.dataset.clear;
        if (key === "review") state.review = false;
        else state[key] = "";
        syncControls();
        syncURL();
        buildFilterChips();
        reset();
      });
    });
  };

  const updateBulkBar = () => {
    if (!selected.size) {
      bulkRoot.innerHTML = "";
      return;
    }
    const chosen = items.filter((book) => selected.has(book.id));
    bulkRoot.innerHTML = `
      <div class="bulk-bar">
        <strong>${selected.size} selected</strong>
        <button class="btn btn-primary btn-sm" type="button" id="bulk-edit">${icon("edit", 14)}<span>Edit selected</span></button>
        <button class="btn btn-ghost btn-sm" type="button" id="bulk-clear">Clear</button>
      </div>
    `;
    bulkRoot.querySelector("#bulk-clear").addEventListener("click", () => {
      selected.clear();
      document.querySelectorAll(".book-card.selected, tr.selected").forEach((element) => element.classList.remove("selected"));
      document.querySelectorAll("input[data-select]").forEach((input) => {
        input.checked = false;
      });
      if (selectAll) selectAll.checked = false;
      updateBulkBar();
    });
    bulkRoot.querySelector("#bulk-edit").addEventListener("click", () => {
      if (!chosen.length) return;
      openBulkDialog(chosen, {
        onSaved: () => {
          selected.clear();
          reset();
        },
      });
    });
  };

  const markSelection = (id, checked) => {
    if (checked) selected.add(id);
    else selected.delete(id);
    results.querySelectorAll(`[data-card-id="${id}"]`).forEach((element) => {
      element.classList.toggle("selected", checked);
    });
    results.querySelectorAll(`input[data-select="${id}"]`).forEach((input) => {
      input.checked = checked;
    });
    if (selectAll) {
      selectAll.checked = items.length > 0 && items.every((book) => selected.has(book.id));
    }
    updateBulkBar();
  };

  const wireSelection = () => {
    results.addEventListener("change", (event) => {
      const input = event.target.closest("input[data-select]");
      if (!input) return;
      markSelection(Number(input.dataset.select), input.checked);
    });
  };
  wireSelection();

  const sortArrow = (key) => {
    if (state.sort !== key) return "";
    return `<span class="sort-arrow">${state.direction === "desc" ? "↓" : "↑"}</span>`;
  };

  const buildTableShell = () => {
    results.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="check-cell"><input type="checkbox" id="select-all" aria-label="Select all loaded books"></th>
              <th class="sortable" data-sort="title">Title ${sortArrow("title")}</th>
              <th class="sortable" data-sort="author">Author ${sortArrow("author")}</th>
              <th class="sortable" data-sort="series">Series ${sortArrow("series")}</th>
              <th class="sortable" data-sort="genre">Genre ${sortArrow("genre")}</th>
              <th class="sortable" data-sort="status">Status ${sortArrow("status")}</th>
              <th>Formats</th>
              <th class="sortable" data-sort="added">Added ${sortArrow("added")}</th>
            </tr>
          </thead>
          <tbody id="book-rows"></tbody>
        </table>
      </div>
    `;
    selectAll = results.querySelector("#select-all");
    selectAll.addEventListener("change", () => {
      items.forEach((book) => {
        if (selectAll.checked) selected.add(book.id);
        else selected.delete(book.id);
      });
      results.querySelectorAll("input[data-select]").forEach((input) => {
        input.checked = selectAll.checked;
      });
      results.querySelectorAll("[data-card-id]").forEach((element) => {
        element.classList.toggle("selected", selectAll.checked);
      });
      updateBulkBar();
    });
    results.querySelectorAll("th.sortable").forEach((header) => {
      header.addEventListener("click", () => {
        const key = header.dataset.sort;
        if (state.sort === key) {
          state.direction = state.direction === "asc" ? "desc" : "asc";
        } else {
          state.sort = key;
          state.direction = key === "added" ? "desc" : "asc";
        }
        sortSelect.value = state.sort;
        syncURL();
        reset();
      });
    });
  };

  const appendBooks = (books) => {
    if (!books.length) return;
    if (state.view === "grid") {
      const grid = results.querySelector("#book-grid");
      grid.insertAdjacentHTML("beforeend", books.map((book) => bookCard(book, { selectable: true })).join(""));
      return;
    }
    const tbody = results.querySelector("#book-rows");
    tbody.insertAdjacentHTML(
      "beforeend",
      books
        .map(
          (book) => `
          <tr data-card-id="${book.id}" class="${selected.has(book.id) ? "selected" : ""}">
            <td class="check-cell"><input type="checkbox" data-select="${book.id}" aria-label="Select ${esc(book.title)}" ${selected.has(book.id) ? "checked" : ""}></td>
            <td>
              <a class="row-title" href="/book/${book.id}" data-link>
                ${rowThumb(book)}
                <span>${esc(book.title)}</span>
              </a>
            </td>
            <td>${esc(authorsLine(book))}</td>
            <td>${seriesText(book)}</td>
            <td>${esc(book.genre || "")}</td>
            <td>${statusBadge(book.status)}</td>
            <td><span class="badges">${formatBadges(book)}</span></td>
            <td class="nowrap">${esc(fmtDate(book.added_at))}</td>
          </tr>`
        )
        .join("")
    );
  };

  const showEmpty = () => {
    if (hasFilters()) {
      results.innerHTML = emptyState({
        iconName: "search",
        title: "No books match",
        text: "Try a different search or clear one of the filters.",
        action: `<button class="btn btn-ghost" type="button" id="clear-filters">Clear filters</button>`,
      });
      results.querySelector("#clear-filters").addEventListener("click", () => {
        state.q = "";
        state.genre = "";
        state.subgenre = "";
        state.status = "";
        state.edition = "";
        state.review = false;
        syncControls();
        syncURL();
        buildFilterChips();
        reset();
      });
    } else {
      results.innerHTML = emptyState({
        iconName: "bookOpen",
        title: "Your library is empty",
        text: "Add an EPUB, an audio file, or a folder of audio files to get started.",
        action: `<button class="btn btn-primary" type="button" id="library-add">${icon("plus", 16)}<span>Add your first book</span></button>`,
      });
      results.querySelector("#library-add").addEventListener("click", () =>
        openAddDialog({ onImported: (book) => navigate(`/book/${book.id}`) })
      );
    }
  };

  const loadMore = async () => {
    if (loading || done) return;
    loading = true;
    const current = generation;
    try {
      const paramsObject = {
        offset,
        limit: PAGE_SIZE,
        sort: state.sort,
        direction: state.direction,
      };
      if (state.q) paramsObject.q = state.q;
      if (state.genre) paramsObject.genre = state.genre;
      if (state.subgenre) paramsObject.subgenre = state.subgenre;
      if (state.status) paramsObject.status = state.status;
      if (state.edition) paramsObject.edition = state.edition;
      if (state.review) paramsObject.review = "true";
      const data = await api.books(paramsObject);
      if (current !== generation) return;
      total = data.total;
      items.push(...data.books);
      appendBooks(data.books);
      offset += data.books.length;
      done = offset >= total || data.books.length === 0;
      countElement.textContent = `${total} book${total === 1 ? "" : "s"}`;
      endNote.textContent = done && total > 0 ? "End of library" : "";
      if (total === 0) showEmpty();
      if (selectAll) {
        selectAll.checked = items.length > 0 && items.every((book) => selected.has(book.id));
      }
      if (!done) {
        window.setTimeout(() => {
          if (current === generation && sentinel.getBoundingClientRect().top < window.innerHeight + 700) {
            loadMore();
          }
        }, 0);
      }
    } catch (error) {
      if (current === generation) {
        done = true;
        toast(error.message, "error");
      }
    } finally {
      loading = false;
    }
  };

  const reset = async () => {
    generation += 1;
    items = [];
    total = 0;
    offset = 0;
    done = false;
    countElement.textContent = "";
    endNote.textContent = "";
    selected.clear();
    updateBulkBar();
    if (state.view === "grid") {
      results.innerHTML = `<div class="cover-grid" id="book-grid"></div>`;
      selectAll = null;
    } else {
      buildTableShell();
    }
    await loadMore();
  };

  gridButton.addEventListener("click", () => {
    if (state.view === "grid") return;
    state.view = "grid";
    syncControls();
    syncURL();
    reset();
  });
  tableButton.addEventListener("click", () => {
    if (state.view === "table") return;
    state.view = "table";
    syncControls();
    syncURL();
    reset();
  });

  let searchTimer = null;
  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => {
      state.q = searchInput.value.trim();
      syncURL();
      buildFilterChips();
      reset();
    }, 280);
  });

  genreSelect.addEventListener("change", () => {
    state.genre = genreSelect.value;
    syncURL();
    buildFilterChips();
    reset();
  });
  subgenreSelect.addEventListener("change", () => {
    state.subgenre = subgenreSelect.value;
    syncURL();
    buildFilterChips();
    reset();
  });
  statusSelect.addEventListener("change", () => {
    state.status = statusSelect.value;
    syncURL();
    buildFilterChips();
    reset();
  });
  editionSelect.addEventListener("change", () => {
    state.edition = editionSelect.value;
    syncURL();
    buildFilterChips();
    reset();
  });
  reviewToggle.addEventListener("click", () => {
    state.review = !state.review;
    syncControls();
    syncURL();
    buildFilterChips();
    reset();
  });
  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    state.direction = state.sort === "added" ? "desc" : "asc";
    syncURL();
    reset();
  });

  const observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) loadMore();
    },
    { rootMargin: "700px 0px" }
  );
  observer.observe(sentinel);

  syncControls();
  buildFilterChips();
  await reset();

  return () => {
    generation += 1;
    window.clearTimeout(searchTimer);
    observer.disconnect();
  };
}
