// Settings: library folder, appearance, server port, genres, check,
// trash, backups and about.
import { api } from "../api.js";
import { applyGenres, applySettings, store } from "../store.js";
import { icon } from "../icons.js";
import { esc, fmtDate, fmtSize } from "../format.js";
import { confirmDialog, toast } from "../ui.js";
import { applyTheme } from "../theme.js";
import { withPathPicker } from "../pathfield.js";
import { openLibraryAt } from "./setup.js";
import { reloadApp } from "../router.js";

const THEME_OPTIONS = [
  ["system", "System", "monitor"],
  ["light", "Light", "sun"],
  ["dark", "Dark", "moon"],
];

export async function settingsView(main) {
  const data = await api.settings();
  applySettings(data.settings);
  applyGenres(data.genres);
  store.version = data.version;
  applyTheme(data.settings.theme, data.settings.accent);
  let genres = [...data.genres];
  let trash = data.trash;

  main.innerHTML = `
    <header class="page-head">
      <div>
        <h1>Settings</h1>
        <p class="subtitle">This machine's library and appearance.</p>
      </div>
    </header>
    <div class="settings-grid">
      <section class="panel" id="panel-library">
        <h2>Library folder</h2>
        <p class="panel-sub">Your books, covers, backups and trash live here. Changing the folder opens a different library; files are never moved between folders.</p>
        <p class="mono">${esc(data.library.path)}</p>
        <div class="form-actions" style="margin-top:14px">
          <button class="btn btn-ghost" type="button" id="show-library-form">${icon("folder", 16)}<span>Change library folder</span></button>
        </div>
        <div id="library-form" hidden>
          <div class="field" style="margin-top:14px">
            <span>New library folder</span>
            <input class="input" id="new-library-path" autocomplete="off" spellcheck="false" placeholder="Folder path">
            <span class="field-help">An existing library opens there; if the folder is empty you will be asked before a new one is created.</span>
          </div>
          <div class="form-actions">
            <button class="btn btn-primary" type="button" id="open-library">${icon("check", 16)}<span>Open library</span></button>
            <button class="btn btn-ghost" type="button" id="cancel-library">Cancel</button>
          </div>
          <div class="inline-error" id="library-error" hidden></div>
        </div>
      </section>

      <section class="panel">
        <h2>Appearance</h2>
        <p class="panel-sub">Light and dark follow the system setting unless you pick one. The accent colour appears on buttons, selected items, badges and links.</p>
        <div class="theme-options" id="theme-options" role="group" aria-label="Theme">
          ${THEME_OPTIONS.map(
            ([value, label, iconName]) =>
              `<button type="button" data-theme="${value}" class="${data.settings.theme === value ? "active" : ""}">${icon(iconName, 15)}<span>${label}</span></button>`
          ).join("")}
        </div>
        <div class="swatches" id="accent-swatches" style="margin-top:18px">
          ${(data.accents || [])
            .map(
              (accent) =>
                `<button class="swatch ${accent.value.toLowerCase() === data.settings.accent.toLowerCase() ? "active" : ""}" type="button" data-accent="${esc(accent.value)}" title="${esc(accent.name)}" aria-label="${esc(accent.name)}" style="background-color:${esc(accent.value)}"></button>`
            )
            .join("")}
          <label class="custom-color">Custom
            <input type="color" id="custom-accent" value="${esc(data.settings.accent)}" aria-label="Custom accent colour">
          </label>
        </div>
      </section>

      <section class="panel">
        <h2>Server</h2>
        <p class="panel-sub">Scriptorium listens on this computer only. The port change takes effect after a restart.</p>
        <div class="inline-form">
          <label class="field" style="flex:0 0 150px">
            <span>Port</span>
            <input class="input" type="number" id="port-input" min="1024" max="65535" value="${esc(data.settings.port)}">
          </label>
          <button class="btn btn-ghost" type="button" id="save-port">${icon("check", 16)}<span>Save port</span></button>
          <span class="field-help" id="server-address">http://127.0.0.1:${esc(data.settings.port)}/</span>
        </div>
      </section>

      <section class="panel">
        <h2>Importing</h2>
        <p class="panel-sub">The review screen and the Replace file dialog start with this choice, and can change it for a single import.</p>
        <label class="check-row">
          <input type="checkbox" id="delete-originals" ${data.settings.delete_originals ? "checked" : ""}>
          <span>Delete originals after import by default</span>
        </label>
        <p class="panel-note">When unticked, the source file or folder stays where it is after the verified copy is saved in the library.</p>
      </section>

      <section class="panel">
        <h2>Main genres</h2>
        <p class="panel-sub">Exactly one main genre per book. “Other” is the catch-all and always stays available.</p>
        <div class="genre-list" id="genre-list"></div>
        <div class="inline-form">
          <input class="input" id="new-genre" placeholder="Add a genre" autocomplete="off">
          <button class="btn btn-ghost" type="button" id="add-genre">${icon("plus", 16)}<span>Add</span></button>
          <button class="btn btn-primary" type="button" id="save-genres">${icon("check", 16)}<span>Save genres</span></button>
        </div>
        <div class="inline-error" id="genre-error" hidden></div>
      </section>

      <section class="panel">
        <h2>Check library</h2>
        <p class="panel-sub">Compares the database with the files on disk. It only reports — it never changes anything.</p>
        <button class="btn btn-ghost" type="button" id="run-check">${icon("search", 16)}<span>Check library</span></button>
        <div id="check-results"></div>
      </section>

      <section class="panel">
        <h2>Trash</h2>
        <p class="panel-sub">Deleted books and editions wait here until you restore them. Nothing is removed automatically.</p>
        <div id="trash-panel"></div>
      </section>

      <section class="panel">
        <h2>Backups</h2>
        <p class="panel-sub">A copy of library.db is made each time Scriptorium starts. The last 5 are kept in the backups folder.</p>
        <div class="backup-list">
          ${
            (data.backups || []).length
              ? data.backups
                  .map(
                    (backup) => `
                    <div class="backup-row">
                      <span class="mono">${esc(backup.name)}</span>
                      <span class="row-sub">${esc(fmtSize(backup.size))} · ${esc(fmtDate(new Date(backup.modified * 1000).toISOString()))}</span>
                    </div>`
                  )
                  .join("")
              : `<div class="panel-note">No backups yet.</div>`
          }
        </div>
      </section>

      <section class="panel">
        <h2>About</h2>
        <p class="panel-sub">Scriptorium ${esc(data.version)} — a local, offline ebook and audiobook library. It never contacts the internet.</p>
        <p class="panel-note">Library folder: <span class="mono">${esc(data.library.path)}</span></p>
      </section>
    </div>
  `;

  const libraryForm = main.querySelector("#library-form");
  const libraryButton = main.querySelector("#show-library-form");
  const libraryPath = main.querySelector("#new-library-path");
  withPathPicker(libraryPath, ["folder"]);
  const libraryError = main.querySelector("#library-error");
  libraryButton.addEventListener("click", () => {
    libraryForm.hidden = !libraryForm.hidden;
    if (!libraryForm.hidden) libraryPath.focus();
  });
  main.querySelector("#cancel-library").addEventListener("click", () => {
    libraryForm.hidden = true;
    libraryError.hidden = true;
  });
  main.querySelector("#open-library").addEventListener("click", async () => {
    const path = libraryPath.value.trim();
    if (!path) {
      libraryError.textContent = "Enter a folder path.";
      libraryError.hidden = false;
      return;
    }
    libraryError.hidden = true;
    try {
      const opened = await openLibraryAt(path);
      if (opened) {
        toast("Library opened");
        reloadApp();
      }
    } catch (error) {
      libraryError.textContent = error.message;
      libraryError.hidden = false;
    }
  });

  const themeButtons = [...main.querySelectorAll("[data-theme]")];
  const setThemeActive = (value) => {
    themeButtons.forEach((button) => button.classList.toggle("active", button.dataset.theme === value));
  };
  themeButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      const value = button.dataset.theme;
      store.settings.theme = value;
      applyTheme(value, store.settings.accent);
      setThemeActive(value);
      try {
        const result = await api.saveSettings({ theme: value });
        applySettings(result);
      } catch (error) {
        toast(error.message, "error");
      }
    });
  });

  const swatchButtons = [...main.querySelectorAll("[data-accent]")];
  const customAccent = main.querySelector("#custom-accent");
  const setAccentActive = (value) => {
    swatchButtons.forEach((button) =>
      button.classList.toggle("active", button.dataset.accent.toLowerCase() === value.toLowerCase())
    );
    customAccent.value = value;
  };
  const saveAccent = async (value) => {
    store.settings.accent = value;
    applyTheme(store.settings.theme, value);
    setAccentActive(value);
    try {
      const result = await api.saveSettings({ accent: value });
      applySettings(result);
    } catch (error) {
      toast(error.message, "error");
    }
  };
  swatchButtons.forEach((button) => {
    button.addEventListener("click", () => saveAccent(button.dataset.accent));
  });
  customAccent.addEventListener("input", () => {
    applyTheme(store.settings.theme, customAccent.value);
    swatchButtons.forEach((button) => button.classList.remove("active"));
  });
  customAccent.addEventListener("change", () => saveAccent(customAccent.value));

  const portInput = main.querySelector("#port-input");
  main.querySelector("#save-port").addEventListener("click", async () => {
    const port = Number(portInput.value);
    if (!Number.isInteger(port) || port < 1024 || port > 65535) {
      toast("Choose a port between 1024 and 65535.", "error");
      return;
    }
    try {
      const result = await api.saveSettings({ port });
      applySettings(result);
      main.querySelector("#server-address").textContent = `http://127.0.0.1:${port}/`;
      toast("Port saved. Restart Scriptorium to use it.");
    } catch (error) {
      toast(error.message, "error");
    }
  });

  const deleteOriginals = main.querySelector("#delete-originals");
  deleteOriginals.addEventListener("change", async () => {
    const value = deleteOriginals.checked;
    try {
      const result = await api.saveSettings({ delete_originals: value });
      applySettings(result);
      toast(value ? "Originals will be deleted after import" : "Originals will be kept after import");
    } catch (error) {
      deleteOriginals.checked = !value;
      toast(error.message, "error");
    }
  });

  const genreList = main.querySelector("#genre-list");
  const newGenre = main.querySelector("#new-genre");
  const genreError = main.querySelector("#genre-error");
  const paintGenres = () => {
    genreList.innerHTML = genres
      .map(
        (genre) => `
        <div class="genre-row">
          <span>${esc(genre)}</span>
          <button type="button" data-genre="${esc(genre)}" title="${genre.toLowerCase() === "other" ? "Other is the catch-all and cannot be removed" : "Remove genre"}" ${genre.toLowerCase() === "other" ? "disabled" : ""}>${icon("x", 15)}</button>
        </div>`
      )
      .join("");
    genreList.querySelectorAll("button[data-genre]").forEach((button) => {
      button.addEventListener("click", () => {
        genres = genres.filter((value) => value !== button.dataset.genre);
        paintGenres();
      });
    });
  };
  paintGenres();
  const addGenre = () => {
    const value = newGenre.value.trim();
    if (!value) return;
    if (!genres.some((genre) => genre.toLowerCase() === value.toLowerCase())) genres.push(value);
    newGenre.value = "";
    genreError.hidden = true;
    paintGenres();
  };
  main.querySelector("#add-genre").addEventListener("click", addGenre);
  newGenre.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addGenre();
    }
  });
  main.querySelector("#save-genres").addEventListener("click", async () => {
    genreError.hidden = true;
    try {
      const result = await api.saveGenres(genres);
      genres = [...result.genres];
      applyGenres(genres);
      paintGenres();
      toast("Genres saved");
    } catch (error) {
      genreError.textContent = error.message;
      genreError.hidden = false;
    }
  });

  const checkResults = main.querySelector("#check-results");
  main.querySelector("#run-check").addEventListener("click", async () => {
    const button = main.querySelector("#run-check");
    button.disabled = true;
    checkResults.innerHTML = `<div class="panel-note">Checking the library…</div>`;
    try {
      const report = await api.check();
      const counts = report.counts;
      checkResults.innerHTML = `
        <div class="counts-row">
          <span class="chip">Missing: ${counts.missing}</span>
          <span class="chip">Changed: ${counts.changed}</span>
          <span class="chip">Extra: ${counts.extra}</span>
        </div>
        ${
          report.problems.length
            ? `<div class="problem-list">${report.problems
                .map(
                  (problem) => `
                  <div class="problem-row">
                    <span>${esc(problem.message)}</span>
                    <code>${esc(problem.path)}</code>
                  </div>`
                )
                .join("")}</div>`
            : `<p class="panel-note">No problems found. Checked ${report.checked_books} books and ${report.checked_files} files.</p>`
        }
      `;
    } catch (error) {
      checkResults.innerHTML = `<div class="inline-error">${esc(error.message)}</div>`;
    } finally {
      button.disabled = false;
    }
  });

  const trashPanel = main.querySelector("#trash-panel");
  const paintTrash = () => {
    const entries = trash.entries || [];
    trashPanel.innerHTML = `
      <p class="panel-note">Trash uses ${esc(fmtSize(trash.size))}.</p>
      ${
        entries.length
          ? `<div class="trash-list">${entries
              .map(
                (entry) => `
                <div class="trash-row">
                  <span>
                    <span>${esc(entry.title)}</span>
                    <span class="row-sub">${entry.kind === "book" ? "Book" : "Edition"} · ${esc(fmtDate(entry.deleted_at))} · ${esc(fmtSize(entry.size))}</span>
                  </span>
                  <button class="btn btn-ghost btn-sm" type="button" data-restore="${esc(entry.id)}">${icon("restore", 14)}<span>Restore</span></button>
                </div>`
              )
              .join("")}</div>
             <div class="form-actions" style="margin-top:14px">
               <button class="btn btn-danger-ghost btn-sm" type="button" id="empty-trash">${icon("trash", 14)}<span>Empty trash</span></button>
             </div>`
          : `<p class="panel-note">Trash is empty.</p>`
      }
    `;
    trashPanel.querySelectorAll("[data-restore]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const result = await api.restore(button.dataset.restore);
          toast(`Restored “${result.book.title}”`);
          const refreshed = await api.trash();
          trash = refreshed;
          paintTrash();
        } catch (error) {
          toast(error.message, "error");
          button.disabled = false;
        }
      });
    });
    const emptyButton = trashPanel.querySelector("#empty-trash");
    if (emptyButton) {
      emptyButton.addEventListener("click", async () => {
        const confirmed = await confirmDialog({
          title: "Empty the trash?",
          message: `Everything in the trash (${fmtSize(trash.size)}) will be deleted for good. This cannot be undone.`,
          confirmLabel: "Empty trash",
          danger: true,
        });
        if (!confirmed) return;
        try {
          await api.emptyTrash();
          trash = { entries: [], size: 0 };
          paintTrash();
          toast("Trash emptied");
        } catch (error) {
          toast(error.message, "error");
        }
      });
    }
  };
  paintTrash();
  return () => {};
}
