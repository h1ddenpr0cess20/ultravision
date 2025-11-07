const MAX_FILES = 16;

const state = {
  files: [],
  previews: new Map(),
  busy: false,
  toastTimer: null,
  lastResult: null,
};

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("file-input");
const fileList = $("file-list");
const browseBtn = $("browse-btn");
const clearBtn = $("clear-btn");
const form = $("analyze-form");
const analyzeBtn = $("analyze-btn");
const statusLine = $("status-line");
const resultsGrid = $("results");
const toast = $("toast");
const downloadFormat = $("download-format");
const downloadBtn = $("download-btn");

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
    item.innerHTML = `
      <div class="file-pill__meta">
        <span class="file-pill__name">${escapeHtml(file.name)}</span>
        <span class="file-pill__details">${formatBytes(file.size)} | ${new Date(file.lastModified).toLocaleString()}</span>
      </div>
      <button type="button" class="btn btn--ghost" data-remove="${index}">Remove</button>
    `;
    const removeBtn = item.querySelector("[data-remove]");
    removeBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      removeFileAt(index);
    });
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
  resultsGrid.innerHTML = "";
  statusLine.textContent = "Add images to get started.";
  state.lastResult = null;
  setDownloadReady(false);
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

  (payload.assets || []).forEach((asset) => {
    const card = document.createElement("article");
    card.className = "result-card";

    const previewEntry = [...state.previews.entries()].find(([key]) =>
      key.startsWith(`${asset.name}|`)
    );
    if (previewEntry) {
      const img = document.createElement("img");
      img.src = previewEntry[1];
      img.alt = asset.name;
      img.className = "result-card__preview";
      card.appendChild(img);
    }

    const title = document.createElement("h3");
    title.textContent = asset.name;
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "result-card__meta";
    const details = [
      asset.meta?.mime && `MIME ${asset.meta.mime}`,
      asset.meta?.width && asset.meta?.height && `${asset.meta.width}x${asset.meta.height}px`,
      asset.meta?.mode && `Mode ${asset.meta.mode}`,
      asset.meta?.size_bytes && formatBytes(asset.meta.size_bytes),
      asset.meta?.sha256 && `SHA ${asset.meta.sha256.slice(0, 10)}...`,
    ].filter(Boolean);
    meta.textContent = details.join(" | ");
    card.appendChild(meta);

    resultsGrid.appendChild(card);
  });

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

browseBtn.addEventListener("click", () => fileInput.click());
clearBtn.addEventListener("click", clearFiles);
form.addEventListener("submit", submitForm);
downloadBtn.addEventListener("click", downloadResults);

renderSelectedFiles();
setDownloadReady(false);

