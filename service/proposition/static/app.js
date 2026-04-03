const tokenKey = "propositionPanelToken";

let serverAllowExecute = false;

async function refreshServerConfig() {
  const el = document.getElementById("executeHint");
  try {
    const cfg = await api("/api/config");
    serverAllowExecute = !!cfg.allow_execute;
    el.textContent = serverAllowExecute
      ? "On-chain dispatch is enabled on this server."
      : "On-chain dispatch is disabled (set PROPOSITION_ALLOW_EXECUTE=1 or start with --allow-execute).";
  } catch (e) {
    el.textContent = "";
  }
}

function getToken() {
  return (document.getElementById("token").value || localStorage.getItem(tokenKey) || "").trim();
}

function authHeaders() {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { ...authHeaders(), ...(opts.headers || {}) } });
  const text = await r.text();
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    body = { raw: text };
  }
  if (!r.ok) {
    const err = new Error(body.error || body.raw || r.statusText);
    err.status = r.status;
    throw err;
  }
  return body;
}

function esc(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderProposal(p) {
  const pending = p.status === "pending";
  const approved = p.status === "approved";
  const canDispatch = approved && serverAllowExecute;
  const disSave = pending ? "" : " disabled";
  const disApr = pending ? "" : " disabled";
  const disDispatch = canDispatch ? "" : " disabled";
  const meta = [];
  if (p.created_at != null) meta.push(`created: ${p.created_at}`);
  if (p.updated_at != null) meta.push(`updated: ${p.updated_at}`);
  if (p.tx_hint) meta.push(`tx/log: ${p.tx_hint}`);
  if (p.dispatch_error) meta.push(`error: ${p.dispatch_error}`);
  const metaBlock = meta.length ? `<pre class="meta">${esc(meta.join("\n"))}</pre>` : "";
  const refs = (p.source_refs || []).map((r) => `<a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(r.label)}</a>`).join(" · ");
  const outs = JSON.stringify(p.outcomes || []);
  return `
    <div class="item" data-id="${p.id}">
      <span class="badge">${esc(p.status)}</span>
      <span class="badge">${esc(p.cadence)}</span>
      <span class="badge">${esc(p.category)}</span>
      <h3>#${p.id}</h3>
      <p>${esc(p.proposition)}</p>
      <p class="muted">Outcomes: <code>${esc(outs)}</code></p>
      <p class="muted">${esc(p.rationale || "")}</p>
      <p class="links">Sources: ${refs || "<span class='muted'>—</span>"}</p>
      ${metaBlock}
      <label>Edit proposition (pending only)
        <textarea class="propEdit"${disSave ? " readonly" : ""}>${esc(p.proposition)}</textarea>
      </label>
      <label>Edit outcomes JSON array
        <textarea class="outEdit"${disSave ? " readonly" : ""}>${esc(JSON.stringify(p.outcomes || []))}</textarea>
      </label>
      <div>
        <button type="button" class="secondary saveBtn"${disSave}>Save edits</button>
        <button type="button" class="approveBtn"${disApr}>Approve</button>
        <button type="button" class="danger rejectBtn"${disApr}>Reject</button>
        <button type="button" class="dispatchBtn"${disDispatch}>Dispatch</button>
      </div>
      <p class="err itemErr"></p>
    </div>
  `;
}

async function loadList() {
  const st = document.getElementById("statusFilter").value;
  const q = st ? `?status=${encodeURIComponent(st)}` : "";
  const sess = document.getElementById("sessionStatus");
  let data;
  try {
    data = await api(`/api/proposals${q}`);
  } catch (e) {
    if (e.status === 401) sess.textContent = "Unauthorized — enter panel token and Save.";
    else sess.textContent = e.message || String(e);
    document.getElementById("list").innerHTML = "<p class='muted'>Could not load proposals.</p>";
    throw e;
  }
  sess.textContent = getToken() ? "Authenticated." : "";
  await refreshServerConfig();
  const host = document.getElementById("list");
  host.innerHTML = (data.proposals || []).map(renderProposal).join("") || "<p class='muted'>No proposals.</p>";

  host.querySelectorAll(".item").forEach((el) => {
    const id = el.getAttribute("data-id");
    const err = el.querySelector(".itemErr");
    const showErr = (e) => {
      err.textContent = e.message || String(e);
    };
    el.querySelector(".saveBtn").addEventListener("click", async () => {
      err.textContent = "";
      try {
        let outcomes;
        try {
          outcomes = JSON.parse(el.querySelector(".outEdit").value);
        } catch {
          throw new Error("Outcomes must be valid JSON array");
        }
        if (!Array.isArray(outcomes) || outcomes.length < 2) throw new Error("At least two outcomes");
        await api(`/api/proposals/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ proposition: el.querySelector(".propEdit").value.trim(), outcomes }),
        });
        await loadList();
      } catch (e) {
        showErr(e);
      }
    });
    el.querySelector(".approveBtn").addEventListener("click", async () => {
      err.textContent = "";
      try {
        await api(`/api/proposals/${id}/approve`, { method: "POST", body: "{}" });
        await loadList();
      } catch (e) {
        showErr(e);
      }
    });
    el.querySelector(".rejectBtn").addEventListener("click", async () => {
      err.textContent = "";
      try {
        await api(`/api/proposals/${id}/reject`, { method: "POST", body: "{}" });
        await loadList();
      } catch (e) {
        showErr(e);
      }
    });
    el.querySelector(".dispatchBtn").addEventListener("click", async () => {
      err.textContent = "";
      try {
        const res = await api(`/api/proposals/${id}/dispatch`, { method: "POST", body: "{}" });
        err.textContent = JSON.stringify(res, null, 2);
        await loadList();
      } catch (e) {
        showErr(e);
      }
    });
  });
}

document.getElementById("saveToken").addEventListener("click", async () => {
  const t = document.getElementById("token").value.trim();
  localStorage.setItem(tokenKey, t);
  document.getElementById("sessionStatus").textContent = t ? "Token saved locally." : "Cleared.";
  await refreshServerConfig();
  loadList().catch(() => {});
});

document.getElementById("reload").addEventListener("click", () => loadList().catch((e) => alert(e.message)));
document.getElementById("statusFilter").addEventListener("change", () => loadList().catch((e) => alert(e.message)));

document.getElementById("runIngest").addEventListener("click", async () => {
  const out = document.getElementById("ingestOut");
  out.textContent = "Running…";
  try {
    const cal = document.getElementById("calendarFlag").checked ? "?calendar=1" : "";
    const data = await api(`/api/ingest${cal}`, { method: "POST", body: "{}" });
    out.textContent = JSON.stringify(data, null, 2);
    await loadList();
  } catch (e) {
    out.textContent = e.message || String(e);
  }
});

(function init() {
  const stored = localStorage.getItem(tokenKey);
  if (stored) document.getElementById("token").value = stored;
  loadList().catch(() => {});
})();
