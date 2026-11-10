// Formatting helpers: HTML escaping, covers, dates, durations and sizes.
export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
  });
}

export function coverName(book, size = "thumb") {
  let name = size === "thumb" ? book.thumbnail || book.cover : book.cover;
  if (!name) {
    name = size === "thumb" ? book.audiobook_thumbnail || book.audiobook_cover : book.audiobook_cover;
  }
  return name || "";
}

export function coverUrl(book, size = "thumb") {
  const name = coverName(book, size);
  if (!name) return "";
  const folder = size === "thumb" ? "thumbnails" : "covers";
  return `/media/${folder}/${encodeURIComponent(name)}`;
}

export function editionCoverUrl(book, edition, size = "thumb") {
  const name = size === "thumb" ? edition.thumbnail || edition.cover : edition.cover;
  if (!name) return coverUrl(book, size);
  const folder = size === "thumb" ? "thumbnails" : "covers";
  return `/media/${folder}/${encodeURIComponent(name)}`;
}

export function authorsLine(book) {
  const authors = book.authors || [];
  return authors.length ? authors.join(" · ") : "Unknown author";
}

export function statusLabel(status) {
  return { unread: "Unread", read: "Read", didnt_finish: "Didn't finish" }[status] || "Unread";
}

export function statusClass(status) {
  return { unread: "accent", read: "success", didnt_finish: "" }[status] || "";
}

export function editionLabel(kind) {
  return kind === "ebook" ? "Ebook" : "Audiobook";
}

export function fmtDate(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function fmtDuration(seconds) {
  const total = Math.round(Number(seconds) || 0);
  if (total <= 0) return "";
  const hours = Math.floor(total / 3600);
  const minutes = Math.round((total % 3600) / 60);
  if (hours && minutes) return `${hours} h ${minutes} min`;
  if (hours) return `${hours} h`;
  return `${Math.max(minutes, 1)} min`;
}

export function fmtSize(bytes) {
  const value = Number(bytes) || 0;
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function totalDuration(book) {
  return (book.editions || []).reduce((sum, edition) => sum + (Number(edition.duration) || 0), 0);
}

export function fileCount(book) {
  return (book.editions || []).reduce((sum, edition) => sum + (edition.files || []).length, 0);
}

export function encodeQuery(value) {
  return encodeURIComponent(String(value ?? ""));
}

export function seriesLabel(book) {
  if (!book.series) return "";
  return book.series_number ? `${book.series} #${book.series_number}` : book.series;
}
