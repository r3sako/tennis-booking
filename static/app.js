// Tennis court booking — frontend logic (vanilla JS).
(function () {
  const app = document.getElementById("app");
  const loggedIn = app.dataset.userId !== "";
  const userId = Number(app.dataset.userId);
  const unlimited = app.dataset.unlimited === "true";
  const startIso = app.dataset.start;

  const grid = document.getElementById("slot-grid");
  const slotsTitle = document.getElementById("slots-title");
  const dateStrip = document.getElementById("date-strip");
  const modal = document.getElementById("modal");
  const modalWhen = document.getElementById("modal-when");
  const modalConfirm = document.getElementById("modal-confirm");
  const modalCancel = document.getElementById("modal-cancel");
  const toast = document.getElementById("toast");

  let selectedDate = startIso;
  let pending = null; // {date, hour}

  function showToast(msg, ok = true) {
    toast.textContent = msg;
    toast.classList.remove("hidden", "bg-emerald-600", "bg-rose-600");
    toast.classList.add(ok ? "bg-emerald-600" : "bg-rose-600");
    setTimeout(() => toast.classList.add("hidden"), 2800);
  }

  function fmtDateLabel(iso) {
    const [y, m, d] = iso.split("-");
    return `${d}.${m}.${y}`;
  }

  // Escape user-controlled text before inserting into HTML.
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function userBookedThisDay(slots) {
    return slots.some((s) => s.status === "booked" && s.tg_user_id === userId);
  }

  function showLoadError(iso) {
    grid.innerHTML =
      '<div class="col-span-full text-center text-rose-500 py-8">' +
      "Не удалось загрузить слоты. " +
      '<button id="retry-slots" class="underline font-medium">Повторить</button>' +
      "</div>";
    const r = document.getElementById("retry-slots");
    if (r) r.addEventListener("click", () => loadSlots(iso));
  }

  async function loadSlots(iso, silent = false) {
    selectedDate = iso;
    slotsTitle.textContent = `Слоты на ${fmtDateLabel(iso)}`;
    if (!silent) {
      grid.innerHTML =
        '<div class="col-span-full text-center text-slate-400 py-8">Загрузка…</div>';
    }

    try {
      const res = await fetch(`/api/slots?date=${iso}`, { cache: "no-store" });
      if (!res.ok) throw new Error("bad status " + res.status);
      const data = await res.json();
      // Ignore stale responses if the user switched dates meanwhile.
      if (selectedDate !== iso) return;
      renderSlots(data.slots);
    } catch (e) {
      if (!silent) showLoadError(iso);
    }
  }

  function renderSlots(slots) {
    // Privileged users (e.g. the trainer) may book multiple slots per day.
    const alreadyBooked = !unlimited && userBookedThisDay(slots);
    grid.innerHTML = "";

    slots.forEach((s) => {
      const cell = document.createElement("div");
      const label = `${s.hour}:00`;
      const range = `${s.hour}:00–${s.hour + 1}:00`;
      const base =
        "rounded-xl p-2 text-center text-sm border select-none transition";

      if (s.status === "booked" && s.tg_user_id === userId) {
        // Own booking → blue, cancellable.
        cell.className = `${base} border-blue-300 bg-blue-50`;
        cell.innerHTML = `
          <div class="font-bold">${label}</div>
          <div class="text-xs text-blue-600 mb-1">Ваша бронь</div>
          <button class="cancel-btn text-xs px-2 py-0.5 rounded bg-blue-500 text-white hover:bg-blue-600"
                  data-id="${s.booking_id}">Отменить</button>`;
      } else if (s.status === "booked") {
        // Booked by other → red/gray, not clickable. Show name + @username.
        const name = esc(s.tg_name || "Занято");
        const uname = s.tg_username ? "@" + esc(s.tg_username) : "";
        cell.className = `${base} border-rose-200 bg-rose-50 text-rose-700`;
        cell.innerHTML = `
          <div class="font-bold">${label}</div>
          <div class="text-xs truncate" title="${name}">${name}</div>
          ${uname ? `<div class="text-[11px] text-rose-400 truncate" title="${uname}">${uname}</div>` : ""}`;
      } else if (s.past) {
        // Past free slot → muted.
        cell.className = `${base} border-slate-200 bg-slate-100 text-slate-400`;
        cell.innerHTML = `
          <div class="font-bold">${label}</div>
          <div class="text-xs">прошёл</div>`;
      } else if (alreadyBooked) {
        // Free but user already has a booking today → green w/ tooltip, not clickable.
        cell.className = `${base} border-emerald-200 bg-emerald-50 text-emerald-700 cursor-not-allowed`;
        cell.title = "Вы уже бронировали сегодня";
        cell.innerHTML = `
          <div class="font-bold">${label}</div>
          <div class="text-xs">свободно</div>`;
      } else {
        // Free + clickable. Anonymous users are sent to login instead.
        cell.className = `${base} border-emerald-300 bg-emerald-50 text-emerald-700 cursor-pointer hover:bg-emerald-100`;
        cell.innerHTML = `
          <div class="font-bold">${label}</div>
          <div class="text-xs">свободно</div>`;
        if (loggedIn) {
          cell.addEventListener("click", () => openModal(s.hour, range));
        } else {
          cell.title = "Войдите, чтобы забронировать";
          cell.addEventListener("click", () => {
            window.location.href = "/login";
          });
        }
      }

      grid.appendChild(cell);
    });

    grid.querySelectorAll(".cancel-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        cancelBooking(btn.dataset.id);
      });
    });
  }

  function openModal(hour, range) {
    pending = { date: selectedDate, hour };
    modalWhen.textContent = `${fmtDateLabel(selectedDate)}, ${range}`;
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  }

  function closeModal() {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    pending = null;
  }

  async function confirmBooking() {
    if (!pending) return;
    const body = JSON.stringify(pending);
    modalConfirm.disabled = true;
    const res = await fetch("/api/book", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    modalConfirm.disabled = false;
    const data = await res.json().catch(() => ({}));
    closeModal();
    if (res.ok) {
      showToast("Бронь создана!");
      loadSlots(selectedDate);
    } else {
      showToast(data.error || "Ошибка бронирования", false);
    }
  }

  async function cancelBooking(id) {
    if (!confirm("Отменить вашу бронь?")) return;
    const res = await fetch(`/api/cancel/${id}`, { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      showToast("Бронь отменена");
      loadSlots(selectedDate);
    } else {
      showToast(data.error || "Ошибка отмены", false);
    }
  }

  // Date strip selection.
  dateStrip.addEventListener("click", (e) => {
    const btn = e.target.closest(".date-btn");
    if (!btn) return;
    dateStrip.querySelectorAll(".date-btn").forEach((b) => {
      b.classList.remove("border-emerald-500", "bg-emerald-50");
      b.classList.add("border-slate-200", "bg-white");
    });
    btn.classList.remove("border-slate-200", "bg-white");
    btn.classList.add("border-emerald-500", "bg-emerald-50");
    loadSlots(btn.dataset.date);
  });

  modalCancel.addEventListener("click", closeModal);
  modalConfirm.addEventListener("click", confirmBooking);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  // Initial load.
  loadSlots(startIso);

  // Refresh the current day's slots every minute so "прошёл" appears on time
  // and other people's bookings/cancellations show up without a manual reload.
  setInterval(() => {
    if (modal.classList.contains("hidden")) loadSlots(selectedDate, true);
  }, 60000);
})();
