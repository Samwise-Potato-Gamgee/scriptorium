// Thin fetch wrapper around the Scriptorium JSON API.
const JSON_HEADERS = { "Content-Type": "application/json" };

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (error) {
      data = null;
    }
  }
  if (!response.ok) {
    const raw = data && (data.error || data.detail);
    const message = typeof raw === "string" ? raw : `Request failed (${response.status})`;
    throw new ApiError(message, response.status);
  }
  return data;
}

function send(method, path, body) {
  return request(path, { method, headers: JSON_HEADERS, body: JSON.stringify(body ?? {}) });
}

export const api = {
  state: () => request("/api/state"),
  openLibrary: (path, create = false) => send("POST", "/api/library/open", { path, create }),
  retryLibrary: () => send("POST", "/api/library/retry", {}),
  home: () => request("/api/home"),
  books: (params) => request(`/api/books?${new URLSearchParams(params)}`),
  book: (id) => request(`/api/books/${id}`),
  updateBook: (id, payload) => send("PATCH", `/api/books/${id}`, payload),
  deleteBook: (id) => request(`/api/books/${id}`, { method: "DELETE" }),
  uploadCover: (id, data, editionId = null) => send("POST", `/api/books/${id}/cover`, { data, edition_id: editionId }),
  bulk: (ids, fields) => send("POST", "/api/books/bulk", { ids, fields }),
  inspect: (path) => send("POST", "/api/inspect", { path }),
  dialog: (kind, start = "") => send("POST", "/api/dialog", { kind, start }),
  importBook: (payload) => send("POST", "/api/import", payload),
  updateEdition: (id, payload) => send("PATCH", `/api/editions/${id}`, payload),
  replaceEdition: (id, path, edition = {}, keepOriginal = true) => send("POST", `/api/editions/${id}/replace`, { path, edition, keep_original: keepOriginal }),
  removeEdition: (id, deleteBook = false) => request(`/api/editions/${id}?delete_book=${deleteBook ? "true" : "false"}`, { method: "DELETE" }),
  series: () => request("/api/series"),
  seriesDetail: (name) => request(`/api/series/detail?${new URLSearchParams({ name })}`),
  suggestions: (kind, q = "", genre = "") => request(`/api/suggestions/${kind}?${new URLSearchParams({ q, genre })}`),
  settings: () => request("/api/settings"),
  saveSettings: (payload) => send("PUT", "/api/settings", payload),
  saveGenres: (genres) => send("PUT", "/api/genres", { genres }),
  trash: () => request("/api/trash"),
  restore: (id) => send("POST", `/api/trash/${encodeURIComponent(id)}/restore`, {}),
  emptyTrash: () => send("POST", "/api/trash/empty", {}),
  check: () => send("POST", "/api/check", {}),
};
