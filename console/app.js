/* Faculty review console. Loads precomputed results (data/cases.json); no model calls.
 * Decisions and the audit log live in this browser (localStorage) and can be exported. */
"use strict";

(() => {
  const STORE_KEY = "acadza-console-v1";
  const INITIAL = { decide: "pending", auto: "applied", reply: "pending" };
  const SECTIONS = [
    ["decide", "Needs your decision"],
    ["auto", "Applied automatically"],
    ["reply", "No change (reply only)"],
  ];
  const STATUS_TEXT = {
    pending: "Needs decision", applied: "Applied automatically", approved: "Fix approved",
    edited: "Fix edited and approved", rejected: "Fix rejected", kept: "Kept as is",
    reverted: "Fix reverted", reply_approved: "Reply approved", reply_edited: "Reply edited",
    sent: "Sent to content team", fix_written: "Fix written", dismissed: "Report dismissed",
    flagged: "Flagged as defect",
  };
  // Every button says exactly what will happen: [label, resulting status, toast].
  const KINDS = {
    fix: { primary: "approve", approve: ["Approve fix", "approved", "Fix approved"],
      edit: ["Edit fix", "edited", "Fix edited and approved"], reject: ["Reject fix", "rejected", "Fix rejected"] },
    auto: { primary: "approve", approve: ["Keep as is", "kept", "Kept as is"],
      edit: ["Edit fix", "edited", "Fix edited and approved"], reject: ["Revert fix", "reverted", "Fix reverted"] },
    nofix: { primary: "edit", approve: ["Mark as sent to content team", "sent", "Sent to content team"],
      edit: ["Write fix", "fix_written", "Fix written"], reject: ["Dismiss report", "dismissed", "Report dismissed"] },
    reply: { primary: "approve", approve: ["Approve reply", "reply_approved", "Reply approved"],
      edit: ["Edit reply", "reply_edited", "Reply edited and approved"], reject: ["Flag as defect", "flagged", "Flagged as defect"] },
  };
  const kindOf = (c) => (c.section === "reply" ? "reply" : c.section === "auto" ? "auto" : c.edit ? "fix" : "nofix");
  const ORDER_NOTE = "Ordered by harm to students: wrong answer keys first, then questions students " +
    "can't solve, wrong solutions, cosmetic, then filing. More reports go higher.";
  const ROUTE_TEXT = {
    decide: null,
    auto: "Applied automatically. Keep it as is, or revert it.",
    reply: "No change to the question. Check the reply.",
  };
  const FACULTY_TODO = {
    option_repair: "Write the missing option. Nothing in the data shows what it was.",
    identical_options: "Write a new distractor for one of the identical options.",
    unsound: "Re-author the options or the statement so exactly one option is correct.",
    diagram: "Add the missing figure, or rewrite the question so it needs none.",
    wrong_chapter: "Move the question to the chapter named in the evidence.",
    syllabus: "Decide whether the question stays in the NEET bank. It stays live meanwhile.",
    stem_data: "Add the missing value to the question.",
    answer_key: "Check the key by hand. The solvers did not agree.",
  };
  const PURIFY = {
    USE_PROFILES: { html: true, mathMl: true },
    FORBID_ATTR: ["style", "class", "id"],
    FORBID_TAGS: ["style", "form", "input", "button"],
  };

  let cases = [];
  let current = -1;
  let editing = false;
  let store = load();

  /* ---------- storage (works without it; private windows can throw) ---------- */
  function load() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORE_KEY));
      if (raw && raw.cases && Array.isArray(raw.audit)) return { undo: [], ...raw };
    } catch (_) { /* fall through to a fresh store */ }
    return { cases: {}, audit: [], undo: [] };
  }
  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); } catch (_) { /* not persisted */ }
  }

  /* ---------- helpers ---------- */
  const $ = (id) => document.getElementById(id);
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === false || v == null) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
    return el;
  }
  function rich(html, cls) {
    const el = h("div", { class: cls || "content" });
    el.innerHTML = DOMPurify.sanitize(html || "", PURIFY); // sanitised: MathML kept, styles dropped
    return el;
  }
  const fmtTime = (iso) => new Date(iso).toLocaleString("en-IN", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  });
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const caseState = (c) => store.cases[c.id] || { status: INITIAL[c.section], history: [] };
  const status = (c) => caseState(c).status;
  const statusText = (c) => (c.section === "reply" && isOpen(c) ? "Reply to check" : STATUS_TEXT[status(c)]);
  const isOpen = (c) => status(c) === INITIAL[c.section];

  /* ---------- top bar ---------- */
  function renderTop(meta) {
    const done = cases.filter((c) => !isOpen(c)).length;
    $("progress").textContent = `Reviewed ${done} of ${cases.length} questions`;
    if (meta) {
      const day = new Date(meta.generated_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
      $("source").textContent = `Precomputed results from ${day}. Opening this page makes no AI calls.`;
    }
  }

  /* ---------- queue ---------- */
  function renderQueue() {
    const nav = $("queue");
    nav.replaceChildren(h("p", { class: "q-order" }, ORDER_NOTE));
    for (const [key, title] of SECTIONS) {
      const items = cases.filter((c) => c.section === key);
      if (!items.length) continue;
      const open = items.filter(isOpen).length;
      const list = h("ol", {});
      for (const c of items) list.append(queueItem(c));
      nav.append(h("section", { class: "q-section", "aria-label": title },
        h("h2", {}, title, h("span", { class: "num" }, `${open} of ${items.length} open`)), list));
    }
  }
  function queueItem(c) {
    const idx = cases.indexOf(c);
    const st = status(c);
    const row = h("button", {
      type: "button", class: "q-row", "aria-current": idx === current ? "true" : "false",
      onclick: () => select(idx),
    },
      h("span", { class: "q-line" },
        h("span", { class: c.urgent ? "label urgent" : "label" }, c.problem),
        h("span", { class: "q-count" }, plural(c.reports.length, "report"))),
      h("span", { class: "q-sub" }, `${c.subject} / ${c.chapter}`),
      h("span", { class: isOpen(c) ? "q-status" : "q-status done" }, statusText(c)));
    const item = h("li", { class: "q-item" }, row);
    if (c.section === "auto" && st === "applied") {
      item.classList.add("has-undo");
      item.append(h("button", {
        type: "button", class: "q-undo", "aria-label": `Revert fix: ${c.problem}`,
        onclick: (e) => { e.stopPropagation(); current = idx; act("reject"); },
      }, "Undo"));
    }
    return item;
  }

  /* ---------- middle: question and diff ---------- */
  function inlineDiff(before, after) {
    const box = h("div", { class: "diff-inline" });
    const parts = Diff.diffWords(before, after);
    const CTX = 70;
    parts.forEach((p, i) => {
      if (p.added) return box.append(h("ins", { class: "add" }, p.value));
      if (p.removed) return box.append(h("del", { class: "rm" }, p.value));
      const first = i === 0, last = i === parts.length - 1;
      let v = p.value;
      if (first && v.length > CTX) v = "… " + v.slice(-CTX);
      else if (last && v.length > CTX) v = v.slice(0, CTX) + " …";
      else if (!first && !last && v.length > 2 * CTX) {
        box.append(v.slice(0, CTX), h("span", { class: "gap" }, " … "));
        v = v.slice(-CTX);
      }
      box.append(v);
    });
    return box;
  }
  function changeBlock(c, edits) {
    const ch = c.change;
    const title = c.section === "auto" ? "Change applied automatically" : "Proposed change";
    const block = h("section", { class: "block" }, h("h2", {}, title));
    if (ch.kind === "fields") {
      const dl = h("dl", { class: "diff-fields" });
      ch.lines.forEach((ln, i) => {
        const after = i === 0 && edits.replace != null ? edits.replace : ln.after;
        dl.append(h("dt", {}, ln.label),
          h("dd", {}, h("del", { class: "rm" }, ln.before), h("span", { class: "arrow", "aria-label": "changes to" }, " → "),
            h("ins", { class: "add" }, after)));
      });
      block.append(dl);
      return block;
    }
    const where = ch.field === "solution" ? "In the stored solution" : "In the question text";
    block.append(h("p", { class: "hint" }, where));
    if (edits.replace != null) {
      block.append(h("p", { class: "hint" }, "Your edit is shown below the original proposal."));
    }
    if (ch.layout === "side") {
      block.append(h("div", { class: "diff-side" },
        h("section", { class: "side-before" }, h("h3", { class: "side-title" }, "Before (removed)"), rich(ch.before_html)),
        h("section", { class: "side-after" }, h("h3", { class: "side-title" }, "After (added)"),
          rich(edits.replace != null ? ch.before_html.replace(ch.find, edits.replace) : ch.after_html))));
    } else {
      block.append(inlineDiff(ch.before_text, ch.after_text));
      if (edits.replace != null) block.append(h("div", { class: "editor" }, h("label", {}, "Your version"), rich(edits.replace, "preview content")));
    }
    block.append(h("details", { class: "raw" }, h("summary", {}, "Exact change in the stored HTML"),
      h("pre", {}, `find:    ${ch.find}\nreplace: ${edits.replace != null ? edits.replace : ch.replace}`)));
    return block;
  }
  function noChangeBlock(c, st) {
    if (c.section === "reply") {
      return h("section", { class: "block" }, h("h2", {}, "No change to the question"),
        h("p", { class: "no-edit" }, "The report did not find a defect in the stored question. Only the student reply goes out."));
    }
    return h("section", { class: "block" }, h("h2", {}, "No automatic fix"),
      h("p", { class: "no-edit" }, FACULTY_TODO[c.repair] || "Needs a faculty decision; see the evidence."),
      st.fix ? h("div", { class: "block" }, h("h2", {}, "Your fix for the content team"), h("p", { class: "no-edit" }, st.fix)) : null);
  }
  function renderCase(c) {
    const art = $("case");
    art.replaceChildren();
    art.scrollTop = 0;
    const st = caseState(c);
    art.append(
      h("p", { class: "case-meta" }, h("span", {}, c.qtype), c.level ? h("span", {}, c.level[0] + c.level.slice(1).toLowerCase()) : null,
        h("span", { class: "mono" }, `ID ${c.id}`)),
      h("h2", { class: "case-title" }, `${c.subject} / ${c.chapter}`),
      h("section", { class: "block" }, h("h2", {}, "Question as students see it now"), rich(c.question_html),
        h("p", { class: "stored-answer" }, "Stored answer: ", h("span", { class: "mono" }, c.answer))),
      c.change ? changeBlock(c, { replace: st.replace }) : noChangeBlock(c, st),
    );
    if (editing && editTarget(c) === "change") art.append(changeEditor(c));
    if (editing && editTarget(c) === "fix") art.append(fixEditor(c));
    if (!(c.change && c.change.field === "solution")) {
      art.append(h("section", { class: "block" },
        h("details", { class: "solution" }, h("summary", {}, "Stored solution"), rich(c.solution_html))));
    }
  }

  /* ---------- right: decision ---------- */
  function renderDecision(c) {
    const body = $("decision-body");
    body.replaceChildren();
    body.scrollTop = 0;
    const st = caseState(c);
    const agree = c.checks.filter((k) => k.agrees).length;
    const routeLine = isOpen(c) ? ROUTE_TEXT[c.section] : `${STATUS_TEXT[st.status]}.`;
    body.append(
      h("section", {},
        h("h2", {}, c.problem),
        routeLine ? h("p", { class: "route" }, routeLine) : null),
      h("section", {},
        h("h3", {}, "Confidence"),
        h("p", { class: "confidence" }, h("span", { class: "num" }, c.confidence.toFixed(2)),
          h("span", { class: "agree" }, `${agree} of ${c.checks.length} checks agree`)),
        h("ul", { class: "checks" }, c.checks.map((k) => h("li", { class: k.agrees ? "" : "disagree" },
          h("span", { class: "mark", "aria-label": k.agrees ? "agrees" : "disagrees" }, k.agrees ? "✓" : "✗"),
          h("span", {}, k.check))))),
      h("section", {}, h("h3", {}, "Evidence"), h("p", { class: "evidence" }, c.evidence),
        c.guard_notes.length ? h("p", { class: "guard" }, `Safety guard: ${c.guard_notes.join("; ")}`) : null),
      h("section", {}, h("h3", {}, `Student ${c.reports.length === 1 ? "report" : "reports"} and ${c.reports.length === 1 ? "reply" : "replies"}`),
        h("div", { class: "reports" }, c.reports.map((r) => reportView(r, st)))),
    );
    const k = KINDS[kindOf(c)];
    $("actionbar").replaceChildren(
      ...[k.primary, ...["approve", "edit", "reject"].filter((a) => a !== k.primary)].map((a) => h("button", {
        type: "button", class: a === k.primary ? "btn-primary" : "btn", "data-action": a,
      }, `${k[a][0]} `, h("kbd", {}, a[0].toUpperCase()))),
      h("button", { type: "button", class: "btn", "data-action": "undo", disabled: !canUndo() }, "Undo ", h("kbd", {}, "U")));
  }
  function reportView(r, st) {
    const edited = st.replies && st.replies[r.reportId];
    const wrap = h("div", {},
      h("p", { class: "report-meta" }, h("span", { class: "mono" }, r.reportId), h("span", {}, r.source), h("span", { class: "num" }, fmtTime(r.reportedAt))),
      r.injection
        ? h("p", { class: "report-comment flagged" }, `Flagged: the comment tries to instruct the system, so no model ever read it as an instruction. Text: “${r.comment}”`)
        : h("p", { class: "report-comment" }, `“${r.comment}”`));
    if (editing && editTarget(cases[current]) === "reply") {
      wrap.append(h("div", { class: "editor" }, h("label", { for: `reply-${r.reportId}` }, `Reply to ${r.reportId}`),
        h("textarea", { id: `reply-${r.reportId}`, class: "prose", rows: "5", "data-report": r.reportId }, edited || r.reply)));
    } else {
      wrap.append(h("p", { class: "reply" }, h("span", { class: "who" }, edited ? "Reply (edited by you)" : "Reply the student will see"), edited || r.reply));
    }
    return wrap;
  }

  /* ---------- editing ---------- */
  const hasChangeEdit = (c) => Boolean(c && c.edit);
  // What E edits: the proposed change, a fix you write for the content team, or the reply.
  const editTarget = (c) => (c.edit ? "change" : kindOf(c) === "nofix" ? "fix" : "reply");
  function fixEditor(c) {
    const st = caseState(c);
    return h("section", { class: "block editor" },
      h("label", { for: "edit-fix" }, "Your fix for the content team"),
      h("textarea", { id: "edit-fix", class: "prose", rows: "5", placeholder: FACULTY_TODO[c.repair] || "Describe the fix." }, st.fix || ""),
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn-primary", onclick: saveEdit }, "Save fix ", h("kbd", {}, "Ctrl+Enter")),
        h("button", { type: "button", class: "btn", onclick: cancelEdit }, "Cancel ", h("kbd", {}, "Esc"))));
  }
  function changeEditor(c) {
    const st = caseState(c);
    const value = st.replace != null ? st.replace : (typeof c.edit.replace === "string" ? c.edit.replace : JSON.stringify(c.edit.replace));
    const area = h("textarea", { id: "edit-replace", rows: String(Math.min(12, 2 + Math.ceil(String(value).length / 70))) }, String(value));
    const preview = rich(String(value), "preview content");
    area.addEventListener("input", () => { preview.innerHTML = DOMPurify.sanitize(area.value, PURIFY); });
    return h("section", { class: "block editor" },
      h("label", { for: "edit-replace" }, `Edit the replacement text (${c.change.field === "answer" ? "answer key" : c.change.field})`),
      area, preview,
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn-primary", onclick: saveEdit }, "Save and approve ", h("kbd", {}, "Ctrl+Enter")),
        h("button", { type: "button", class: "btn", onclick: cancelEdit }, "Cancel ", h("kbd", {}, "Esc"))));
  }
  function startEdit() {
    if (current < 0) return;
    editing = true;
    render();
    const target = document.querySelector("#edit-replace, #edit-fix, .decision textarea");
    if (target) target.focus();
    if (editTarget(cases[current]) === "reply") {
      $("decision-body").append(h("div", { class: "editor row" },
        h("button", { type: "button", class: "btn-primary", onclick: saveEdit }, "Save and approve ", h("kbd", {}, "Ctrl+Enter")),
        h("button", { type: "button", class: "btn", onclick: cancelEdit }, "Cancel ", h("kbd", {}, "Esc"))));
    }
  }
  function cancelEdit() { editing = false; render(); }
  function saveEdit() {
    const c = cases[current];
    if (hasChangeEdit(c)) {
      const raw = $("edit-replace").value;
      let value = raw;
      if (c.change.field === "answer" && /^\s*\[/.test(raw)) {
        try { value = JSON.parse(raw); } catch (_) { return toast("That answer list is not valid JSON."); }
      }
      editing = false;
      return act("edit", { replace: value });
    }
    if (editTarget(c) === "fix") {
      const text = $("edit-fix").value.trim();
      if (!text) return toast("Write the fix first, or press Esc to cancel.");
      editing = false;
      return act("edit", { fix: text });
    }
    const replies = {};
    document.querySelectorAll(".decision textarea[data-report]").forEach((t) => { replies[t.dataset.report] = t.value.trim(); });
    editing = false;
    act("edit", { replies });
  }

  /* ---------- actions + audit ---------- */
  // U undoes your most recent action anywhere (and jumps back to it), not "something on the
  // current case": after an action the console has already moved on to the next case.
  const canUndo = () => store.undo.length > 0;
  function proposal(c) {
    return c.edit ? { field: c.edit.field, find: c.edit.find, replace: c.edit.replace } : null;
  }
  function undoLast() {
    if (!canUndo()) return toast("Nothing to undo yet.");
    const id = store.undo.pop();
    const idx = cases.findIndex((x) => x.id === id);
    const c = cases[idx];
    const st = JSON.parse(JSON.stringify(caseState(c)));
    const prev = st.history.pop() || { status: INITIAL[c.section] };
    store.audit.push({
      at: new Date().toISOString(), question: c.id, reports: c.reports.map((r) => r.reportId),
      action: "undo", status_before: st.status, status_after: prev.status,
      field: c.edit ? c.edit.field : "reply", before: st.status, after: prev.status,
    });
    store.cases[c.id] = { ...st, status: prev.status, replace: prev.replace, replies: prev.replies, fix: prev.fix };
    save();
    toast(`Undone: ${c.reports.map((r) => r.reportId).join(", ")} ${c.reports.length === 1 ? "is" : "are"} back to "${STATUS_TEXT[prev.status]}".`);
    select(idx);
  }
  function act(action, payload) {
    if (action === "undo") return undoLast();
    if (current < 0) return;
    const c = cases[current];
    const st = JSON.parse(JSON.stringify(caseState(c)));
    const before = { status: st.status, replace: st.replace, replies: st.replies, fix: st.fix };
    let entry = { action, before: null, after: null };
    const kind = KINDS[kindOf(c)];
    const label = kind[action][0].toLowerCase();
    {
      st.history.push(before);
      st.status = kind[action][1];
      if (action === "approve") {
        entry = { action: label, before: proposal(c) && proposal(c).find, after: proposal(c) ? (st.replace != null ? st.replace : proposal(c).replace) : (st.fix || "reply as written") };
      } else if (action === "reject" && c.section === "auto") {
        entry = { action: label, before: c.edit && c.edit.replace, after: c.edit && c.edit.find };
      } else if (action === "reject") {
        entry = { action: label, before: proposal(c) && proposal(c).replace, after: proposal(c) ? "stored content kept" : "verdict rejected" };
      } else if (action === "edit") {
        if (payload.replace != null) {
          st.replace = payload.replace;
          entry = { action: label, before: c.edit.replace, after: payload.replace };
        } else if (payload.fix != null) {
          st.fix = payload.fix;
          entry = { action: label, before: null, after: payload.fix };
        } else {
          st.replies = { ...(st.replies || {}), ...payload.replies };
          entry = { action: label, before: c.reports.map((r) => r.reply), after: c.reports.map((r) => st.replies[r.reportId]) };
        }
      }
    }
    store.cases[c.id] = st;
    store.undo.push(c.id);
    store.audit.push({
      at: new Date().toISOString(), question: c.id, reports: c.reports.map((r) => r.reportId),
      action: entry.action, status_before: before.status, status_after: st.status,
      field: c.edit ? c.edit.field : "reply", before: entry.before, after: entry.after,
    });
    save();
    toast(`${kind[action][2]}: ${c.reports.map((r) => r.reportId).join(", ")}. Press U to undo.`);
    advance();
  }
  function advance() {
    for (let step = 1; step <= cases.length; step++) {
      const idx = (current + step) % cases.length;
      if (isOpen(cases[idx])) return select(idx);
    }
    current = -1;
    render();
  }

  /* ---------- selection + render ---------- */
  function select(idx) {
    if (idx < 0 || idx >= cases.length) return;
    editing = false;
    current = idx;
    try { history.replaceState(null, "", `#${cases[idx].id}`); } catch (_) { /* file:// */ }
    render();
    const row = document.querySelector('.q-row[aria-current="true"]');
    if (row) row.scrollIntoView({ block: "nearest" });
  }
  function render() {
    renderTop();
    renderQueue();
    const bar = $("actionbar");
    if (current < 0) {
      $("case").replaceChildren(h("p", { class: "empty" }, `All ${cases.length} questions are reviewed. Export the audit log to keep a record.`));
      $("decision-body").replaceChildren();
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    renderCase(cases[current]);
    renderDecision(cases[current]);
  }

  /* ---------- drawer, help, toast ---------- */
  let toastTimer;
  function toast(text) {
    const t = $("toast");
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 3500);
  }
  function openLog() {
    const body = $("log-body");
    body.replaceChildren();
    if (!store.audit.length) body.append(h("p", { class: "log-empty" }, "No actions yet."));
    for (const e of [...store.audit].reverse()) {
      const show = (v) => (v == null ? "(none)" : typeof v === "string" ? v : JSON.stringify(v));
      body.append(h("div", { class: "log-entry" },
        h("p", { class: "log-head" }, h("span", { class: "num" }, fmtTime(e.at)), h("span", { class: "log-action" }, e.action),
          h("span", { class: "mono" }, e.reports.join(", ")), h("span", {}, `${STATUS_TEXT[e.status_before] || e.status_before} to ${STATUS_TEXT[e.status_after] || e.status_after}`)),
        h("p", { class: "log-change" }, `before: ${show(e.before)}`),
        h("p", { class: "log-change" }, `after:  ${show(e.after)}`)));
    }
    $("log").hidden = false;
    $("close-log").focus();
  }
  function exportLog() {
    const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), decisions: store.cases, audit: store.audit }, null, 2)], { type: "application/json" });
    const a = h("a", { href: URL.createObjectURL(blob), download: `acadza-audit-${new Date().toISOString().slice(0, 10)}.json` });
    document.body.append(a);
    a.click();
    a.remove();
  }
  const closeOverlays = () => { $("log").hidden = true; $("help").hidden = true; };

  /* ---------- keyboard ---------- */
  function onKey(e) {
    const typing = /^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName);
    if (e.key === "Escape") {
      if (!$("log").hidden || !$("help").hidden) return closeOverlays();
      if (editing) return cancelEdit();
      return;
    }
    if (typing) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); saveEdit(); }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    const k = e.key.toLowerCase();
    const map = {
      j: () => select(Math.min(cases.length - 1, current + 1)),
      k: () => select(Math.max(0, current - 1)),
      a: () => act("approve"), e: () => startEdit(), r: () => act("reject"), u: () => act("undo"),
      l: () => openLog(), "?": () => { $("help").hidden = false; $("close-help").focus(); },
    };
    if (map[k] || map[e.key]) { e.preventDefault(); (map[k] || map[e.key])(); }
  }

  /* ---------- boot ---------- */
  async function boot() {
    document.addEventListener("keydown", onKey);
    $("actionbar").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-action]");
      if (!btn) return;
      const a = btn.dataset.action;
      if (a === "edit") startEdit(); else act(a);
    });
    $("open-log").addEventListener("click", openLog);
    $("close-log").addEventListener("click", closeOverlays);
    $("export-log").addEventListener("click", exportLog);
    $("open-help").addEventListener("click", () => { $("help").hidden = false; $("close-help").focus(); });
    $("close-help").addEventListener("click", closeOverlays);
    try {
      const res = await fetch("data/cases.json", { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // Array order must equal the visual order (sections, then urgency) so J/K and
      // "move to next case" follow what the faculty member sees.
      const sectionIndex = Object.fromEntries(SECTIONS.map(([key], i) => [key, i]));
      cases = data.cases
        .map((c, i) => ({ c, i }))
        .sort((x, y) => sectionIndex[x.c.section] - sectionIndex[y.c.section] || x.i - y.i)
        .map(({ c }) => c);
      renderTop(data);
    } catch (err) {
      $("case").replaceChildren(h("p", { class: "empty" }, `Could not load data/cases.json (${err.message}). Serve this folder over HTTP, not file://.`));
      return;
    }
    window.addEventListener("hashchange", () => {
      const idx = cases.findIndex((c) => `#${c.id}` === location.hash);
      if (idx >= 0 && idx !== current) select(idx);
    });
    const fromHash = cases.findIndex((c) => `#${c.id}` === location.hash);
    if (fromHash >= 0) return select(fromHash);
    const firstOpen = cases.findIndex(isOpen);
    if (firstOpen >= 0) select(firstOpen); else { current = -1; render(); }
  }
  boot();
})();
