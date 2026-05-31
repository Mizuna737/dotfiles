// ==UserScript==
// @name           zenPywalGlobalBoost
// @description    Applies pywal colors as a global Zen boost to all pages without a domain-specific boost. Live-reloads on pywal update.
// @include        main
// ==/UserScript==

(function () {
  const POLL_MS = 1000;
  const HOME = Services.dirsvc.get("Home", Ci.nsIFile).path;
  const WAL_COLORS_PATH  = HOME + "/.cache/wal/colors.json";
  const WAL_CONFIG_PATH  = HOME + "/dotfiles/zen/pywalBoost.json";

  // Defaults — overridden by pywalBoost.json if present.
  // contrast  0→1: lower = stronger tint blend
  // saturation 0→1: lower = more vivid accent color
  const DEFAULTS = { contrast: 0.75, saturation: null };

  const { gZenBoostsManager } = ChromeUtils.importESModule(
    "resource:///modules/zen/boosts/ZenBoostsManager.sys.mjs"
  );

  // ── color math ──────────────────────────────────────────────────────────────

  function hueToRgb(p, q, t) {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  }

  function hslToRgb(h, s, l) {
    let r, g, b;
    if (s === 0) {
      r = g = b = l;
    } else {
      const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
      const p = 2 * l - q;
      r = hueToRgb(p, q, h + 1 / 3);
      g = hueToRgb(p, q, h);
      b = hueToRgb(p, q, h - 1 / 3);
    }
    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)];
  }

  function rgbToHsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    const l = (mx + mn) / 2;
    if (mx === mn) return [0, 0, l];
    const d = mx - mn;
    const s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    let h;
    if (mx === r)      h = ((g - b) / d) % 6;
    else if (mx === g) h = (b - r) / d + 2;
    else               h = (r - g) / d + 4;
    return [h * 60, s, l];
  }

  function hexToRgb(hex) {
    return [
      parseInt(hex.slice(1, 3), 16),
      parseInt(hex.slice(3, 5), 16),
      parseInt(hex.slice(5, 7), 16),
    ];
  }

  // Pack RGB + contrast into the nscolor uint32 Zen's C++ backend expects.
  // Alpha byte encodes contrast (not opacity) — see nsZenBoostsBackend.cpp.
  function buildNsColor(hueDeg, boostSat, boostBright, boostContrast) {
    const [r, g, b] = hslToRgb(
      hueDeg / 360,
      1 - boostSat,                    // slider is inverted
      0.1 + 0.9 * boostBright          // mapped from [0.1, 1.0]
    );
    const contrastByte = Math.round((1 - boostContrast) * 255);
    return ((contrastByte << 24) | (b << 16) | (g << 8) | r) >>> 0;
  }

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  function computeColorsFromWal(walJson) {
    const colors = walJson.colors;
    const [r6, g6, b6] = hexToRgb(colors.color6);
    const [r3, g3, b3] = hexToRgb(colors.color3);
    const [hue6, sat6, light6] = rgbToHsl(r6, g6, b6);
    const [hue3] = rgbToHsl(r3, g3, b3);

    // cfg.saturation overrides pywal-derived value when set; lower = more vivid
    const boostSat    = cfg.saturation !== null ? cfg.saturation : 1 - sat6;
    const boostBright = clamp((light6 - 0.1) / 0.9, 0, 1);
    const delta       = (hue3 - hue6 + 360) % 360;
    const nsColor     = buildNsColor(hue6, boostSat, boostBright, cfg.contrast);
    return { nsColor, delta };
  }

  async function loadConfig() {
    try {
      const raw = await IOUtils.readUTF8(WAL_CONFIG_PATH);
      const parsed = JSON.parse(raw);
      cfg = {
        contrast:   typeof parsed.contrast   === "number" ? parsed.contrast   : DEFAULTS.contrast,
        saturation: typeof parsed.saturation === "number" ? parsed.saturation : DEFAULTS.saturation,
      };
    } catch (_) {
      cfg = { ...DEFAULTS };
    }
  }

  // ── state ────────────────────────────────────────────────────────────────────

  let pywalNsColor  = 0;
  let pywalDelta    = 55;
  let lastMtime     = 0;
  let lastCfgMtime  = 0;
  let cfg           = { ...DEFAULTS };

  // ── apply ────────────────────────────────────────────────────────────────────

  function applyToTab(browser) {
    try {
      const uri = browser.currentURI;
      if (!uri || (!uri.schemeIs("http") && !uri.schemeIs("https"))) return;
      const domain = uri.host;
      if (!domain) return;
      if (gZenBoostsManager.registeredBoostForDomain(domain)) return; // user boost wins
      const bc = browser.browsingContext;
      if (!bc) return;
      bc.zenBoostsData = pywalNsColor;
      bc.zenBoostsComplementaryRotation = pywalDelta;
      bc.isZenBoostsInverted = false;
    } catch (e) {
      // browsing context may be dead (tab closing, etc.)
    }
  }

  function applyToAllTabs() {
    for (const tab of gBrowser.tabs) {
      applyToTab(tab.linkedBrowser);
    }
  }

  // ── load pywal colors ────────────────────────────────────────────────────────

  async function loadWalColors() {
    try {
      const raw = await IOUtils.readUTF8(WAL_COLORS_PATH);
      const { nsColor, delta } = computeColorsFromWal(JSON.parse(raw));
      pywalNsColor = nsColor;
      pywalDelta   = delta;
    } catch (e) {
      console.warn("[zenPywalGlobalBoost] could not load colors.json:", e.message);
      // Keep last known values; don't zero out on transient read error
    }
  }

  // ── poll for pywal changes ───────────────────────────────────────────────────

  setInterval(async () => {
    try {
      let changed = false;

      const { lastModified: colorsMtime } = await IOUtils.stat(WAL_COLORS_PATH);
      if (colorsMtime !== lastMtime) { lastMtime = colorsMtime; changed = true; }

      try {
        const { lastModified: cfgMtime } = await IOUtils.stat(WAL_CONFIG_PATH);
        if (cfgMtime !== lastCfgMtime) { lastCfgMtime = cfgMtime; changed = true; }
      } catch (_) {}

      if (!changed) return;
      await loadConfig();
      await loadWalColors();
      applyToAllTabs();
    } catch (_) {}
  }, POLL_MS);

  // ── hooks ────────────────────────────────────────────────────────────────────

  gBrowser.addTabsProgressListener({
    onLocationChange(browser, progress, _request, _location, _flags) {
      if (!progress.isTopLevel) return;
      applyToTab(browser);
    },
  });

  Services.obs.addObserver(() => {
    applyToAllTabs();
  }, "zen-boosts-update");

  // ── global font override ─────────────────────────────────────────────────────
  // Excludes icon font classes so Google/Material icons don't render as text.

  (() => {
    const css = `body *:not(.google-symbols, gf-load-icon-font, mat-icon, .google-material-icons, .material-icons, [class*="icon"]) { font-family: "Fira Code", monospace !important; }`;
    const uri = Services.io.newURI(`data:text/css;charset=utf-8,${encodeURIComponent(css)}`);
    const sss = Cc["@mozilla.org/content/style-sheet-service;1"].getService(Ci.nsIStyleSheetService);
    sss.loadAndRegisterSheet(uri, sss.AGENT_SHEET);
  })();

  // ── init ─────────────────────────────────────────────────────────────────────

  loadConfig().then(() => loadWalColors()).then(() => applyToAllTabs());
})();
