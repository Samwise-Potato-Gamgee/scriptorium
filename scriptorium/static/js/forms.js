// Forms and dialogs: book field editors, add/review, edit, bulk edit,
// replace file, cover upload, delete and remove-edition flows.
import { api } from "./api.js";
import { store } from "./store.js";
import { icon } from "./icons.js";
import { fmtSize, editionLabel, esc } from "./format.js";
import { withPathPicker } from "./pathfield.js";
import {
  button,
  confirmDialog,
  openModal,
  readFileDataUrl,
  toast,
  toastWarnings,
} from "./ui.js";

function textInput(value = "", attributes = {}) {
  const input = document.createElement("input");
  input.className = "input";
  input.value = value ?? "";
  for (const [key, val] of Object.entries(attributes)) {
    if (val === undefined || val === null || val === false) continue;
    input.setAttribute(key, val);
  }
  return input;
}

function selectInput(options, value) {
  const select = document.createElement("select");
  select.className = "input";
  for (const option of options) {
    const element = document.createElement("option");
    if (Array.isArray(option)) {
      element.value = option[0];
      element.textContent = option[1];
    } else {
      element.value = option;
      element.textContent = option;
    }
    if (element.value === value) element.selected = true;
    select.append(element);
  }
  return select;
}

function field(label, control, { help = "", span = false } = {}) {
  const wrapper = document.createElement("div");
  wrapper.className = `field ${span ? "field-span" : ""}`.trim();
  const text = document.createElement("span");
  text.textContent = label;
  wrapper.append(text, control);
  if (help) {
    const helpElement = document.createElement("span");
    helpElement.className = "field-help";
    helpElement.textContent = help;
    wrapper.append(helpElement);
  }
  return wrapper;
}

function lastFirstToFirstLast(value) {
  const parts = value.split(",");
  if (parts.length !== 2) return "";
  const last = parts[0].trim();
  const first = parts[1].trim();
  return last && first ? `${first} ${last}` : "";
}

function attachSuggestions(input, datalist, kind, getGenre) {
  let timer = null;
  const load = async () => {
    try {
      const genre = typeof getGenre === "function" ? getGenre() : "";
      const result = await api.suggestions(kind, input.value.trim(), genre || "");
      datalist.innerHTML = result.values
        .map((value) => `<option value="${esc(value)}"></option>`)
        .join("");
    } catch (error) {}
  };
  input.addEventListener("focus", load);
  input.addEventListener("input", () => {
    window.clearTimeout(timer);
    timer = window.setTimeout(load, 220);
  });
}

function checkbox(label) {
  const wrapper = document.createElement("label");
  wrapper.className = "check-row";
  const input = document.createElement("input");
  input.type = "checkbox";
  const text = document.createElement("span");
  text.textContent = label;
  wrapper.append(input, text);
  return { element: wrapper, input };
}

export function chipField(initial, { label, placeholder, kind, getGenre = null }) {
  const wrapper = document.createElement("div");
  wrapper.className = "field field-span";
  const labelElement = document.createElement("span");
  labelElement.textContent = label;
  const chips = document.createElement("div");
  chips.className = "chips";
  const row = document.createElement("div");
  row.className = "chip-add";
  const listId = `suggest-${Math.random().toString(36).slice(2)}`;
  const input = textInput("", { placeholder, list: listId, autocomplete: "off" });
  const datalist = document.createElement("datalist");
  datalist.id = listId;
  const add = document.createElement("button");
  add.type = "button";
  add.className = "btn btn-ghost btn-sm";
  add.innerHTML = `${icon("plus", 15)}<span>Add</span>`;
  row.append(input, add);
  wrapper.append(labelElement, chips, row, datalist);
  const values = [...initial];

  const paint = () => {
    chips.replaceChildren(
      ...values.map((value) => {
        const chip = document.createElement("span");
        chip.className = "chip";
        const text = document.createElement("span");
        text.textContent = value;
        const remove = document.createElement("button");
        remove.type = "button";
        remove.setAttribute("aria-label", `Remove ${value}`);
        remove.innerHTML = icon("x", 13);
        remove.addEventListener("click", () => {
          const index = values.indexOf(value);
          if (index >= 0) values.splice(index, 1);
          paint();
        });
        chip.append(text, remove);
        return chip;
      })
    );
  };

  const addValue = async () => {
    let value = input.value.replace(/\s+/g, " ").trim();
    if (!value) return;
    if (kind === "author") {
      const converted = lastFirstToFirstLast(value);
      if (converted) {
        const accepted = await confirmDialog({
          title: "Convert author name?",
          message: `Names are stored as First Last. Use “${converted}” instead of “${value}”?`,
          confirmLabel: `Use ${converted}`,
        });
        if (accepted) value = converted;
      }
    }
    if (!values.some((item) => item.toLowerCase() === value.toLowerCase())) {
      values.push(value);
    }
    input.value = "";
    paint();
    input.focus();
  };

  add.addEventListener("click", addValue);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      addValue();
    }
  });
  attachSuggestions(input, datalist, kind, getGenre);
  paint();

  return {
    element: wrapper,
    getValues: () => [...values],
    flush: async () => {
      if (input.value.trim()) await addValue();
    },
  };
}

export function bookFields(values = {}, { showReview = false, showCover = false } = {}) {
  const root = document.createElement("div");
  root.className = "form-grid";
  const title = textInput(values.title || "", { placeholder: "Book title" });
  const authors = chipField(values.authors || [], {
    label: "Authors",
    placeholder: "Type a name, then Add",
    kind: "author",
  });
  const genreValue = values.genre || "Other";
  const genreOptions = [...store.genres];
  if (!genreOptions.some((value) => value.toLowerCase() === genreValue.toLowerCase())) {
    genreOptions.push(genreValue);
  }
  const genre = selectInput(genreOptions, genreValue);
  const status = selectInput(
    [
      ["unread", "Unread"],
      ["read", "Read"],
      ["didnt_finish", "Didn't finish"],
    ],
    values.status || "unread"
  );
  const seriesId = `series-${Math.random().toString(36).slice(2)}`;
  const series = textInput(values.series || "", {
    placeholder: "Series name",
    list: seriesId,
    autocomplete: "off",
  });
  const seriesList = document.createElement("datalist");
  seriesList.id = seriesId;
  attachSuggestions(series, seriesList, "series");
  const seriesNumber = textInput(values.series_number || "", {
    placeholder: "e.g. 2",
    inputmode: "decimal",
  });
  const subgenres = chipField(values.subgenres || [], {
    label: "Subgenres",
    placeholder: "Add a subgenre",
    kind: "subgenre",
    getGenre: () => genre.value,
  });
  const description = document.createElement("textarea");
  description.className = "input";
  description.rows = 5;
  description.value = values.description || "";
  description.placeholder = "Description";
  const reviewCheck = showReview
    ? checkbox("Needs review")
    : null;
  if (reviewCheck) reviewCheck.input.checked = Boolean(values.needs_review);
  let coverInput = null;
  if (showCover) {
    coverInput = document.createElement("input");
    coverInput.type = "file";
    coverInput.className = "input";
    coverInput.accept = "image/*";
  }
  root.append(
    field("Title", title, { span: true }),
    authors.element,
    field("Series", series),
    field("Series number", seriesNumber),
    field("Main genre", genre),
    field("Status", status),
    subgenres.element,
    field("Description", description, { span: true }),
    seriesList
  );
  if (reviewCheck) {
    root.append(reviewCheck.element);
    reviewCheck.element.classList.add("field-span");
  }
  if (coverInput) {
    root.append(
      field("Cover image", coverInput, {
        span: true,
        help: "Optional. JPEG or PNG; replaces the current cover.",
      })
    );
  }
  return {
    element: root,
    flush: async () => {
      await authors.flush();
      await subgenres.flush();
    },
    getValues: () => ({
      title: title.value.trim(),
      authors: authors.getValues(),
      series: series.value.trim(),
      series_number: seriesNumber.value.trim(),
      genre: genre.value,
      status: status.value,
      subgenres: subgenres.getValues(),
      description: description.value,
      needs_review: reviewCheck ? reviewCheck.input.checked : undefined,
    }),
    getCoverFile: () => (coverInput && coverInput.files && coverInput.files[0]) || null,
  };
}

function errorElement(body) {
  const element = document.createElement("div");
  element.className = "inline-error";
  element.hidden = true;
  body.append(element);
  return element;
}

function showError(element, message) {
  element.textContent = message;
  element.hidden = false;
}

function setFooter(dialog, elements) {
  dialog.footer.replaceChildren(...elements);
}

export function openAddDialog({ onImported }) {
  const cancel = button("Cancel", { kind: "btn-ghost" });
  const dialog = openModal({
    title: "Add a book",
    size: "wide",
    body: "",
    footer: [cancel],
  });
  cancel.addEventListener("click", dialog.close);
  let inspected = null;

  const showPathStep = (path = "") => {
    dialog.body.innerHTML = `
      <div class="setup-form">
        <label class="field">
          <span>File or folder path</span>
          <input class="input" id="add-path" autocomplete="off" placeholder="/path/to/book.epub or /path/to/audio-folder" value="${esc(path)}">
          <span class="field-help">The file is read directly where it sits. EPUB, MP3, M4A, M4B, or a folder of audio files. Nothing is uploaded.</span>
        </label>
      </div>
      <div class="inline-error" id="add-error" hidden></div>
    `;
    const input = dialog.body.querySelector("#add-path");
    const error = dialog.body.querySelector("#add-error");
    withPathPicker(input, ["file", "folder"]);
    const inspect = button("Read file", { kind: "btn-primary", iconName: "search" });
    const back = button("Cancel", { kind: "btn-ghost" });
    back.addEventListener("click", dialog.close);
    setFooter(dialog, [back, inspect]);
    const run = async () => {
      const path = input.value.trim();
      if (!path) {
        showError(error, "Enter a file or folder path.");
        input.focus();
        return;
      }
      inspect.disabled = true;
      inspect.innerHTML = `<span>Reading…</span>`;
      error.hidden = true;
      try {
        inspected = await api.inspect(path);
        showReviewStep();
      } catch (requestError) {
        showError(error, requestError.message);
      } finally {
        inspect.disabled = false;
        inspect.innerHTML = `${icon("search", 16)}<span>Read file</span>`;
      }
    };
    inspect.addEventListener("click", run);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        run();
      }
    });
    window.setTimeout(() => input.focus(), 40);
  };

  const showReviewStep = () => {
    const data = inspected;
    const metadata = data.metadata;
    const formatName = data.format === "ebook" ? "ebook" : "audiobook";
    const sourceText =
      data.source_kind === "folder"
        ? `Audiobook · folder of ${data.file_count} files`
        : `${formatName === "ebook" ? "Ebook · EPUB" : "Audiobook · single file"}`;
    const cover = data.cover_preview
      ? `<img src="${esc(data.cover_preview)}" alt="">`
      : `<div class="cover-placeholder">No cover</div>`;
    dialog.body.innerHTML = `
      <div class="review-head">
        <div class="review-cover">${cover}</div>
        <div class="review-info">
          <h3>${esc(metadata.title || "No title found in the tags")}</h3>
          <p>${esc(sourceText)} · ${esc(fmtSize(data.total_size))}</p>
          <div class="badges">
            <span class="badge accent">${esc(formatName === "ebook" ? "Ebook" : "Audiobook")}</span>
            ${metadata.narrator ? `<span class="badge">Narrator: ${esc(metadata.narrator)}</span>` : ""}
          </div>
        </div>
      </div>
      <div id="duplicate-area"></div>
      <div id="book-fields"></div>
      <div id="edition-fields" class="form-grid"></div>
      <div class="field field-span" id="import-options"></div>
      <div class="inline-error" id="add-error" hidden></div>
    `;
    const error = dialog.body.querySelector("#add-error");
    const duplicateArea = dialog.body.querySelector("#duplicate-area");
    const bookArea = dialog.body.querySelector("#book-fields");
    const editionArea = dialog.body.querySelector("#edition-fields");
    const importOptions = dialog.body.querySelector("#import-options");
    const form = bookFields(
      {
        title: metadata.title || "",
        authors: metadata.authors || [],
        series: metadata.series || "",
        series_number: metadata.series_number || "",
        description: metadata.description || "",
        genre: "Other",
        status: "unread",
        subgenres: [],
      },
      { showReview: false, showCover: false }
    );
    bookArea.append(form.element);
    let narratorInput = null;
    if (data.format === "audiobook") {
      narratorInput = textInput(metadata.narrator || "", { placeholder: "Narrator" });
      editionArea.append(
        field("Narrator", narratorInput, {
          help: "Stored on the audiobook edition only.",
        })
      );
    }
    const deleteOriginal = checkbox("Delete the original after import");
    deleteOriginal.input.checked = Boolean(store.settings.delete_originals);
    importOptions.append(deleteOriginal.element);
    if (data.source_kind === "folder") {
      const note = document.createElement("span");
      note.className = "field-help";
      note.textContent =
        "The whole folder is kept or deleted; stray non-audio files are always left behind.";
      importOptions.append(note);
    }
    let attachTarget = null;
    if (data.duplicates.length) {
      const sameFormat = data.format === "ebook" ? "ebook" : "audiobook";
      const options = data.duplicates
        .map((duplicate) => {
          const already = data.format === "ebook" ? duplicate.has_ebook : duplicate.has_audiobook;
          return `
            <label class="radio-option ${already ? "disabled" : ""}">
              <input type="radio" name="duplicate-choice" value="${duplicate.id}" ${already ? "disabled" : ""}>
              <span>
                Attach as ${esc(formatName)} edition to “${esc(duplicate.title)}”
                <span class="field-help">${already ? `That book already has ${sameFormat === "ebook" ? "an ebook" : "an audiobook"} edition.` : "Book details stay unchanged."}</span>
              </span>
            </label>
          `;
        })
        .join("");
      duplicateArea.innerHTML = `
        <div class="notice warning">
          ${icon("alert", 18)}
          <div>
            A book with the same title and first author already exists.
            ${data.duplicates.some((item) => (data.format === "ebook" ? item.has_ebook : item.has_audiobook)) ? ` One of the matching books already has ${data.format === "ebook" ? "an ebook" : "an audiobook"} edition.` : ""}
          </div>
        </div>
        <div class="radio-list">
          <label class="radio-option">
            <input type="radio" name="duplicate-choice" value="new" checked>
            <span>Create a separate entry<span class="field-help">The folder gets a number suffix if needed.</span></span>
          </label>
          ${options}
        </div>
      `;
      duplicateArea.addEventListener("change", (event) => {
        const value = event.target.value;
        attachTarget = value === "new" ? null : Number(value);
        bookArea.hidden = Boolean(attachTarget);
        let note = bookArea.querySelector("[data-attach-note]");
        if (attachTarget) {
          if (!note) {
            note = document.createElement("div");
            note.className = "notice muted";
            note.dataset.attachNote = "1";
            note.innerHTML = `${icon("book", 18)}<div>The book's details stay as they are. Only the narrator is stored with this audiobook edition.</div>`;
            bookArea.prepend(note);
          }
          note.hidden = false;
        } else if (note) {
          note.hidden = true;
        }
      });
    }
    const back = button("Back", { kind: "btn-ghost", iconName: "back" });
    const save = button("Import", { kind: "btn-primary", iconName: "download" });
    setFooter(dialog, [back, save]);
    back.addEventListener("click", () => showPathStep(data.path));
    save.addEventListener("click", async () => {
      await form.flush();
      const values = form.getValues();
      if (!attachTarget && !values.title) {
        showError(error, "A title is required.");
        return;
      }
      save.disabled = true;
      save.innerHTML = `<span>Importing…</span>`;
      error.hidden = true;
      const payload = {
        path: data.path,
        format: data.format,
        mode: attachTarget ? "attach" : "new",
        target_book_id: attachTarget,
        book: values,
        edition: { narrator: narratorInput ? narratorInput.value.trim() : "" },
        keep_original: !deleteOriginal.input.checked,
      };
      try {
        const result = await api.importBook(payload);
        dialog.close();
        toast(`Imported “${result.book.title}”`);
        toastWarnings(result.warnings || []);
        if (onImported) onImported(result.book);
      } catch (requestError) {
        showError(error, requestError.message);
        save.disabled = false;
        save.innerHTML = `${icon("download", 16)}<span>Import</span>`;
      }
    });
    window.setTimeout(() => {
      const title = bookArea.querySelector("input");
      if (!metadata.title && title) title.focus();
    }, 40);
  };

  showPathStep();
  return dialog;
}

export function openEditDialog(book, { onSaved }) {
  const cancel = button("Cancel", { kind: "btn-ghost" });
  const dialog = openModal({ title: "Edit book", size: "wide", body: "", footer: [cancel] });
  cancel.addEventListener("click", dialog.close);
  const form = bookFields(book, { showReview: true, showCover: true });
  const error = errorElement(dialog.body);
  dialog.body.append(form.element);
  const save = button("Save changes", { kind: "btn-primary", iconName: "check" });
  setFooter(dialog, [cancel, save]);
  save.addEventListener("click", async () => {
    await form.flush();
    const values = form.getValues();
    if (!values.title) {
      showError(error, "A title is required.");
      return;
    }
    save.disabled = true;
    save.innerHTML = `<span>Saving…</span>`;
    error.hidden = true;
    try {
      const result = await api.updateBook(book.id, values);
      let updated = result.book;
      const file = form.getCoverFile();
      if (file) {
        const data = await readFileDataUrl(file);
        const uploaded = await api.uploadCover(book.id, data);
        updated = uploaded.book;
      }
      dialog.close();
      toast("Book updated");
      if (onSaved) onSaved(updated);
    } catch (requestError) {
      showError(error, requestError.message);
      save.disabled = false;
      save.innerHTML = `${icon("check", 16)}<span>Save changes</span>`;
    }
  });
}

export function openBulkDialog(books, { onSaved }) {
  const ids = books.map((book) => book.id);
  const cancel = button("Cancel", { kind: "btn-ghost" });
  const dialog = openModal({
    title: `Edit ${ids.length} book${ids.length === 1 ? "" : "s"}`,
    size: "",
    body: "",
    footer: [cancel],
  });
  cancel.addEventListener("click", dialog.close);
  const genre = selectInput([["", "— no change —"], ...store.genres.map((value) => [value, value])], "");
  const status = selectInput(
    [
      ["", "— no change —"],
      ["unread", "Unread"],
      ["read", "Read"],
      ["didnt_finish", "Didn't finish"],
    ],
    ""
  );
  const series = textInput("", { placeholder: "Series name" });
  const seriesClear = checkbox("Remove from series");
  const subgenres = textInput("", { placeholder: "Separate subgenres with commas" });
  const subgenresReplace = checkbox("Replace subgenres with this list");
  const grid = document.createElement("div");
  grid.className = "form-grid";
  grid.append(
    field("Main genre", genre),
    field("Status", status),
    field("Series", series),
    field("Subgenres", subgenres, { help: "Free-form; separated by commas." })
  );
  const checks = document.createElement("div");
  checks.className = "field field-span";
  checks.append(seriesClear.element, subgenresReplace.element);
  grid.append(checks);
  dialog.body.append(grid);
  const error = errorElement(dialog.body);
  const save = button("Apply", { kind: "btn-primary", iconName: "check" });
  setFooter(dialog, [cancel, save]);
  save.addEventListener("click", async () => {
    const fields = {};
    if (genre.value) fields.genre = genre.value;
    if (status.value) fields.status = status.value;
    if (seriesClear.input.checked) fields.series = "";
    else if (series.value.trim()) fields.series = series.value.trim();
    if (subgenresReplace.input.checked) {
      fields.subgenres = subgenres.value
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
    }
    if (!Object.keys(fields).length) {
      showError(error, "Choose at least one change.");
      return;
    }
    save.disabled = true;
    try {
      const result = await api.bulk(ids, fields);
      dialog.close();
      toast(`${result.updated} book${result.updated === 1 ? "" : "s"} updated`);
      if (onSaved) onSaved();
    } catch (requestError) {
      showError(error, requestError.message);
      save.disabled = false;
    }
  });
}

export function openReplaceDialog(book, edition, { onReplaced }) {
  const cancel = button("Cancel", { kind: "btn-ghost" });
  const dialog = openModal({
    title: `Replace ${editionLabel(edition.kind).toLowerCase()} file`,
    body: "",
    footer: [cancel],
  });
  cancel.addEventListener("click", dialog.close);
  const notice = document.createElement("div");
  notice.className = "notice warning";
  notice.innerHTML = `${icon("alert", 18)}<div>The current file will be moved to the trash. Choose the new file or folder path below.</div>`;
  const path = textInput("", { placeholder: "Path to the new file or folder", autocomplete: "off" });
  const error = errorElement(dialog.body);
  dialog.body.append(notice, field("New file path", path, { help: edition.kind === "audiobook" ? "A single audio file or a folder of audio files." : "An EPUB file." }));
  withPathPicker(path, edition.kind === "audiobook" ? ["file", "folder"] : ["file"]);
  const deleteOriginal = checkbox("Delete the original after import");
  deleteOriginal.input.checked = Boolean(store.settings.delete_originals);
  dialog.body.append(deleteOriginal.element);
  const replace = button("Replace file", { kind: "btn-danger", iconName: "refresh" });
  setFooter(dialog, [cancel, replace]);
  replace.addEventListener("click", async () => {
    if (!path.value.trim()) {
      showError(error, "Enter a file or folder path.");
      return;
    }
    replace.disabled = true;
    replace.innerHTML = `<span>Replacing…</span>`;
    try {
      const result = await api.replaceEdition(
        edition.id,
        path.value.trim(),
        { narrator: edition.narrator || "" },
        !deleteOriginal.input.checked
      );
      dialog.close();
      toast("File replaced");
      toastWarnings(result.warnings || []);
      if (onReplaced) onReplaced(result.book);
    } catch (requestError) {
      showError(error, requestError.message);
      replace.disabled = false;
      replace.innerHTML = `${icon("refresh", 16)}<span>Replace file</span>`;
    }
  });
}

export function openNarratorDialog(book, edition, { onSaved }) {
  const cancel = button("Cancel", { kind: "btn-ghost" });
  const dialog = openModal({
    title: "Audiobook narrator",
    body: "",
    footer: [cancel],
  });
  cancel.addEventListener("click", dialog.close);
  const input = textInput(edition.narrator || "", { placeholder: "Narrator" });
  dialog.body.append(
    field("Narrator", input, {
      help: "Stored on this audiobook edition only.",
    })
  );
  const error = errorElement(dialog.body);
  const save = button("Save narrator", { kind: "btn-primary", iconName: "check" });
  setFooter(dialog, [cancel, save]);
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const result = await api.updateEdition(edition.id, { narrator: input.value.trim() });
      dialog.close();
      toast("Narrator updated");
      if (onSaved) onSaved(result.book);
    } catch (requestError) {
      showError(error, requestError.message);
      save.disabled = false;
    }
  });
}

export function openEditionCoverDialog(book, edition, { onSaved }) {
  const cancel = button("Cancel", { kind: "btn-ghost" });
  const dialog = openModal({
    title: "Audiobook cover",
    body: "",
    footer: [cancel],
  });
  cancel.addEventListener("click", dialog.close);
  const current = edition.cover || book.cover;
  const preview = current
    ? `<div class="review-cover"><img src="/media/thumbnails/${encodeURIComponent(edition.thumbnail || current)}" alt=""></div>`
    : "";
  const input = document.createElement("input");
  input.type = "file";
  input.className = "input";
  input.accept = "image/*";
  dialog.body.innerHTML = `<div class="review-head">${preview}<div class="review-info"><h3>Optional cover</h3><p>Without its own cover the audiobook uses the book cover.</p></div></div>`;
  dialog.body.append(field("New cover image", input, { help: "JPEG or PNG." }));
  const error = errorElement(dialog.body);
  const save = button("Save cover", { kind: "btn-primary", iconName: "upload" });
  setFooter(dialog, [cancel, save]);
  save.addEventListener("click", async () => {
    const file = input.files && input.files[0];
    if (!file) {
      showError(error, "Choose an image first.");
      return;
    }
    save.disabled = true;
    try {
      const data = await readFileDataUrl(file);
      const result = await api.uploadCover(book.id, data, edition.id);
      dialog.close();
      toast("Cover updated");
      if (onSaved) onSaved(result.book);
    } catch (requestError) {
      showError(error, requestError.message);
      save.disabled = false;
    }
  });
}

export async function openDeleteBookDialog(book, { onDeleted }) {
  const confirmed = await confirmDialog({
    title: "Delete this book?",
    message: `“${book.title}” and its files will be moved to the trash. You can restore it from Settings.`,
    confirmLabel: "Delete book",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await api.deleteBook(book.id);
    toast("Book moved to trash");
    if (onDeleted) onDeleted();
  } catch (error) {
    toast(error.message, "error");
  }
}

export async function openRemoveEditionDialog(book, edition, { onRemoved, onBookDeleted }) {
  const last = (book.editions || []).length === 1;
  const confirmed = await confirmDialog({
    title: "Remove edition?",
    message: last
      ? `This is the last edition. Removing it will delete “${book.title}” and move its files to the trash.`
      : `Only this ${editionLabel(edition.kind).toLowerCase()} edition's files will move to the trash. The rest of the book stays.`,
    confirmLabel: last ? "Delete book" : "Remove edition",
    danger: true,
  });
  if (!confirmed) return;
  try {
    const result = await api.removeEdition(edition.id, last);
    if (result.deleted_book) {
      toast("Book moved to trash");
      if (onBookDeleted) onBookDeleted();
    } else {
      toast("Edition moved to trash");
      if (onRemoved) onRemoved(result.book);
    }
  } catch (error) {
    toast(error.message, "error");
  }
}
