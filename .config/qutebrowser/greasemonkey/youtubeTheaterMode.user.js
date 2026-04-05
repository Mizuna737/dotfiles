// ==UserScript==
// @name         YouTube Full Width Theater
// @namespace    https://github.com/max/dotfiles
// @version      1.9
// @description  Makes YouTube theater mode use full screen width and height, enabled by default
// @match        https://www.youtube.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
  const style = document.createElement("style");
  style.textContent = `
        /* Hide scrollbar */
        ::-webkit-scrollbar { display: none !important; }
        * { scrollbar-width: none !important; }

        /* Elevate player above masthead (masthead is z-index 2020) */
        ytd-watch-flexy[theater] #player-container {
            z-index: 2021 !important;
            position: relative !important;
            max-width: 100vw !important;
            width: 100% !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
        }

        ytd-watch-flexy[theater] #full-bleed-container {
            z-index: 2021 !important;
            position: relative !important;
            max-width: 100vw !important;
            overflow: hidden !important;
        }

        /* Remove top offset YouTube adds for the header */
        ytd-app {
            --ytd-toolbar-height: 0px !important;
        }

        /* Remove top margin from page content */
        ytd-watch-flexy[theater] #page-manager.ytd-app {
            margin-top: 0 !important;
            padding-top: 0 !important;
        }

        /* Full viewport height on the player chain */
        ytd-watch-flexy[theater],
        ytd-watch-flexy[theater] #full-bleed-container,
        ytd-watch-flexy[theater] #player-container,
        ytd-watch-flexy[theater] #ytd-player,
        ytd-watch-flexy[theater] #movie_player,
        ytd-watch-flexy[theater] .html5-video-container,
        ytd-watch-flexy[theater] video {
            height: 100vh !important;
            max-height: 100vh !important;
        }

        /* Constrain player width to viewport — clip on the player container only, not the page */
        ytd-watch-flexy[theater] #full-bleed-container,
        ytd-watch-flexy[theater] #player-container,
        ytd-watch-flexy[theater] #ytd-player,
        ytd-watch-flexy[theater] #movie_player,
        ytd-watch-flexy[theater] .html5-video-container {
            width: 100vw !important;
            max-width: 100vw !important;
        }

        ytd-watch-flexy[theater] video {
            width: 100vw !important;
            max-width: 100vw !important;
            object-fit: contain !important;
        }

        /* Clip overflow only on the player container, not the full page */
        ytd-watch-flexy[theater] #full-bleed-container {
            overflow: hidden !important;
        }
    `;
  document.head.appendChild(style);

  // Enable theater mode by default on video pages
  function enableTheater() {
    const flexy = document.querySelector("ytd-watch-flexy");
    if (!flexy) return;
    if (flexy.hasAttribute("theater")) return; // already in theater mode

    // Click the theater mode button
    const btn = document.querySelector(".ytp-size-button");
    if (btn) {
      btn.click();
    }
  }

  // Run on page load and SPA navigation
  window.addEventListener("yt-navigate-finish", () =>
    setTimeout(enableTheater, 800),
  );
  setTimeout(enableTheater, 1500);
})();
