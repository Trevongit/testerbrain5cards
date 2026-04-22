// ==UserScript==
// @name         G-Codex Bridge Injector
// @namespace    https://g-codex.local
// @version      1.0.0
// @description  Copy LLM replies as G-Codex injection blocks for local watcher ingestion.
// @match        https://grok.com/*
// @match        https://gemini.google.com/*
// @match        https://chatgpt.com/*
// @match        https://claude.ai/*
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
  "use strict";

  const BRIDGE_CLASS = "g-codex-bridge-btn";
  const SOURCE_BY_HOST = {
    "grok.com": "Grok",
    "gemini.google.com": "Gemini 3",
    "chatgpt.com": "ChatGPT",
    "claude.ai": "Claude",
  };

  function detectSource() {
    return SOURCE_BY_HOST[window.location.hostname] || "Human";
  }

  function addStyles() {
    const style = document.createElement("style");
    style.textContent = `
      .${BRIDGE_CLASS} {
        margin-left: 8px !important;
        padding: 4px 8px !important;
        border-radius: 6px !important;
        border: 1px solid #ffdd57 !important;
        background: #141821 !important;
        color: #ffdd57 !important;
        font-size: 12px !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
        cursor: pointer !important;
        opacity: 0.92 !important;
      }
      .${BRIDGE_CLASS}:hover {
        background: #1d2230 !important;
        opacity: 1 !important;
      }
    `;
    document.head.appendChild(style);
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    if (typeof GM_setClipboard === "function") {
      GM_setClipboard(text, "text");
      return Promise.resolve();
    }
    return Promise.reject(new Error("Clipboard API unavailable"));
  }

  function findMessageContainer(anchor) {
    return (
      anchor.closest("article") ||
      anchor.closest("[data-message-id]") ||
      anchor.closest("[data-testid*='message']") ||
      anchor.closest("[class*='message']") ||
      anchor.closest("[class*='response']") ||
      anchor.parentElement
    );
  }

  function extractMessageText(container) {
    if (!container) return "";

    const candidates = [
      "[data-message-author-role='assistant']",
      "[data-message-id]",
      ".markdown",
      ".prose",
      "[class*='markdown']",
      "[class*='prose']",
      "[class*='message-content']",
    ];

    for (const selector of candidates) {
      const node = container.querySelector(selector);
      if (node && node.innerText && node.innerText.trim()) {
        return node.innerText.trim();
      }
    }

    return (container.innerText || "").trim();
  }

  function buildInjectionBlock(source, messageText) {
    const timestamp = new Date().toISOString();
    return [
      "### 🧠 G-CODEX INJECTION:",
      `Source: ${source}`,
      `Timestamp: ${timestamp}`,
      "Content:",
      messageText,
    ].join("\n");
  }

  function wireBridgeButton(copyButton) {
    if (!copyButton || copyButton.dataset.gCodexBridgeBound === "1") return;
    copyButton.dataset.gCodexBridgeBound = "1";

    const existing = copyButton.parentElement?.querySelector(`.${BRIDGE_CLASS}`);
    if (existing) return;

    const bridgeButton = document.createElement("button");
    bridgeButton.type = "button";
    bridgeButton.className = BRIDGE_CLASS;
    bridgeButton.textContent = "⚡ G-Codex";

    bridgeButton.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      const source = detectSource();
      const container = findMessageContainer(copyButton);
      const messageText = extractMessageText(container);
      if (!messageText) return;

      const payload = buildInjectionBlock(source, messageText);
      try {
        await copyText(payload);
        const original = bridgeButton.textContent;
        bridgeButton.textContent = "✅ Injected";
        window.setTimeout(() => {
          bridgeButton.textContent = original;
        }, 1200);
      } catch (err) {
        bridgeButton.textContent = "❌ Copy Failed";
        window.setTimeout(() => {
          bridgeButton.textContent = "⚡ G-Codex";
        }, 1500);
      }
    });

    copyButton.insertAdjacentElement("afterend", bridgeButton);
  }

  function looksLikeCopyButton(button) {
    const label = `${button.innerText || ""} ${button.getAttribute("aria-label") || ""}`.toLowerCase();
    return label.includes("copy");
  }

  function scanAndInject(root = document) {
    const buttons = root.querySelectorAll("button, [role='button']");
    buttons.forEach((button) => {
      if (looksLikeCopyButton(button)) {
        wireBridgeButton(button);
      }
    });
  }

  function startObserver() {
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (!(node instanceof HTMLElement)) continue;
          scanAndInject(node);
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  addStyles();
  scanAndInject(document);
  startObserver();
})();
