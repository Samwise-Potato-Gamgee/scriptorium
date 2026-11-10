// Book page: large cover, shared details, both editions and their actions.
import { api } from "../api.js";
import { icon } from "../icons.js";
import {
  coverUrl,
  editionLabel,
  esc,
  fileCount,
  fmtDate,
  fmtDuration,
  fmtSize,
  totalDuration,
} from "../format.js";
import { statusBadge } from "../components.js";
import {
  openDeleteBookDialog,
  openEditDialog,
  openEditionCoverDialog,
  openNarratorDialog,
  openRemoveEditionDialog,
  openReplaceDialog,
} from "../forms.js";
import { navigate } from "../router.js";

function editionPath(edition) {
  if (edition.is_folder) return edition.path;
  const files = edition.files || [];
  return files.length ? files[0].path : edition.path;
}

function editionSize(edition) {
  return (edition.files || []).reduce((sum, file) => sum + (Number(file.size) || 0), 0);
}

function editionCard(book, edition) {
  const audiobook = edition.kind === "audiobook";
  const files = edition.files || [];
  const rows = [
    `<dt>Path</dt><dd class="mono">${esc(editionPath(edition))}</dd>`,
  ];
  if (audiobook) {
    if (edition.duration) rows.push(`<dt>Duration</dt><dd>${esc(fmtDuration(edition.duration))}</dd>`);
    if (edition.narrator) rows.push(`<dt>Narrator</dt><dd>${esc(edition.narrator)}</dd>`);
    if (edition.is_folder) {
      rows.push(`<dt>Files</dt><dd>${files.length} file${files.length === 1 ? "" : "s"} in play order</dd>`);
    }
    if (edition.cover) rows.push(`<dt>Cover</dt><dd>This edition has its own cover</dd>`);
  }
  rows.push(`<dt>Size</dt><dd>${esc(fmtSize(editionSize(edition)))}</dd>`);
  if (edition.imported_from) {
    rows.push(`<dt>Imported from</dt><dd>${esc(edition.imported_from)}</dd>`);
  }
  return `
    <article class="edition-card">
      <div class="edition-head">
        <span class="edition-icon">${icon(audiobook ? "headphones" : "bookOpen", 19)}</span>
        <div>
          <div class="edition-name">${editionLabel(edition.kind)} edition</div>
          <div class="edition-sub">${audiobook ? (edition.is_folder ? "Folder audiobook" : "Single audio file") : "Single EPUB file"}</div>
        </div>
      </div>
      <dl class="edition-rows">${rows.join("")}</dl>
      <div class="edition-actions">
        <button class="btn btn-ghost btn-sm" type="button" data-action="replace" data-edition="${edition.id}">${icon("refresh", 14)}<span>Replace file</span></button>
        ${audiobook ? `<button class="btn btn-ghost btn-sm" type="button" data-action="narrator" data-edition="${edition.id}">${icon("edit", 14)}<span>Narrator</span></button>` : ""}
        ${audiobook ? `<button class="btn btn-ghost btn-sm" type="button" data-action="cover" data-edition="${edition.id}">${icon("image", 14)}<span>Cover</span></button>` : ""}
        <button class="btn btn-danger-ghost btn-sm" type="button" data-action="remove" data-edition="${edition.id}">${icon("trash", 14)}<span>Remove edition</span></button>
      </div>
    </article>
  `;
}

export async function bookView(main, params) {
  const bookId = Number(params.id);
  let book = null;

  const paint = async () => {
    const data = await api.book(bookId);
    book = data.book;
    const cover = coverUrl(book, "cover");
    const series = book.series
      ? `<a href="/series?name=${encodeURIComponent(book.series)}" data-link>${esc(book.series)}${book.series_number ? ` #${esc(book.series_number)}` : ""}</a>`
      : "";
    const duration = totalDuration(book);
    main.innerHTML = `
      <a class="back-link" href="/library" data-link>${icon("back", 16)}<span>Library</span></a>
      <div class="book-layout">
        <div class="book-cover-wrap">
          <div class="book-cover">${cover ? `<img src="${esc(cover)}" alt="">` : `<div class="cover-placeholder">${esc(book.title)}</div>`}</div>
        </div>
        <div>
          ${series ? `<div class="eyebrow">${icon("series", 13)} ${series}</div>` : ""}
          <h1 class="book-title">${esc(book.title)}</h1>
          <p class="book-authors">${book.authors && book.authors.length ? `by ${esc(book.authors.join(", "))}` : "Unknown author"}</p>
          <div class="book-meta">
            ${statusBadge(book.status)}
            <span class="chip">${esc(book.genre || "Other")}</span>
            ${(book.subgenres || []).map((value) => `<span class="chip">${esc(value)}</span>`).join("")}
            ${book.needs_review ? `<span class="badge danger">${icon("alert", 12)} Needs review</span>` : ""}
            ${book.has_ebook ? `<span class="badge outline">${icon("bookOpen", 12)} Ebook</span>` : ""}
            ${book.has_audiobook ? `<span class="badge outline">${icon("headphones", 12)} Audiobook</span>` : ""}
          </div>
          <p class="description">${book.description ? esc(book.description) : "No description."}</p>
          <div class="book-actions">
            <button class="btn btn-primary" type="button" id="book-edit">${icon("edit", 16)}<span>Edit book</span></button>
            <button class="btn btn-danger-ghost" type="button" id="book-delete">${icon("trash", 16)}<span>Delete book</span></button>
          </div>
          <dl class="details-grid">
            <dt>Added</dt><dd>${esc(fmtDate(book.added_at)) || "—"}</dd>
            <dt>Imported from</dt><dd>${esc(book.imported_from || "—")}${book.imported_from_kind === "folder" ? " (folder)" : ""}</dd>
            <dt>Total duration</dt><dd>${duration ? esc(fmtDuration(duration)) : "—"}</dd>
            <dt>Files</dt><dd>${fileCount(book)}</dd>
            <dt>Editions</dt><dd>${(book.editions || []).map((edition) => editionLabel(edition.kind)).join(" · ") || "—"}</dd>
          </dl>
        </div>
      </div>
      <section class="editions">
        <div class="section-head">
          <h2>Editions</h2>
          <span class="field-help">One edition of each format</span>
        </div>
        ${(book.editions || []).length ? `<div class="edition-grid">${book.editions.map((edition) => editionCard(book, edition)).join("")}</div>` : `<div class="notice muted">This book has no editions.</div>`}
      </section>
    `;
    wire();
  };

  const wire = () => {
    main.querySelector("#book-edit").addEventListener("click", () =>
      openEditDialog(book, { onSaved: () => paint() })
    );
    main.querySelector("#book-delete").addEventListener("click", () =>
      openDeleteBookDialog(book, { onDeleted: () => navigate("/library") })
    );
    main.querySelectorAll("[data-action]").forEach((button) => {
      const edition = (book.editions || []).find((item) => item.id === Number(button.dataset.edition));
      if (!edition) return;
      const action = button.dataset.action;
      button.addEventListener("click", () => {
        if (action === "replace") {
          openReplaceDialog(book, edition, { onReplaced: () => paint() });
        } else if (action === "narrator") {
          openNarratorDialog(book, edition, { onSaved: () => paint() });
        } else if (action === "cover") {
          openEditionCoverDialog(book, edition, { onSaved: () => paint() });
        } else if (action === "remove") {
          openRemoveEditionDialog(book, edition, {
            onRemoved: () => paint(),
            onBookDeleted: () => navigate("/library"),
          });
        }
      });
    });
  };

  await paint();
  return () => {};
}
