const strokeW = 2;
const scaleFactor = 10;

// Thickness (in the same units as your bins/items file) of each horizontal
// cross-section "slice" view. Lower = more slices, finer detail.
const SLICE_INTERVAL = 5;

let result;

async function setup() {
  noLoop();

  // We render every view into offscreen buffers (p5.Graphics) and attach
  // their canvases straight into the page ourselves, so we don't need (or
  // want) p5's own default canvas.
  noCanvas();

  const container = createPageContainer();

  try {
    const res = await fetch("output.txt");
    if (!res.ok) throw new Error(`HTTP status ${res.status}`);
    const text = await res.text();
    result = text.split(/\r?\n/);
  } catch (err) {
    renderMessage(container, `Failed to load output.txt: ${err}`, true);
    return;
  }

  if (!result || !Array.isArray(result) || result.length === 0) {
    renderMessage(
      container,
      "output.txt is missing or empty. Make sure you're running this " +
      "sketch through a local server (not file://) and that " +
      "box_packer_3d.py has been run so output.txt exists.",
      true
    );
    return;
  }

  const bins = parseOutput(result);

  if (bins.length === 0) {
    renderMessage(container, "output.txt didn't contain any bins (no '#' header lines found).", true);
    return;
  }

  for (const bin of bins) {
    renderBin(container, bin);
  }
}

// ---------------------------------------------------------------------
// Page scaffolding
// ---------------------------------------------------------------------

function createPageContainer() {
  const style = document.createElement("style");
  style.textContent = `
    body { background: #000; color: #eee; font-family: sans-serif; margin: 0; padding: 20px; }
    .bin-section { margin-bottom: 48px; border-bottom: 1px solid #333; padding-bottom: 32px; }
    .bin-heading { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
    .bin-heading h2 { margin: 0 0 4px 0; }
    .bin-heading .meta { color: #999; font-size: 14px; }
    .bin-heading button {
      margin-left: auto; background: #222; color: #eee; border: 1px solid #555;
      border-radius: 4px; padding: 6px 12px; cursor: pointer; font-size: 13px;
    }
    .bin-heading button:hover { background: #333; }
    .bin-canvas-wrap { overflow-x: auto; margin-top: 12px; }
    .empty-note { color: #e0a030; margin-top: 8px; }
    .error-note { color: #e05050; }
  `;
  document.head.appendChild(style);

  const container = document.createElement("div");
  container.id = "bins-container";
  document.body.appendChild(container);
  return container;
}

function renderMessage(container, text, isError) {
  const p = document.createElement("p");
  p.className = isError ? "error-note" : "";
  p.textContent = text;
  container.appendChild(p);
}

// ---------------------------------------------------------------------
// Parsing output.txt
// ---------------------------------------------------------------------

function parseOutput(lines) {
  let bins = [];
  let currentBin = null;

  for (let row of lines) {
    row = row.trim();
    if (row === "") continue;

    if (row[0] === "#") {
      let parts = row.substring(1).split(",");
      currentBin = {
        name: parts[0],
        length: float(parts[1]),
        height: float(parts[2]),
        width: float(parts[3]),
        items: []
      };
      bins.push(currentBin);
    } else {
      if (!currentBin) continue; // malformed file: item line before any bin header
      let parts = row.split(",");
      currentBin.items.push({
        name: parts[0],
        x1: float(parts[1]),
        y1: float(parts[2]),
        z1: float(parts[3]),
        x2: float(parts[4]),
        y2: float(parts[5]),
        z2: float(parts[6])
      });
    }
  }

  return bins;
}

// ---------------------------------------------------------------------
// Rendering one bin: builds the composite offscreen buffer, then attaches
// its real <canvas> element into the DOM so it's actually visible, and
// wires up an explicit "Download PNG" button (a single user-initiated
// download per click never gets throttled by the browser, unlike firing
// several downloads at once).
// ---------------------------------------------------------------------

function renderBin(container, bin) {
  const section = document.createElement("div");
  section.className = "bin-section";

  const heading = document.createElement("div");
  heading.className = "bin-heading";
  heading.innerHTML = `
    <h2>${escapeHtml(bin.name)}</h2>
    <span class="meta">${nf(bin.length, 0, 1)} &times; ${nf(bin.height, 0, 1)} &times; ${nf(bin.width, 0, 1)} (L&times;H&times;W) &mdash; ${bin.items.length} item(s)</span>
  `;
  section.appendChild(heading);

  if (bin.items.length === 0) {
    const note = document.createElement("div");
    note.className = "empty-note";
    note.textContent = "This bin has no items placed in it.";
    section.appendChild(note);
  }

  const pg = buildBinGraphics(bin);

  const canvasWrap = document.createElement("div");
  canvasWrap.className = "bin-canvas-wrap";
  canvasWrap.appendChild(pg.canvas);
  section.appendChild(canvasWrap);

  const downloadBtn = document.createElement("button");
  downloadBtn.textContent = "Download PNG";
  downloadBtn.onclick = () => {
    const filename = bin.name.replace(/[^a-zA-Z0-9_-]/g, "_") + ".png";
    save(pg, filename);
  };
  heading.appendChild(downloadBtn);

  container.appendChild(section);
}

function buildBinGraphics(bin) {
  const margin = 40;

  const topWidth = bin.length * scaleFactor;
  const topHeight = bin.width * scaleFactor;

  const frontWidth = bin.length * scaleFactor;
  const frontHeight = bin.height * scaleFactor;

  const sideWidth = bin.width * scaleFactor;
  const sideHeight = bin.height * scaleFactor;

  // One slice per SLICE_INTERVAL units of height, covering the whole bin
  // (the last slice may be thinner than SLICE_INTERVAL if it doesn't divide
  // evenly).
  const sliceRanges = [];
  for (let y0 = 0; y0 < bin.height - 1e-9; y0 += SLICE_INTERVAL) {
    sliceRanges.push([y0, Math.min(y0 + SLICE_INTERVAL, bin.height)]);
  }
  if (sliceRanges.length === 0) {
    sliceRanges.push([0, bin.height]);
  }

  const sliceRowHeight = topHeight + margin * 1.5;

  const canvasWidth = Math.max(
    topWidth + margin * 2,
    frontWidth * 2 + margin * 3,
    topWidth + margin * 2
  );

  const canvasHeight =
    30 +                                    // title
    margin +
    topHeight + margin * 2 +                // top view
    frontHeight + margin * 2 +              // front/back row
    sideHeight + margin * 2 +               // left/right row
    sliceRanges.length * sliceRowHeight +    // slice rows
    margin;

  const pg = createGraphics(canvasWidth, canvasHeight);

  pg.background(0);
  pg.textAlign(CENTER, CENTER);
  pg.textSize(20);
  pg.fill(255);
  pg.noStroke();
  pg.text(bin.name, canvasWidth / 2, 20);

  let cursorY = 50;

  // TOP VIEW
  const topX = (canvasWidth - topWidth) / 2;
  drawTopView(pg, bin, topX, cursorY);
  cursorY += topHeight + margin * 2;

  // FRONT & BACK VIEWS
  const frontX = canvasWidth / 2 - frontWidth - margin / 2;
  const backX = canvasWidth / 2 + margin / 2;
  drawFrontView(pg, bin, frontX, cursorY);
  drawBackView(pg, bin, backX, cursorY);
  cursorY += frontHeight + margin * 2;

  // LEFT & RIGHT VIEWS
  const leftX = canvasWidth / 2 - sideWidth - margin / 2;
  const rightX = canvasWidth / 2 + margin / 2;
  drawLeftView(pg, bin, leftX, cursorY);
  drawRightView(pg, bin, rightX, cursorY);
  cursorY += sideHeight + margin * 2;

  // HEIGHT-INTERVAL SLICE VIEWS
  for (const [y0, y1] of sliceRanges) {
    drawSliceView(pg, bin, topX, cursorY, y0, y1);
    cursorY += sliceRowHeight;
  }

  return pg;
}

// ---------------------------------------------------------------------
// Individual view drawers
// ---------------------------------------------------------------------

function drawTopView(pg, bin, ox, oy) {
  const w = bin.length * scaleFactor;
  const h = bin.width * scaleFactor;

  drawViewLabel(pg, "TOP", ox + w / 2, oy - 15);

  pg.noFill();
  pg.stroke(255);
  pg.strokeWeight(strokeW);
  pg.rect(ox, oy, w, h);

  for (const item of bin.items) {
    const x1 = ox + item.x1 * scaleFactor;
    const x2 = ox + item.x2 * scaleFactor;
    const y1 = oy + item.z1 * scaleFactor;
    const y2 = oy + item.z2 * scaleFactor;
    drawItem(pg, item, x1, y1, x2, y2, true);
  }
}

function drawFrontView(pg, bin, ox, oy) {
  const w = bin.length * scaleFactor;
  const h = bin.height * scaleFactor;

  drawViewLabel(pg, "FRONT", ox + w / 2, oy - 15);

  pg.noFill();
  pg.stroke(255);
  pg.strokeWeight(strokeW);
  pg.rect(ox, oy, w, h);

  for (const item of bin.items) {
    const x1 = ox + item.x1 * scaleFactor;
    const x2 = ox + item.x2 * scaleFactor;
    const y1 = oy + h - item.y2 * scaleFactor;
    const y2 = oy + h - item.y1 * scaleFactor;
    drawItem(pg, item, x1, y1, x2, y2, true);
  }
}

function drawBackView(pg, bin, ox, oy) {
  const w = bin.length * scaleFactor;
  const h = bin.height * scaleFactor;

  drawViewLabel(pg, "BACK", ox + w / 2, oy - 15);

  pg.noFill();
  pg.stroke(255);
  pg.strokeWeight(strokeW);
  pg.rect(ox, oy, w, h);

  for (const item of bin.items) {
    const x1 = ox + w - item.x2 * scaleFactor;
    const x2 = ox + w - item.x1 * scaleFactor;
    const y1 = oy + h - item.y2 * scaleFactor;
    const y2 = oy + h - item.y1 * scaleFactor;
    drawItem(pg, item, x1, y1, x2, y2, true);
  }
}

function drawLeftView(pg, bin, ox, oy) {
  const w = bin.width * scaleFactor;
  const h = bin.height * scaleFactor;

  drawViewLabel(pg, "LEFT", ox + w / 2, oy - 15);

  pg.noFill();
  pg.stroke(255);
  pg.strokeWeight(strokeW);
  pg.rect(ox, oy, w, h);

  for (const item of bin.items) {
    const x1 = ox + item.z1 * scaleFactor;
    const x2 = ox + item.z2 * scaleFactor;
    const y1 = oy + h - item.y2 * scaleFactor;
    const y2 = oy + h - item.y1 * scaleFactor;
    drawItem(pg, item, x1, y1, x2, y2, true);
  }
}

function drawRightView(pg, bin, ox, oy) {
  const w = bin.width * scaleFactor;
  const h = bin.height * scaleFactor;

  drawViewLabel(pg, "RIGHT", ox + w / 2, oy - 15);

  pg.noFill();
  pg.stroke(255);
  pg.strokeWeight(strokeW);
  pg.rect(ox, oy, w, h);

  for (const item of bin.items) {
    const x1 = ox + w - item.z2 * scaleFactor;
    const x2 = ox + w - item.z1 * scaleFactor;
    const y1 = oy + h - item.y2 * scaleFactor;
    const y2 = oy + h - item.y1 * scaleFactor;
    drawItem(pg, item, x1, y1, x2, y2, true);
  }
}

// A horizontal cross-section: a top-down plan view of everything occupying
// the height band [y0, y1). Items that only partially occupy the band (they
// start or end partway through it) are drawn with a dashed outline so it's
// visually obvious they're "cut" by this slice rather than fully contained
// in it.
function drawSliceView(pg, bin, ox, oy, y0, y1) {
  const w = bin.length * scaleFactor;
  const h = bin.width * scaleFactor;

  drawViewLabel(pg, `SLICE  y=[${nf(y0, 0, 1)}, ${nf(y1, 0, 1)})`, ox + w / 2, oy - 15);

  pg.noFill();
  pg.stroke(255);
  pg.strokeWeight(strokeW);
  pg.rect(ox, oy, w, h);

  for (const item of bin.items) {
    // Does this item's vertical extent intersect the slice band at all?
    const overlaps = item.y1 < y1 && item.y2 > y0;
    if (!overlaps) continue;

    const fullySpans = item.y1 <= y0 + 1e-9 && item.y2 >= y1 - 1e-9;

    const x1 = ox + item.x1 * scaleFactor;
    const x2 = ox + item.x2 * scaleFactor;
    const y1px = oy + item.z1 * scaleFactor;
    const y2px = oy + item.z2 * scaleFactor;
    drawItem(pg, item, x1, y1px, x2, y2px, fullySpans);
  }
}

function drawViewLabel(pg, label, x, y) {
  pg.noStroke();
  pg.fill(255);
  pg.textSize(16);
  pg.textAlign(CENTER, CENTER);
  pg.text(label, x, y);
}

// `solid` controls whether the outline is drawn solid (item fully occupies
// this view's depth/height band) or dashed (only partially - i.e. it's cut
// by a slice boundary). p5 doesn't expose a stroke dash pattern directly on
// its 2D canvas wrapper's `rect`, so we fall back to the underlying canvas
// context to draw a dashed rect when needed.
function drawItem(pg, item, x1, y1, x2, y2, solid) {
  let hash = 0;
  for (let i = 0; i < item.name.length; i++) {
    hash = ((hash << 5) - hash) + item.name.charCodeAt(i);
    hash |= 0;
  }

  const r = abs(hash) % 256;
  const g = abs(hash * 17) % 256;
  const b = abs(hash * 31) % 256;
  const c = color(r, g, b);

  const rx = min(x1, x2);
  const ry = min(y1, y2);
  const rw = abs(x2 - x1);
  const rh = abs(y2 - y1);

  const ctx = pg.drawingContext;
  ctx.save();
  ctx.strokeStyle = `rgb(${r}, ${g}, ${b})`;
  ctx.lineWidth = strokeW;
  ctx.setLineDash(solid ? [] : [6, 4]);
  ctx.strokeRect(rx, ry, rw, rh);
  ctx.restore();

  pg.noStroke();
  pg.fill(c);
  pg.textSize(12);
  pg.textAlign(LEFT, TOP);

  const dx = abs(item.x2 - item.x1);
  const dy = abs(item.y2 - item.y1);
  const dz = abs(item.z2 - item.z1);

  const label = `${item.name} (${nf(dx, 0, 1)}, ${nf(dy, 0, 1)}, ${nf(dz, 0, 1)})`;

  pg.text(label, rx + 4, ry + 4, rw - 8, rh - 8);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}