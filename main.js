/* Trans Bavaria Trail — interactions */
(() => {
  "use strict";

  /**
   * Where form submissions go. Set ONE of these:
   *  - formEndpoint: e.g. a Formspree URL ("https://formspree.io/f/xxxx") – submits in the background
   *  - email: fallback, opens the visitor's mail app with a prefilled message
   */
  const CONFIG = {
    formEndpoint: "",
    email: "",
  };

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

  /* ---------------- header + menu ---------------- */
  const header = $("#header");
  const toggle = $("#menu-toggle");
  const onScrollHeader = () => header.classList.toggle("is-scrolled", window.scrollY > 40);
  onScrollHeader();
  window.addEventListener("scroll", onScrollHeader, { passive: true });

  const setMenu = (open) => {
    document.body.classList.toggle("menu-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Menü schließen" : "Menü öffnen");
  };
  toggle.addEventListener("click", () => setMenu(!document.body.classList.contains("menu-open")));
  $$("#nav a").forEach((a) => a.addEventListener("click", () => setMenu(false)));
  document.addEventListener("keydown", (e) => e.key === "Escape" && setMenu(false));

  const navLinks = $$("#nav a");
  const sectionObs = new IntersectionObserver(
    (entries) =>
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        navLinks.forEach((a) => a.classList.toggle("is-active", a.getAttribute("href") === `#${en.target.id}`));
      }),
    { rootMargin: "-45% 0px -50% 0px" }
  );
  navLinks.forEach((a) => {
    const t = $(a.getAttribute("href"));
    if (t) sectionObs.observe(t);
  });

  /* ---------------- reveal + counters ---------------- */
  const countUp = (el) => {
    const target = Number(el.dataset.count);
    if (reduceMotion || !target) return;
    const from = target > 1000 ? target - 60 : 0;
    const t0 = performance.now();
    const dur = 1400;
    const step = (t) => {
      const p = clamp((t - t0) / dur, 0, 1);
      el.textContent = Math.round(from + (target - from) * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const revealObs = new IntersectionObserver(
    (entries) =>
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        en.target.classList.add("in");
        const c = $("[data-count]", en.target);
        if (c) countUp(c);
        revealObs.unobserve(en.target);
      }),
    { threshold: 0.15, rootMargin: "0px 0px -6% 0px" }
  );
  $$(".reveal").forEach((el) => revealObs.observe(el));

  /* ---------------- manifest: words light up while scrolling ---------------- */
  const manifest = $("#manifest");
  const words = [];
  if (manifest) {
    const frag = document.createDocumentFragment();
    manifest.childNodes.forEach((node) => {
      const cls = node.nodeType === 1 ? (node.hasAttribute("data-hl") ? "hl" : node.hasAttribute("data-am") ? "am" : "") : "";
      node.textContent
        .split(/\s+/)
        .filter(Boolean)
        .forEach((w) => {
          const s = document.createElement("span");
          s.className = `w ${cls}`.trim();
          s.setAttribute("aria-hidden", "true");
          s.textContent = w;
          words.push(s);
          frag.append(s, " ");
        });
    });
    manifest.replaceChildren(frag);
  }
  const updateManifest = () => {
    if (!words.length) return;
    const r = manifest.getBoundingClientRect();
    const vh = window.innerHeight;
    const p = clamp((vh * 0.85 - r.top) / (r.height + vh * 0.35), 0, 1);
    const n = reduceMotion ? words.length : Math.round(p * words.length);
    words.forEach((w, i) => w.classList.toggle("on", i < n));
  };

  /* ---------------- topographic contour background ---------------- */
  const topo = $("#topo");
  const drawTopo = () => {
    if (!topo) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = topo.clientWidth;
    const h = topo.clientHeight;
    topo.width = w * dpr;
    topo.height = h * dpr;
    const ctx = topo.getContext("2d");
    ctx.scale(dpr, dpr);

    // value noise
    const rand = (() => {
      let s = 2022;
      return () => ((s = (s * 16807) % 2147483647) / 2147483647);
    })();
    const G = 9;
    const grid = Array.from({ length: G + 2 }, () => Array.from({ length: G + 2 }, rand));
    const smooth = (t) => t * t * (3 - 2 * t);
    const noise = (x, y) => {
      const xi = Math.floor(x), yi = Math.floor(y);
      const xf = smooth(x - xi), yf = smooth(y - yi);
      const a = grid[yi][xi], b = grid[yi][xi + 1], c = grid[yi + 1][xi], d = grid[yi + 1][xi + 1];
      return a + (b - a) * xf + (c - a) * yf + (a - b - c + d) * xf * yf;
    };
    const field = (x, y) => {
      const u = (x / w) * (G - 2) * 0.55 + 1;
      const v = (y / h) * (G - 2) * 0.55 + 1;
      return noise(u, v) * 0.7 + noise(u * 1.9 + 0.3, v * 1.9 + 0.2) * 0.3;
    };

    const cell = 10;
    const cols = Math.ceil(w / cell) + 1;
    const rows = Math.ceil(h / cell) + 1;
    const vals = new Float32Array(cols * rows);
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) vals[j * cols + i] = field(i * cell, j * cell);

    const levels = 16;
    for (let l = 1; l < levels; l++) {
      const iso = 0.12 + (l / levels) * 0.8;
      const major = l % 4 === 0;
      ctx.strokeStyle = major ? "rgba(201,160,78,0.28)" : "rgba(216,230,243,0.10)";
      ctx.lineWidth = major ? 1.2 : 0.8;
      ctx.beginPath();
      for (let j = 0; j < rows - 1; j++) {
        for (let i = 0; i < cols - 1; i++) {
          const a = vals[j * cols + i], b = vals[j * cols + i + 1];
          const c = vals[(j + 1) * cols + i + 1], d = vals[(j + 1) * cols + i];
          const idx = (a > iso) | ((b > iso) << 1) | ((c > iso) << 2) | ((d > iso) << 3);
          if (idx === 0 || idx === 15) continue;
          const x = i * cell, y = j * cell;
          const lerp = (p, q) => (iso - p) / (q - p);
          const top = [x + cell * lerp(a, b), y];
          const right = [x + cell, y + cell * lerp(b, c)];
          const bottom = [x + cell * lerp(d, c), y + cell];
          const left = [x, y + cell * lerp(a, d)];
          const seg = {
            1: [left, top], 2: [top, right], 3: [left, right], 4: [right, bottom], 5: [left, top, right, bottom],
            6: [top, bottom], 7: [left, bottom], 8: [left, bottom], 9: [top, bottom], 10: [top, right, left, bottom],
            11: [right, bottom], 12: [left, right], 13: [top, right], 14: [left, top],
          }[idx];
          for (let k = 0; k < seg.length; k += 2) {
            ctx.moveTo(seg[k][0], seg[k][1]);
            ctx.lineTo(seg[k + 1][0], seg[k + 1][1]);
          }
        }
      }
      ctx.stroke();
    }
  };
  let topoW = 0;
  const maybeDrawTopo = () => {
    if (topo && topo.clientWidth !== topoW) {
      topoW = topo.clientWidth;
      drawTopo();
    }
  };
  maybeDrawTopo();
  window.addEventListener("resize", maybeDrawTopo);

  /* ---------------- hero: patch tilt, parallax, rider ---------------- */
  const hero = $(".hero");
  const tilt = $("#tilt");
  if (tilt && !reduceMotion && window.matchMedia("(pointer: fine)").matches) {
    hero.addEventListener("pointermove", (e) => {
      const r = tilt.getBoundingClientRect();
      const x = (e.clientX - (r.left + r.width / 2)) / r.width;
      const y = (e.clientY - (r.top + r.height / 2)) / r.height;
      tilt.style.transform = `rotateY(${clamp(x, -1, 1) * 12}deg) rotateX(${clamp(-y, -1, 1) * 10}deg)`;
    });
    hero.addEventListener("pointerleave", () => (tilt.style.transform = ""));
  }

  const layers = $$("#landscape .layer");
  const updateParallax = () => {
    if (reduceMotion) return;
    const y = window.scrollY;
    if (y > window.innerHeight * 1.2) return;
    layers.forEach((l) => (l.style.transform = `translateY(${y * Number(l.dataset.depth)}px)`));
    if (topo) topo.style.transform = `translateY(${y * 0.3}px)`;
  };

  const track = $("#hero-track");
  const rider = $("#rider");
  let heroVisible = true;
  new IntersectionObserver(([en]) => (heroVisible = en.isIntersecting)).observe(hero);
  if (track && rider) {
    const len = track.getTotalLength();
    const loop = 22000;
    const placeRider = (t) => {
      const p = (t % loop) / loop;
      const at = len * p;
      const pt = track.getPointAtLength(at);
      const ahead = track.getPointAtLength(Math.min(len, at + 4));
      const ang = (Math.atan2(ahead.y - pt.y, ahead.x - pt.x) * 180) / Math.PI;
      rider.setAttribute("transform", `translate(${pt.x.toFixed(1)} ${pt.y.toFixed(1)}) rotate(${ang.toFixed(1)})`);
    };
    if (reduceMotion) placeRider(loop * 0.55);
    else {
      const tick = (t) => {
        if (heroVisible) placeRider(t);
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }

  /* ---------------- route: map draws while scrolling through stages ---------------- */
  const line = $("#route-line");
  const stages = $$("#stages .stage");
  const pins = $$("#bayern-map .pin");
  const districts = $$("#bayern-map .district");
  const stageLabel = $("#map-stage");
  const districtLabel = $("#map-district");
  const pinAt = Object.fromEntries(pins.map((p) => [p.dataset.stop, Number(p.dataset.at)]));
  let routeLen = 0;
  let drawn = 0;
  let target = 0;

  if (line) {
    routeLen = line.getTotalLength();
    line.style.strokeDasharray = `${routeLen} ${routeLen}`;
    line.style.strokeDashoffset = routeLen;
  }

  const updateRoute = () => {
    if (!line || !stages.length) return;
    const mid = window.innerHeight * 0.55;
    let active = -1;
    let within = 0;
    stages.forEach((s, i) => {
      const r = s.getBoundingClientRect();
      if (r.top <= mid) {
        active = i;
        within = clamp((mid - r.top) / r.height, 0, 1);
      }
    });
    stages.forEach((s, i) => s.classList.toggle("is-active", i === active));
    if (active < 0) {
      target = 0;
    } else {
      const prev = active === 0 ? 0 : pinAt[stages[active - 1].dataset.until];
      const cur = pinAt[stages[active].dataset.until];
      target = prev + (cur - prev) * clamp(within * 1.6, 0, 1);
      const d = stages[active].dataset.district;
      districts.forEach((el) => el.classList.toggle("is-active", el.dataset.district === d));
      stageLabel.textContent = String(active + 1).padStart(2, "0");
      districtLabel.textContent = d;
    }
    if (reduceMotion) drawn = target;
  };

  const animateRoute = () => {
    drawn += (target - drawn) * 0.12;
    if (Math.abs(target - drawn) < 0.0005) drawn = target;
    line.style.strokeDashoffset = routeLen * (1 - drawn);
    pins.forEach((p) => p.classList.toggle("reached", Number(p.dataset.at) <= drawn + 0.002 && drawn > 0));
    requestAnimationFrame(animateRoute);
  };
  if (line) requestAnimationFrame(animateRoute);

  /* ---------------- BBS seal tilt ---------------- */
  const seal = $("#seal");
  if (seal && !reduceMotion && window.matchMedia("(pointer: fine)").matches) {
    seal.addEventListener("pointermove", (e) => {
      const r = seal.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5;
      const y = (e.clientY - r.top) / r.height - 0.5;
      seal.style.transform = `perspective(900px) rotateY(${x * 14}deg) rotateX(${-y * 14}deg)`;
    });
    seal.addEventListener("pointerleave", () => (seal.style.transform = ""));
  }

  /* ---------------- scroll loop ---------------- */
  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      updateParallax();
      updateManifest();
      updateRoute();
      ticking = false;
    });
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  onScroll();

  /* ---------------- forms ---------------- */
  const SUBJECTS = { scout: "Scout-Liste: Eintrag", tipp: "Brauerei-Tipp" };
  $$("form[data-form]").forEach((form) => {
    const status = $(".form-status", form);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (form._gotcha && form._gotcha.value) return;
      const invalid = $$("[required]", form).find((f) => !f.value.trim() || (f.type === "email" && !f.checkValidity()));
      if (invalid) {
        status.textContent = invalid.type === "email" ? "Bitte eine gültige E-Mail-Adresse eingeben." : "Bitte die Pflichtfelder ausfüllen.";
        invalid.focus();
        return;
      }
      const data = Object.fromEntries(new FormData(form));
      delete data._gotcha;
      const kind = form.dataset.form;

      if (CONFIG.formEndpoint) {
        status.textContent = "Wird gesendet …";
        try {
          const res = await fetch(CONFIG.formEndpoint, {
            method: "POST",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({ _subject: SUBJECTS[kind], formular: kind, ...data }),
          });
          if (!res.ok) throw new Error(res.status);
          form.reset();
          status.textContent = kind === "scout" ? "Du bist auf der Scout-Liste. Prost!" : "Danke! Dein Tipp ist bei der Crew gelandet.";
        } catch {
          status.textContent = "Das hat nicht geklappt. Bitte versuch es später noch einmal.";
        }
        return;
      }

      if (CONFIG.email) {
        const body = Object.entries(data)
          .filter(([, v]) => v)
          .map(([k, v]) => `${k}: ${v}`)
          .join("\n");
        window.location.href = `mailto:${CONFIG.email}?subject=${encodeURIComponent(SUBJECTS[kind])}&body=${encodeURIComponent(body)}`;
        status.textContent = "Dein Mailprogramm öffnet sich – einfach absenden.";
        return;
      }

      status.textContent = "Das Formular ist noch nicht freigeschaltet – schau bald wieder vorbei.";
    });
  });
})();
