async function previewAction() {
  const wager = document.getElementById("wager").value.trim();
  const action = document.getElementById("action").value;
  const outcomeRaw = document.getElementById("outcomeIndex").value;
  const pv = document.getElementById("protocolVersion").value;
  const winAns = document.getElementById("winningAnswer").value;
  const body = { wager, action, protocolVersion: pv };
  if (action === "resolve" && outcomeRaw !== "") body.outcomeIndex = Number(outcomeRaw);
  if (action === "resolve" && pv === "freeform" && winAns.trim() !== "") body.winningAnswer = winAns;

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
