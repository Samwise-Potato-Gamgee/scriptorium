// First-start and missing-library screens, plus the shared open-or-create flow.
import { api } from "../api.js";
import { icon } from "../icons.js";
import { esc } from "../format.js";
import { confirmDialog, toast } from "../ui.js";
import { withPathPicker } from "../pathfield.js";
import { reloadApp } from "../router.js";

export async function openLibraryAt(path) {
  try {
    await api.openLibrary(path, false);
    return true;
  } catch (error) {
    if (
      error.message === "no library found at this path" ||
      error.message === "the folder does not exist"
    ) {
      const create = await confirmDialog({
        title: "Create a new library?",
        message: `There is no library at “${path}”. Create a new empty library in that folder? Nothing else in the folder is touched.`,
        confirmLabel: "Create library",
      });
      if (!create) return false;
      await api.openLibrary(path, true);
      return true;
    }
    throw error;
  }
}

function pathForm(defaultPath, buttonLabel) {
  const wrapper = document.createElement("form");
  wrapper.className = "setup-form";
  const id = `library-path-${Math.random().toString(36).slice(2)}`;
  wrapper.innerHTML = `
    <label class="field" for="${id}">
      <span>Library folder</span>
      <input class="input" id="${id}" autocomplete="off" spellcheck="false" placeholder="Choose a folder for your library" value="${esc(defaultPath)}">
      <span class="field-help">This folder holds library.db, covers, backups and your books. It can live on another drive.</span>
    </label>
    <div class="setup-actions">
      <button class="btn btn-primary" type="submit">${icon("folder", 16)}<span>${esc(buttonLabel)}</span></button>
    </div>
    <div class="inline-error" hidden></div>
  `;
  withPathPicker(wrapper.querySelector("input.input"), ["folder"]);
  return wrapper;
}

function wireForm(form, onDone) {
  const input = form.querySelector("input.input");
  const button = form.querySelector("button[type=submit]");
  const error = form.querySelector(".inline-error");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const path = input.value.trim();
    if (!path) {
      error.textContent = "Enter a folder path.";
      error.hidden = false;
      return;
    }
    button.disabled = true;
    error.hidden = true;
    try {
      const opened = await openLibraryAt(path);
      if (opened) {
        toast("Library opened");
        if (onDone) onDone();
        else reloadApp();
      }
    } catch (requestError) {
      error.textContent = requestError.message;
      error.hidden = false;
    } finally {
      button.disabled = false;
    }
  });
  return input;
}

export function renderBlocked(main, state) {
  const missing = state.library.status === "missing";
  const defaultPath = `${state.default_library_parent}/Scriptorium Library`;
  const path = state.library.path || defaultPath;
  const card = document.createElement("div");
  card.className = "setup-wrap";
  card.innerHTML = `
    <div class="setup-card">
      <div class="setup-mark">${icon(missing ? "alert" : "bookOpen", 25)}</div>
      <h1>${missing ? "Library folder not found" : "Welcome to Scriptorium"}</h1>
      <p>${
        missing
          ? `The library at <span class="mono">${esc(state.library.path)}</span> could not be found. If it is on an external drive, connect it and try again. A new library is never created automatically.`
          : "A local, offline home for your ebooks and audiobooks. Choose the folder where your library should live — it is opened if it already exists, or you can create a new empty one."
      }</p>
      <div id="setup-body"></div>
      <p class="panel-note">Your per-machine settings live outside the library, so you can move or remove the library folder independently.</p>
    </div>
  `;
  main.replaceChildren(card);
  const body = card.querySelector("#setup-body");
  if (missing) {
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "btn btn-primary";
    retry.innerHTML = `${icon("refresh", 16)}<span>Retry</span>`;
    retry.addEventListener("click", async () => {
      retry.disabled = true;
      try {
        await api.retryLibrary();
        reloadApp();
      } catch (error) {
        const errorBox = body.querySelector(".retry-error") || document.createElement("div");
        errorBox.className = "inline-error retry-error";
        errorBox.textContent = error.message;
        body.append(errorBox);
      } finally {
        retry.disabled = false;
      }
    });
    const heading = document.createElement("p");
    heading.className = "panel-sub";
    heading.textContent = "Pick another folder:";
    body.append(retry, heading);
  }
  const form = pathForm(path, missing ? "Open or create here" : "Open library");
  wireForm(form);
  body.append(form);
}
