(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // seven-segment digits: segments a..g as polygons in a 50x80 cell
  const SEG = {a:"6,2 44,2 38,9 12,9", b:"46,4 46,38 40,34 40,10", c:"46,42 46,76 40,70 40,46",
    d:"6,78 44,78 38,71 12,71", e:"4,42 10,46 10,70 4,76", f:"4,4 10,10 10,34 4,38", g:"8,40 13,35 37,35 42,40 37,45 13,45"};
  const MAP = {0:"abcdef",1:"bc",2:"abged",3:"abgcd",4:"fgbc",5:"afgcd",6:"afgedc",7:"abc",8:"abcdefg",9:"abcdfg"," ":""};
  const svg = document.getElementById("fare"), NS = "http://www.w3.org/2000/svg";
  const cells = [];
  for (let i = 0; i < 6; i++) {
    const g = document.createElementNS(NS, "g");
    g.setAttribute("transform", `translate(${i * 50 + (i >= 4 ? 10 : 0)},0)`);
    const segs = {};
    for (const k in SEG) { const p = document.createElementNS(NS, "polygon"); p.setAttribute("points", SEG[k]); p.setAttribute("class", "s"); g.appendChild(p); segs[k] = p; }
    svg.appendChild(g); cells.push(segs);
  }
  const dot = document.createElementNS(NS, "circle");
  dot.setAttribute("cx", 203); dot.setAttribute("cy", 74); dot.setAttribute("r", 5); dot.setAttribute("class", "on"); svg.appendChild(dot);
  function show(v) {
    const s = Math.round(v * 100).toString().padStart(3, "0").padStart(6, " ");
    s.split("").forEach((ch, i) => { const on = MAP[ch] || ""; for (const k in cells[i]) cells[i][k].setAttribute("class", on.includes(k) ? "on" : "s"); });
    svg.setAttribute("aria-label", "$" + v.toFixed(2));
  }
  const RATE = {linux: .006, windows: .010, macos: .062};
  const RIDES = [
    [["Docs", "linux", 50], ["CI › lint", "linux", 70], ["CI › test (ubuntu)", "linux", 350], ["CI › test (windows)", "windows", 490], ["E2E nightly", "linux", 784], ["CI › test (macos)", "macos", 490]],
    [["Lint", "linux", 120], ["Unit", "linux", 900], ["Build (win)", "windows", 300], ["iOS build", "macos", 640], ["Deploy", "linux", 60]],
    [["Docs", "linux", 40], ["Test matrix", "linux", 1800], ["Nightly fuzz", "linux", 2400], ["Release (mac)", "macos", 45]],
  ];
  const meter = document.getElementById("meter"), flag = document.getElementById("flagText");
  const minsEl = document.getElementById("mins"), wfEl = document.getElementById("wf");
  const tariffs = [...document.querySelectorAll(".tariffs span")];
  let ride = 0, timer = null;
  function light(sku) { tariffs.forEach(t => t.classList.toggle("lit", t.dataset.sku === sku)); }
  function finalState(r) {
    let c = 0, m = 0; r.forEach(([, s, n]) => { c += n * RATE[s]; m += n; });
    show(c); minsEl.value = m.toLocaleString("en"); wfEl.value = r[r.length - 1][0]; light(r[r.length - 1][1]);
    meter.classList.add("hired"); flag.textContent = "HIRED";
  }
  function run(r) {
    clearInterval(timer);
    if (reduce) return finalState(r);
    meter.classList.remove("hired"); flag.textContent = "FOR HIRE"; show(0); minsEl.value = "0"; wfEl.value = "—"; light(null);
    let cost = 0, mins = 0, leg = 0, left = 0;
    setTimeout(() => {
      meter.classList.add("hired"); flag.textContent = "HIRED";
      timer = setInterval(() => {
        if (left <= 0) {
          if (leg >= r.length) { clearInterval(timer); return; }
          left = r[leg][2]; wfEl.value = r[leg][0]; light(r[leg][1]); leg++;
        }
        const step = Math.min(left, 10), sku = r[leg - 1][1];
        left -= step; mins += step; cost += step * RATE[sku];
        show(cost); minsEl.value = mins.toLocaleString("en");
      }, 40);
    }, 700);
  }
  document.getElementById("again").addEventListener("click", () => { ride = (ride + 1) % RIDES.length; run(RIDES[ride]); });
  const io = "IntersectionObserver" in window ? IntersectionObserver : null;
  if (io) new io((es, o) => { if (es[0].isIntersecting) { run(RIDES[0]); o.disconnect(); } }, {threshold: .4}).observe(meter);
  else run(RIDES[0]);
  // receipt prints line by line
  const rc = document.getElementById("receipt");
  const spans = [...rc.querySelectorAll(".ln")];
  if (reduce || !io) spans.forEach(s => s.classList.add("shown"));
  else new io((es, o) => { if (!es[0].isIntersecting) return; o.disconnect(); spans.forEach((s, i) => setTimeout(() => s.classList.add("shown"), i * 70)); }, {threshold: .2}).observe(rc);
})();
