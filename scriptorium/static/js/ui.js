// Shared UI primitives: toasts, modals, confirmation dialogs and empty states.
import { icon } from "./icons.js";
import { esc } from "./format.js";

const TOAST_ICONS = { success: "check", error: "alert", info: "alert" };

export function toast(message, type = "success", options = {}) {
  const root = document.getElementById("toasts");
  if (!root) return null;
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.innerHTML = `
    <span class="toast-icon">${icon(TOAST_ICONS[type] || "alert", 18)}</span>
    <div class="toast-text">${esc(message)}</div>
    <button class="toast-close" type="button" aria-label="Dismiss">${icon("x", 15)}</button>
  `;
  const remove = () => node.remove();
  node.querySelector(".toast-close").addEventListener("click", remove);
  root.append(node);
  if (type !== "error" || options.sticky === false) {
    window.setTimeout(remove, options.duration || 4200);
  }
  return node;
}

export function toastWarnings(warnings = []) {
  warnings.forEach((warning) => toast(warning, "error"));
}

export function openModal({ title = "", body = "", footer = [], size = "", onClose = null }) {
  const root = document.getElementById("modal-root");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  const modal = document.createElement("div");
  modal.className = `modal ${size}`.trim();
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  const head = document.createElement("div");
  head.className = "modal-head";
  head.innerHTML = `<h2>${esc(title)}</h2><button class="modal-close" type="button" aria-label="Close">${icon("x", 18)}</button>`;
  const bodyElement = document.createElement("div");
  bodyElement.className = "modal-body";
  if (typeof body === "string") bodyElement.innerHTML = body;
  else bodyElement.append(body);
  const foot = document.createElement("div");
  foot.className = "modal-foot";
  for (const element of footer) foot.append(element);
  modal.append(head, bodyElement, foot);
  backdrop.append(modal);
  root.append(backdrop);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey);
    backdrop.remove();
    if (onClose) onClose();
  };
  const onKey = (event) => {
    if (event.key === "Escape" && root.lastElementChild === backdrop) {
      event.stopPropagation();
      close();
    }
  };
  head.querySelector(".modal-close").addEventListener("click", close);
  backdrop.addEventListener("click", (event) => {
    if (event.target === backdrop) close();
  });
  document.addEventListener("keydown", onKey);
  window.setTimeout(() => {
    const focusable = modal.querySelector("input:not([type=radio]):not([type=checkbox]), textarea, select");
    if (focusable) focusable.focus();
  }, 30);
  return { modal, body: bodyElement, footer: foot, close };
}

export function confirmDialog({
  title = "Are you sure?",
  message = "",
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
}) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
      dialog.close();
    };
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "btn btn-ghost";
    cancel.textContent = cancelLabel;
    cancel.addEventListener("click", () => finish(false));
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = `btn ${danger ? "btn-danger" : "btn-primary"}`;
    confirm.textContent = confirmLabel;
    confirm.addEventListener("click", () => finish(true));
    const dialog = openModal({
      title,
      size: "narrow",
      body: `<p class="confirm-text">${esc(message)}</p>`,
      footer: [cancel, confirm],
      onClose: () => {
        if (!settled) {
          settled = true;
          resolve(false);
        }
      },
    });
    confirm.focus();
  });
}

export function emptyState({ iconName = "book", title, text = "", action = "" }) {
  return `
    <div class="empty-state">
      <span class="empty-icon">${icon(iconName, 24)}</span>
      <h3>${esc(title)}</h3>
      ${text ? `<p>${esc(text)}</p>` : ""}
      ${action}
    </div>
  `;
}

export function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("the file could not be read"));
    reader.readAsDataURL(file);
  });
}

export function button(label, { kind = "", type = "button", iconName = "", size = "" } = {}) {
  const element = document.createElement("button");
  element.type = type;
  element.className = `btn ${kind} ${size}`.trim();
  element.innerHTML = `${iconName ? icon(iconName, 16) : ""}<span>${esc(label)}</span>`;
  return element;
}
