const $ = (id) => document.getElementById(id);
const state = {
  po: null,
  invoice: null,
  busy: false,
  run: null,
  source: null,
  page: 1,
  dirty: false,
  filter: "all",
  runs: [],
  historyExpanded: false,
};
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const format = (value, currency) => {
  if (value == null) return "—";
  const [whole, fraction = ""] = String(value).split(".");
  const decimal = fraction.replace(/0+$/, "");
  const sign = whole === "-0" && decimal ? "−" : "";
  return `${sign}${new Intl.NumberFormat("vi-VN").format(BigInt(whole))}${decimal ? "," + decimal : ""}${currency ? " " + currency : ""}`;
};
const icon = (name) =>
  `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const capture = (entry) => ({
  ...entry,
  original: structuredClone(entry.document),
});
const discard = () =>
  !state.dirty ||
  confirm("Thay chứng từ đang mở? Các chỉnh sửa chưa lưu sẽ được thay thế.");
function goToResults() {
  $("results").focus({ preventScroll: true });
  $("results").scrollIntoView({
    behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
    block: "start",
  });
}
function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
  $("notice").classList.toggle(
    "loading",
    state.busy && message.startsWith("Đang"),
  );
}
function invalidate() {
  state.run = null;
  state.filter = "all";
  $("results").hidden = true;
  $("reviewed").checked = false;
  updateControls();
}
function updateControls() {
  const count = Number(!!state.po) + Number(!!state.invoice);
  $("compare").disabled =
    state.busy || count < 2 || !$("reviewed").checked || !!state.run;
  $("compare").querySelector("span").textContent = state.run
    ? "Đã lưu kết quả"
    : state.busy
      ? "Đang xử lý…"
      : "Đối chiếu & lưu";
  ["demo", "po-file", "invoice-file", "method"].forEach(
    (id) => ($(id).disabled = state.busy),
  );
  document
    .querySelectorAll(
      ".document-panel input,.document-panel button,#reviewed,#refresh,[data-filter],[data-run]",
    )
    .forEach((el) => (el.disabled = state.busy));
  $("document-section").hidden = count === 0;
  $("review-bar").hidden = count === 0;
  $("first-run").hidden = count > 0;
  $("file-count").textContent = `${count}/2`;
  $("upload-progress").textContent = `${count}/2 chứng từ đã thêm`;
  $("review-hint").textContent =
    count < 2
      ? "Thêm đủ PO và hóa đơn để tiếp tục."
      : state.run
        ? "Kết quả đã lưu. Chỉnh sửa dữ liệu để tạo lần đối chiếu mới."
        : $("reviewed").checked
          ? "Sẵn sàng đối chiếu và lưu kết quả."
          : "Xác nhận kiểm tra để bắt đầu đối chiếu.";
  const current = state.run ? 2 : count === 2 ? 1 : 0;
  ["step-upload", "step-review", "step-result"].forEach((id, index) => {
    $(id).className =
      index < current ? "done" : index === current ? "current" : "";
    if (index === current) $(id).setAttribute("aria-current", "step");
    else $(id).removeAttribute("aria-current");
  });
  for (const side of ["po", "invoice"]) {
    $(side + "-file-name").textContent =
      state[side]?.filename || "Kéo thả tài liệu vào đây";
    document
      .querySelector(`[data-drop="${side}"]`)
      .classList.toggle("loaded", !!state[side]);
  }
  $("compare").setAttribute("aria-busy", String(state.busy));
  document
    .querySelectorAll("[data-help]")
    .forEach((button) => (button.disabled = state.busy));
  $("edit-state").textContent = state.dirty
    ? "Có chỉnh sửa chưa lưu"
    : state.run
      ? "Đã lưu kết quả"
      : "Chưa chỉnh sửa";
}
function markEdited(side) {
  const entry = state[side];
  if (!entry) return;
  const original = entry.original;
  $(side + "-panel")
    .querySelectorAll("input")
    .forEach((input) => {
      let before;
      if (input.dataset.field) before = original[input.dataset.field];
      else {
        const line =
          entry.document.lines[Number(input.closest("tr").dataset.index)];
        before = original.lines.find((item) => item.line_id === line.line_id)?.[
          input.dataset.key
        ];
      }
      const changed = String(before ?? "") !== input.value;
      input.classList.toggle("edited", changed);
      if (changed) input.title = `Ban đầu: ${before ?? "Chưa có"}`;
      else input.removeAttribute("title");
    });
}
async function api(path, options = {}) {
  const res = await fetch(path, options);
  const payload = await res.json();
  if (!res.ok)
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : "Dữ liệu không hợp lệ. Kiểm tra số lượng, giá và các trường bắt buộc.",
    );
  return payload;
}
async function task(fn, message = "Đang xử lý chứng từ…") {
  if (state.busy) return;
  state.busy = true;
  updateControls();
  notice(message);
  try {
    await fn();
    notice();
  } catch (error) {
    notice(error.message);
  } finally {
    state.busy = false;
    updateControls();
  }
}
function editor(side) {
  const entry = state[side],
    title = side === "po" ? "Đơn đặt hàng" : "Hóa đơn";
  const panel = $(side + "-panel");
  if (!entry) {
    panel.innerHTML = `<div class="panel-head"><h3>${title}</h3></div><div class="empty"><h3>Chưa có ${title.toLowerCase()}</h3><p>Thêm chứng từ còn lại để kiểm tra dữ liệu và bắt đầu đối chiếu.</p><button data-choose="${side}">${icon("upload")}Chọn tài liệu</button></div>`;
    panel.querySelector("[data-choose]").onclick = () => {
      $("upload-details").open = true;
      $(side + "-file").click();
    };
    return;
  }
  const d = entry.document;
  const fields = [
    ["number", "Số chứng từ"],
    ["supplier", "Nhà cung cấp"],
    ["currency", "Tiền tệ"],
    ...(side === "invoice" ? [["po_reference", "PO tham chiếu"]] : []),
  ];
  const numeric = [
    ["quantity", "Số lượng"],
    ["unit_price", "Đơn giá"],
    ["stated_total", "Tiền trên chứng từ"],
  ];
  panel.innerHTML = `
    <div class="panel-head"><div class="panel-identity">${icon("doc")}<div><h3>${title}</h3><p class="hint">${esc(entry.filename)} · ${entry.method === "ai" ? "AI đọc" : "Dữ liệu mẫu"}</p></div></div><button data-source="${side}">Bản gốc ${icon("external")}</button></div>
    <div class="doc-fields">${fields.map(([key, label]) => `<label>${label}<input data-field="${key}" value="${esc(d[key])}" maxlength="${key === "currency" ? 3 : key === "supplier" ? 200 : 100}"></label>`).join("")}</div>
    <div class="table-wrap" tabindex="0" aria-label="Dòng hàng ${title.toLowerCase()}"><table class="editable"><thead><tr><th>Mặt hàng</th><th>ĐVT</th><th class="num">SL</th><th class="num">Đơn giá</th><th class="num">Thành tiền</th><th>Nguồn</th></tr></thead><tbody>
    ${d.lines.map((line, index) => `<tr data-index="${index}"><td><input class="sku" aria-label="SKU dòng ${index + 1}" data-key="sku" value="${esc(line.sku)}" maxlength="80" placeholder="Mã hàng"><input class="desc" aria-label="Mô tả dòng ${index + 1}" data-key="description" value="${esc(line.description)}" maxlength="500" placeholder="Tên mặt hàng"></td><td data-label="Đơn vị"><input aria-label="Đơn vị dòng ${index + 1}" data-key="unit" value="${esc(line.unit)}" maxlength="40"></td>${numeric.map(([key, label]) => `<td data-label="${label}"><input class="num" aria-label="${label} dòng ${index + 1}" data-key="${key}" inputmode="decimal" value="${esc(line[key])}" placeholder="Chưa rõ"></td>`).join("")}<td><div class="row-actions"><button class="row-source" data-line="${index}" title="Xem trang ${line.page}" aria-label="Xem nguồn dòng ${index + 1}, trang ${line.page}">${icon("doc")}</button><button class="remove" data-remove="${index}" aria-label="Xóa dòng ${index + 1}">×</button></div></td></tr>`).join("")}
    </tbody></table></div><div class="panel-foot"><span class="hint">${d.lines.length} dòng · Nhập số không có dấu phân cách nghìn</span><button data-add="${side}">+ Thêm dòng</button></div>`;
  panel.querySelectorAll("[data-field]").forEach((input) =>
    input.addEventListener("input", () => {
      d[input.dataset.field] = input.value.trim() || null;
      state.dirty = true;
      invalidate();
      markEdited(side);
    }),
  );
  panel.querySelectorAll("[data-key]").forEach((input) =>
    input.addEventListener("input", () => {
      const line = d.lines[Number(input.closest("tr").dataset.index)];
      line[input.dataset.key] =
        input.value.trim() || (input.dataset.key === "description" ? "" : null);
      state.dirty = true;
      invalidate();
      markEdited(side);
    }),
  );
  panel.querySelector("[data-source]").onclick = () => showSource(side);
  panel
    .querySelectorAll("[data-line]")
    .forEach(
      (button) =>
        (button.onclick = () =>
          showSource(side, d.lines[Number(button.dataset.line)])),
    );
  panel.querySelectorAll("[data-remove]").forEach(
    (button) =>
      (button.onclick = () => {
        d.lines.splice(Number(button.dataset.remove), 1);
        state.dirty = true;
        invalidate();
        editor(side);
      }),
  );
  panel.querySelector("[data-add]").onclick = () => {
    d.lines.push({
      line_id: crypto.randomUUID(),
      sku: null,
      description: "",
      unit: null,
      quantity: null,
      unit_price: null,
      stated_total: null,
      page: 1,
      quote: "",
    });
    state.dirty = true;
    invalidate();
    editor(side);
    panel.querySelector("tr:last-child .sku")?.focus();
  };
  markEdited(side);
  updateControls();
}
async function refreshStatus() {
  try {
    const value = await api("/api/status");
    $("sql-status").textContent = value.sql_connected
      ? "SQL Server đã kết nối"
      : "SQL Server chưa sẵn sàng";
    $("sql-status").className = value.sql_connected ? "online" : "";
    $("ai-status").textContent = value.ai_configured
      ? "AI đã cấu hình"
      : "AI chưa cấu hình";
    $("ai-option").disabled = !value.ai_configured;
    $("ai-option").textContent = value.ai_configured
      ? "AI · gửi tài liệu tới OpenAI"
      : "AI · chưa cấu hình API";
  } catch {
    $("sql-status").textContent = "Không kết nối được ứng dụng";
  }
}
$("method").onchange = () => {
  $("method-note").textContent =
    $("method").value === "ai"
      ? "Ảnh và nội dung các trang sẽ gửi tới OpenAI để đọc. Có phí API theo model đã chọn."
      : "Bộ mẫu là dữ liệu giả lập, dùng để kiểm tra luồng đối chiếu.";
};
$("demo").onclick = () =>
  task(async () => {
    if (!discard()) return;
    const demo = await api("/api/demo", { method: "POST" });
    state.po = capture(demo.po);
    state.invoice = capture(demo.invoice);
    state.dirty = false;
    invalidate();
    editor("po");
    editor("invoice");
    $("upload-details").open = false;
  }, "Đang mở bộ chứng từ mẫu…");
async function uploadFile(side, file) {
  if (!file || state.busy) return;
  await task(
    async () => {
      if (file.size > 10 * 1024 * 1024)
        throw new Error("Tài liệu vượt giới hạn 10 MB. Chọn file nhỏ hơn.");
      if (!discard()) return;
      const body = new FormData();
      body.append("file", file);
      body.append("kind", side === "po" ? "PO" : "INVOICE");
      body.append("method", $("method").value);
      state[side] = capture(
        await api("/api/documents", { method: "POST", body }),
      );
      invalidate();
      editor(side);
      if (state.po && state.invoice) $("upload-details").open = false;
    },
    $("method").value === "ai"
      ? "Đang đọc tài liệu bằng AI. Có thể mất khoảng một phút…"
      : "Đang đọc dữ liệu chứng từ…",
  );
  $(side + "-file").value = "";
}
for (const side of ["po", "invoice"]) {
  $(side + "-file").onchange = (event) =>
    uploadFile(side, event.target.files[0]);
  const zone = document.querySelector(`[data-drop="${side}"]`);
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (!state.busy) zone.classList.add("drag-over");
  });
  zone.addEventListener("dragleave", (event) => {
    if (!zone.contains(event.relatedTarget)) zone.classList.remove("drag-over");
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("drag-over");
    if (event.dataTransfer.files.length !== 1) {
      notice("Chọn một tài liệu cho mỗi bên.");
      return;
    }
    uploadFile(side, event.dataTransfer.files[0]);
  });
}
$("reviewed").onchange = updateControls;
$("compare").onclick = () =>
  task(async () => {
    const body = {
      po_id: state.po.id,
      invoice_id: state.invoice.id,
      po: state.po.document,
      invoice: state.invoice.document,
      reviewed: $("reviewed").checked,
    };
    state.run = await api("/api/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    state.dirty = false;
    state.filter = "all";
    renderResults();
    goToResults();
    await loadHistory();
  }, "Đang đối chiếu và lưu kết quả…");
function renderResults() {
  const r = state.run.result;
  const attention = r.rows.filter((row) => row.status !== "matched").length;
  const resultTitle = !r.complete
    ? "Cần kiểm tra thêm thông tin"
    : attention
      ? `${attention} dòng cần kiểm tra`
      : "Các dòng hàng đã khớp";
  const neutral =
    r.net_difference == null || /^[-+]?0(?:\.0+)?$/.test(r.net_difference);
  const options = [
    ["all", "Tất cả", r.rows.length],
    ["attention", "Cần kiểm tra", attention],
    ["matched", "Đã khớp", r.rows.length - attention],
  ];
  $("results").innerHTML = `
    <div class="result-top"><div><h2>${resultTitle}</h2><p class="hint">${esc(state.po.document.number || "PO")} / ${esc(state.invoice.document.number || "Hóa đơn")} · Mã đối chiếu ${esc(state.run.id.slice(0, 8))}</p></div><span class="saved-note">${icon("check")}Đã lưu vào SQL Server</span></div>
    <div class="totals"><div><div class="total-label">Tổng PO tính lại</div><div class="amount">${format(r.po_total, state.po.document.currency)}</div></div><div><div class="total-label">Tổng hóa đơn tính lại</div><div class="amount">${format(r.invoice_total, state.invoice.document.currency)}</div></div><div class="delta ${neutral ? "neutral" : ""}"><div class="total-label">Chênh lệch thuần · Hóa đơn − PO</div><div class="amount">${format(r.net_difference, r.currency)}</div></div></div>
    ${r.issues.length ? `<div class="issues">${r.issues.map(esc).join("<br>")}</div>` : ""}
    <div class="result-toolbar"><div class="result-filters" role="group" aria-label="Lọc kết quả">${options.map(([key, label, count]) => `<button class="filter-button" data-filter="${key}" aria-pressed="${state.filter === key}">${label}<span class="count">${count}</span></button>`).join("")}</div><span class="hint">Bấm PO / HĐ để xem nguồn</span></div>
    <div class="table-wrap" tabindex="0" aria-label="Kết quả theo dòng hàng"><table class="result-table"><thead><tr><th>Mặt hàng</th><th>Kết quả</th><th class="num">PO</th><th class="num">Hóa đơn</th><th class="num">Chênh lệch</th><th>Chứng từ</th></tr></thead><tbody>${r.rows.map((row, index) => `<tr data-status="${row.status}"><td><strong>${esc(row.sku || "Chưa có SKU")}</strong><div class="hint">${esc(row.description)}</div></td><td><span class="status ${row.status}">${{ matched: "Khớp", difference: "Chênh lệch", review: "Chưa đủ thông tin" }[row.status]}</span><div class="hint">${row.notes.map(esc).join("<br>")}</div></td><td class="num" data-label="PO">${format(row.po_amount)}</td><td class="num" data-label="Hóa đơn">${format(row.invoice_amount)}</td><td class="num" data-label="Chênh lệch">${format(row.delta)}</td><td>${row.po_line ? `<button class="row-source" data-result="${index}" data-side="po">PO ${icon("external")}</button>` : ""}${row.invoice_line ? `<button class="row-source" data-result="${index}" data-side="invoice">HĐ ${icon("external")}</button>` : ""}</td></tr>`).join("")}</tbody></table><p class="filter-empty" id="filter-empty" hidden>Không có dòng nào trong nhóm này.</p></div>
    <p class="basis">${esc(r.basis)} ${r.complete ? "" : "Chưa tính chênh lệch tổng vì còn thông tin cần kiểm tra."}</p>`;
  $("results").hidden = false;
  $("results")
    .querySelectorAll("[data-result]")
    .forEach(
      (button) =>
        (button.onclick = () => {
          const row = r.rows[Number(button.dataset.result)];
          showSource(
            button.dataset.side,
            row[button.dataset.side === "po" ? "po_line" : "invoice_line"],
          );
        }),
    );
  $("results")
    .querySelectorAll("[data-filter]")
    .forEach(
      (button) =>
        (button.onclick = () => {
          state.filter = button.dataset.filter;
          filterResults();
        }),
    );
  filterResults();
  updateControls();
}
function filterResults() {
  let shown = 0;
  $("results")
    .querySelectorAll("[data-status]")
    .forEach((row) => {
      const visible =
        state.filter === "all" ||
        (state.filter === "matched"
          ? row.dataset.status === "matched"
          : row.dataset.status !== "matched");
      row.hidden = !visible;
      if (visible) shown++;
    });
  $("results")
    .querySelectorAll("[data-filter]")
    .forEach((button) =>
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.filter === state.filter),
      ),
    );
  $("filter-empty").hidden = shown > 0;
}
function showSource(side, line = null) {
  state.source = { side, line };
  state.page = line?.page || 1;
  $("evidence-title").textContent = state[side].filename;
  drawPage();
  $("evidence-dialog").showModal();
}
function drawPage() {
  const { side, line } = state.source,
    entry = state[side];
  $("source-image").src = `/api/documents/${entry.id}/page/${state.page}`;
  $("page-label").textContent = `Trang ${state.page} / ${entry.pages}`;
  $("prev-page").disabled = state.page <= 1;
  $("next-page").disabled = state.page >= entry.pages;
  const anchor = line ? entry.evidence[line.line_id] : null;
  const show = anchor?.page === state.page;
  $("highlights").innerHTML = show
    ? anchor.rects
        .map(
          ([x0, y0, x1, y1]) =>
            `<mark style="left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%"></mark>`,
        )
        .join("")
    : "";
  $("evidence-note").textContent = line
    ? anchor?.text_found
      ? "Vùng trích xuất ban đầu. Hãy đối chiếu các giá trị bạn đã sửa với bản gốc."
      : "Chưa xác minh được vị trí câu trích. Kiểm tra trực tiếp trang tài liệu."
    : "Bản tài liệu gốc được tải lên.";
  $("source-quote").textContent = line?.quote || "";
}
$("close-evidence").onclick = () => $("evidence-dialog").close();
$("prev-page").onclick = () => {
  state.page--;
  drawPage();
};
$("next-page").onclick = () => {
  state.page++;
  drawPage();
};
$("source-image").onerror = () => {
  $("evidence-note").textContent =
    "Không tải được trang tài liệu. Thử mở lại bản gốc.";
};
async function loadHistory() {
  try {
    state.runs = await api("/api/runs");
    renderHistory();
  } catch {
    $("history").innerHTML =
      '<p class="history-empty">Chưa đọc được lịch sử. Kiểm tra kết nối SQL Server rồi bấm Tải lại.</p>';
    $("history-count").textContent = "";
  }
}
function renderHistory() {
  const runs = state.runs,
    visible = state.historyExpanded ? runs : runs.slice(0, 6);
  $("history-count").textContent =
    runs.length === 30 ? "30 gần nhất" : String(runs.length);
  $("history").innerHTML = runs.length
    ? `<div class="history-list">${visible.map((run) => `<button class="history-item" data-run="${esc(run.id)}"><span><strong>${format(run.delta, run.currency)}</strong><span class="history-date">${new Date(run.created_at).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} · ${run.complete ? "Đã đối chiếu" : "Cần xem lại"}</span></span>${icon("arrow")}</button>`).join("")}</div>${runs.length > 6 ? `<button class="history-more" id="history-more">${state.historyExpanded ? "Thu gọn" : `Xem thêm ${runs.length - 6} lần đối chiếu`}</button>` : ""}`
    : '<p class="history-empty">Chưa có kết quả đã lưu. Thêm một cặp chứng từ để bắt đầu.</p>';
  if ($("history-more"))
    $("history-more").onclick = () => {
      state.historyExpanded = !state.historyExpanded;
      renderHistory();
    };
  $("history")
    .querySelectorAll("[data-run]")
    .forEach(
      (button) =>
        (button.onclick = () =>
          task(async () => {
            if (!discard()) return;
            const run = await api("/api/runs/" + button.dataset.run);
            const [po, invoice] = await Promise.all([
              api("/api/documents/" + run.snapshot.po_id),
              api("/api/documents/" + run.snapshot.invoice_id),
            ]);
            state.po = { ...capture(po), document: run.snapshot.po };
            state.invoice = {
              ...capture(invoice),
              document: run.snapshot.invoice,
            };
            state.run = run;
            state.dirty = false;
            state.filter = "all";
            editor("po");
            editor("invoice");
            $("reviewed").checked = true;
            $("upload-details").open = false;
            renderResults();
            goToResults();
          }, "Đang mở kết quả đã lưu…")),
    );
}
document
  .querySelectorAll("[data-help]")
  .forEach((button) => (button.onclick = () => $("help-dialog").showModal()));
$("close-help").onclick = $("help-done").onclick = () =>
  $("help-dialog").close();
document.querySelectorAll(".sidebar a.nav-item").forEach(
  (link) =>
    (link.onclick = () => {
      document.querySelectorAll(".sidebar a.nav-item").forEach((item) => {
        item.classList.toggle("active", item === link);
        if (item === link) item.setAttribute("aria-current", "page");
        else item.removeAttribute("aria-current");
      });
    }),
);
window.addEventListener("beforeunload", (event) => {
  if (state.dirty) {
    event.preventDefault();
    event.returnValue = "";
  }
});
$("refresh").onclick = () =>
  task(async () => {
    await refreshStatus();
    await loadHistory();
  });
editor("po");
editor("invoice");
updateControls();
refreshStatus();
loadHistory();
