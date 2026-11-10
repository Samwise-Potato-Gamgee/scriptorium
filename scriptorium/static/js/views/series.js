// Series views: the series list and one series in order with missing numbers.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { authorsLine, esc, statusLabel } from "../format.js";
import { formatBadges, rowThumb, statusBadge } from "../components.js";
import { emptyState } from "../ui.js";

export async function seriesView(main, params, search) {
  const name = (search.get("name") || "").trim();
  if (name) return seriesDetail(main, name);
  const data = await api.series();
  const series = data.series || [];
  if (!series.length) {
    main.innerHTML = `
      <header class="page-head"><div><h1>Series</h1><p class="subtitle">Books grouped by series.</p></div></header>
      ${emptyState({
        iconName: "series",
        title: "No series yet",
        text: "Set a series name on a book in the edit form and it will appear here in order.",
      })}
    `;
    return () => {};
  }
  main.innerHTML = `
    <header class="page-head">
      <div>
        <h1>Series</h1>
        <p class="subtitle">${series.length} series in your library.</p>
      </div>
    </header>
    <div class="series-list">
      ${series
        .map(
          (entry) => `
          <a class="series-entry" href="/series?name=${encodeURIComponent(entry.name)}" data-link>
            <div>
              <h3>${esc(entry.name)}</h3>
              <p>${entry.count} book${entry.count === 1 ? "" : "s"}</p>
            </div>
            <span class="chip">${icon("series", 13)} ${entry.count}</span>
          </a>`
        )
        .join("")}
    </div>
  `;
  return () => {};
}

async function seriesDetail(main, name) {
  const data = await api.seriesDetail(name);
  const books = data.books || [];
  if (!books.length) {
    main.innerHTML = `
      <a class="back-link" href="/series" data-link>${icon("back", 16)}<span>All series</span></a>
      ${emptyState({
        iconName: "series",
        title: "Series not found",
        text: "No books carry this series name any more.",
      })}
    `;
    return () => {};
  }
  main.innerHTML = `
    <a class="back-link" href="/series" data-link>${icon("back", 16)}<span>All series</span></a>
    <header class="page-head">
      <div>
        <h1>${esc(data.name)}</h1>
        <p class="subtitle">${books.length} book${books.length === 1 ? "" : "s"} in this series.</p>
      </div>
    </header>
    ${(data.gaps || []).length ? `<div class="gap-list">${data.gaps.map((number) => `<span class="chip accent">Missing #${esc(number)}</span>`).join("")}</div>` : ""}
    <div class="series-list">
      ${books
        .map(
          (book) => `
          <a class="series-book" href="/book/${book.id}" data-link>
            <span class="series-number">${book.series_number ? `#${esc(book.series_number)}` : "—"}</span>
            ${rowThumb(book)}
            <span class="series-book-main">
              <h3>${esc(book.title)}</h3>
              <p>${esc(authorsLine(book))}${book.status ? ` · ${esc(statusLabel(book.status))}` : ""}</p>
            </span>
            <span class="badges">${formatBadges(book)}${statusBadge(book.status)}</span>
          </a>`
        )
        .join("")}
    </div>
  `;
  return () => {};
}
