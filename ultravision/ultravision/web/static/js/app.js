const MAX_FILES = 16;
const CUSTOM_VALUE = "__custom__";
const DEFAULT_MODEL_OPTIONS = ["qwen/qwen3-vl-8b", "qwen/qwen3-vl-30b"];
const DEFAULT_SERVER = {
  value: "http://localhost:1234",
  label: "LM Studio · localhost:1234",
  service: "lm_studio",
  models: [...DEFAULT_MODEL_OPTIONS],
};

const state = {
  files: [],
  previews: new Map(),
  busy: false,
  toastTimer: null,
  lastResult: null,
  discovery: {
    servers: new Map(),
    raw: null,
    status: "idle",
  },
};

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("file-input");
const fileList = $("file-list");
const browseBtn = $("browse-btn");
const clearBtn = $("clear-btn");
const serverSelect = $("server-select");
const refreshDiscoveryBtn = $("refresh-discovery");
const apiBaseField = $("api-base");
const apiBaseCustom = $("api-base-custom");
const modelSelect = $("model-select");
const modelField = $("model");
const modelCustom = $("model-custom");
const form = $("analyze-form");
const analyzeBtn = $("analyze-btn");
const statusLine = $("status-line");
const resultsGrid = $("results");
const toast = $("toast");
const downloadFormat = $("download-format");
const downloadBtn = $("download-btn");
const lightbox = $("image-lightbox");
const lightboxImage = $("lightbox-image");
const lightboxCaption = $("lightbox-caption");
const lightboxClose = $("lightbox-close");

const sliderDisplays = {};
document.querySelectorAll("[data-display-target]").forEach((el) => {
  sliderDisplays[el.dataset.displayTarget] = el;
});

const sliderFormatters = {
  temperature: (value) => Number(value).toFixed(2),
  top_p: (value) => Number(value).toFixed(2),
  presence_penalty: (value) => Number(value).toFixed(2),
  frequency_penalty: (value) => Number(value).toFixed(2),
  max_tokens: (value) => `${Math.round(Number(value))} tokens`,
};

document.querySelectorAll('input[type="range"][data-display]').forEach((input) => {
  const key = input.dataset.display;
  const formatter = sliderFormatters[key] || ((value) => value);
  const update = () => {
    const span = sliderDisplays[key];
    if (span) {
      span.textContent = formatter(input.value);
    }
  };
  input.addEventListener("input", update);
  update();
});

function serviceLabel(service) {
  return service === "ollama" ? "Ollama" : "LM Studio";
}

function trimAddress(address) {
  return (address || "").replace(/^https?:\/\//i, "");
}

function initializeServerControls() {
  if (serverSelect) {
    serverSelect.innerHTML = "";
    const loadingOption = document.createElement("option");
    loadingOption.value = "";
    loadingOption.textContent = "Searching for servers...";
    loadingOption.disabled = true;
    loadingOption.selected = true;
    serverSelect.appendChild(loadingOption);
    serverSelect.disabled = true;
  }
  if (modelSelect) {
    modelSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select a server to load models";
    placeholder.disabled = true;
    placeholder.selected = true;
    modelSelect.appendChild(placeholder);
    modelSelect.disabled = true;
  }
}

function buildServerEntries(results) {
  if (!results) return [];
  const entries = [];
  ["lm_studio", "ollama"].forEach((service) => {
    (results[service] || []).forEach((server) => {
      const addresses = new Set([server.server_address, ...(server.local_addresses || [])].filter(Boolean));
      const models = Array.from(new Set(server.vision_models || []));
      addresses.forEach((address) => {
        entries.push({
          value: address,
          label: `${serviceLabel(service)} · ${trimAddress(address)}`,
          service,
          models: models.length ? models : DEFAULT_MODEL_OPTIONS,
        });
      });
    });
  });
  return entries;
}

function setServerOptions(entries, { allowDefaultFallback = false } = {}) {
  if (!serverSelect || !apiBaseField) return;
  const map = new Map();
  const wasCustom = serverSelect.value === CUSTOM_VALUE || (apiBaseCustom && !apiBaseCustom.hidden);
  const manualValue = wasCustom ? (apiBaseCustom?.value || apiBaseField.value) : "";
  entries.forEach((entry) => {
    if (!entry || !entry.value) return;
    const existing = map.get(entry.value);
    if (!existing || (!existing.models?.length && entry.models?.length)) {
      map.set(entry.value, entry);
    }
  });
  if (!map.size && allowDefaultFallback) {
    map.set(DEFAULT_SERVER.value, DEFAULT_SERVER);
  }
  state.discovery.servers = map;
  serverSelect.innerHTML = "";
  serverSelect.disabled = false;
  if (!map.size) {
    const customOption = document.createElement("option");
    customOption.value = CUSTOM_VALUE;
    customOption.textContent = "Custom server...";
    serverSelect.appendChild(customOption);
    serverSelect.value = CUSTOM_VALUE;
    if (apiBaseCustom) {
      apiBaseCustom.hidden = false;
      apiBaseCustom.required = true;
      apiBaseCustom.value = manualValue || "";
    }
    apiBaseField.value = (manualValue || "").trim();
    handleServerSelection(true);
    return;
  }
  [...map.values()].forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.value;
    option.textContent = entry.label;
    option.dataset.service = entry.service || "manual";
    serverSelect.appendChild(option);
  });
  const customOption = document.createElement("option");
  customOption.value = CUSTOM_VALUE;
  customOption.textContent = "Custom server...";
  serverSelect.appendChild(customOption);
  if (wasCustom) {
    serverSelect.value = CUSTOM_VALUE;
    if (apiBaseCustom) {
      apiBaseCustom.hidden = false;
      apiBaseCustom.required = true;
      apiBaseCustom.value = manualValue || "";
    }
    apiBaseField.value = (manualValue || "").trim();
    handleServerSelection(true);
    return;
  }
  const previous = apiBaseField.value;
  const hasPrevious = previous && map.has(previous);
  const firstEntry = map.values().next().value;
  const fallback = firstEntry ? firstEntry.value : DEFAULT_SERVER.value;
  serverSelect.value = hasPrevious ? previous : fallback;
  handleServerSelection(true);
}

function handleServerSelection(programmatic = false) {
  if (!serverSelect || !apiBaseField) return;
  const value = serverSelect.value;
  const useCustom = value === CUSTOM_VALUE;
  const manualModelValue = (modelCustom && modelCustom.value) || modelField.value;
  if (apiBaseCustom) {
    apiBaseCustom.hidden = !useCustom;
    apiBaseCustom.required = useCustom;
    if (useCustom && !apiBaseCustom.value) {
      apiBaseCustom.value = apiBaseField.value || "";
    }
  }
  if (useCustom) {
    apiBaseField.value = apiBaseCustom ? apiBaseCustom.value.trim() : "";
    if (!programmatic && apiBaseCustom) {
      setTimeout(() => apiBaseCustom.focus(), 40);
    }
    setModelOptions([], true, true);
    if (modelCustom) {
      modelCustom.value = manualModelValue || "";
    }
    modelField.value = (manualModelValue || "").trim();
    return;
  }
  apiBaseField.value = value;
  const entry = state.discovery.servers.get(value);
  setModelOptions(entry?.models || DEFAULT_MODEL_OPTIONS, programmatic, false);
}

function handleCustomServerInput() {
  if (!apiBaseField || !apiBaseCustom) return;
  apiBaseField.value = apiBaseCustom.value.trim();
}

function setModelOptions(models = [], programmatic = false, forceCustom = false) {
  if (!modelSelect || !modelField) return;
  modelSelect.disabled = false;
  const source = Array.isArray(models) ? models : [];
  const unique = Array.from(new Set(source.filter(Boolean)));
  modelSelect.innerHTML = "";
  unique.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    modelSelect.appendChild(option);
  });
  const customOption = document.createElement("option");
  customOption.value = CUSTOM_VALUE;
  customOption.textContent = "Custom model...";
  modelSelect.appendChild(customOption);
  const previous = modelField.value;
  const shouldUseCustom = forceCustom || (Boolean(previous) && !unique.includes(previous));
  const fallback = unique[0] || DEFAULT_MODEL_OPTIONS[0];
  if (shouldUseCustom || !unique.length) {
    modelSelect.value = CUSTOM_VALUE;
    handleModelSelection(true);
    return;
  }
  if (previous && unique.includes(previous)) {
    modelSelect.value = previous;
  } else {
    modelSelect.value = fallback;
  }
  handleModelSelection(programmatic);
}

function handleModelSelection(programmatic = false) {
  if (!modelSelect || !modelField) return;
  const value = modelSelect.value;
  const useCustom = value === CUSTOM_VALUE;
  if (modelCustom) {
    modelCustom.hidden = !useCustom;
    modelCustom.required = useCustom;
  }
  if (useCustom) {
    if (modelCustom && !modelCustom.value) {
      modelCustom.value = modelField.value || "";
    }
    modelField.value = modelCustom ? modelCustom.value.trim() : "";
    if (!programmatic && modelCustom) {
      setTimeout(() => modelCustom.focus(), 40);
    }
    return;
  }
  modelField.value = value;
  if (modelCustom && !programmatic) {
    modelCustom.value = "";
  }
}

function handleCustomModelInput() {
  if (!modelField || !modelCustom) return;
  modelField.value = modelCustom.value.trim();
}

async function loadDiscovery(showFeedback = false) {
  if (!serverSelect) return;
  if (state.discovery.status === "loading") return;
  state.discovery.status = "loading";
  if (refreshDiscoveryBtn) {
    refreshDiscoveryBtn.disabled = true;
  }
  try {
    const response = await fetch("/api/discover");
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || response.statusText);
    }
    const payload = await response.json();
    state.discovery.raw = payload;
    const entries = buildServerEntries(payload);
    setServerOptions(entries);
    if (showFeedback) {
      if (entries.length) {
        showToast(`Found ${entries.length} server${entries.length === 1 ? "" : "s"}.`);
      } else {
        showToast("No vision servers detected yet.", "warn");
      }
    }
  } catch (error) {
    console.error("Discovery failed", error);
    if (showFeedback) {
      showToast("Server discovery failed - enter settings manually.", "error");
    }
    state.discovery.raw = null;
    if (!state.discovery.servers.size) {
      setServerOptions([], { allowDefaultFallback: true });
    }
  } finally {
    state.discovery.status = "idle";
    if (refreshDiscoveryBtn) {
      refreshDiscoveryBtn.disabled = false;
    }
  }
}

function showToast(message, tone = "info") {
  toast.textContent = message;
  toast.dataset.tone = tone;
  toast.classList.add("visible");
  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  state.toastTimer = setTimeout(() => toast.classList.remove("visible"), 3600);
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[exponent]}`;
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, (match) =>
    ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    })[match]
  );
}

function sanitizeFilename(name) {
  return name.replace(/[^a-z0-9]+/gi, "-").replace(/^-+|-+$/g, "").toLowerCase() || "ultravision-output";
}

function isoSlug() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

function escapeCsv(value) {
  const str = value == null ? "" : String(value);
  if (/[",\r\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function renderInlineMarkdown(text) {
  if (!text) return "";
  let escaped = escapeHtml(text);

  escaped = escaped.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_match, label, url) =>
    `<a href="${url}" target="_blank" rel="noreferrer noopener">${label}</a>`
  );

  escaped = escaped.replace(/`([^`]+)`/g, (_match, code) => `<code>${code}</code>`);

  escaped = escaped.replace(/\*\*(.+?)\*\*/g, (_match, content) => `<strong>${content}</strong>`);
  escaped = escaped.replace(/__(.+?)__/g, (_match, content) => `<strong>${content}</strong>`);

  escaped = escaped.replace(/(^|[\s(])\*([^\*\n]+?)\*(?=[\s).,;:!?]|$)/g, (_match, prefix, content) =>
    `${prefix}<em>${content}</em>`
  );
  escaped = escaped.replace(/(^|[\s(])_([^\_\n]+?)_(?=[\s).,;:!?]|$)/g, (_match, prefix, content) =>
    `${prefix}<em>${content}</em>`
  );

  return escaped;
}

function renderMarkdown(markdown) {
  if (!markdown) return "";
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  let html = "";
  let inCodeBlock = false;
  let codeBuffer = [];
  let listType = null;
  let paragraph = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    html += `<p>${renderInlineMarkdown(paragraph.join(" ").trim())}</p>`;
    paragraph = [];
  };

  const flushList = () => {
    if (!listType) return;
    html += listType === "ul" ? "</ul>" : "</ol>";
    listType = null;
  };

  const flushCode = () => {
    if (!codeBuffer.length) return;
    html += `<pre><code>${codeBuffer.map((line) => escapeHtml(line)).join("\n")}</code></pre>`;
    codeBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine;
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        flushCode();
        inCodeBlock = false;
      } else {
        flushParagraph();
        flushList();
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = headingMatch[1].length;
      html += `<h${level}>${renderInlineMarkdown(headingMatch[2].trim())}</h${level}>`;
      continue;
    }

    const unorderedMatch = line.match(/^\s*[-*]\s+(.*)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType !== "ul") {
        flushList();
        html += "<ul>";
        listType = "ul";
      }
      html += `<li>${renderInlineMarkdown(unorderedMatch[1].trim())}</li>`;
      continue;
    }

    const orderedMatch = line.match(/^\s*\d+\.\s+(.*)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType !== "ol") {
        flushList();
        html += "<ol>";
        listType = "ol";
      }
      html += `<li>${renderInlineMarkdown(orderedMatch[1].trim())}</li>`;
      continue;
    }

    flushList();
    paragraph.push(line.trim());
  }

  flushParagraph();
  flushList();
  if (inCodeBlock) {
    flushCode();
  }

  return html;
}

function buildExport(format, payload) {
  const assets = payload.assets || [];
  const summary = (payload.summary || "").trim();
  const baseName = sanitizeFilename(assets[0]?.name || "ultravision");
  const timestamp = isoSlug();

  switch (format) {
    case "markdown": {
      let output = `# UltraVision Analysis Report\n\n`;
      output += `**Generated:** ${new Date().toLocaleString()}\n\n`;
      if (summary) {
        output += `## Summary\n\n${summary}\n\n`;
      } else {
        output += `## Summary\n\n_No narrative returned._\n\n`;
      }
      if (assets.length) {
        output += `## Assets\n\n`;
        for (const asset of assets) {
          const meta = asset.meta || {};
          output += `### ${asset.name}\n`;
          output += `- MIME: ${meta.mime || "?"}\n`;
          if (meta.width && meta.height) {
            output += `- Dimensions: ${meta.width}x${meta.height}\n`;
          }
          if (meta.size_bytes != null) {
            output += `- Size: ${meta.size_bytes} bytes\n`;
          }
          if (meta.sha256) {
            output += `- SHA256: \`${meta.sha256}\`\n`;
          }
          output += "\n";
        }
      }
      return {
        filename: `${baseName}-${timestamp}.md`,
        mime: "text/markdown;charset=utf-8",
        content: output,
      };
    }
    case "text": {
      let output = `UltraVision Analysis Report\nGenerated: ${new Date().toLocaleString()}\n\n`;
      output += `Summary:\n${summary || "(No narrative returned)"}\n\n`;
      if (assets.length) {
        output += "Assets:\n";
        for (const asset of assets) {
          const meta = asset.meta || {};
          const parts = [asset.name];
          if (meta.mime) parts.push(meta.mime);
          if (meta.size_bytes != null) parts.push(`${meta.size_bytes} bytes`);
          if (meta.width && meta.height) parts.push(`${meta.width}x${meta.height}`);
          output += `- ${parts.join(" | ")}\n`;
        }
      }
      return {
        filename: `${baseName}-${timestamp}.txt`,
        mime: "text/plain;charset=utf-8",
        content: output,
      };
    }
    case "json": {
      const exportObject = {
        summary,
        assets,
        request: payload.request,
        messages: payload.messages,
      };
      return {
        filename: `${baseName}-${timestamp}.json`,
        mime: "application/json",
        content: JSON.stringify(exportObject, null, 2),
      };
    }
    case "jsonl": {
      const record = {
        files: assets.map((asset) => asset.name),
        text: summary,
        meta: assets.map((asset) => asset.meta || {}),
        request: payload.request,
      };
      return {
        filename: `${baseName}-${timestamp}.jsonl`,
        mime: "application/json",
        content: `${JSON.stringify(record)}\n`,
      };
    }
    case "csv": {
      const header = ["file", "mime", "width", "height", "size_bytes", "summary"];
      const rows = [header.join(",")];
      if (assets.length) {
        for (const asset of assets) {
          const meta = asset.meta || {};
          rows.push(
            [
              escapeCsv(asset.name),
              escapeCsv(meta.mime || ""),
              escapeCsv(meta.width != null ? meta.width : ""),
              escapeCsv(meta.height != null ? meta.height : ""),
              escapeCsv(meta.size_bytes != null ? meta.size_bytes : ""),
              escapeCsv(summary.replace(/\s+/g, " ").trim()),
            ].join(",")
          );
        }
      } else {
        rows.push([escapeCsv("summary"), "", "", "", "", escapeCsv(summary)].join(","));
      }
      return {
        filename: `${baseName}-${timestamp}.csv`,
        mime: "text/csv;charset=utf-8",
        content: rows.join("\n"),
      };
    }
    default:
      throw new Error(`Unsupported format: ${format}`);
  }
}

function triggerDownload({ filename, mime, content }) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function setDownloadReady(flag) {
  downloadBtn.disabled = !flag;
}

function openLightbox(src, alt, captionText) {
  if (!lightbox || !lightboxImage) return;
  lightboxImage.src = src;
  lightboxImage.alt = alt || "Image preview";
  if (lightboxCaption) {
    lightboxCaption.textContent = captionText || "";
    lightboxCaption.style.display = captionText ? "block" : "none";
  }
  lightbox.classList.add("lightbox--open");
  lightbox.setAttribute("aria-hidden", "false");
  lightboxClose?.focus();
}

function closeLightbox() {
  if (!lightbox || !lightboxImage) return;
  lightbox.classList.remove("lightbox--open");
  lightbox.setAttribute("aria-hidden", "true");
  lightboxImage.src = "";
  lightboxImage.alt = "";
  if (lightboxCaption) {
    lightboxCaption.textContent = "";
    lightboxCaption.style.display = "none";
  }
}

function clearPreviews() {
  state.previews.forEach((url) => URL.revokeObjectURL(url));
  state.previews.clear();
}

function renderSelectedFiles() {
  fileList.innerHTML = "";
  if (!state.files.length) {
    const placeholder = document.createElement("li");
    placeholder.className = "dropzone__placeholder";
    placeholder.textContent = "No files selected. Drag images here or browse to add them.";
    fileList.appendChild(placeholder);
    return;
  }

  state.files.forEach((file, index) => {
    const item = document.createElement("li");
    item.className = "file-pill";

    const key = fileKey(file);
    let previewUrl = state.previews.get(key);
    if (!previewUrl) {
      previewUrl = URL.createObjectURL(file);
      state.previews.set(key, previewUrl);
    }
    if (previewUrl) {
      const thumb = document.createElement("div");
      thumb.className = "file-pill__thumb";
      const img = document.createElement("img");
      img.src = previewUrl;
      img.alt = file.name ? `Preview of ${file.name}` : "Image preview";
      thumb.appendChild(img);
      item.appendChild(thumb);
    }

    const meta = document.createElement("div");
    meta.className = "file-pill__meta";
    const name = document.createElement("span");
    name.className = "file-pill__name";
    name.textContent = file.name || "Untitled image";
    const details = document.createElement("span");
    details.className = "file-pill__details";
    details.textContent = `${formatBytes(file.size)} | ${new Date(file.lastModified).toLocaleString()}`;
    meta.appendChild(name);
    meta.appendChild(details);
    item.appendChild(meta);

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn--ghost";
    removeBtn.dataset.remove = index;
    removeBtn.textContent = "Remove";
    removeBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      removeFileAt(index);
    });
    item.appendChild(removeBtn);

    fileList.appendChild(item);
  });
}

function fileKey(file) {
  return `${file.name}|${file.lastModified}|${file.size}`;
}

function addFiles(list) {
  const incoming = Array.from(list);
  if (!incoming.length) return;

  let added = 0;
  for (const file of incoming) {
    if (!file.type.startsWith("image/")) {
      showToast(`Skipped ${file.name}: not an image.`, "error");
      continue;
    }
    if (state.files.length >= MAX_FILES) {
      showToast(`Limit reached: only ${MAX_FILES} images per batch.`, "error");
      break;
    }
    const key = fileKey(file);
    if (state.previews.has(key)) {
      continue;
    }
    state.files.push(file);
    state.previews.set(key, URL.createObjectURL(file));
    added += 1;
  }

  if (added) {
    renderSelectedFiles();
    dropzone.classList.add("pulse");
    setTimeout(() => dropzone.classList.remove("pulse"), 360);
  }
}

function removeFileAt(index) {
  const [removed] = state.files.splice(index, 1);
  if (removed) {
    const key = fileKey(removed);
    const url = state.previews.get(key);
    if (url) {
      URL.revokeObjectURL(url);
      state.previews.delete(key);
    }
  }
  renderSelectedFiles();
}

function clearFiles() {
  clearPreviews();
  state.files = [];
  fileInput.value = "";
  renderSelectedFiles();
}

function setBusy(flag) {
  state.busy = flag;
  analyzeBtn.disabled = flag;
  analyzeBtn.classList.toggle("loading", flag);
}

async function submitForm(event) {
  event.preventDefault();
  if (state.busy) {
    return;
  }
  if (!state.files.length) {
    dropzone.classList.add("shake");
    setTimeout(() => dropzone.classList.remove("shake"), 520);
    showToast("Add at least one image before analyzing.", "error");
    return;
  }

  setBusy(true);
  statusLine.textContent = "Submitting request...";
  resultsGrid.innerHTML = "";
  state.lastResult = null;
  setDownloadReady(false);

  const formData = new FormData(form);
  formData.delete("files");
  state.files.forEach((file) => formData.append("files", file, file.name));

  try {
    const response = await fetch("/api/analyze", { method: "POST", body: formData });
    if (!response.ok) {
      let message = response.statusText;
      try {
        const text = await response.text();
        message = text || message;
      } catch {
        // ignore
      }
      showToast(`Server error: ${message}`, "error");
      statusLine.textContent = "Request failed - adjust settings and retry.";
      return;
    }
    const payload = await response.json();
    renderResults(payload);
    showToast("Analysis complete.");
  } catch (error) {
    console.error(error);
    showToast("Network error - ensure the server and LM Studio are reachable.", "error");
    statusLine.textContent = "Network error - retry when ready.";
  } finally {
    setBusy(false);
  }
}

function renderResults(payload) {
  state.lastResult = payload;
  setDownloadReady(true);

  statusLine.textContent = payload.summary
    ? "Summary ready - see details below."
    : "Processed images - review the output below.";

  resultsGrid.innerHTML = "";

  if (payload.summary) {
    const summaryCard = document.createElement("article");
    summaryCard.className = "summary-card";
    const summaryText = payload.summary.trim();
    const summaryHtml = summaryText ? renderMarkdown(summaryText) : "";
    summaryCard.innerHTML = `
      <h3>Model Summary</h3>
      <div class="markdown-content">${summaryHtml || "<p>(No summary provided.)</p>"}</div>
    `;
    resultsGrid.appendChild(summaryCard);
  }

  const assets = payload.assets || [];
  if (assets.length) {
    const gallery = document.createElement("div");
    gallery.className = "results__gallery";
    assets.forEach((asset) => {
      const tile = document.createElement("article");
      tile.className = "results__tile";

      const details = [
        asset.meta?.width && asset.meta?.height && `${asset.meta.width}x${asset.meta.height}px`,
        asset.meta?.size_bytes && formatBytes(asset.meta.size_bytes),
        asset.meta?.mime,
      ].filter(Boolean);
      const metaText = details.join(" · ") || "Uploaded image";

      const previewEntry = [...state.previews.entries()].find(([key]) =>
        key.startsWith(`${asset.name}|`)
      );
      if (previewEntry) {
        const img = document.createElement("img");
        img.src = previewEntry[1];
        img.alt = asset.name;
        tile.appendChild(img);
        tile.classList.add("results__tile--clickable");
        tile.addEventListener("click", () =>
          openLightbox(previewEntry[1], asset.name, metaText)
        );
      } else {
        tile.classList.add("results__tile--empty");
        const placeholder = document.createElement("div");
        placeholder.className = "results__tile-empty";
        placeholder.textContent = "Preview unavailable";
        tile.appendChild(placeholder);
      }

      const caption = document.createElement("div");
      caption.className = "results__caption";
      const title = document.createElement("strong");
      title.textContent = asset.name;
      const metaLine = document.createElement("span");
      metaLine.textContent = metaText;
      caption.appendChild(title);
      caption.appendChild(metaLine);
      tile.appendChild(caption);

      gallery.appendChild(tile);
    });
    resultsGrid.appendChild(gallery);
  } else {
    const placeholder = document.createElement("p");
    placeholder.className = "results__placeholder";
    placeholder.textContent = "Images processed - upload more to keep exploring.";
    resultsGrid.appendChild(placeholder);
  }
}

function downloadResults() {
  if (!state.lastResult) {
    showToast("Run an analysis before downloading.", "error");
    return;
  }
  try {
    const format = downloadFormat.value;
    const artifact = buildExport(format, state.lastResult);
    triggerDownload(artifact);
    showToast(`Saved results as ${artifact.filename}.`);
  } catch (error) {
    console.error(error);
    showToast("Unable to export - try a different format.", "error");
  }
}

dropzone.addEventListener("click", (event) => {
  if (event.target === dropzone) {
    fileInput.click();
  }
});

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("drag-active");
});

dropzone.addEventListener("dragleave", (event) => {
  if (!dropzone.contains(event.relatedTarget)) {
    dropzone.classList.remove("drag-active");
  }
});

dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("drag-active");
  addFiles(event.dataTransfer.files);
});

fileInput.addEventListener("change", (event) => {
  addFiles(event.target.files);
  fileInput.value = "";
});

if (serverSelect) {
  serverSelect.addEventListener("change", () => handleServerSelection(false));
}
if (refreshDiscoveryBtn) {
  refreshDiscoveryBtn.addEventListener("click", () => loadDiscovery(true));
}
if (apiBaseCustom) {
  apiBaseCustom.addEventListener("input", handleCustomServerInput);
}
if (modelSelect) {
  modelSelect.addEventListener("change", () => handleModelSelection(false));
}
if (modelCustom) {
  modelCustom.addEventListener("input", handleCustomModelInput);
}

browseBtn.addEventListener("click", () => fileInput.click());
clearBtn.addEventListener("click", clearFiles);
form.addEventListener("submit", submitForm);
downloadBtn.addEventListener("click", downloadResults);

if (lightbox) {
  lightbox.addEventListener("click", (event) => {
    if (
      event.target === lightbox ||
      event.target.dataset?.lightboxClose !== undefined
    ) {
      closeLightbox();
    }
  });
}

lightboxClose?.addEventListener("click", closeLightbox);

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && lightbox?.classList.contains("lightbox--open")) {
    closeLightbox();
  }
});

initializeServerControls();
renderSelectedFiles();
setDownloadReady(false);
loadDiscovery();
