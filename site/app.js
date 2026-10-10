(function () {
  "use strict";
  var I = window.Iso;
  if (!I) return;
  var reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  var IO = "IntersectionObserver" in window;
  // [job, runner, billed minutes, optional $/min for larger runners]
  var CITIES = [
    { name: "a monorepo", w: [
      { name: "CI", jobs: [["lint", "linux", 140], ["test (ubuntu)", "linux", 1050], ["test (windows)", "windows", 420]] },
      { name: "Fuzz nightly", jobs: [["libfuzzer", "linux", 1400]] },
      { name: "iOS", jobs: [["build", "macos", 180], ["ui-tests", "macos", 120]] },
      { name: "E2E", jobs: [["playwright", "linux", 310, 0.022]] },
      { name: "Release", jobs: [["package", "linux", 30], ["notarize", "macos", 24]] },
      { name: "Docs", jobs: [["build", "linux", 90]] }] },
    { name: "a mobile app", w: [
      { name: "Lint", jobs: [["lint", "linux", 120]] },
      { name: "Unit tests", jobs: [["unit", "linux", 900]] },
      { name: "iOS build", jobs: [["xcodebuild", "macos", 640]] },
      { name: "Windows build", jobs: [["msbuild", "windows", 300]] },
      { name: "Deploy", jobs: [["deploy", "linux", 60]] }] },
    { name: "a Linux-only library", w: [
      { name: "Docs", jobs: [["build", "linux", 40]] },
      { name: "Test matrix", jobs: [["py3.9-3.13", "linux", 1800]] },
      { name: "Nightly fuzz", jobs: [["fuzz", "linux", 2400]] },
      { name: "Release (mac)", jobs: [["wheels", "macos", 45]] }] }
  ];
  var DEMO = [
    { name: "CI", jobs: [["lint", "linux", 70], ["test (ubuntu)", "linux", 350], ["test (windows)", "windows", 490], ["test (macos)", "macos", 490]] },
    { name: "E2E nightly", jobs: [["playwright", "linux", 196, 0.022]] },
    { name: "Docs", jobs: [["build", "linux", 50]] },
    { name: "Release", jobs: [["publish", "linux", 9], ["sign", "self", 17]] }
  ];
  function fmtMin(n) { return Math.round(n).toLocaleString("en"); }

  // brick drop: fall with gravity, land, small bounce
  function drop(br, delay, dist, done) {
    var a = br.g.animate([
      { transform: "translateY(" + (-dist) + "px)", opacity: 0, easing: "cubic-bezier(.45,0,1,.6)" },
      { opacity: 1, offset: 0.2 },
      { transform: "translateY(0px)", offset: 0.74, easing: "cubic-bezier(0,.4,.5,1)" },
      { transform: "translateY(" + (-Math.min(5, 1 + br.h * 0.15)) + "px)", offset: 0.87, easing: "cubic-bezier(.5,0,1,.5)" },
      { transform: "translateY(0px)" }
    ], { duration: 640, delay: delay, fill: "backwards" });
    if (done) a.onfinish = done;
    return a;
  }
  function build(c, animate, onTick) {
    var anims = [];
    c.buildings.forEach(function (b, bi) {
      var n = b.bricks.length, per = n ? Math.min(85, 1700 / n) : 0, start = 150 + bi * 110;
      var run = 0;
      if (b.label) b.label.textContent = I.money(animate ? 0 : b.cost);
      var lift = function (z) { if (b.lblG) b.lblG.style.transform = "translateY(" + (b.top - z).toFixed(1) + "px)"; };
      if (!animate) return;
      lift(2);
      b.bricks.forEach(function (br, k) {
        anims.push(drop(br, start + k * per, 170 + br.z * 0.25, function () {
          run += br.cost;
          if (b.label) b.label.textContent = I.money(k === n - 1 ? b.cost : run);
          lift(br.z + br.h);
          if (onTick) onTick(br);
        }));
      });
    });
    return anims;
  }

  /* hero city */
  var svg = document.getElementById("city"), fig = svg.parentNode;
  var outMin = document.getElementById("cityMin"), outCost = document.getElementById("cityCost"), outName = document.getElementById("cityName");
  var cur = 0, hero = null, busy = false, lastW = 0;
  var sky = document.querySelector(".sky");
  function heroOpts(fs) {
    var w = svg.clientWidth || innerWidth, narrow = w < 700, n = CITIES[cur].w.length;
    return { cols: narrow ? Math.ceil(n / 2) : n, maxH: narrow ? 240 : 260, lot: 40, step: narrow ? 64 : 92, fs: fs || 13, margin: 6, plaza: false, setViewBox: false, footLabels: narrow };
  }
  function layoutHero() {
    var data = CITIES[cur].w, r = svg.getBoundingClientRect();
    var S = sky.getBoundingClientRect().bottom - r.top + 18, RH = Math.max(160, r.height - S);
    var c, fs = 13, scale = 1;
    for (var pass = 0; pass < 3; pass++) {
      c = I.city(svg, data, heroOpts(fs));
      var v = c.viewBox;
      scale = Math.min(r.width * 0.94 / v[2], RH / v[3], 1.8);
      var nfs = Math.max(10, Math.min(26, 13.5 / scale));
      if (Math.abs(nfs - fs) < 0.4) break;
      fs = nfs;
    }
    var v2 = c.viewBox, W = r.width / scale, H = r.height / scale;
    var vb = [v2[0] + v2[2] / 2 - W / 2, v2[1] + v2[3] - H + 8 / scale, W, H];
    svg.setAttribute("viewBox", vb.map(function (n) { return n.toFixed(1); }).join(" "));
    lastW = r.width;
    return c;
  }
  function totals(data) {
    return { min: data.reduce(function (s, w) { return s + I.minutes(w); }, 0), cost: data.reduce(function (s, w) { return s + I.cost(w); }, 0) };
  }
  function showHero(animate) {
    var data = CITIES[cur].w, t = totals(data);
    outName.textContent = CITIES[cur].name;
    hero = layoutHero();
    svg.setAttribute("aria-label", CITIES[cur].name + ": " + data.map(function (w) { return w.name + " " + I.money(I.cost(w)); }).join(", "));
    if (!animate) { outMin.value = fmtMin(t.min); outCost.value = I.money(t.cost); build(hero, false); return; }
    var m = 0, cst = 0;
    outMin.value = "0"; outCost.value = "$0.00";
    var anims = build(hero, true, function (br) { m += br.min; cst += br.cost; outMin.value = fmtMin(m); outCost.value = I.money(cst); });
    busy = true;
    Promise.all(anims.map(function (a) { return a.finished; })).then(function () { outMin.value = fmtMin(t.min); outCost.value = I.money(t.cost); busy = false; }, function () { busy = false; });
  }
  function knockDown(next) {
    if (reduce || !hero) return next();
    var anims = [];
    hero.buildings.forEach(function (b) {
      b.bricks.forEach(function (br) {
        anims.push(br.g.animate([{ transform: "translateY(0)", opacity: 1 }, { transform: "translateY(" + (180 + Math.random() * 120) + "px)", opacity: 0 }],
          { duration: 420, delay: Math.random() * 260 + (1 - br.z / 400) * 120, easing: "cubic-bezier(.5,0,1,.6)", fill: "forwards" }));
      });
    });
    svg.querySelectorAll(".lbl").forEach(function (l) { anims.push(l.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, fill: "forwards" })); });
    Promise.all(anims.map(function (a) { return a.finished; })).then(next, next);
  }
  document.getElementById("again").addEventListener("click", function () {
    if (busy && !reduce) return;
    busy = true;
    knockDown(function () { cur = (cur + 1) % CITIES.length; showHero(!reduce); if (reduce) busy = false; });
  });
  showHero(!reduce);
  var rt;
  addEventListener("resize", function () {
    clearTimeout(rt);
    rt = setTimeout(function () { if (Math.abs(svg.getBoundingClientRect().width - lastW) > 30) { hero && hero.buildings.forEach(function (b) { b.bricks.forEach(function (br) { br.g.getAnimations().forEach(function (a) { a.cancel(); }); }); }); busy = false; showHero(false); } if (tourCity) tourLayout(); }, 200);
  });

  /* survey: pinned scene, camera pans building to building */
  var tour = document.getElementById("tour"), tourCity = null, vbNow = null, active = -1, raf = 0;
  function tourLayout() {
    tourCity = I.city(tour, DEMO, { labels: false, cols: 4, maxH: 300, lot: 40, step: 74, margin: 14, minBrick: 2.2 });
    vbNow = null; aim(active, true);
  }
  function target(i) {
    var r = tour.getBoundingClientRect(), asp = (r.width / r.height) || 1.4, full = tourCity.viewBox;
    var cx, cy, w, h;
    if (i < 0) { cx = full[0] + full[2] / 2; cy = full[1] + full[3] / 2; w = full[2]; h = full[3]; }
    else {
      var b = tourCity.buildings[i], L = tourCity.lot;
      var left = I.P(b.x, b.y + L, 0)[0] - 26, right = I.P(b.x + L, b.y, 0)[0] + 26;
      var top = I.P(b.x, b.y, b.top)[1] - 30, bottom = I.P(b.x + L, b.y + L, 0)[1] + 26;
      cx = (left + right) / 2; cy = (top + bottom) / 2; w = Math.max(right - left, 260); h = Math.max(bottom - top, 190);
    }
    if (w / h < asp) w = h * asp; else h = w / asp;
    return [cx - w / 2, cy - h / 2, w, h];
  }
  function setVB(v) { vbNow = v; tour.setAttribute("viewBox", v.map(function (n) { return n.toFixed(1); }).join(" ")); }
  function aim(i, instant) {
    if (!tourCity) return;
    var to = target(i), from = vbNow;
    cancelAnimationFrame(raf);
    if (instant || reduce || !from) return setVB(to);
    var t0 = performance.now(), D = 900;
    (function step(now) {
      var p = Math.min(1, (now - t0) / D), e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
      setVB(from.map(function (f, k) { return f + (to[k] - f) * e; }));
      if (p < 1) raf = requestAnimationFrame(step);
    })(t0);
  }
  var stops = [].slice.call(document.querySelectorAll(".stop"));
  // build the survey scene only when it is about to scroll into view (keeps the first paint light)
  function lazy(el, fn) {
    if (!IO) return fn();
    new IntersectionObserver(function (es, o) { if (es[0].isIntersecting) { o.disconnect(); fn(); } }, { rootMargin: "600px 0px" }).observe(el);
  }
  lazy(tour, tourLayout);
  function activate(s) {
    stops.forEach(function (x) { x.classList.toggle("on", x === s); });
    active = +s.getAttribute("data-b"); if (tourCity) aim(active);
  }
  if (IO) {
    var io = new IntersectionObserver(function (es) { es.forEach(function (e) { if (e.isIntersecting) activate(e.target); }); }, { rootMargin: "-45% 0px -45% 0px" });
    stops.forEach(function (s) { io.observe(s); });
    if (!reduce) {
      new IntersectionObserver(function (es, o) { if (es[0].isIntersecting && tourCity) { o.disconnect(); build(tourCity, true); } }, { threshold: 0.3 }).observe(tour);
    }
  } else stops.forEach(function (s) { s.classList.add("on"); });

  /* brick conversion: ten billed minutes per runner, same scale */
  var conv = document.getElementById("conv");
  lazy(conv, function () {
  var RUN = [["linux", "Linux"], ["windows", "Windows"], ["macos", "macOS"]], K = 270 / 0.62, LOT = 46, S = 96, bb = [1e9, 1e9, -1e9, -1e9];
  var cg = I.el("g", {}, conv), convBricks = [];
  RUN.forEach(function (r, i) {
    var x = i * S, y = -i * S, h = I.RATE[r[0]] * K, z = 0;
    I.box(cg, x - 4, y - 4, 0, LOT + 8, LOT + 8, 2, I.PAL.lot, "pad", bb);
    for (var k = 0; k < 10; k++) {
      convBricks.push({ g: I.box(cg, x, y, 2 + z, LOT, LOT, Math.max(h - 0.7, 0.8), I.PAL[r[0]], "brick", bb), z: z, h: h, k: k });
      z += h;
    }
    var base = I.P(x + LOT, y + LOT, 0), mid = I.P(x + LOT / 2, y + LOT / 2, 0)[0], top = I.P(x + LOT / 2, y + LOT / 2, z + 2);
    var t1 = I.el("text", { x: mid, y: base[1] + 34, "text-anchor": "middle", "class": "big" }, cg); t1.textContent = r[1];
    var t2 = I.el("text", { x: mid, y: base[1] + 58, "text-anchor": "middle" }, cg); t2.textContent = "10 min";
    var t3 = I.el("text", { x: top[0], y: top[1] - LOT / 2 - 12, "text-anchor": "middle", "class": "usdt" }, cg); t3.textContent = I.money(10 * I.RATE[r[0]]);
    bb[3] = Math.max(bb[3], base[1] + 66); bb[1] = Math.min(bb[1], top[1] - LOT / 2 - 34);
  });
  conv.setAttribute("viewBox", [bb[0] - 60, bb[1], bb[2] - bb[0] + 120, bb[3] - bb[1]].map(function (n) { return n.toFixed(1); }).join(" "));
  if (IO && !reduce) {
    convBricks.forEach(function (b) { b.g.style.opacity = 0; });
    new IntersectionObserver(function (es, o) {
      if (!es[0].isIntersecting) return; o.disconnect();
      convBricks.forEach(function (b) { b.g.style.opacity = ""; drop(b, 100 + b.k * 140, 160 + b.z * 0.3); });
    }, { threshold: 0.35 }).observe(conv);
  }
  });
})();
