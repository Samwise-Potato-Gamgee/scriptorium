// In-memory application state shared by the shell and views.
export const store = {
  state: null,
  settings: { theme: "system", accent: "#e0a13a", port: 8737, delete_originals: false },
  genres: [],
  accents: [],
  version: "",
  ready: false,
};

export function applySettings(payload = {}) {
  store.settings = { ...store.settings, ...(payload.settings || payload) };
}

export function applyGenres(genres) {
  store.genres = genres || [];
}
