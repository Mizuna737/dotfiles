// ==UserScript==
// @name         YouTube MPRIS Metadata Refresh
// @namespace    https://github.com/max/dotfiles
// @version      1.3
// @description  Forces Chromium to re-broadcast correct MPRIS metadata when YouTube switches videos
// @author       max
// @match        https://www.youtube.com/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==

(function () {
  "use strict";

  let lastTitle = document.title;
  let refreshTimeout = null;

  function forceMetadataRefresh() {
    const video = document.querySelector("video");
    if (!video) return;

    const wasPlaying = !video.paused;
    const originalTime = video.currentTime;

    // Step 1: pause
    video.pause();

    // Step 2: seek forward one second
    setTimeout(() => {
      video.currentTime = originalTime + 1;

      // Step 3: seek back
      setTimeout(() => {
        video.currentTime = originalTime;

        // Step 4: resume if it was playing
        setTimeout(() => {
          if (wasPlaying) video.play();
        }, 25);
      }, 25);
    }, 25);
  }

  const titleEl = document.querySelector("title");
  if (titleEl) {
    const titleObserver = new MutationObserver(() => {
      const newTitle = document.title;
      if (newTitle !== lastTitle && newTitle !== "YouTube") {
        lastTitle = newTitle;
        clearTimeout(refreshTimeout);
        refreshTimeout = setTimeout(forceMetadataRefresh, 300);
      }
    });
    titleObserver.observe(titleEl, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  }

  window.addEventListener("yt-navigate-finish", () => {
    clearTimeout(refreshTimeout);
    refreshTimeout = setTimeout(forceMetadataRefresh, 300);
  });
})();
