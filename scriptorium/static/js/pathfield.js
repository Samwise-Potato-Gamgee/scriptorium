// Native path pickers: ask the local server to open the operating system's
// file or folder dialog and put the chosen path into a path field.
import { api } from "./api.js";
import { button, toast } from "./ui.js";

const LABELS = { file: "Choose file…", folder: "Choose folder…" };
const ICONS = { file: "file", folder: "folder" };

export async function pickPath(kind, start = "") {
  try {
    const result = await api.dialog(kind, start);
    return result.path || "";
  } catch (error) {
    toast(error.message, "error");
    return "";
  }
}

function pickerButton(kind, input) {
  const element = button(LABELS[kind], {
    kind: "btn-ghost",
    size: "btn-sm",
    iconName: ICONS[kind],
  });
  element.addEventListener("click", async () => {
    element.disabled = true;
    try {
      const chosen = await pickPath(kind, input.value.trim());
      if (chosen) {
        input.value = chosen;
        input.dispatchEvent(new Event("input", { bubbles: true }));
      }
    } finally {
      element.disabled = false;
    }
  });
  return element;
}

export function pathPicker(input, kinds = ["file", "folder"]) {
  const actions = document.createElement("span");
  actions.className = "path-actions";
  for (const kind of kinds) actions.append(pickerButton(kind, input));
  return actions;
}

export function withPathPicker(input, kinds = ["file", "folder"]) {
  const row = document.createElement("div");
  row.className = "path-row";
  input.replaceWith(row);
  row.append(input, pathPicker(input, kinds));
  return row;
}
