// Application shell: boot, navigation, theme toggle, add dialog and routing.
import { api } from "./api.js";
import { applyGenres, applySettings, store } from "./store.js";
import { icon } from "./icons.js";
import { toast } from "./ui.js";
import { applyTheme, resolvedTheme, toggleTheme } from "./theme.js";
import { registerNavigation } from "./router.js";
import { renderBlocked } from "./views/setup.js";
import { homeView } from "./views/home.js";
import { libraryView } from "./views/library.js";
import { bookView } from "./views/book.js";
import { seriesView } from "./views/series.js";
import { settingsView } from "./views/settings.js";
import { openAddDialog } from "./forms.js";

const NAV_ITEMS = [
  ["/", "Home", "home"],
  ["/library", "Library", "library"],
  ["/series", "Series", "series"],
  ["/settings", "Settings", "settings"],
];

const nav = document.getElementById("nav");
const main = document.getElementById("main");
const addButton = document.getElementById("add-button");
const themeToggle = document.getElementById("theme-toggle");
let cleanup = null;
let renderToken = 0;

nav.innerHTML = NAV_ITEMS.map(
  ([href, label, iconName]) =>
    `<a href="${href}" data-link>${icon(iconName, 19)}<span>${label}</span></a>`
).join("");
addButton.innerHTML = `${icon("plus", 17)}<span>Add book</span>`;

function updateActive(pathname) {
  nav.querySelectorAll("a[data-link]").forEach((link) => {
    const href = link.getAttribute("href");
    const active =
      href === "/"
        ? pathname === "/"
        : pathname === href || (href === "/library" && pathname.startsWith("/book/"));
    link.classList.toggle("active", active);
  });
}

function updateThemeButton() {
  const dark = resolvedTheme() === "dark";
  themeToggle.innerHTML = `${icon(dark ? "sun" : "moon", 17)}<span>${dark ? "Light" : "Dark"}</span>`;
  themeToggle.title = dark ? "Switch to light theme" : "Switch to dark theme";
}

function setChrome(enabled) {
  nav.hidden = !enabled;
  addButton.hidden = !enabled;
  addButton.disabled = !enabled;
}

function loadingMarkup() {
  return `<div class="loading-screen"><span class="spinner"></span></div>`;
}

function fatalView(container, message) {
  container.innerHTML = `
    <div class="empty-state">
      <span class="empty-icon">${icon("alert", 24)}</span>
      <h3>Something went wrong</h3>
      <p>${message}</p>
      <button class="btn btn-primary" type="button" id="fatal-retry">${icon("refresh", 16)}<span>Try again</span></button>
    </div>
  `;
  const retry = container.querySelector("#fatal-retry");
  if (retry) retry.addEventListener("click", () => boot());
}

async function render() {
  if (!store.ready) return;
  const pathname = window.location.pathname;
  const search = new URLSearchParams(window.location.search);
  let view = null;
  let params = {};
  if (pathname === "/") {
    view = homeView;
  } else if (pathname === "/library") {
    view = libraryView;
  } else if (pathname === "/series") {
    view = seriesView;
  } else if (pathname === "/settings") {
    view = settingsView;
  } else {
    const match = pathname.match(/^\/book\/(\d+)$/);
    if (match) {
      view = bookView;
      params = { id: match[1] };
    }
  }
  if (!view) {
    history.replaceState(null, "", "/");
    window.scrollTo({ top: 0 });
    return render();
  }
  updateActive(pathname);
  const token = ++renderToken;
  if (cleanup) {
    try {
      cleanup();
    } catch (error) {}
    cleanup = null;
  }
  const container = document.createElement("div");
  container.className = "view";
  container.innerHTML = loadingMarkup();
  main.replaceChildren(container);
  try {
    const result = await view(container, params, search);
    if (token === renderToken) cleanup = typeof result === "function" ? result : null;
  } catch (error) {
    if (token !== renderToken) return;
    if (error.status === 409) {
      boot();
      return;
    }
    if (error.status === 404) {
      container.innerHTML = `
        <a class="back-link" href="/library" data-link>${icon("back", 16)}<span>Library</span></a>
        <div class="empty-state">
          <span class="empty-icon">${icon("alert", 24)}</span>
          <h3>Book not found</h3>
          <p>${error.message}</p>
        </div>
      `;
      return;
    }
    fatalView(container, error.message);
  }
}

function navigateTo(url, { replace = false } = {}) {
  const current = `${window.location.pathname}${window.location.search}`;
  if (url === current) {
    if (!replace) render();
    return;
  }
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  window.scrollTo({ top: 0 });
  render();
}

async function boot() {
  renderToken += 1;
  if (cleanup) {
    try {
      cleanup();
    } catch (error) {}
    cleanup = null;
  }
  try {
    const state = await api.state();
    store.state = state;
    store.accents = state.accents || [];
    store.version = state.version;
    store.settings = { ...state.settings };
    applyTheme(state.settings.theme, state.settings.accent);
    updateThemeButton();
    if (state.library.status === "ok") {
      const settings = await api.settings();
      applySettings(settings);
      applyGenres(settings.genres);
      store.version = settings.version;
      store.ready = true;
      setChrome(true);
      await render();
    } else {
      store.ready = false;
      setChrome(false);
      main.replaceChildren();
      renderBlocked(main, state);
    }
  } catch (error) {
    store.ready = false;
    setChrome(false);
    main.replaceChildren();
    const container = document.createElement("div");
    main.append(container);
    fatalView(container, error.message);
  }
}

themeToggle.addEventListener("click", async () => {
  const next = toggleTheme();
  store.settings.theme = next;
  updateThemeButton();
  try {
    const result = await api.saveSettings({ theme: next });
    applySettings(result);
  } catch (error) {
    toast(error.message, "error");
  }
});

window.addEventListener("scriptorium-theme", updateThemeButton);

addButton.addEventListener("click", () => {
  if (!store.ready) return;
  openAddDialog({ onImported: (book) => navigateTo(`/book/${book.id}`) });
});

document.addEventListener("click", (event) => {
  const link = event.target.closest("a[data-link]");
  if (!link) return;
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
    return;
  }
  const href = link.getAttribute("href");
  if (!href || /^(https?:|mailto:)/.test(href)) return;
  event.preventDefault();
  navigateTo(href);
});

window.addEventListener("popstate", () => {
  if (store.ready) render();
});

registerNavigation(navigateTo, boot);
boot();
