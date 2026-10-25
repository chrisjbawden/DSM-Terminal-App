const sudoStatusBadge = document.getElementById("sudoStatusBadge");
const helpStatus = document.getElementById("helpStatus");
const copyButtons = Array.from(document.querySelectorAll(".copy-button"));
const helpShell = document.querySelector(".help-shell");
const fontFamilySelect = document.getElementById("fontFamilySelect");
const STATUS_REFRESH_MS = 3000;
const FONT_STORAGE_KEY = "dsm-terminal-font-family";
const FONT_OPTIONS = [
  { label: "System Default", family: "Menlo, Monaco, Consolas, monospace", alwaysAvailable: true },
  { label: "Cascadia Code NF", family: "Cascadia Code NF, monospace", alwaysAvailable: true },
  { label: "Fira Code", family: "Fira Code, monospace", alwaysAvailable: true },
  { label: "JetBrains Mono", family: "JetBrains Mono, monospace", alwaysAvailable: true },
  { label: "Source Code Pro", family: "Source Code Pro, monospace", alwaysAvailable: true },
  { label: "IBM Plex Mono", family: "IBM Plex Mono, monospace", alwaysAvailable: true }
];

function postFontChange(fontFamily) {
  try {
    const frame = window.frameElement;
    const windowId = frame && frame.getAttribute("data-window-id");
    window.parent.postMessage({
      type: "dsm-terminal-font-change",
      windowId,
      fontFamily
    }, "*");
  } catch (error) {
  }
}

function loadFontOptions() {
  if (!fontFamilySelect) {
    return;
  }

  const availableFonts = FONT_OPTIONS;
  const savedFamily = window.localStorage.getItem(FONT_STORAGE_KEY);
  const selectedFont = availableFonts.some((font) => font.family === savedFamily)
    ? savedFamily
    : availableFonts[0].family;

  fontFamilySelect.replaceChildren(...availableFonts.map((font) => {
    const option = document.createElement("option");
    option.value = font.family;
    option.textContent = font.label;
    return option;
  }));
  fontFamilySelect.value = selectedFont;
}

if (fontFamilySelect) {
  loadFontOptions();
  fontFamilySelect.addEventListener("change", () => {
    const fontFamily = fontFamilySelect.value;
    window.localStorage.setItem(FONT_STORAGE_KEY, fontFamily);
    postFontChange(fontFamily);
  });
}

function postHeightToParent() {
  try {
    if (!window.parent || window.parent === window || !document.body) {
      return;
    }
    const frame = window.frameElement;
    const windowId = frame && frame.getAttribute("data-window-id");
    const contentNode = helpShell || document.body;
    const height = Math.ceil(contentNode.scrollHeight + 42);
    window.parent.postMessage({
      type: "dsm-terminal-help-size",
      windowId,
      height
    }, "*");
  } catch (error) {
  }
}

async function callJsonEndpoint(url, payload = null) {
  const response = await fetch(url, {
    method: payload ? "POST" : "GET",
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  return response.json();
}

function setHelpStatus(message, isError = false) {
  helpStatus.textContent = message || "";
  helpStatus.style.color = isError ? "var(--danger)" : "";
}

function setSudoBadge(state, label) {
  sudoStatusBadge.textContent = label;
  sudoStatusBadge.classList.remove("enabled", "disabled");
  if (state) {
    sudoStatusBadge.classList.add(state);
  }
}

async function loadSudoStatus() {
  try {
    const payload = await callJsonEndpoint("sudo_status.cgi");
    if (!payload.ok) {
      throw new Error(payload.error || "Unable to check sudo status");
    }

    if (payload.available === false) {
      setSudoBadge("disabled", "Unavailable");
      setHelpStatus("`sudo` is not available in this package environment.");
    } else if (payload.enabled) {
      setSudoBadge("enabled", "Enabled");
      setHelpStatus("Passwordless sudo is currently enabled for `sc-dsm-terminal`.");
    } else {
      setSudoBadge("disabled", "Disabled");
      setHelpStatus("Passwordless sudo is currently disabled for `sc-dsm-terminal`.");
    }
  } catch (error) {
    if (!sudoStatusBadge.textContent || sudoStatusBadge.textContent === "Checking...") {
      setSudoBadge("disabled", "Unknown");
    }
    setHelpStatus(`Unable to check sudo status: ${error.message}`, true);
  }
  postHeightToParent();
}

async function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "readonly");
  area.style.position = "absolute";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  document.body.removeChild(area);
}

copyButtons.forEach((button) => {
  button.addEventListener("click", async () => {
    const targetId = button.getAttribute("data-copy-target");
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) {
      return;
    }
    try {
      await copyText(target.textContent || "");
      const original = button.textContent;
      button.textContent = "✓";
      window.setTimeout(() => {
        button.textContent = original;
      }, 1200);
    } catch (error) {
      setHelpStatus(`Copy failed: ${error.message}`, true);
    }
  });
});

if (window.ResizeObserver) {
  const observer = new window.ResizeObserver(() => {
    postHeightToParent();
  });
  observer.observe(document.body);
}

window.addEventListener("load", () => {
  postHeightToParent();
});

window.setInterval(() => {
  void loadSudoStatus();
}, STATUS_REFRESH_MS);

void loadSudoStatus();
