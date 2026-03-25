async function previewAction() {
  const market = document.getElementById("market").value.trim();
  const action = document.getElementById("action").value;
  const outcomeRaw = document.getElementById("outcomeIndex").value;
  const body = { market, action };
  if (action === "resolve" && outcomeRaw !== "") body.outcomeIndex = Number(outcomeRaw);

  const res = await fetch("/api/preview/action", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  document.getElementById("out").textContent = JSON.stringify(json, null, 2);
}

document.getElementById("preview").addEventListener("click", () => {
  previewAction().catch((e) => {
    document.getElementById("out").textContent = String(e);
  });
});
