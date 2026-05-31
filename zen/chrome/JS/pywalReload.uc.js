// ==UserScript==
// @name           pywalReload
// @description    Watches pywal-generated CSS and live-reloads via nsIStyleSheetService.
// @include        main
// ==/UserScript==

(function () {
  const POLL_MS = 1000;
  const SHEET_PATH_PARTS = ["chrome", "pywal.css"];

  const sss = Cc["@mozilla.org/content/style-sheet-service;1"]
    .getService(Ci.nsIStyleSheetService);

  const profileDir = Services.dirsvc.get("ProfD", Ci.nsIFile);
  const cssFile = profileDir.clone();
  for (const part of SHEET_PATH_PARTS) cssFile.append(part);

  let lastMtime = 0;
  let currentUri = null;

  const reload = async () => {
    const text = await IOUtils.readUTF8(cssFile.path);
    const dataUri = Services.io.newURI(
      "data:text/css;charset=utf-8;base64," +
        btoa(unescape(encodeURIComponent(text)))
    );
    if (currentUri && sss.sheetRegistered(currentUri, sss.AUTHOR_SHEET)) {
      sss.unregisterSheet(currentUri, sss.AUTHOR_SHEET);
    }
    sss.loadAndRegisterSheet(dataUri, sss.AUTHOR_SHEET);
    currentUri = dataUri;
  };

  setInterval(() => {
    if (!cssFile.exists()) return;
    const mtime = cssFile.lastModifiedTime;
    if (mtime === lastMtime) return;
    lastMtime = mtime;
    reload().catch((e) => console.error("[pywalReload] reload failed:", e));
  }, POLL_MS);
})();
