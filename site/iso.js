/* runbill isometric city: tiny projection + city builder. No dependencies. */
(function (root) {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  // three flat faces per material: [top, left (+y face), right (+x face)]
  var PAL = {
    linux: ["#f7f6f2", "#dcdcd8", "#bcbdbd"],
    windows: ["#7a8693", "#626d79", "#4c5560"],
    macos: ["#1d3fbf", "#17329a", "#112676"],
    plaza: ["#b9bdc3", "#a5aab1", "#8e939b"],
    lot: ["#aeb2b9", "#999ea6", "#868b93"]
  };
  var RATE = { linux: 0.006, windows: 0.010, macos: 0.062, self: 0 };
  // 2:1 isometric: x runs right-down, y runs left-down, z up
  function P(x, y, z) { return [x - y, (x + y) / 2 - z]; }
  var I_P = P;
  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function pts(list, bb) {
    return list.map(function (p) {
      var s = P(p[0], p[1], p[2]);
      if (bb) { bb[0] = Math.min(bb[0], s[0]); bb[1] = Math.min(bb[1], s[1]); bb[2] = Math.max(bb[2], s[0]); bb[3] = Math.max(bb[3], s[1]); }
      return s[0].toFixed(2) + "," + s[1].toFixed(2);
    }).join(" ");
  }
  function box(parent, x, y, z, w, d, h, pal, cls, bb) {
    var g = el("g", cls ? { "class": cls } : {}, parent);
    var X = x + w, Y = y + d, Z = z + h;
    el("polygon", { points: pts([[x, Y, z], [X, Y, z], [X, Y, Z], [x, Y, Z]], bb), fill: pal[1] }, g);
    el("polygon", { points: pts([[X, y, z], [X, Y, z], [X, Y, Z], [X, y, Z]], bb), fill: pal[2] }, g);
    el("polygon", { points: pts([[x, y, Z], [X, y, Z], [X, Y, Z], [x, Y, Z]], bb), fill: pal[0] }, g);
    return g;
  }
  function jobRate(j) { return j[3] != null ? j[3] : RATE[j[1]]; }
  function cost(w) { return w.jobs.reduce(function (s, j) { return s + j[2] * jobRate(j); }, 0); }
  function minutes(w) { return w.jobs.reduce(function (s, j) { return s + j[2]; }, 0); }
  function money(v) { return "$" + v.toFixed(2); }

  /* city(svg, workflows, opts) -> {buildings, viewBox, K, M}
     opts: cols (lots per row), lot (footprint), step (lot pitch), maxH (tallest building), minBrick,
           labels (bool), fs (label font size, user units), plaza (bool) */
  function city(svg, data, o) {
    o = o || {};
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var lot = o.lot || 40, step = o.step || 66, maxH = o.maxH || 300, cols = o.cols || data.length;
    var fs = o.fs || 13, bb = [1e9, 1e9, -1e9, -1e9];
    var maxCost = Math.max.apply(null, data.map(cost)) || 1;
    var K = maxH / maxCost;                       // user units per dollar, shared by every building
    var M = [5, 10, 20, 25, 50, 100, 200, 500].find(function (m) { return m * RATE.linux * K >= (o.minBrick || 2.6); }) || 1000;
    var B = data.map(function (w, i) {
      var c = i % cols, r = Math.floor(i / cols);
      var stag = (cols > 3 && c % 2) ? step * 0.42 : 0;   // stagger alternate lots back/forth
      var x = c * step + stag + r * step * 1.15, y = -c * step + stag + r * step * 0.15;  // later rows interleave in front
      return { w: w, i: i, r: r, x: x, y: y, cost: cost(w), min: minutes(w) };
    });
    var order = B.slice().sort(function (a, b) { return (a.x + a.y) - (b.x + b.y); });
    var scene = el("g", { "class": "scene" }, svg);
    if (o.plaza !== false) {
      var xs = B.map(function (b) { return b.x; }), ys = B.map(function (b) { return b.y; });
      var pad = step * 0.55;
      var x0 = Math.min.apply(null, xs) - pad, y0 = Math.min.apply(null, ys) - pad;
      var x1 = Math.max.apply(null, xs) + lot + pad, y1 = Math.max.apply(null, ys) + lot + pad;
      box(scene, x0, y0, -12, x1 - x0, y1 - y0, 12, PAL.plaza, "plaza", bb);
    }
    order.forEach(function (b) {
      var g = el("g", { "class": "bldg", "data-i": b.i }, scene);
      box(g, b.x - 4, b.y - 4, 0, lot + 8, lot + 8, 2, PAL.lot, "pad", bb);
      var z = 2, bricks = [];
      b.w.jobs.forEach(function (j) {
        var left = j[2], r = jobRate(j), sku = j[1] === "self" ? "linux" : j[1];
        while (left > 0) {
          var m = Math.min(M, left), h = m * r * K;
          left -= m;
          if (h <= 0) continue;
          var bg = box(g, b.x, b.y, z, lot, lot, Math.max(h - (h > 3 ? 0.7 : 0), 0.6), PAL[sku], "brick " + sku, bb);
          bricks.push({ g: bg, cost: m * r, min: m, z: z, h: h });
          z += h;
        }
      });
      b.g = g; b.bricks = bricks; b.top = z;
      var c = P(b.x + lot / 2, b.y + lot / 2, z);
      b.anchor = c;
      b.foot = P(b.x + lot, b.y + lot, 0);
    });
    if (o.labels !== false) {
      var lg = el("g", { "class": "labels" }, scene), placed = [];
      var cw = 0.62 * fs;   // Red Hat Mono advance ~0.6em
      order.slice().sort(function (a, b) { return b.anchor[1] - a.anchor[1]; }).forEach(function (b) {
        var roof = b.anchor[1] - lot * 0.25;
        var w = Math.max(b.w.name.length * cw, 7 * cw * 1.25) + fs * 0.8, hgt = fs * 2.9;
        var y = roof - fs * 1.1, x = b.anchor[0], moved = false, guard = 0;
        var foot = o.footLabels && b.r > 0;
        if (foot) { y = I_P(b.x + lot, b.y + lot, 0)[1] + fs * 3.6; roof = y; }
        var hit = function () {
          return placed.find(function (p) { return Math.abs(p.x - x) < (p.w + w) / 2 && y > p.y - p.h - fs * 0.2 && y - hgt < p.y + fs * 0.2; });
        };
        var h;
        while (!foot && (h = hit()) && guard++ < 20) { y = h.y - h.h - fs * 0.5; moved = true; }
        placed.push({ x: x, y: y, w: w, h: hgt });
        var t = el("g", { "class": "lbl" }, lg);
        if (moved) el("line", { x1: x, y1: roof - 2, x2: x, y2: (y + fs * 0.35).toFixed(1), "class": "lead" }, t);
        var v = el("text", { "class": "lbl-v", x: x.toFixed(1), y: y.toFixed(1), "text-anchor": "middle", "font-size": (fs * 1.25).toFixed(1) }, t);
        v.textContent = money(b.cost);
        var n = el("text", { "class": "lbl-n", x: x.toFixed(1), y: (y - fs * 1.45).toFixed(1), "text-anchor": "middle", "font-size": fs.toFixed(1) }, t);
        n.textContent = b.w.name;
        b.label = v; b.lblG = t;
        bb[1] = Math.min(bb[1], y - hgt); bb[3] = Math.max(bb[3], y + fs * 0.5); bb[0] = Math.min(bb[0], x - w / 2); bb[2] = Math.max(bb[2], x + w / 2);
      });
    }
    var m = o.margin == null ? 8 : o.margin;
    var vb = [bb[0] - m, bb[1] - m, bb[2] - bb[0] + 2 * m, bb[3] - bb[1] + 2 * m];
    if (o.setViewBox !== false) svg.setAttribute("viewBox", vb.map(function (n) { return n.toFixed(1); }).join(" "));
    return { buildings: B, viewBox: vb, K: K, M: M, lot: lot };
  }
  root.Iso = { P: P, el: el, box: box, city: city, cost: cost, minutes: minutes, money: money, PAL: PAL, RATE: RATE, NS: NS };
})(window);
