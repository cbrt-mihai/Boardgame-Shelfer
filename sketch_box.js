const strokeW = 2;
const scaleFactor = 10;

let result;

async function setup() {
  noLoop();
  result = await loadStrings("output.txt");
  if (!result || !Array.isArray(result)) return;

  let bins = parseOutput(result);

  // Calculate total canvas height across all bins
  let totalHeight = 0;
  let maxWidth = 0;

  for (let bin of bins) {
    let topWidth = bin.length * scaleFactor;
    let frontWidth = bin.length * scaleFactor;
    let topHeight = bin.width * scaleFactor;
    let frontHeight = bin.height * scaleFactor;
    let sideHeight = bin.height * scaleFactor;

    let binW = max(topWidth + 80, frontWidth * 2 + 120);
    let binH = topHeight + frontHeight + sideHeight + 200;

    maxWidth = max(maxWidth, binW);
    totalHeight += binH;
  }

  createCanvas(maxWidth, totalHeight);
  background(0);

  let currentY = 0;
  for (let bin of bins) {
    drawBin(bin, currentY);
    currentY += (bin.width + bin.height * 2) * scaleFactor + 200;
  }
}


function parseOutput(lines) {
  let bins = [];
  let currentBin = null;

  for (let row of lines) {
    row = row.trim();

    if (row === "") {
      continue;
    }

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
    }
    else {
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

function drawBin(bin, startY) {
  let margin = 40;
  let topWidth = bin.length * scaleFactor;
  let topHeight = bin.width * scaleFactor;
  let frontWidth = bin.length * scaleFactor;
  let frontHeight = bin.height * scaleFactor;
  let sideWidth = bin.width * scaleFactor;
  let sideHeight = bin.height * scaleFactor;

  let canvasWidth = width;

  textAlign(CENTER, CENTER);
  textSize(20);
  fill(255);
  noStroke();

  text(bin.name, canvasWidth / 2, startY + 20);

  let topX = (canvasWidth - topWidth) / 2;
  let topY = startY + 50;

  drawTopView(bin, topX, topY);

  let frontY = topY + topHeight + margin * 2;
  let frontX = canvasWidth / 2 - frontWidth - margin / 2;
  drawFrontView(bin, frontX, frontY);

  let backX = canvasWidth / 2 + margin / 2;
  drawBackView(bin, backX, frontY);

  let sideY = frontY + frontHeight + margin * 2;
  let leftX = canvasWidth / 2 - sideWidth - margin / 2;
  drawLeftView(bin, leftX, sideY);

  let rightX = canvasWidth / 2 + margin / 2;
  drawRightView(bin, rightX, sideY);
}


  // -------------------------
  // TOP
  // -------------------------

  let topX = (canvasWidth - topWidth) / 2;
  let topY = 50;

  drawTopView(bin, topX, topY);


  // -------------------------
  // FRONT
  // -------------------------

  let frontY =
    topY +
    topHeight +
    margin * 2;

  let frontX =
    canvasWidth / 2 -
    frontWidth -
    margin / 2;

  drawFrontView(
    bin,
    frontX,
    frontY
  );


  // -------------------------
  // BACK
  // -------------------------

  let backX =
    canvasWidth / 2 +
    margin / 2;

  drawBackView(
    bin,
    backX,
    frontY
  );


  // -------------------------
  // LEFT
  // -------------------------

  let sideY =
    frontY +
    frontHeight +
    margin * 2;

  let leftX =
    canvasWidth / 2 -
    sideWidth -
    margin / 2;

  drawLeftView(
    bin,
    leftX,
    sideY
  );


  // -------------------------
  // RIGHT
  // -------------------------

  let rightX =
    canvasWidth / 2 +
    margin / 2;

  drawRightView(
    bin,
    rightX,
    sideY
  );
}

function drawTopView(bin, ox, oy) {

  let w = bin.length * scaleFactor;
  let h = bin.width * scaleFactor;

  drawViewLabel("TOP", ox + w / 2, oy - 15);

  // Bin boundary
  noFill();
  stroke(255);
  strokeWeight(strokeW);

  rect(
    ox,
    oy,
    w,
    h
  );

  for (let item of bin.items) {

    let x1 = ox + item.x1 * scaleFactor;
    let x2 = ox + item.x2 * scaleFactor;

    let y1 = oy + item.z1 * scaleFactor;
    let y2 = oy + item.z2 * scaleFactor;

    drawItem(
      item,
      x1,
      y1,
      x2,
      y2
    );
  }
}

function drawFrontView(bin, ox, oy) {

  let w = bin.length * scaleFactor;
  let h = bin.height * scaleFactor;

  drawViewLabel(
    "FRONT",
    ox + w / 2,
    oy - 15
  );

  noFill();
  stroke(255);
  strokeWeight(strokeW);

  rect(
    ox,
    oy,
    w,
    h
  );

  for (let item of bin.items) {

    let x1 = ox + item.x1 * scaleFactor;
    let x2 = ox + item.x2 * scaleFactor;

    let y1 =
      oy +
      h -
      item.y2 * scaleFactor;

    let y2 =
      oy +
      h -
      item.y1 * scaleFactor;

    drawItem(
      item,
      x1,
      y1,
      x2,
      y2
    );
  }
}

function drawBackView(bin, ox, oy) {

  let w = bin.length * scaleFactor;
  let h = bin.height * scaleFactor;

  drawViewLabel(
    "BACK",
    ox + w / 2,
    oy - 15
  );

  noFill();
  stroke(255);
  strokeWeight(strokeW);

  rect(
    ox,
    oy,
    w,
    h
  );

  for (let item of bin.items) {

    let x1 =
      ox +
      w -
      item.x2 * scaleFactor;

    let x2 =
      ox +
      w -
      item.x1 * scaleFactor;

    let y1 =
      oy +
      h -
      item.y2 * scaleFactor;

    let y2 =
      oy +
      h -
      item.y1 * scaleFactor;

    drawItem(
      item,
      x1,
      y1,
      x2,
      y2
    );
  }
}

function drawLeftView(bin, ox, oy) {

  let w = bin.width * scaleFactor;
  let h = bin.height * scaleFactor;

  drawViewLabel(
    "LEFT",
    ox + w / 2,
    oy - 15
  );

  noFill();
  stroke(255);
  strokeWeight(strokeW);

  rect(
    ox,
    oy,
    w,
    h
  );

  for (let item of bin.items) {

    let x1 =
      ox +
      item.z1 * scaleFactor;

    let x2 =
      ox +
      item.z2 * scaleFactor;

    let y1 =
      oy +
      h -
      item.y2 * scaleFactor;

    let y2 =
      oy +
      h -
      item.y1 * scaleFactor;

    drawItem(
      item,
      x1,
      y1,
      x2,
      y2
    );
  }
}

function drawRightView(bin, ox, oy) {

  let w = bin.width * scaleFactor;
  let h = bin.height * scaleFactor;

  drawViewLabel(
    "RIGHT",
    ox + w / 2,
    oy - 15
  );

  noFill();
  stroke(255);
  strokeWeight(strokeW);

  rect(
    ox,
    oy,
    w,
    h
  );

  for (let item of bin.items) {

    let x1 =
      ox +
      w -
      item.z2 * scaleFactor;

    let x2 =
      ox +
      w -
      item.z1 * scaleFactor;

    let y1 =
      oy +
      h -
      item.y2 * scaleFactor;

    let y2 =
      oy +
      h -
      item.y1 * scaleFactor;

    drawItem(
      item,
      x1,
      y1,
      x2,
      y2
    );
  }
}

function drawViewLabel(label, x, y) {

  noStroke();
  fill(255);

  textSize(16);
  textAlign(CENTER, CENTER);

  text(label, x, y);
}


function drawItem(item, x1, y1, x2, y2) {

  // Generate a deterministic colour from the item name
  let hash = 0;

  for (let i = 0; i < item.name.length; i++) {
    hash =
      ((hash << 5) - hash) +
      item.name.charCodeAt(i);

    hash |= 0;
  }

  let r = abs(hash) % 256;
  let g = abs(hash * 17) % 256;
  let b = abs(hash * 31) % 256;

  let c = color(r, g, b);

  noFill();
  stroke(c);
  strokeWeight(strokeW);

  rectMode(CORNERS);

  rect(
    x1,
    y1,
    x2,
    y2
  );

  // Label
  noStroke();
  fill(c);

  textSize(12);
  textAlign(LEFT, TOP);

  let label =
    item.name +
    " (" +
    nf(item.x2 - item.x1, 0, 1) +
    ", " +
    nf(item.y2 - item.y1, 0, 1) +
    ", " +
    nf(item.z2 - item.z1, 0, 1) +
    ")";

  text(
    label,
    min(x1, x2) + 4,
    min(y1, y2) + 4,
    abs(x2 - x1) - 8,
    abs(y2 - y1) - 8
  );
}