async function loadMarkets() {
  const res = await fetch("/api/markets?limit=100");
  const data = await res.json();
  const tbody = document.getElementById("markets");
  tbody.innerHTML = "";
  for (const m of data.markets || []) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${m.market_address}</td>
      <td>${m.state}</td>
      <td>${m.proposer}</td>
      <td>${m.resolver}</td>
      <td>${m.betting_close_time}</td>
      <td>${m.resolution_window}</td>
    `;
    tbody.appendChild(tr);
  }
}

document.getElementById("refresh").addEventListener("click", () => {
  loadMarkets().catch((e) => {
    console.error(e);
  });
});

loadMarkets().catch((e) => {
  console.error(e);
});
