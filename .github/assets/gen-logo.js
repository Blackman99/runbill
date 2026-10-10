// Generates site/logo.svg, site/favicon.svg and docs/assets/logo.svg: three isometric cubes in layers.
// Run: node .github/assets/gen-logo.js
const fs = require("fs");
const PAL = { linux: ["#f7f6f2", "#dcdcd8", "#bcbdbd"], windows: ["#7a8693", "#626d79", "#4c5560"],
  macos: ["#1d3fbf", "#17329a", "#112676"], plaza: ["#b9bdc3", "#a5aab1", "#8e939b"] };
const A = 13.2, H = 13.2;              // cube edge (x/y units) and height, in output px
const OX = 32, OY = 26.2;               // origin offset so the drawing is centred in 64x64
const P = (x, y, z) => [OX + (x - y) * A, OY + (x + y) * A / 2 - z * H];
const f = (n) => +n.toFixed(2);
const poly = (pts, fill) => `<polygon points="${pts.map(p => P(...p).map(f).join(",")).join(" ")}" fill="${fill}"/>`;
function box(x, y, z, w, d, h, pal) {
  const X = x + w, Y = y + d, Z = z + h;
  return poly([[x, Y, z], [X, Y, z], [X, Y, Z], [x, Y, Z]], pal[1]) +
         poly([[X, y, z], [X, Y, z], [X, Y, Z], [X, y, Z]], pal[2]) +
         poly([[x, y, Z], [X, y, Z], [X, Y, Z], [x, Y, Z]], pal[0]);
}
const body = box(-0.16, -0.16, -0.22, 2.32, 2.32, 0.22, PAL.plaza) +
  box(0, 1, 0, 1, 1, 1, PAL.linux) + box(1, 0, 0, 1, 1, 1, PAL.windows) + box(0.5, 0.5, 1, 1, 1, 1, PAL.macos);
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="runbill">${body}</svg>\n`;
for (const p of ["site/logo.svg", "site/favicon.svg", "docs/assets/logo.svg"]) fs.writeFileSync(p, svg);
console.log(body);
