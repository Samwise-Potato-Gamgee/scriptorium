// Reusable book presentation pieces: cover tiles, badges and series links.
import { icon } from "./icons.js";
import {
  authorsLine,
  coverUrl,
  editionLabel,
  esc,
  seriesLabel,
  statusClass,
  statusLabel,
} from "./format.js";

export function formatBadges(book) {
  const ebook = book.has_ebook ?? (book.editions || []).some((edition) => edition.kind === "ebook");
  const audiobook = book.has_audiobook ?? (book.editions || []).some((edition) => edition.kind === "audiobook");
  return [
    ebook ? `<span class="format-badge" title="Ebook">${icon("bookOpen", 13)}</span>` : "",
    audiobook ? `<span class="format-badge" title="Audiobook">${icon("headphones", 13)}</span>` : "",
  ].join("");
}

export function statusBadge(status) {
  return `<span class="badge ${statusClass(status)}">${esc(statusLabel(status))}</span>`;
}

export function coverBlock(book, { size = "thumb", lazy = true } = {}) {
  const url = coverUrl(book, size);
  if (!url) {
    return `<div class="cover-placeholder">${esc(book.title)}</div>`;
  }
  return `<img ${lazy ? 'loading="lazy"' : ""} src="${esc(url)}" alt="">`;
}

export function bookCard(book, { selectable = false } = {}) {
  return `
    <div class="book-card" data-card-id="${book.id}">
      <a class="card-main" href="/book/${book.id}" data-link>
        <div class="cover">
          ${coverBlock(book)}
          <div class="formats">${formatBadges(book)}</div>
        </div>
        <div class="card-title">${esc(book.title)}</div>
        <div class="card-author">${esc(authorsLine(book))}</div>
      </a>
      ${selectable ? `<label class="card-check" title="Select this book"><input type="checkbox" data-select="${book.id}" aria-label="Select ${esc(book.title)}"></label>` : ""}
    </div>
  `;
}

export function rowThumb(book) {
  const url = coverUrl(book, "thumb");
  return `<div class="row-thumb">${url ? `<img loading="lazy" src="${esc(url)}" alt="">` : `<div class="cover-placeholder">${esc((book.title || "").slice(0, 2))}</div>`}</div>`;
}

export function seriesText(book) {
  const label = seriesLabel(book);
  if (!label) return `<span class="muted">—</span>`;
  return `<a href="/series?name=${encodeURIComponent(book.series)}" data-link>${esc(label)}</a>`;
}

export function editionBadges(book) {
  return (book.editions || [])
    .map((edition) => `<span class="badge outline">${icon(edition.kind === "ebook" ? "bookOpen" : "headphones", 12)} ${editionLabel(edition.kind)}</span>`)
    .join("");
}
