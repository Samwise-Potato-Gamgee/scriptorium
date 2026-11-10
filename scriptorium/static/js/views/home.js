// Home view: counts plus recently added and unread rows.
import { api } from "../api.js";
import { store } from "../store.js";
import { icon } from "../icons.js";
import { bookCard } from "../components.js";
import { fmtDuration, esc } from "../format.js";
import { emptyState } from "../ui.js";
import { openAddDialog } from "../forms.js";
import { navigate } from "../router.js";

export async function homeView(main) {
  main.innerHTML = `<div class="loading-screen"><span class="spinner"></span></div>`;
  const data = await api.home();
  const counts = data.counts;
  const stats = [
    { value: counts.books, label: "Books" },
    { value: counts.ebooks, label: "Ebooks" },
    { value: counts.audiobooks, label: "Audiobooks" },
    { value: fmtDuration(counts.listening_seconds) || "0 min", label: "Listening" },
  ];
  const row = (title, books, linkText = "Browse library") => `
    <section class="section">
      <div class="section-head">
        <h2>${esc(title)}</h2>
        <a href="/library" data-link>${esc(linkText)}</a>
      </div>
      <div class="cover-grid">
        ${books.map((book) => bookCard(book)).join("")}
      </div>
    </section>
  `;
  const emptyActions = `
    <button class="btn btn-primary" type="button" id="home-add">${icon("plus", 16)}<span>Add your first book</span></button>
  `;
  main.innerHTML = `
    <header class="page-head">
      <div>
        <h1>Home</h1>
        <p class="subtitle">${store.state && store.state.library.path ? esc(store.state.library.path) : "Your library at a glance."}</p>
      </div>
      <button class="btn btn-primary" type="button" id="home-add-top">${icon("plus", 16)}<span>Add book</span></button>
    </header>
    <section class="stats">
      ${stats
        .map(
          (item) => `
          <div class="stat">
            <span class="stat-value">${esc(item.value)}</span>
            <span class="stat-label">${esc(item.label)}</span>
          </div>`
        )
        .join("")}
    </section>
    ${
      counts.books
        ? `${data.recent.length ? row("Recently added", data.recent) : ""}
           ${data.unread.length ? row("Unread — pick up next", data.unread) : ""}`
        : emptyState({
            iconName: "bookOpen",
            title: "Your library is empty",
            text: "Add an EPUB, an audio file, or a folder of audio files to get started.",
            action: emptyActions,
          })
    }
  `;
  const openAdd = () =>
    openAddDialog({
      onImported: (book) => navigate(`/book/${book.id}`),
    });
  main.querySelector("#home-add-top").addEventListener("click", openAdd);
  const emptyButton = main.querySelector("#home-add");
  if (emptyButton) emptyButton.addEventListener("click", openAdd);
  return () => {};
}
