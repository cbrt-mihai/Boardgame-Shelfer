strokeW = 3
scaleFactor = 10

let result;
function preload() {
  result = loadStrings('output.txt');
}

function setup() {
  console.log(result)
}

function draw() {
  var cnt = 0;
  var name, len, hei, wid;
  
  for(let i = 0; i < result.length; i++) {
    console.log(cnt)
    if(result[i][0] == "#") {
      parts = result[i].split(",")
      name1 = name
      name = parts[0]
      len = parts[1]
      hei = parts[2]
      wid = parts[3]
      
      if(cnt > 0) {
        saveCanvas(name1, "png")
      }
      cnt++;

      createCanvas(len*scaleFactor+5, hei*scaleFactor+5);
      background(0);
    }
    else {
      parts = result[i].split(",")
      nameParts = parts[0].split("-")
      let name = nameParts[0] + " (" + nameParts[1] + ", " + nameParts[2] + ")"
      let x1 = float(parts[1]) * scaleFactor
      let y1 = float(parts[2]) * scaleFactor
      let x2 = float(parts[3]) * scaleFactor
      let y2 = float(parts[4]) * scaleFactor
      
      console.log(name,x1,y1,x2,y2)

      ny1 = height - y1
      ny2 = height - y2

      let randomCol = color(random(256),random(256),random(256))

      noFill()
      stroke(randomCol)
      strokeWeight(strokeW)
      rectMode(CORNERS)
      rect(x1, ny1, x2, ny2)

      textSize(14)
      stroke(0)
      strokeWeight(strokeW)
      fill(randomCol)
      rectMode(CORNERS)
      textWrap(CHAR);
      text(name, x1 + strokeW*2, ny2 + strokeW*2, x2-x1, height - y1+y2)
    }
  }
  saveCanvas(name, "png")
  noLoop();
}