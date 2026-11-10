// Navigation hooks so views can change the address without importing the shell.
let navigateHandler = null;
let reloadHandler = null;

export function registerNavigation(handler, reload) {
  navigateHandler = handler;
  reloadHandler = reload;
}

export function navigate(url, options = {}) {
  if (navigateHandler) {
    navigateHandler(url, options);
  } else {
    window.location.assign(url);
  }
}

export function reloadApp() {
  if (reloadHandler) reloadHandler();
  else window.location.reload();
}
