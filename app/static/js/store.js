const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char]));
const money = (value) => `${Number(value).toLocaleString("vi-VN")} ₫`;
// Refund amounts are stored in minor units: VND*100, or PayPal USD cents.
const moneyMinor = (value, currency) => currency === "USD"
  ? (Number(value) / 100).toLocaleString("en-US", {style:"currency", currency:"USD"})
  : `${(Number(value) / 100).toLocaleString("vi-VN")} ₫`;
const message = (text) => { const node = document.querySelector("[data-message]"); if (node) node.textContent = text; };
// Gateways (VNPAY QR included) must not replace the current page: they open in a
// new tab instead. The tab is created during the click gesture, otherwise
// browsers treat the later redirect as a blocked popup.
function popPaymentTab() {
  const tab = window.open("about:blank", "_blank");
  if (tab) { try { tab.opener = null; } catch (error) { /* older browsers */ } }
  return tab;
}
function signalPaymentUpdate() {
  try { localStorage.setItem("electrohub-payment", String(Date.now())); } catch (error) { /* private mode */ }
}

async function request(path, options = {}) {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const headers = { ...((options.body && !isFormData) ? {"Content-Type":"application/json"} : {}), ...options.headers };
  if (options.method && options.method !== "GET") {
    const csrf = await fetch("/api/v1/auth/csrf").then((r) => r.json());
    headers["X-CSRF-Token"] = csrf.csrf_token;
  }
  const response = await fetch(path, {...options, headers});
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.detail || "Không thể hoàn tất yêu cầu");
    error.status = response.status;
    throw error;
  }
  return data;
}

function discountPercent(product) {
  if (product.price <= 0 || product.sale_price === null || product.sale_price >= product.price) return "0";
  return (Math.round((product.price - product.sale_price) / product.price * 1000) / 10).toLocaleString("vi-VN", {maximumFractionDigits:1});
}

function productCard(product) {
  const onSale = product.sale_price !== null && product.sale_price < product.price;
  return `<article class="product-card"><a class="product-image" href="/products/${encodeURIComponent(product.slug)}"><img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" width="560" height="420" loading="lazy">${onSale ? `<span class="sale-label">Giảm ${discountPercent(product)}%</span>` : ''}</a><p class="product-sku">${escapeHtml(product.sku)}</p><a class="product-name" href="/products/${encodeURIComponent(product.slug)}"><h2>${escapeHtml(product.name)}</h2></a><div class="card-price"><span class="price">${money(product.sale_price ?? product.price)}</span>${onSale ? `<del>${money(product.price)}</del>` : ''}</div><p class="stock-status">${product.stock > 0 ? `Còn hàng · ${product.stock}` : 'Tạm hết hàng'}</p><div class="product-actions"><button class="button-light" data-add-to-cart="${product.id}" ${product.stock < 1 ? "disabled" : ""}>Thêm vào giỏ</button><button data-buy-now="${product.id}" ${product.stock < 1 ? "disabled" : ""}>Mua ngay</button></div></article>`;
}

// Đơn hàng và thanh toán là hai trạng thái độc lập: đơn "Chờ xác nhận" nghĩa là
// shop chưa xác nhận xử lý, không đồng nghĩa với việc khách chưa trả tiền.
const statusNames = {pending:"Chờ xác nhận",confirmed:"Đã xác nhận",shipping:"Đang giao",done:"Hoàn tất",cancelled:"Đã hủy"};
const paymentStatusNames = {pending:"Chờ thanh toán",paid:"Đã thanh toán",failed:"Thanh toán chưa thành công",refund_pending:"Đã hủy, chờ shop xác nhận hoàn tiền",refunded:"Đã hoàn tiền"};
const paymentTones = {pending:"is-waiting",paid:"is-paid",failed:"is-failed",refund_pending:"is-refund",refunded:"is-refund"};
const providerNames = {PAYPAL:"PayPal",paypal:"PayPal",VNPAY:"VNPAY",vnpay:"VNPAY"};

function orderTag(status) {
  return `<span class="status-tag order-tag">Đơn hàng: ${escapeHtml(statusNames[status] || status)}</span>`;
}

function paymentTag(payment) {
  if (!payment) return `<span class="status-tag payment-tag is-unknown">Thanh toán: chưa có thông tin</span>`;
  const provider = providerNames[payment.method] ? ` · ${providerNames[payment.method]}` : "";
  const label = `${paymentStatusNames[payment.status] || payment.status}${provider}`;
  return `<span class="status-tag payment-tag ${paymentTones[payment.status] || "is-unknown"}">Thanh toán: ${escapeHtml(label)}</span>`;
}

// Lý do cổng thanh toán quay về mà không xác nhận được giao dịch. Hiển thị rõ để
// khách biết tiền đã vào hệ thống chưa, thay vì im lặng hiện "Chờ thanh toán".
const paymentReturnNotes = {
  opened: "Đã mở cổng thanh toán ở một tab mới. Trạng thái tại đây sẽ cập nhật sau khi bạn hoàn tất thanh toán.",
  cancelled: "Bạn đã hủy thanh toán tại cổng. Đơn hàng vẫn chờ thanh toán.",
  error: "Cổng thanh toán chưa xác nhận được giao dịch này. Nếu bạn đã bấm thanh toán thành công, hãy bấm “Kiểm tra lại thanh toán” hoặc liên hệ cửa hàng kèm mã đơn.",
  invalid: "Chữ ký xác thực từ cổng thanh toán không hợp lệ nên giao dịch chưa được ghi nhận. Bấm “Kiểm tra lại thanh toán” để thử lại.",
  amount: "Số tiền giao dịch không khớp đơn hàng nên hệ thống chưa ghi nhận. Liên hệ cửa hàng kèm mã đơn để được đối soát.",
  notfound: "Không tìm thấy giao dịch thanh toán cho đơn này. Bấm “Kiểm tra lại thanh toán” hoặc chọn thanh toán lại.",
};

async function loadUserNav() {
  const nav = document.querySelector("[data-user-nav]");
  if (!nav) return;
  try {
    const user = await request("/api/v1/auth/me");
    window.currentUser = user;
    const initial = (user.name || "U").trim().charAt(0).toUpperCase();

    refreshCartCount();

    nav.innerHTML = `
      <a href="/account" class="user-profile-link" title="Tài khoản cá nhân: ${escapeHtml(user.name)}">
        <span class="user-avatar" aria-hidden="true">${escapeHtml(initial)}</span>
        <span class="user-name">${escapeHtml(user.name)}</span>
      </a>
    `;
  } catch {
    /* Người dùng chưa đăng nhập; giữ liên kết mặc định. */
  }
}

async function loadAccountSidebar() {
  const sidebar = document.querySelector("[data-account-sidebar]");
  if (!sidebar) return;
  try {
    const user = window.currentUser || (await request("/api/v1/auth/me"));
    window.currentUser = user;
    const initial = (user.name || "U").trim().charAt(0).toUpperCase();

    const avatar = sidebar.querySelector("[data-sidebar-avatar]");
    if (avatar) avatar.textContent = initial;
    const name = sidebar.querySelector("[data-sidebar-name]");
    if (name) name.textContent = user.name;
    const email = sidebar.querySelector("[data-sidebar-email]");
    if (email) email.textContent = user.email;
    const rolePill = sidebar.querySelector("[data-sidebar-role]");
    if (rolePill) {
      const roleLabels = { admin: "Quản lý (Admin)", staff: "Nhân viên (Staff)", customer: "Khách hàng" };
      rolePill.textContent = roleLabels[user.role] || user.role;
      rolePill.className = `role-pill role-${user.role}`;
    }

    const path = location.pathname;
    const accLink = sidebar.querySelector("[data-link-account]");
    if (accLink) accLink.classList.toggle("is-active", path === "/account");
    const ordersLink = sidebar.querySelector("[data-link-orders]");
    if (ordersLink) ordersLink.classList.toggle("is-active", path === "/account/orders");

    const staffManagerLinks = sidebar.querySelector("[data-staff-manager-links]");
    if (staffManagerLinks) {
      let extra = "";
      if (user.role === "staff" || user.role === "admin") {
        const isStaffActive = path === "/staff/orders" || path === "/admin/orders";
        extra += `
          <a href="/staff/orders" class="sidebar-link ${isStaffActive ? 'is-active' : ''}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
            <span>Xử lý đơn hàng</span>
          </a>
        `;
      }
      if (user.role === "admin") {
        const isManagerActive = path === "/manager";
        const isProductsActive = path === "/admin/products";
        const isNewsletterActive = path === "/admin/newsletter";
        const isUsersActive = path === "/admin/users";
        extra += `
          <a href="/manager" class="sidebar-link ${isManagerActive ? 'is-active' : ''}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>
            <span>Báo cáo doanh thu</span>
          </a>
          <a href="/admin/products" class="sidebar-link ${isProductsActive ? 'is-active' : ''}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>
            <span>Danh mục sản phẩm</span>
          </a>
          <a href="/admin/newsletter" class="sidebar-link ${isNewsletterActive ? 'is-active' : ''}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
            <span>Email marketing</span>
          </a>
          <a href="/admin/users" class="sidebar-link ${isUsersActive ? 'is-active' : ''}">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
            <span>Phân quyền & Người dùng</span>
          </a>
        `;
      }
      staffManagerLinks.innerHTML = extra;
    }

    const nameInput = document.querySelector("[data-profile-name-input]");
    if (nameInput) nameInput.value = user.name || "";
    const emailInput = document.querySelector("[data-profile-email-input]");
    if (emailInput) emailInput.value = user.email || "";

    const savedShipping = JSON.parse(localStorage.getItem("electrohub_default_shipping") || "{}");
    const phoneInput = document.querySelector("[data-profile-phone-input]");
    if (phoneInput && !phoneInput.value && savedShipping.phone) phoneInput.value = savedShipping.phone;
    const addrInput = document.querySelector("[data-profile-address-input]");
    if (addrInput && !addrInput.value && savedShipping.address) addrInput.value = savedShipping.address;
  } catch {
    if (location.pathname === "/account" || location.pathname === "/account/orders") {
      location.assign(`/account/login?next=${encodeURIComponent(location.pathname)}`);
    }
  }
}

let catalogProducts = [];
async function loadProducts() {
  if (!document.querySelector("[data-products]")) return;
  const params = new URLSearchParams(location.search);
  const search = document.querySelector("[data-product-search]");
  if (search) search.value = params.get("q") || "";
  const headerSearch = document.querySelector(".header-search input");
  if (headerSearch) headerSearch.value = params.get("q") || "";
  const sale = document.querySelector("[data-sale-filter]");
  if (sale) sale.checked = params.get("sale") === "1";
  try {
    const data = await request("/api/v1/products");
    catalogProducts = data.items;
    applyProductSearch();
  } catch (error) {
    // The list is already rendered by the server; never wipe it on a failed fetch.
    const list = document.querySelector("[data-products]");
    if (list && !list.children.length) list.textContent = error.message;
    else message(error.message);
  }
}

function applyProductSearch() {
  const list = document.querySelector("[data-products]");
  if (!list) return;
  const normalize = (value) => value.toLocaleLowerCase("vi").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d");
  const query = normalize(document.querySelector("[data-product-search]")?.value.trim() || "");
  let products = catalogProducts.filter((product) => normalize(`${product.name} ${product.sku}`).includes(query));
  if (document.querySelector("[data-stock-filter]")?.checked) products = products.filter((product) => product.stock > 0);
  if (document.querySelector("[data-sale-filter]")?.checked) products = products.filter((product) => product.sale_price !== null && product.sale_price < product.price);
  const sort = document.querySelector("[data-product-sort]")?.value;
  products.sort((a, b) => sort === "price-asc" ? (a.sale_price ?? a.price) - (b.sale_price ?? b.price) : sort === "price-desc" ? (b.sale_price ?? b.price) - (a.sale_price ?? a.price) : sort === "newest" ? b.id - a.id : a.name.localeCompare(b.name, "vi"));
  list.innerHTML = products.map(productCard).join("") || '<div class="empty-state"><h2>Không tìm thấy sản phẩm</h2><p>Thử từ khóa khác hoặc bỏ bớt bộ lọc.</p><a href="/collections/all">Xem tất cả sản phẩm</a></div>';
  const count = document.querySelector("[data-product-count]");
  if (count) count.textContent = `${products.length} sản phẩm`;
}

async function refreshCartCount() {
  try {
    const cart = await request("/api/v1/cart");
    document.querySelectorAll("[data-cart-count]").forEach((node) => node.textContent = cart.items.reduce((sum, item) => sum + item.qty, 0));
  } catch { document.querySelectorAll("[data-cart-count]").forEach((node) => node.textContent = "0"); }
}

async function loadManagerStats() {
  const stats = document.querySelector("[data-manager-stats]");
  if (!stats) return;
  try {
    const [products, orders, pending] = await Promise.all([
      request("/api/v1/admin/products"),
      request("/api/v1/admin/orders?page_size=50"),
      request("/api/v1/admin/orders?status=pending&page_size=1"),
    ]);
    stats.innerHTML = `<article><span>Sản phẩm</span><strong>${products.items.length}</strong></article><article><span>Đơn hàng</span><strong>${orders.total}</strong></article><article><span>Chờ xác nhận</span><strong>${pending.total}</strong></article>`;
  } catch (error) { stats.innerHTML = `<p>${escapeHtml(error.message)}</p>`; }
}

async function loadAccountOrders() {
  const list = document.querySelector("[data-account-orders]");
  if (!list) return;
  try {
    const data = await request("/api/v1/orders");
    list.innerHTML = data.items.map((order) => `<article class="account-order"><header><h2>Đơn ${escapeHtml(order.code)}</h2><span class="tag-row">${orderTag(order.status)}${paymentTag(order.payment)}</span></header><p>${new Date(order.created_at).toLocaleDateString("vi-VN")} · ${money(order.total)} · ${order.item_count} sản phẩm</p><a href="/cart/tracking?code=${encodeURIComponent(order.code)}">Tra cứu đơn</a></article>`).join("") || "<p>Bạn chưa có đơn hàng nào. <a href=\"/collections/all\">Xem sản phẩm</a></p>";
  } catch (error) { list.innerHTML = `<p>${escapeHtml(error.message)} · <a href="/account/login">Đăng nhập</a></p>`; }
}

async function loadStaffOrders(status = "") {
  const list = document.querySelector("[data-staff-orders]");
  if (!list) return;
  try {
    const query = status ? `?status=${encodeURIComponent(status)}&page_size=50` : "?page_size=50";
    const data = await request(`/api/v1/admin/orders${query}`);
    list.innerHTML = data.items.map((order) => `<article class="order-card" data-order-card="${escapeHtml(order.code)}"><div><h2>Đơn ${escapeHtml(order.code)} · ${money(order.total)}</h2><p class="tag-row">${orderTag(order.status)}${paymentTag(order.payment)}</p><p>${order.item_count} sản phẩm · ${new Date(order.created_at).toLocaleString("vi-VN")}</p><button type="button" class="button-light" data-order-detail="${escapeHtml(order.code)}">Xem chi tiết</button></div><label>Trạng thái đơn<select data-order-status="${escapeHtml(order.code)}">${Object.entries(statusNames).map(([key, label]) => `<option value="${key}" ${key === order.status ? "selected" : ""}>${label}</option>`).join("")}</select></label></article>`).join("") || "<p>Không có đơn hàng phù hợp.</p>";
  } catch (error) { list.innerHTML = `<p>${escapeHtml(error.message)} · <a href="/account/login">Đăng nhập</a></p>`; }
}

let checkoutTotal = 0;
let checkoutVatPercent = 0;

function renderPaymentConversion(total, vatPercent) {
  checkoutTotal = Number(total) || 0;
  checkoutVatPercent = Number(vatPercent) || 0;
  const form = document.querySelector("[data-checkout]");
  const note = document.querySelector("[data-payment-conversion]");
  if (!form || !note) return;
  const method = form.querySelector('input[name="payment_method"]:checked')?.value;
  if (!checkoutTotal || !method) { note.textContent = ""; return; }
  if (method === "PAYPAL") {
    const rate = Number(form.dataset.usdRate) || 25000;
    const usdCents = Math.round((checkoutTotal / rate) * 100);
    const usd = (usdCents / 100).toLocaleString("en-US", {style:"currency", currency:"USD"});
    note.innerHTML = `PayPal thu <strong>${usd}</strong> · tỷ giá 1 USD = ${rate.toLocaleString("vi-VN")} ₫ · đã gồm VAT ${checkoutVatPercent}%`;
  } else {
    note.innerHTML = `VNPAY thu <strong>${money(checkoutTotal)}</strong> · thanh toán bằng VND · đã gồm VAT ${checkoutVatPercent}%`;
  }
}

function prefillCheckoutForm() {
  const form = document.querySelector("[data-checkout]");
  if (!form) return;
  try {
    const saved = JSON.parse(localStorage.getItem("electrohub_default_shipping") || "{}");
    const nameInput = form.querySelector("input[name='name']");
    const phoneInput = form.querySelector("input[name='phone']");
    const addrInput = form.querySelector("textarea[name='address']");
    if (nameInput && !nameInput.value) {
      nameInput.value = saved.name || window.currentUser?.name || "";
    }
    if (phoneInput && !phoneInput.value && saved.phone) {
      phoneInput.value = saved.phone;
    }
    if (addrInput && !addrInput.value && saved.address) {
      addrInput.value = saved.address;
    }
  } catch {}
}

async function loadCart() {
  const target = document.querySelector("[data-cart]");
  const summary = document.querySelector("[data-cart-summary], [data-checkout-summary]");
  if (!target && !summary) return;
  const checkout = document.querySelector("[data-checkout-link]");
  const submit = document.querySelector("[data-place-order]");
  try {
    const cart = await request("/api/v1/cart");
    if (target) target.innerHTML = cart.items.map((item) => `<div class="cart-row"><div><a href="/products/${encodeURIComponent(item.slug)}">${escapeHtml(item.name)}</a><small>${money(item.unit_price)} / sản phẩm</small></div><label>Số lượng <input type="number" min="1" max="${Math.min(item.stock,99)}" value="${item.qty}" data-qty="${item.id}"></label><strong>${money(item.line_total)}</strong><button class="remove-item" data-delete="${item.id}">Xóa</button></div>`).join("") || '<div class="empty-state"><h2>Giỏ hàng đang trống</h2><p>Chọn sản phẩm để bắt đầu mua sắm.</p><a class="button" href="/collections/all">Xem sản phẩm</a></div>';
    if (summary) summary.innerHTML = `${summary.hasAttribute("data-checkout-summary") ? cart.items.map((item) => `<p class="summary-line"><span>${escapeHtml(item.name)} × ${item.qty}</span><strong>${money(item.line_total)}</strong></p>`).join("") : ""}<dl><div><dt>Tạm tính</dt><dd>${money(cart.subtotal)}</dd></div><div><dt>Giảm giá</dt><dd>−${money(cart.discount)}</dd></div><div><dt>VAT (${cart.vat_percent}%)</dt><dd>${money(cart.vat)}</dd></div><div><dt>Phí giao hàng</dt><dd>${money(cart.shipping_fee)}</dd></div><div class="summary-total"><dt>Tổng thanh toán</dt><dd>${money(cart.total)}</dd></div></dl>${!cart.items.length ? '<p>Chưa có sản phẩm để đặt hàng.</p>' : ''}`;
    renderPaymentConversion(cart.total, cart.vat_percent);
    prefillCheckoutForm();
    if (checkout) checkout.hidden = !cart.items.length;
    if (submit) submit.disabled = !cart.items.length;
    refreshCartCount();
  } catch (error) {
    const text = `<div class="empty-state"><p>${escapeHtml(error.message)}</p><a class="button" href="/account/login">Đăng nhập để mua hàng</a></div>`;
    if (target) target.innerHTML = text;
    if (summary) summary.innerHTML = text;
    if (checkout) checkout.hidden = true;
    if (submit) submit.disabled = true;
  }
}

document.addEventListener("click", async (event) => {
  if (event.target.closest("[data-logout]")) {
    try { await request("/api/v1/auth/logout", {method:"POST", body:"{}"}); location.href = "/"; }
    catch (error) { message(error.message); }
    return;
  }
  const buy = event.target.closest("[data-buy-now]");
  const add = event.target.closest("[data-add-to-cart]");
  const remove = event.target.closest("[data-delete]");
  const action = buy || add;
  if (!action && !remove) return;
  const input = action ? document.querySelector("[data-purchase-qty]") : null;
  if (input && !input.reportValidity()) return;
  const purchase = action ? {product_id:Number(action.dataset.buyNow || action.dataset.addToCart),qty:input ? Number(input.value) : 1} : null;
  const buttons = action?.parentElement.querySelectorAll("[data-buy-now], [data-add-to-cart]");
  try {
    buttons?.forEach((button) => button.disabled = true);
    if (action) await request("/api/v1/cart/items", {method:"POST", body:JSON.stringify(purchase)});
    if (buy) { sessionStorage.removeItem("electrohub.pendingBuy"); location.assign("/checkout"); return; }
    if (remove) await request(`/api/v1/cart/items/${remove.dataset.delete}`, {method:"DELETE"});
    await refreshCartCount();
    if (remove) await loadCart(); else message("Đã thêm sản phẩm vào giỏ hàng. Bạn có thể tiếp tục mua sắm hoặc mở Giỏ hàng để đặt mua.");
  } catch (error) {
    if (buy && error.status === 401) {
      sessionStorage.setItem("electrohub.pendingBuy", JSON.stringify(purchase));
      location.assign("/account/login?next=checkout");
      return;
    }
    message(error.message);
  } finally { buttons?.forEach((button) => button.disabled = false); }
});

document.querySelector("[data-product-search]")?.addEventListener("input", applyProductSearch);
["[data-stock-filter]", "[data-sale-filter]", "[data-product-sort]"].forEach((selector) => document.querySelector(selector)?.addEventListener("change", applyProductSearch));
document.querySelector("[data-order-filter]")?.addEventListener("change", (event) => loadStaffOrders(event.target.value));
document.querySelector("[data-staff-orders]")?.addEventListener("change", async (event) => {
  const select = event.target.closest("[data-order-status]");
  if (!select) return;
  try {
    await request(`/api/v1/admin/orders/${encodeURIComponent(select.dataset.orderStatus)}`, {method:"PATCH", body:JSON.stringify({status:select.value})});
    message("Đã cập nhật trạng thái đơn hàng.");
  } catch (error) { message(error.message); loadStaffOrders(document.querySelector("[data-order-filter]")?.value || ""); }
});
document.querySelector("[data-staff-orders]")?.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-order-detail]");
  if (!button) return;
  try {
    const order = await request(`/api/v1/orders/${encodeURIComponent(button.dataset.orderDetail)}`);
    const card = button.closest("[data-order-card]");
    card.querySelector(".order-detail")?.remove();
    card.insertAdjacentHTML("beforeend", `<div class="order-detail"><p>${escapeHtml(order.address.name)} · ${escapeHtml(order.address.phone)} · ${escapeHtml(order.address.address)}</p><p>${order.items.map((item) => `${escapeHtml(item.name)} × ${item.qty}`).join(" · ")}</p></div>`);
    button.remove();
  } catch (error) { message(error.message); }
});

document.addEventListener("change", async (event) => {
  const input = event.target.closest("[data-qty]");
  if (!input) return;
  try {
    await request(`/api/v1/cart/items/${input.dataset.qty}`, {method:"PUT", body:JSON.stringify({qty:Number(input.value)})});
    await loadCart();
    await refreshCartCount();
  } catch (error) { message(error.message); await loadCart(); }
});

document.querySelector("[data-newsletter]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const output = document.querySelector("[data-newsletter-message]");
  try {
    const form = new FormData(event.currentTarget);
    const data = await request("/api/v1/newsletter/subscribe", {
      method:"POST",
      body:JSON.stringify({email:form.get("email"),consent:form.has("consent")})
    });
    if (output) output.textContent = data.detail;
    else alert(data.detail);
    event.currentTarget.reset();
  } catch (error) {
    if (output) output.textContent = error.message;
    else alert(error.message);
  }
});

document.querySelector("[data-login]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    const user = await request("/api/v1/auth/login", {method:"POST", body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))});
    const pending = sessionStorage.getItem("electrohub.pendingBuy");
    sessionStorage.removeItem("electrohub.pendingBuy");
    if (pending && new URLSearchParams(location.search).get("next") === "checkout") {
      const purchase = JSON.parse(pending);
      if (!Number.isInteger(purchase.product_id) || purchase.product_id < 1 || !Number.isInteger(purchase.qty) || purchase.qty < 1 || purchase.qty > 99) throw new Error("Sản phẩm mua ngay không hợp lệ. Vui lòng chọn lại sản phẩm.");
      await request("/api/v1/cart/items", {method:"POST", body:JSON.stringify(purchase)});
      location.assign("/checkout");
      return;
    }
    const nextUrl = new URLSearchParams(location.search).get("next");
    if (nextUrl && nextUrl.startsWith("/") && !nextUrl.startsWith("//")) {
      location.assign(nextUrl);
      return;
    }
    location.href = user.role === "admin" ? "/manager" : user.role === "staff" ? "/staff/orders" : "/account";
  } catch (error) { message(error.message); button.disabled = false; }
});

document.querySelector("[data-register]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form));
  if (data.password !== data.confirm_password) { message("Mật khẩu nhập lại chưa khớp."); return; }
  delete data.confirm_password;
  const submit = form.querySelector("button");
  submit.disabled = true;
  try { await request("/api/v1/auth/register", {method:"POST", body:JSON.stringify(data)}); location.href = "/account/login?registered=1"; }
  catch (error) { message(error.message); submit.disabled = false; }
});
if (document.querySelector("[data-login]") && new URLSearchParams(location.search).get("registered") === "1") message("Tạo tài khoản thành công. Vui lòng đăng nhập để mua hàng.");

document.querySelector("[data-checkout]")?.addEventListener("change", (event) => {
  if (event.target.name === "payment_method") renderPaymentConversion(checkoutTotal, checkoutVatPercent);
});

document.querySelector("[data-checkout]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector("[data-place-order]");
  submit.disabled = true;
  const tab = popPaymentTab();
  const formData = Object.fromEntries(new FormData(form));
  if (formData.name && formData.phone && formData.address) {
    try {
      localStorage.setItem("electrohub_default_shipping", JSON.stringify({
        name: formData.name,
        phone: formData.phone,
        address: formData.address,
      }));
    } catch {}
  }
  let order;
  try { order = await request("/api/v1/orders", {method:"POST", body:JSON.stringify(formData)}); }
  catch (error) { tab?.close(); message(error.message); submit.disabled = false; return; }
  const tracking = `/cart/tracking?code=${encodeURIComponent(order.code)}`;
  try {
    const payment = await request(`/api/v1/payments/orders/${encodeURIComponent(order.code)}/session`, {method:"POST", body:"{}"});
    // The gateway (VNPAY QR included) must never replace the current page.
    if (tab && !tab.closed) {
      tab.location.assign(payment.url);
      location.assign(`${tracking}&payment=opened`);
      return;
    }
    // Popup was blocked: offer an explicit link (anchors are never blocked).
    submit.disabled = false;
    message(`Đơn ${order.code} đã tạo. Trình duyệt đã chặn tab mới — dùng liên kết bên dưới để hoàn tất thanh toán.`);
    offerNewTabLink(payment.url, "Mở cổng thanh toán (tab mới) →", form);
    offerNewTabLink(tracking, "Xem trạng thái đơn hàng →", form);
  } catch (error) {
    tab?.close();
    message(`Đơn ${order.code} đã tạo. ${error.message}. Vui lòng lưu mã đơn và liên hệ cửa hàng để hoàn tất thanh toán.`);
    offerNewTabLink(tracking, "Xem đơn hàng vừa tạo →", form);
  }
});

// Anchor links with target="_blank" always work, even when window.open popups
// are blocked by the browser.
function offerNewTabLink(url, text, appendTo) {
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = text;
  link.className = "button-light";
  appendTo.append(link);
}

async function trackOrder(form) {
  const data = new FormData(form);
  const result = document.querySelector("[data-result]");
  try {
    const phone = data.get("phone");
    const order = await request(`/api/v1/orders/${encodeURIComponent(data.get("code"))}${phone ? `?phone=${encodeURIComponent(phone)}` : ""}`);
    const refundNames = {scheduled:"Chờ đủ thời hạn giữ tiền",processing:"Đang xử lý hoàn tiền",succeeded:"Đã hoàn tiền",failed:"Hoàn tiền lỗi, shop sẽ thử lại",rejected:"Shop từ chối hoàn tiền"};
    const refund = order.refund ? `<p class="refund-note">Hoàn tiền ${moneyMinor(order.refund.amount, order.refund.currency)}: ${escapeHtml(refundNames[order.refund.status] || order.refund.status)} · đủ điều kiện ${new Date(order.refund.due_at).toLocaleString("vi-VN")}</p>` : "";
    const payable = ["pending", "failed"].includes(order.payment?.status) && order.status !== "cancelled";
    const cancellable = ["pending", "confirmed"].includes(order.status);
    const paymentNote = paymentReturnNotes[new URLSearchParams(location.search).get("payment")];
    if (new URLSearchParams(location.search).get("payment") === "opened") message("Đã mở cổng thanh toán ở một tab mới. Trạng thái tại đây sẽ cập nhật sau khi bạn hoàn tất thanh toán.");
    else if (paymentNote) message(paymentNote);
    result.innerHTML = `<article class="order-summary"><h2>Đơn hàng ${escapeHtml(order.code)}</h2><p class="tag-row">${orderTag(order.status)}${paymentTag(order.payment)}</p><p>${escapeHtml(order.address.name)} · ${escapeHtml(order.address.phone)}</p><p>${escapeHtml(order.address.address)}</p>${order.items.map((item) => `<p class="summary-line"><span>${escapeHtml(item.name)} × ${item.qty}</span><strong>${money(item.line_total)}</strong></p>`).join("")}<hr>${order.vat ? `<p class="summary-line"><span>VAT</span><span>${money(order.vat)}</span></p>` : ""}<p>Tổng thanh toán: <strong>${money(order.total)}</strong></p>${refund}${payable ? `<a class="button" href="/payments/${encodeURIComponent(order.code)}">Tiếp tục thanh toán</a>` : ""}${cancellable ? `<button class="button-light" data-cancel-order="${escapeHtml(order.code)}">Hủy đơn</button>` : ""}<a href="/collections/all">Tiếp tục mua sắm →</a></article>`;
  } catch (error) { result.textContent = error.message; }
}
const trackingForm = document.querySelector("[data-track]");
trackingForm?.addEventListener("submit", (event) => { event.preventDefault(); trackOrder(event.currentTarget); });
if (trackingForm?.elements.code.value) trackOrder(trackingForm);

// A settled payment in another tab (or a focused return to this one) refreshes
// the order status and cart without reloading the page.
window.addEventListener("storage", (event) => {
  if (event.key !== "electrohub-payment") return;
  const form = document.querySelector("[data-track]");
  if (form?.elements.code.value) trackOrder(form);
  if (document.querySelector("[data-payment-summary]")) loadPaymentDemo();
});
window.addEventListener("focus", () => {
  const form = document.querySelector("[data-track]");
  if (form?.elements.code.value) trackOrder(form);
  if (document.querySelector("[data-payment-summary]")) loadPaymentDemo();
});

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-cancel-order]");
  if (!button || !confirm("Hủy đơn hàng này? Nếu đã thanh toán, shop sẽ xác nhận hoàn tiền sau thời hạn giữ tiền.")) return;
  button.disabled = true;
  try {
    await request(`/api/v1/orders/${encodeURIComponent(button.dataset.cancelOrder)}/cancel`, {method:"POST", body:JSON.stringify({reason:"Khách hủy đơn"})});
    message("Đã hủy đơn hàng.");
    const form = document.querySelector("[data-track]");
    if (form) await trackOrder(form);
  } catch (error) { message(error.message); button.disabled = false; }
});

document.querySelector("[data-campaign]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!confirm("Gửi email marketing tới tất cả người đã đăng ký?")) return;
  try {
    const result = await request("/api/v1/newsletter/send", {method:"POST", body:JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)))});
    message(result.detail);
    if (typeof loadNewsletterAdmin === "function") await loadNewsletterAdmin();
  }
  catch (error) { message(error.message); }
});

async function loadNewsletterAdmin() {
  const container = document.querySelector("[data-marketing-stats]");
  if (!container) return;

  try {
    const [subs, camps] = await Promise.all([
      request("/api/v1/admin/newsletter/subscribers?page_size=1"),
      request("/api/v1/admin/newsletter/campaigns?page_size=1"),
    ]);
    const statSubs = document.querySelector("[data-stat-subscribers]");
    const statCamps = document.querySelector("[data-stat-campaigns]");
    const badgeSubs = document.querySelector("[data-subscribers-badge]");
    const badgeCamps = document.querySelector("[data-campaigns-badge]");

    if (statSubs) statSubs.textContent = subs.total;
    if (badgeSubs) badgeSubs.textContent = subs.total;
    if (statCamps) statCamps.textContent = camps.total;
    if (badgeCamps) badgeCamps.textContent = camps.total;
  } catch (err) {
    console.error("Failed to load newsletter stats:", err);
  }

  await loadAdminSubscribers();
  await loadAdminCampaigns();
}

async function loadAdminSubscribers(query = "") {
  const tableContainer = document.querySelector("[data-subscribers-table-container]");
  if (!tableContainer) return;

  try {
    const url = `/api/v1/admin/newsletter/subscribers${query ? `?q=${encodeURIComponent(query)}` : ""}`;
    const result = await request(url);
    if (!result.items.length) {
      tableContainer.innerHTML = `<div class="empty-state"><h2>Chưa có người đăng ký nhận tin</h2><p>${query ? "Không tìm thấy email khớp với từ khóa tìm kiếm." : "Khi khách hàng nhập email ở chân trang web, danh sách sẽ hiển thị tại đây."}</p></div>`;
      return;
    }

    tableContainer.innerHTML = `
      <table class="newsletter-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Email</th>
            <th>Ngày đăng ký</th>
            <th style="text-align: right;">Hành động</th>
          </tr>
        </thead>
        <tbody>
          ${result.items.map((sub) => `
            <tr>
              <td>#${sub.id}</td>
              <td><strong>${escapeHtml(sub.email)}</strong></td>
              <td>${new Date(sub.created_at).toLocaleString("vi-VN")}</td>
              <td style="text-align: right;">
                <button type="button" class="remove-item" data-delete-sub="${sub.id}" title="Xóa người đăng ký">Xóa</button>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (error) {
    tableContainer.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

async function loadAdminCampaigns() {
  const tableContainer = document.querySelector("[data-campaigns-table-container]");
  if (!tableContainer) return;

  try {
    const result = await request("/api/v1/admin/newsletter/campaigns");
    if (!result.items.length) {
      tableContainer.innerHTML = `<div class="empty-state"><h2>Chưa có chiến dịch nào</h2><p>Các chiến dịch đã gửi qua email sẽ được lưu lại lịch sử tại đây.</p></div>`;
      return;
    }

    const statusBadge = (st) => {
      if (st === "sent") return `<span class="badge badge-sent">Đã gửi</span>`;
      if (st === "sending") return `<span class="badge badge-sending">Đang gửi</span>`;
      return `<span class="badge badge-failed">Thất bại</span>`;
    };

    tableContainer.innerHTML = `
      <table class="newsletter-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Tiêu đề chiến dịch</th>
            <th>Số người nhận</th>
            <th>Thời gian gửi</th>
            <th>Trạng thái</th>
          </tr>
        </thead>
        <tbody>
          ${result.items.map((camp) => `
            <tr>
              <td>#${camp.id}</td>
              <td><strong>${escapeHtml(camp.subject)}</strong></td>
              <td>${camp.recipient_count} người</td>
              <td>${new Date(camp.sent_at).toLocaleString("vi-VN")}</td>
              <td>${statusBadge(camp.status)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch (error) {
    tableContainer.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

const campaignPresets = {
  flash_sale: {
    subject: "⚡ [ElectroHub] FLASH SALE CUỐI TUẦN: Giảm tới 30% linh kiện & thiết bị điện tử!",
    body: `Kính gửi quý khách hàng,

Cuối tuần này, ElectroHub mang đến chương trình FLASH SALE bùng nổ với hàng loạt ưu đãi hấp dẫn dành riêng cho cộng đồng kỹ thuật & DIY:

🔥 GIẢM TỚI 30% các dòng vi điều khiển: ESP32-WROOM, Arduino Uno R3, STM32 Blue Pill.
🔥 ĐỒNG GIÁ linh kiện cảm biến: Cảm biến nhiệt ẩm DHT11, cảm biến khoảng cách HC-SR04, module Relay 5V.
🔥 MIỄN PHÍ VẬN CHUYỂN cho tất cả đơn hàng từ 300.000₫.

⏰ Thời gian áp dụng: Từ Thứ Sáu đến hết Chủ Nhật tuần này.
Số lượng linh kiện khuyến mãi có hạn, hãy nhanh tay đặt hàng ngay hôm nay để nhận ưu đãi!

ElectroHub rất hân hạnh được đồng hành cùng những dự án sáng tạo của bạn.`
  },
  new_arrival: {
    subject: "🚀 [ElectroHub] HÀNG MỚI VỀ: Khám phá các dòng module vi điều khiển & cảm biến thế hệ mới!",
    body: `Chào bạn,

ElectroHub xin thông báo kho hàng vừa cập bến các sản phẩm và linh kiện điện tử mới nhất phục vụ cho các dự án IoT, Robotics và tự động hóa:

✨ Module ESP32-S3 Dual-Core hiệu năng cao, tích hợp AI & kết nối không dây mạnh mẽ.
✨ Mạch sạc nhanh Type-C và module hạ áp Buck đa năng thế hệ mới.
✨ Cảm biến môi trường độ chính xác cao BME280 và module đo dòng INA219.

Tất cả sản phẩm đều được kiểm tra chất lượng kỹ lưỡng và có sẵn số lượng lớn tại kho.

👉 Xem ngay danh mục sản phẩm mới để không bỏ lỡ linh kiện cho dự án của bạn!`
  },
  voucher_gift: {
    subject: "🎁 [ElectroHub] TẶNG BẠN VOUCHER ĐẶC QUYỀN: Giảm ngay 15% cho đơn hàng tiếp theo!",
    body: `Kính gửi quý khách hàng thân thiết,

Để cảm ơn sự tin tưởng và đồng hành của bạn cùng ElectroHub trong suốt thời gian qua, chúng tôi xin gửi tặng bạn món quà tri ân đặc biệt:

🎟 Mã giảm giá: TRIAN2026
💰 Ưu đãi: Giảm 15% trên tổng giá trị đơn hàng (tối đa 100.000₫).
📅 Hạn sử dụng: Đến hết ngày 30 của tháng này.

Mã ưu đãi áp dụng cho tất cả sản phẩm đang có tại website ElectroHub: từ bo mạch phát triển, cảm biến, linh kiện thụ động đến phụ kiện nguồn.

Hãy nhập mã TRIAN2026 tại bước giỏ hàng hoặc thanh toán để nhận ưu đãi nhé!`
  },
  store_notice: {
    subject: "📢 [ElectroHub] THÔNG BÁO: Cập nhật chính sách giao hàng và bảo hành linh kiện",
    body: `Kính gửi quý khách hàng,

Nhằm nâng cao chất lượng dịch vụ và mang lại trải nghiệm mua sắm tốt nhất, ElectroHub xin trân trọng thông báo một số cập nhật mới:

📦 Thời gian giao hàng: Giao hàng hỏa tốc trong 2-4 giờ tại nội thành và 1-3 ngày trên toàn quốc.
🛡 Chính sách bảo hành: Hỗ trợ 1 đổi 1 trong vòng 7 ngày đối với các bo mạch, module phát hiện lỗi từ nhà sản xuất.
💬 Kênh hỗ trợ trực tuyến: Đội ngũ kỹ thuật hỗ trợ tư vấn linh kiện và sơ đồ đấu nối 24/7.

Mọi thắc mắc cần hỗ trợ, quý khách vui lòng liên hệ qua fanpage hoặc hotline của ElectroHub.

Trân trọng cảm ơn sự đồng hành của quý khách!`
  }
};

function applyCampaignTemplate(templateId) {
  const form = document.querySelector("[data-campaign]");
  if (!form || !templateId || !campaignPresets[templateId]) return;

  const tpl = campaignPresets[templateId];
  const subjectInput = form.querySelector('[name="subject"]');
  const bodyInput = form.querySelector('[name="body"]');

  if (subjectInput) subjectInput.value = tpl.subject;
  if (bodyInput) bodyInput.value = tpl.body;

  // Auto trigger preview
  document.querySelector("[data-preview-btn]")?.click();
}

document.querySelector("[data-template-select]")?.addEventListener("change", (e) => {
  if (e.target.value) applyCampaignTemplate(e.target.value);
});

document.querySelector("[data-apply-template]")?.addEventListener("click", () => {
  const select = document.querySelector("[data-template-select]");
  if (select && select.value) applyCampaignTemplate(select.value);
  else message("Vui lòng chọn một mẫu email từ danh sách.");
});

document.querySelectorAll("[data-tab-target]").forEach((tabBtn) => {
  tabBtn.addEventListener("click", () => {
    const target = tabBtn.dataset.tabTarget;
    document.querySelectorAll("[data-tab-target]").forEach((btn) => btn.classList.remove("is-active"));
    tabBtn.classList.add("is-active");

    document.querySelectorAll("[data-tab-pane]").forEach((pane) => {
      pane.hidden = pane.dataset.tabPane !== target;
    });

    if (target === "subscribers") loadAdminSubscribers();
    if (target === "history") loadAdminCampaigns();
  });
});

document.querySelector("[data-preview-btn]")?.addEventListener("click", async () => {
  const form = document.querySelector("[data-campaign]");
  const container = document.querySelector("[data-preview-container]");
  if (!form || !container) return;

  const subject = form.querySelector('[name="subject"]')?.value?.trim();
  const body = form.querySelector('[name="body"]')?.value?.trim();

  if (!subject || !body) {
    message("Vui lòng nhập cả Tiêu đề và Nội dung để xem trước.");
    return;
  }

  container.innerHTML = `<p style="text-align: center; color: var(--muted); padding-top: 60px;">Đang tạo bản xem trước…</p>`;
  try {
    const res = await request("/api/v1/admin/newsletter/preview", {
      method: "POST",
      body: JSON.stringify({ subject, body }),
    });
    const iframe = document.createElement("iframe");
    iframe.style.width = "100%";
    iframe.style.height = "480px";
    iframe.style.border = "none";
    iframe.srcdoc = res.html;
    container.innerHTML = "";
    container.appendChild(iframe);
  } catch (error) {
    container.innerHTML = `<p style="color: #b54c28;">Lỗi xem trước: ${escapeHtml(error.message)}</p>`;
  }
});

document.querySelector("[data-sub-search]")?.addEventListener("input", (e) => {
  clearTimeout(window._subSearchTimer);
  window._subSearchTimer = setTimeout(() => {
    loadAdminSubscribers(e.target.value.trim());
  }, 300);
});

document.querySelector("[data-sub-refresh]")?.addEventListener("click", () => {
  const searchInput = document.querySelector("[data-sub-search]");
  loadAdminSubscribers(searchInput?.value.trim() || "");
});

document.querySelector("[data-campaigns-refresh]")?.addEventListener("click", () => {
  loadAdminCampaigns();
});

document.querySelector("[data-subscribers-table-container]")?.addEventListener("click", async (e) => {
  const delBtn = e.target.closest("[data-delete-sub]");
  if (!delBtn) return;
  const id = delBtn.dataset.deleteSub;
  if (!confirm("Bạn có chắc chắn muốn xóa người đăng ký này?")) return;

  delBtn.disabled = true;
  try {
    await request(`/api/v1/admin/newsletter/subscribers/${id}`, { method: "DELETE" });
    message("Đã xóa người đăng ký.");
    await loadNewsletterAdmin();
  } catch (error) {
    message(error.message);
    delBtn.disabled = false;
  }
});

document.querySelector("[data-unsubscribe]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  try {
    const response = await fetch("/api/v1/newsletter/unsubscribe", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded","X-CSRF-Token":form.get("csrf_token")}, body:new URLSearchParams({token:form.get("token")})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Không thể hủy đăng ký");
    message(result.detail);
  } catch (error) { message(error.message); }
});

function toSlug(str) {
  return (str || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[đĐ]/g, "d")
    .replace(/[^a-z0-9\s-]/g, "")
    .trim()
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function initAdminTinyMCE() {
  const textarea = document.getElementById("admin-product-description");
  if (!textarea) return;
  if (typeof tinymce === "undefined") {
    setTimeout(initAdminTinyMCE, 300);
    return;
  }
  if (tinymce.get("admin-product-description")) return;

  tinymce.init({
    selector: "#admin-product-description",
    height: 320,
    menubar: false,
    statusbar: true,
    branding: false,
    promotion: false,
    elementpath: false,
    plugins: "advlist autolink lists link table code wordcount",
    toolbar:
      "undo redo | blocks | bold italic underline | bullist numlist | table | link | code",
    content_style:
      "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #2d3748; padding: 12px; } table { width: 100%; border-collapse: collapse; } th, td { border: 1px solid #cbd5e0; padding: 6px 10px; }",
    setup(editor) {
      editor.on("init", () => {
        if (textarea.value) {
          editor.setContent(textarea.value);
        }
      });
      editor.on("change keyup input NodeChange", () => {
        editor.save();
        updateLiveProductPreview();
      });
    },
  });
}

function switchProductTab(target) {
  document.querySelectorAll("[data-tab-product-target]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tabProductTarget === target);
  });
  document.querySelectorAll("[data-tab-product-pane]").forEach((pane) => {
    pane.hidden = pane.dataset.tabProductPane !== target;
  });
  if (target === "editor") {
    initAdminTinyMCE();
  }
}

function updateLiveProductPreview() {
  const form = document.querySelector("[data-admin-product]");
  if (!form) return;
  const name = form.elements.name?.value.trim() || "Tên sản phẩm mẫu";
  const slug = form.elements.slug?.value.trim() || "ten-san-pham-mau";
  const sku = form.elements.sku?.value.trim() || "SKU-PROD";
  const price = Number(form.elements.price?.value || 0);
  const salePrice = form.elements.sale_price?.value ? Number(form.elements.sale_price.value) : null;
  const stock = Number(form.elements.stock?.value || 0);
  const imageUrl = form.elements.image_url?.value.trim() || "/static/img/product-placeholder.svg";

  let desc = "";
  if (typeof tinymce !== "undefined" && tinymce.get("admin-product-description")) {
    desc = tinymce.get("admin-product-description").getContent().trim();
  } else if (form.elements.description) {
    desc = form.elements.description.value.trim();
  }

  document.querySelectorAll("[data-live-name]").forEach((el) => { el.textContent = name; });
  const liveSlugUrl = document.querySelector("[data-live-slug-url]");
  if (liveSlugUrl) liveSlugUrl.textContent = slug;
  const slugPreview = document.querySelector("[data-slug-preview]");
  if (slugPreview) slugPreview.textContent = slug;
  const liveTitle = document.querySelector("[data-live-title]");
  if (liveTitle) liveTitle.textContent = name;
  const liveSku = document.querySelector("[data-live-sku]");
  if (liveSku) liveSku.textContent = sku;

  const imgThumb = document.querySelector("[data-image-preview]");
  if (imgThumb) {
    imgThumb.src = imageUrl;
    imgThumb.alt = name;
  }
  const displayNameEl = document.querySelector("[data-image-display-name]");
  if (displayNameEl) {
    if (!imageUrl || imageUrl.includes("product-placeholder.svg")) {
      displayNameEl.textContent = "Chưa chọn ảnh (dùng ảnh mặc định)";
      displayNameEl.style.background = "#f1f5f9";
      displayNameEl.style.color = "#64748b";
    } else {
      const filename = imageUrl.split("/").pop() || imageUrl;
      displayNameEl.textContent = filename;
      displayNameEl.style.background = "#dcfce7";
      displayNameEl.style.color = "#15803d";
    }
  }
  const liveImg = document.querySelector("[data-live-img]");
  if (liveImg) {
    liveImg.src = imageUrl;
    liveImg.alt = name;
  }

  // Live Gallery Thumbnails in Storefront Preview
  const galleryInputs = Array.from(document.querySelectorAll("[data-gallery-url]"));
  const galleryUrls = galleryInputs.map((inp) => inp.value.trim()).filter(Boolean);
  const allImages = [imageUrl, ...galleryUrls];

  const liveGalleryThumbs = document.querySelector("[data-live-gallery-thumbs]");
  const liveNavPrev = document.querySelector("[data-live-gallery-nav='prev']");
  const liveNavNext = document.querySelector("[data-live-gallery-nav='next']");

  if (liveGalleryThumbs) {
    if (allImages.length > 1) {
      liveGalleryThumbs.style.display = "flex";
      liveGalleryThumbs.innerHTML = allImages
        .map(
          (u, idx) => `
        <button type="button" class="gallery-thumb${idx === 0 ? " is-active" : ""}" data-live-thumb-src="${escapeHtml(u)}" style="padding:2px;" aria-label="Xem ảnh ${idx + 1}">
          <img src="${escapeHtml(u)}" alt="" width="56" height="56" style="width:56px;height:56px;object-fit:contain;">
        </button>`
        )
        .join("");

      liveGalleryThumbs.querySelectorAll(".gallery-thumb").forEach((thumbBtn) => {
        thumbBtn.addEventListener("click", (e) => {
          if (e.button !== undefined && e.button !== 0) return;
          const targetSrc = thumbBtn.dataset.liveThumbSrc;
          if (liveImg && targetSrc) liveImg.src = targetSrc;
          liveGalleryThumbs.querySelectorAll(".gallery-thumb").forEach((t) => t.classList.remove("is-active"));
          thumbBtn.classList.add("is-active");
        });
      });

      if (liveNavPrev) liveNavPrev.style.display = "flex";
      if (liveNavNext) liveNavNext.style.display = "flex";
    } else {
      liveGalleryThumbs.style.display = "none";
      liveGalleryThumbs.innerHTML = "";
      if (liveNavPrev) liveNavPrev.style.display = "none";
      if (liveNavNext) liveNavNext.style.display = "none";
    }
  }

  const defaultDescHtml = "<p>Mô tả sản phẩm sẽ hiển thị tại đây khi bạn nhập vào form bên trên.</p>";
  const liveDesc = document.querySelector("[data-live-desc]");
  if (liveDesc) liveDesc.innerHTML = desc || defaultDescHtml;
  const liveInfo = document.querySelector("[data-live-info-text]");
  if (liveInfo) liveInfo.innerHTML = desc || "<p>Sản phẩm chất lượng cao tại ElectroHub, đáp ứng tiêu chuẩn nghiên cứu và lắp ráp mạch điện tử.</p>";

  const priceHint = document.querySelector("[data-price-hint]");
  if (priceHint) {
    if (price > 0) {
      priceHint.innerHTML = `Định dạng: <strong style="color:var(--ink);">${money(price)}</strong>`;
      priceHint.className = "field-hint is-ok";
    } else {
      priceHint.innerHTML = "Nhập giá bán chính thức (VND)";
      priceHint.className = "field-hint";
    }
  }

  const salePriceHint = document.querySelector("[data-sale-price-hint]");
  if (salePriceHint) {
    if (salePrice !== null) {
      if (salePrice >= price && price > 0) {
        salePriceHint.innerHTML = `Giá khuyến mãi phải nhỏ hơn giá gốc (${money(price)})`;
        salePriceHint.className = "field-hint is-error";
      } else if (salePrice < price && price > 0) {
        const pct = Math.round((1 - salePrice / price) * 100);
        salePriceHint.innerHTML = `Định dạng: <strong style="color:var(--accent);">${money(salePrice)}</strong> (Tiết kiệm ${pct}%)`;
        salePriceHint.className = "field-hint is-ok";
      } else {
        salePriceHint.innerHTML = `Định dạng: ${money(salePrice)}`;
        salePriceHint.className = "field-hint";
      }
    } else {
      salePriceHint.innerHTML = "Để trống nếu sản phẩm không có chương trình giảm giá";
      salePriceHint.className = "field-hint";
    }
  }

  const livePrice = document.querySelector("[data-live-price]");
  const liveOrig = document.querySelector("[data-live-original]");
  const liveDisc = document.querySelector("[data-live-discount]");

  if (salePrice && salePrice < price) {
    if (livePrice) livePrice.textContent = money(salePrice);
    if (liveOrig) {
      liveOrig.textContent = money(price);
      liveOrig.style.display = "inline";
    }
    if (liveDisc) {
      const pct = Math.round((1 - salePrice / price) * 100);
      liveDisc.textContent = `Giảm ${pct}%`;
      liveDisc.style.display = "inline-block";
    }
  } else {
    if (livePrice) livePrice.textContent = money(price || 0);
    if (liveOrig) liveOrig.style.display = "none";
    if (liveDisc) liveDisc.style.display = "none";
  }

  const liveStock = document.querySelector("[data-live-stock]");
  const btnAdd = document.querySelector("[data-live-btn-add]");
  const btnBuy = document.querySelector("[data-live-btn-buy]");
  if (liveStock) {
    if (stock <= 0) {
      liveStock.textContent = "Hết hàng";
      liveStock.style.color = "#d9381e";
      if (btnAdd) btnAdd.disabled = true;
      if (btnBuy) btnBuy.disabled = true;
    } else {
      liveStock.textContent = `Còn hàng · ${stock} sản phẩm`;
      liveStock.style.color = "#2e7d32";
      if (btnAdd) btnAdd.disabled = false;
      if (btnBuy) btnBuy.disabled = false;
    }
  }
}

function renderAdminProductsList() {
  const list = document.querySelector("[data-admin-products]");
  if (!list) return;
  const items = window.adminProducts || [];
  const searchInput = document.querySelector("[data-admin-product-search]");
  const stockFilter = document.querySelector("[data-admin-stock-filter]");
  const query = (searchInput?.value || "").toLowerCase().trim();
  const filter = stockFilter?.value || "";

  const filtered = items.filter((p) => {
    if (query) {
      const matchName = (p.name || "").toLowerCase().includes(query);
      const matchSku = (p.sku || "").toLowerCase().includes(query);
      const matchSlug = (p.slug || "").toLowerCase().includes(query);
      if (!matchName && !matchSku && !matchSlug) return false;
    }
    if (filter === "in_stock" && (p.stock || 0) <= 0) return false;
    if (filter === "out_of_stock" && (p.stock || 0) > 0) return false;
    if (filter === "sale" && (!p.sale_price || p.sale_price >= p.price)) return false;
    return true;
  });

  const totalBadge = document.querySelector("[data-product-total-badge]");
  if (totalBadge) totalBadge.textContent = items.length;

  if (!filtered.length) {
    list.innerHTML = `<p style="grid-column:1/-1;text-align:center;padding:32px;color:var(--muted);">${items.length === 0 ? "Chưa có sản phẩm nào trong kho." : "Không tìm thấy sản phẩm phù hợp bộ lọc."}</p>`;
    return;
  }

  list.innerHTML = filtered.map((product) => {
    const isSale = product.sale_price && product.sale_price < product.price;
    const stockBadge = product.stock <= 0
      ? `<span style="font-size:0.75rem;padding:3px 10px;border-radius:12px;background:#fee2e2;color:#b91c1c;font-weight:600;display:inline-block;white-space:nowrap;">Hết hàng</span>`
      : product.stock <= 10
        ? `<span style="font-size:0.75rem;padding:3px 10px;border-radius:12px;background:#fef3c7;color:#b45309;font-weight:600;display:inline-block;white-space:nowrap;">Sắp hết: ${product.stock}</span>`
        : `<span style="font-size:0.75rem;padding:3px 10px;border-radius:12px;background:#dcfce7;color:#15803d;font-weight:600;display:inline-block;white-space:nowrap;">Còn hàng: ${product.stock}</span>`;

    const priceHtml = isSale
      ? `<strong style="color:var(--accent);font-size:1.05rem;">${money(product.sale_price)}</strong> <del style="color:var(--muted);font-size:0.86rem;margin-left:6px;">${money(product.price)}</del>`
      : `<strong style="font-size:1.05rem;color:var(--ink);">${money(product.price)}</strong>`;

    return `<article class="product-card" style="display:flex;flex-direction:column;justify-content:space-between;border:1px solid #e2e8f0;border-radius:8px;padding:14px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,0.03);">
      <div>
        <!-- Dòng 1: Khung ảnh sản phẩm -->
        <div style="background:#f8fafb;border-radius:6px;padding:8px;display:flex;align-items:center;justify-content:center;height:160px;margin-bottom:10px;overflow:hidden;">
          <img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" width="560" height="420" loading="lazy" style="max-height:100%;max-width:100%;object-fit:contain;">
        </div>

        <!-- Dòng 2: Mã SKU riêng 1 dòng -->
        <div style="margin-bottom:4px;">
          <span style="font-size:0.75rem;padding:3px 8px;border-radius:4px;background:#edf2f7;color:#4a5568;font-family:monospace;font-weight:600;display:inline-block;white-space:nowrap;">${escapeHtml(product.sku)}</span>
        </div>

        <!-- Dòng 3: Tình trạng tồn kho riêng 1 dòng -->
        <div style="margin-bottom:8px;">
          ${stockBadge}
        </div>

        <!-- Dòng 4: Tên sản phẩm riêng dòng -->
        <h2 style="font-size:0.96rem;margin:4px 0 6px;line-height:1.4;font-weight:650;color:var(--ink);">${escapeHtml(product.name)}</h2>

        <!-- Dòng 5: Giá tiền riêng dòng -->
        <div style="margin-bottom:14px;">${priceHtml}</div>
      </div>

      <!-- Dòng 6: Các nút thao tác xếp theo từng dòng xuống, tránh để đôi -->
      <div style="display:flex;flex-direction:column;gap:6px;padding-top:10px;border-top:1px solid #f1f5f9;margin-top:auto;">
        <button type="button" class="button-admin-light" data-edit-product="${product.id}" style="width:100%;padding:8px 12px;font-size:0.86rem;font-weight:600;white-space:nowrap;">Chỉnh sửa</button>
        <a href="/products/${encodeURIComponent(product.slug)}" target="_blank" class="button-admin-light" style="width:100%;padding:8px 12px;font-size:0.86rem;text-decoration:none;display:inline-flex;align-items:center;justify-content:center;white-space:nowrap;" title="Xem sản phẩm bán lẻ">Xem trên web</a>
      </div>
    </article>`;
  }).join("");
}

async function loadAdminProducts() {
  const list = document.querySelector("[data-admin-products]");
  if (!list) return;
  try {
    const result = await request("/api/v1/admin/products");
    window.adminProducts = result.items;
    renderAdminProductsList();
    updateLiveProductPreview();
  } catch (error) { message(error.message); }
}

document.querySelectorAll("[data-tab-product-target]").forEach((btn) => {
  btn.addEventListener("click", () => switchProductTab(btn.dataset.tabProductTarget));
});

document.querySelector("[data-switch-to-create]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-admin-product]");
  if (form) {
    form.reset();
    form.elements.id.value = "";
    form.elements.image_url.value = "/static/img/product-placeholder.svg";
  }
  const galleryContainer = document.querySelector("[data-gallery-container]");
  if (galleryContainer) galleryContainer.innerHTML = "";
  if (typeof tinymce !== "undefined" && tinymce.get("admin-product-description")) {
    tinymce.get("admin-product-description").setContent("");
  }
  const heading = document.querySelector("[data-editor-heading]");
  if (heading) heading.textContent = "Tạo sản phẩm mới";
  const label = document.querySelector("[data-editor-tab-label]");
  if (label) label.textContent = "Tạo sản phẩm mới";
  switchProductTab("editor");
  updateLiveProductPreview();
  form?.elements.name?.focus();
});

document.querySelectorAll("[data-back-to-list]").forEach((btn) => {
  btn.addEventListener("click", () => switchProductTab("list"));
});

document.querySelector("[data-admin-product-search]")?.addEventListener("input", renderAdminProductsList);
document.querySelector("[data-admin-stock-filter]")?.addEventListener("change", renderAdminProductsList);

const adminProductForm = document.querySelector("[data-admin-product]");
if (adminProductForm) {
  adminProductForm.addEventListener("input", (event) => {
    if (event.target.name === "name" && !adminProductForm.elements.id.value) {
      adminProductForm.elements.slug.value = toSlug(event.target.value);
    }
    if (event.target.name === "sku") {
      event.target.value = event.target.value.toUpperCase();
    }
    updateLiveProductPreview();
  });
  adminProductForm.addEventListener("change", updateLiveProductPreview);
}

// Helper: Auto-generate slug from name
document.querySelector("[data-generate-slug]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-admin-product]");
  if (!form) return;
  const name = form.elements.name?.value.trim() || "";
  if (!name) {
    message("Vui lòng nhập tên sản phẩm trước khi tạo slug.");
    return;
  }
  form.elements.slug.value = toSlug(name);
  updateLiveProductPreview();
});

// Helper: Auto-suggest SKU
document.querySelector("[data-generate-sku]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-admin-product]");
  if (!form) return;
  const name = form.elements.name?.value.trim() || "";
  if (!name) {
    message("Vui lòng nhập tên sản phẩm trước khi gợi ý SKU.");
    return;
  }
  const slugClean = toSlug(name).toUpperCase();
  const parts = slugClean.split("-").filter(Boolean);
  let suggested = "";
  if (parts.length <= 3) {
    suggested = parts.join("-");
  } else {
    suggested = parts.slice(0, 4).join("-");
  }
  form.elements.sku.value = suggested.substring(0, 32);
  updateLiveProductPreview();
});

// Helper: Stock preset chips
document.querySelectorAll("[data-preset-stock]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const form = document.querySelector("[data-admin-product]");
    if (!form) return;
    const val = parseInt(btn.dataset.presetStock, 10);
    if (val === 0) {
      form.elements.stock.value = 0;
    } else {
      const cur = parseInt(form.elements.stock.value, 10) || 0;
      form.elements.stock.value = cur + val;
    }
    updateLiveProductPreview();
  });
});

// Helper: Toggle manual URL box
document.querySelector("[data-toggle-manual-url]")?.addEventListener("click", () => {
  const box = document.querySelector("[data-manual-url-box]");
  if (box) box.style.display = box.style.display === "none" ? "block" : "none";
});

// Helper: Upload Primary Image from Device
document.querySelector("[data-trigger-upload-primary]")?.addEventListener("click", () => {
  document.querySelector("[data-upload-primary]")?.click();
});

document.querySelector("[data-upload-primary]")?.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  const statusEl = document.querySelector("[data-upload-primary-status]");
  if (statusEl) {
    statusEl.textContent = "Đang tải ảnh lên...";
    statusEl.style.color = "var(--accent)";
  }
  const formData = new FormData();
  formData.append("file", file);
  try {
    const result = await request("/api/v1/admin/products/upload-image", {
      method: "POST",
      body: formData,
    });
    const form = document.querySelector("[data-admin-product]");
    if (form) form.elements.image_url.value = result.url;
    if (statusEl) {
      statusEl.textContent = "Đã tải xong";
      statusEl.style.color = "#15803d";
    }
    setTimeout(() => { if (statusEl) statusEl.textContent = ""; }, 3000);
    updateLiveProductPreview();
  } catch (error) {
    if (statusEl) {
      statusEl.textContent = `Lỗi: ${error.message}`;
      statusEl.style.color = "#b91c1c";
    }
    message(error.message);
  } finally {
    event.target.value = "";
  }
});

// Helper: Upload Multiple Secondary Gallery Images from Device
document.querySelector("[data-trigger-upload-gallery]")?.addEventListener("click", () => {
  document.querySelector("[data-upload-gallery]")?.click();
});

document.querySelector("[data-upload-gallery]")?.addEventListener("change", async (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  message(`Đang tải lên ${files.length} ảnh phụ...`);
  for (const file of files) {
    const formData = new FormData();
    formData.append("file", file);
    try {
      const result = await request("/api/v1/admin/products/upload-image", {
        method: "POST",
        body: formData,
      });
      addGalleryRow(result.url, file.name);
    } catch (error) {
      message(`Không thể tải ${file.name}: ${error.message}`);
    }
  }
  event.target.value = "";
  updateLiveProductPreview();
});

// Helper: Visual Library Modal
let currentLibraryTarget = "primary";

async function openImageLibrary(target = "primary") {
  currentLibraryTarget = target;
  const dialog = document.querySelector("[data-image-library-dialog]");
  const grid = document.querySelector("[data-library-grid]");
  if (!dialog || !grid) return;

  grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;color:var(--muted);padding:24px;">Đang tải kho ảnh mẫu...</p>`;
  if (typeof dialog.showModal === "function") {
    dialog.showModal();
  } else {
    dialog.style.display = "block";
  }

  try {
    const res = await request("/api/v1/admin/products/library-images");
    const items = res.items || [];
    if (!items.length) {
      grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;color:var(--muted);padding:24px;">Chưa có ảnh nào trong kho.</p>`;
      return;
    }
    grid.innerHTML = items
      .map(
        (img) => `
      <div class="library-item-card" data-select-library-img="${escapeHtml(img.url)}" style="border:1px solid #e2e8f0;border-radius:8px;padding:8px;cursor:pointer;background:#fff;text-align:center;transition:all 0.15s;display:flex;flex-direction:column;align-items:center;">
        <div style="width:110px;height:110px;display:flex;align-items:center;justify-content:center;background:#f8fafb;border-radius:6px;overflow:hidden;margin-bottom:6px;">
          <img src="${escapeHtml(img.url)}" alt="${escapeHtml(img.name)}" style="max-width:100%;max-height:100%;object-fit:contain;">
        </div>
        <span style="font-size:0.75rem;font-weight:600;color:var(--ink);line-height:1.2;word-break:break-word;">${escapeHtml(img.name)}</span>
      </div>`
      )
      .join("");

    grid.querySelectorAll("[data-select-library-img]").forEach((card) => {
      card.addEventListener("click", () => {
        const url = card.dataset.selectLibraryImg;
        if (currentLibraryTarget === "primary") {
          const form = document.querySelector("[data-admin-product]");
          if (form) form.elements.image_url.value = url;
        } else {
          addGalleryRow(url, "");
        }
        updateLiveProductPreview();
        closeImageLibrary();
      });
      card.addEventListener("mouseenter", () => {
        card.style.borderColor = "var(--accent)";
        card.style.boxShadow = "0 4px 10px rgba(0,0,0,0.08)";
      });
      card.addEventListener("mouseleave", () => {
        card.style.borderColor = "#e2e8f0";
        card.style.boxShadow = "none";
      });
    });
  } catch (error) {
    grid.innerHTML = `<p style="grid-column:1/-1;text-align:center;color:#c53030;padding:24px;">Lỗi tải ảnh: ${escapeHtml(error.message)}</p>`;
  }
}

function closeImageLibrary() {
  const dialog = document.querySelector("[data-image-library-dialog]");
  if (!dialog) return;
  if (typeof dialog.close === "function") {
    dialog.close();
  } else {
    dialog.style.display = "none";
  }
}

document.querySelectorAll("[data-open-library]").forEach((btn) => {
  btn.addEventListener("click", () => openImageLibrary(btn.dataset.openLibrary || "primary"));
});
document.querySelector("[data-close-library]")?.addEventListener("click", closeImageLibrary);
document.querySelector("[data-image-library-dialog]")?.addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeImageLibrary();
});

// Helper: Dynamic Gallery Row Management
function addGalleryRow(url = "", alt = "") {
  const container = document.querySelector("[data-gallery-container]");
  if (!container) return;
  const row = document.createElement("div");
  row.className = "gallery-edit-row";
  row.style.cssText =
    "display:flex;gap:10px;align-items:center;background:#fff;padding:8px 12px;border-radius:6px;border:1px solid #dce3e5;";
  const defaultThumb = url || "/static/img/product-placeholder.svg";
  row.innerHTML = `
    <img src="${escapeHtml(defaultThumb)}" alt="Ảnh phụ" style="width:42px;height:42px;border:1px solid #e2e8f0;border-radius:4px;object-fit:contain;background:#fff;flex-shrink:0;">
    <input type="text" data-gallery-url value="${escapeHtml(url)}" placeholder="Đường dẫn ảnh phụ (/static/img/... hoặc https://...)" maxlength="500" style="flex:1;font-size:0.86rem;padding:7px 10px;border:1px solid #cbd5e0;border-radius:4px;">
    <button type="button" data-remove-gallery-row class="button-admin-light" style="padding:6px 12px;color:#c53030;border-color:#fca5a5;font-size:0.82rem;flex-shrink:0;" title="Xóa ảnh phụ này">Xóa</button>
  `;
  const imgEl = row.querySelector("img");
  const inputEl = row.querySelector("[data-gallery-url]");
  inputEl.addEventListener("input", () => {
    imgEl.src = inputEl.value.trim() || "/static/img/product-placeholder.svg";
    updateLiveProductPreview();
  });
  row.querySelector("[data-remove-gallery-row]").addEventListener("click", () => {
    row.remove();
    updateLiveProductPreview();
  });
  container.appendChild(row);
  updateLiveProductPreview();
}

const GALLERY_PRESETS = {
  "arduino-uno": [
    "/static/img/products/arduino-uno-1.png",
    "/static/img/products/arduino-uno-2.png",
    "/static/img/products/arduino-uno-3.png",
  ],
  "esp32-devkit": [
    "/static/img/products/esp32-devkit-1.png",
    "/static/img/products/esp32-devkit-2.png",
  ],
  "dht22": [
    "/static/img/products/dht22-1.png",
    "/static/img/products/dht22-2.png",
    "/static/img/products/dht22-3.png",
  ],
};

document.querySelectorAll("[data-preset-gallery]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const key = btn.dataset.presetGallery;
    const container = document.querySelector("[data-gallery-container]");
    if (!container) return;
    if (key === "clear") {
      container.innerHTML = "";
      updateLiveProductPreview();
      return;
    }
    const urls = GALLERY_PRESETS[key] || [];
    urls.forEach((u) => addGalleryRow(u));
  });
});

document.querySelector("[data-add-gallery-item]")?.addEventListener("click", () => {
  addGalleryRow("");
});

document.querySelector("[data-live-gallery-nav='prev']")?.addEventListener("click", () => {
  const thumbs = Array.from(document.querySelectorAll("[data-live-gallery-thumbs] .gallery-thumb"));
  if (thumbs.length <= 1) return;
  const currentIdx = thumbs.findIndex((t) => t.classList.contains("is-active"));
  const prevIdx = (currentIdx - 1 + thumbs.length) % thumbs.length;
  thumbs[prevIdx]?.click();
});

document.querySelector("[data-live-gallery-nav='next']")?.addEventListener("click", () => {
  const thumbs = Array.from(document.querySelectorAll("[data-live-gallery-thumbs] .gallery-thumb"));
  if (thumbs.length <= 1) return;
  const currentIdx = thumbs.findIndex((t) => t.classList.contains("is-active"));
  const nextIdx = (currentIdx + 1) % thumbs.length;
  thumbs[nextIdx]?.click();
});

// Helper: Insert standard product description template
document.querySelector("[data-insert-template]")?.addEventListener("click", () => {
  const template = `<h3>Đặc điểm nổi bật</h3>
<ul>
  <li>Thiết kế nhỏ gọn, độ bền cao, hoạt động ổn định và tiết kiệm năng lượng.</li>
  <li>Dễ dàng kết nối và tương thích tốt với các hệ sinh thái vi điều khiển phổ biến.</li>
</ul>
<h3>Thông số kỹ thuật</h3>
<ul>
  <li><strong>Điện áp hoạt động:</strong> 3.3V - 5V DC</li>
  <li><strong>Chuẩn giao tiếp:</strong> I2C / SPI / UART</li>
  <li><strong>Nhiệt độ hoạt động:</strong> -20°C đến 70°C</li>
</ul>
<h3>Ứng dụng thực tế</h3>
<p>Thích hợp cho các dự án IoT, thiết bị nhà thông minh, tự động hóa và học tập kỹ thuật điện tử.</p>`;

  if (typeof tinymce !== "undefined" && tinymce.get("admin-product-description")) {
    tinymce.get("admin-product-description").setContent(template);
  } else {
    const textarea = document.getElementById("admin-product-description");
    if (textarea) textarea.value = template;
  }
  updateLiveProductPreview();
});

document.querySelector("[data-admin-product]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formEl = event.currentTarget;
  if (typeof tinymce !== "undefined") {
    tinymce.triggerSave();
  }
  const form = new FormData(formEl);
  const id = form.get("id");
  const product = Object.fromEntries(form);
  product.price = Number(product.price);
  product.sale_price = product.sale_price === "" ? null : Number(product.sale_price);
  product.stock = Number(product.stock);
  delete product.id;

  // Collect gallery images
  const galleryInputs = Array.from(formEl.querySelectorAll("[data-gallery-url]"));
  const galleryUrls = galleryInputs.map((i) => i.value.trim()).filter(Boolean);
  product.images = galleryUrls.map((u, idx) => ({
    url: u,
    alt: product.name,
    sort: idx,
  }));

  if (product.sale_price !== null && product.sale_price >= product.price) {
    message("Giá khuyến mãi phải nhỏ hơn giá gốc.");
    return;
  }

  const submitBtn = formEl.querySelector("[data-save-btn]");
  const originalBtnText = submitBtn ? submitBtn.textContent : "Lưu sản phẩm";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Đang lưu sản phẩm...";
  }

  try {
    await request(id ? `/api/v1/admin/products/${id}` : "/api/v1/admin/products", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(product),
    });
    formEl.reset();
    formEl.elements.image_url.value = "/static/img/product-placeholder.svg";
    formEl.elements.id.value = "";
    const galleryContainer = document.querySelector("[data-gallery-container]");
    if (galleryContainer) galleryContainer.innerHTML = "";
    if (typeof tinymce !== "undefined" && tinymce.get("admin-product-description")) {
      tinymce.get("admin-product-description").setContent("");
    }
    message(id ? "Đã cập nhật sản phẩm thành công." : "Đã tạo sản phẩm mới thành công.");
    await loadAdminProducts();
    switchProductTab("list");
  } catch (error) {
    message(error.message);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = originalBtnText;
    }
  }
});

document.querySelector("[data-admin-products]")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-edit-product]");
  if (!button) return;
  const product = window.adminProducts?.find((item) => item.id === Number(button.dataset.editProduct));
  if (!product) return;
  const form = document.querySelector("[data-admin-product]");
  if (!form) return;
  for (const [key, value] of Object.entries(product)) {
    if (form.elements[key]) form.elements[key].value = value ?? "";
  }
  const galleryContainer = document.querySelector("[data-gallery-container]");
  if (galleryContainer) {
    galleryContainer.innerHTML = "";
    if (product.images && product.images.length) {
      product.images.forEach((img) => addGalleryRow(img.url, img.alt));
    }
  }
  if (typeof tinymce !== "undefined" && tinymce.get("admin-product-description")) {
    tinymce.get("admin-product-description").setContent(product.description || "");
  }
  const heading = document.querySelector("[data-editor-heading]");
  if (heading) heading.textContent = `Chỉnh sửa: ${product.name}`;
  const label = document.querySelector("[data-editor-tab-label]");
  if (label) label.textContent = `Sửa: ${product.name}`;
  switchProductTab("editor");
  updateLiveProductPreview();
  form.scrollIntoView({behavior:"smooth", block:"start"});
});

document.querySelector("[data-reset-product]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-admin-product]");
  if (!form) return;
  form.reset();
  form.elements.id.value = "";
  form.elements.image_url.value = "/static/img/product-placeholder.svg";
  const galleryContainer = document.querySelector("[data-gallery-container]");
  if (galleryContainer) galleryContainer.innerHTML = "";
  if (typeof tinymce !== "undefined" && tinymce.get("admin-product-description")) {
    tinymce.get("admin-product-description").setContent("");
  }
  const heading = document.querySelector("[data-editor-heading]");
  if (heading) heading.textContent = "Tạo sản phẩm mới";
  const label = document.querySelector("[data-editor-tab-label]");
  if (label) label.textContent = "Tạo & Chỉnh sửa sản phẩm";
  updateLiveProductPreview();
});

async function currentRole() {
  if (window.currentUser) return window.currentUser.role;
  try { window.currentUser = await request("/api/v1/auth/me"); return window.currentUser.role; } catch { return null; }
}

async function loadAdminRefunds() {
  const list = document.querySelector("[data-admin-refunds]");
  if (!list) return;
  try {
    const [data, role] = await Promise.all([request("/api/v1/admin/refunds"), currentRole()]);
    const isAdmin = role === "admin";
    list.innerHTML = data.items.map((refund) => {
      const actionable = isAdmin && ["scheduled", "failed"].includes(refund.status);
      return `<article class="order-card" data-refund-card="${refund.id}"><div><h2>Đơn ${escapeHtml(refund.order_code)} · ${moneyMinor(refund.amount, refund.currency)}</h2><p>${escapeHtml(refund.method)} · ${escapeHtml(refund.provider)} · thanh toán ${escapeHtml(paymentStatusNames[refund.payment_status] || refund.payment_status)}</p><p>Yêu cầu ${new Date(refund.requested_at).toLocaleString("vi-VN")} · đủ điều kiện ${new Date(refund.due_at).toLocaleString("vi-VN")} · ${escapeHtml(refundStatusNames[refund.status] || refund.status)}</p>${refund.reason ? `<p>Lý do: ${escapeHtml(refund.reason)}</p>` : ""}${actionable ? `<p><button type="button" data-confirm-refund="${refund.id}" ${refund.due ? "" : "disabled"}>${refund.due ? "Xác nhận hoàn tiền" : "Chưa đủ hạn"}</button> <button type="button" class="button-light" data-reject-refund="${refund.id}">Từ chối</button></p>` : ""}</div></article>`;
    }).join("") || "<p>Không có yêu cầu hoàn tiền.</p>";
  } catch (error) { list.innerHTML = `<p>${escapeHtml(error.message)}</p>`; }
}

document.querySelector("[data-admin-refunds]")?.addEventListener("click", async (event) => {
  const confirmButton = event.target.closest("[data-confirm-refund]");
  const rejectButton = event.target.closest("[data-reject-refund]");
  if (!confirmButton && !rejectButton) return;
  if (confirmButton && !confirm("Gọi cổng thanh toán để hoàn tiền cho đơn này?")) return;
  const id = confirmButton ? confirmButton.dataset.confirmRefund : rejectButton.dataset.rejectRefund;
  const reason = rejectButton ? prompt("Lý do từ chối hoàn tiền:", "Chưa nhận lại hàng") : null;
  if (rejectButton && reason === null) return;
  (confirmButton || rejectButton).disabled = true;
  try {
    await request(`/api/v1/admin/refunds/${id}/${confirmButton ? "confirm" : "reject"}`, {method:"POST", body:JSON.stringify(confirmButton ? {} : {reason:reason || ""})});
    message(confirmButton ? "Đã hoàn tiền thành công." : "Đã từ chối yêu cầu hoàn tiền.");
    await loadAdminRefunds();
  } catch (error) { message(error.message); (confirmButton || rejectButton).disabled = false; }
});

loadProducts();
loadCart();
loadAdminProducts();
initAdminTinyMCE();
loadUserNav();
loadAccountSidebar();
loadManagerStats();
loadRevenueReport();
loadAdminUsers();
loadAccountOrders();
loadStaffOrders();
loadAdminRefunds();
loadNewsletterAdmin();

const refundStatusNames = {scheduled:"Chờ đủ thời hạn giữ tiền",processing:"Đang xử lý hoàn tiền",succeeded:"Đã hoàn tiền",failed:"Hoàn tiền lỗi, shop sẽ thử lại",rejected:"Shop từ chối hoàn tiền"};

function paymentAmount(payment) {
  const page = document.querySelector(".payment-page");
  const rate = Number(page?.dataset.usdRate) || 25000;
  if (payment.currency === "USD" && payment.amount_minor !== null && payment.amount_minor !== undefined) {
    const usd = (payment.amount_minor / 100).toLocaleString("en-US", {style:"currency", currency:"USD"});
    return `<strong class="price">${escapeHtml(usd)}</strong><small>≈ ${money(payment.total)} · tỷ giá 1 USD = ${rate.toLocaleString("vi-VN")} ₫</small>`;
  }
  if (payment.simulation) return `<strong class="price">${money(payment.total)}</strong>`;
  return `<strong class="price">${money(payment.total)}</strong><small>VNPAY thu VND, không quy đổi</small>`;
}

async function loadPaymentDemo() {
  const summary = document.querySelector("[data-payment-summary]");
  if (!summary) return;
  const code = decodeURIComponent(location.pathname.split("/").pop());
  try {
    const payment = await request(`/api/v1/payments/orders/${encodeURIComponent(code)}`);
    const label = payment.method === "PAYPAL" ? "PayPal" : "VNPAY";
    document.querySelector("[data-payment-provider]").textContent = `${label} · ${payment.simulation ? "Mô phỏng" : "Sandbox"}`;
    const refund = payment.refund ? `<p class="refund-note">Hoàn tiền ${moneyMinor(payment.refund.amount, payment.refund.currency)}: ${escapeHtml(refundStatusNames[payment.refund.status] || payment.refund.status)} · đủ điều kiện ${new Date(payment.refund.due_at).toLocaleString("vi-VN")}</p>` : "";
    const vatPercent = Number(document.querySelector(".payment-page")?.dataset.vatPercent) || 0;
    const vatLine = payment.vat
      ? `<p class="summary-line"><span>Đã bao gồm VAT (${vatPercent}%)</span><strong>${money(payment.vat)}</strong></p>`
      : "";
    summary.innerHTML = `<p>Đơn hàng <strong>${escapeHtml(payment.code)}</strong></p><p>Tổng thanh toán</p>${paymentAmount(payment)}${vatLine}<p class="tag-row">${orderTag(payment.order_status)}${paymentTag(payment)}</p>${refund}`;
    const settled = ["paid", "refund_pending", "refunded"].includes(payment.status);
    if (settled) { signalPaymentUpdate(); refreshCartCount(); }
    const actions = document.querySelector("[data-payment-actions]");
    actions.hidden = settled;
    document.querySelectorAll("[data-simulate]").forEach((node) => node.hidden = !payment.simulation);
    const retry = document.querySelector("[data-payment-retry]");
    retry.hidden = payment.simulation;
    retry.textContent = (payment.attempt || 1) > 1 ? "Thanh toán lại" : "Thanh toán ngay";
    // Chỉ PayPal có endpoint đồng bộ; mock/VNPAY không cần nút này.
    const refresh = document.querySelector("[data-payment-refresh]");
    if (refresh) refresh.hidden = payment.simulation || payment.provider !== "paypal";
    const note = paymentReturnNotes[new URLSearchParams(location.search).get("payment")];
    if (note) message(note);
  } catch (error) { summary.textContent = error.message; }
}

// Đối soát lại với PayPal: khách đã trả tiền ở cổng nhưng trang vẫn hiện
// "Chờ thanh toán" (mất liên kết quay về, capture lỗi mạng...).
document.querySelector("[data-payment-refresh]")?.addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const code = decodeURIComponent(location.pathname.split("/").pop());
  button.disabled = true;
  message("Đang kiểm tra lại giao dịch với PayPal…");
  try {
    await request(`/api/v1/payments/orders/${encodeURIComponent(code)}/sync`, {method:"POST", body:"{}"});
    await loadPaymentDemo();
    message("Đã đối soát với PayPal. Xem trạng thái thanh toán ở trên.");
  } catch (error) { message(error.message); }
  finally { button.disabled = false; }
});

document.querySelector("[data-payment-actions]")?.addEventListener("click", async (event) => {
  const code = decodeURIComponent(location.pathname.split("/").pop());
  const retry = event.target.closest("[data-payment-retry]");
  if (retry) {
    retry.disabled = true;
    const tab = popPaymentTab();
    try {
      const session = await request(`/api/v1/payments/orders/${encodeURIComponent(code)}/session`, {method:"POST", body:"{}"});
      if (tab && !tab.closed) {
        tab.location.assign(session.url);
        message("Đã mở cổng thanh toán trong tab mới. Trang này sẽ tự cập nhật sau khi bạn hoàn tất thanh toán.");
      } else {
        message("Trình duyệt đã chặn tab mới — bấm liên kết bên dưới để mở cổng thanh toán.");
        offerNewTabLink(session.url, "Mở cổng thanh toán (tab mới) →", document.querySelector("[data-payment-actions]"));
      }
    } catch (error) { tab?.close(); message(error.message); }
    finally { retry.disabled = false; }
    return;
  }
  const button = event.target.closest("[data-simulate]");
  if (!button) return;
  const buttons = document.querySelectorAll("[data-simulate]");
  buttons.forEach((node) => node.disabled = true);
  try {
    await request(`/api/v1/payments/orders/${encodeURIComponent(code)}/simulate`, {method:"POST", body:JSON.stringify({result:button.dataset.simulate})});
    if (button.dataset.simulate === "paid") { signalPaymentUpdate(); location.assign(`/cart/tracking?code=${encodeURIComponent(code)}`); }
    else { message("Đã mô phỏng thanh toán thất bại. Bạn có thể thử lại trên cùng đơn hàng."); await loadPaymentDemo(); }
  } catch (error) { message(error.message); }
  finally { buttons.forEach((node) => node.disabled = false); }
});
loadPaymentDemo();

function initProductGallery() {
  const gallery = document.querySelector(".product-gallery");
  if (!gallery) return;
  const mainImg = gallery.querySelector("#product-gallery-main");
  const thumbs = Array.from(gallery.querySelectorAll(".gallery-thumb"));
  const navPrev = gallery.querySelector("[data-gallery-nav='prev']");
  const navNext = gallery.querySelector("[data-gallery-nav='next']");
  if (!mainImg || !thumbs.length) return;

  const switchToIndex = (index) => {
    if (index < 0 || index >= thumbs.length) return;
    const targetThumb = thumbs[index];
    const src = targetThumb.dataset.fullSrc;
    if (src && mainImg.getAttribute("src") !== src) {
      mainImg.style.opacity = "0.7";
      mainImg.onload = () => {
        mainImg.style.opacity = "1";
      };
      mainImg.onerror = () => {
        mainImg.style.opacity = "1";
      };
      mainImg.src = src;
      if (mainImg.complete) {
        mainImg.style.opacity = "1";
      }
    }
    thumbs.forEach((t) => {
      t.classList.remove("is-active");
      t.setAttribute("aria-current", "false");
    });
    targetThumb.classList.add("is-active");
    targetThumb.setAttribute("aria-current", "true");
    targetThumb.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  };

  const getActiveIndex = () => {
    const idx = thumbs.findIndex((t) => t.classList.contains("is-active"));
    return idx >= 0 ? idx : 0;
  };

  // Only switch when left mouse button is clicked (event.button === 0)
  thumbs.forEach((thumb, idx) => {
    thumb.addEventListener("click", (e) => {
      if (e.button !== undefined && e.button !== 0) return;
      switchToIndex(idx);
    });
  });

  navPrev?.addEventListener("click", (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    const current = getActiveIndex();
    const prev = (current - 1 + thumbs.length) % thumbs.length;
    switchToIndex(prev);
  });

  navNext?.addEventListener("click", (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    const current = getActiveIndex();
    const next = (current + 1) % thumbs.length;
    switchToIndex(next);
  });
}
initProductGallery();

async function ensureCatalogProducts() {
  if (catalogProducts && catalogProducts.length > 0) return catalogProducts;
  try {
    const data = await request("/api/v1/products");
    catalogProducts = data.items || [];
    return catalogProducts;
  } catch {
    return [];
  }
}

function initLiveSearch() {
  const input = document.getElementById("store-search");
  const dropdown = document.getElementById("search-dropdown");
  if (!input || !dropdown) return;

  const normalize = (value) =>
    String(value || "")
      .toLocaleLowerCase("vi")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d");

  let debounceTimer = null;

  const renderDropdown = async () => {
    const rawVal = input.value.trim();
    const query = normalize(rawVal);

    // Đồng bộ với danh sách sản phẩm nếu đang ở trang catalog
    const catalogSearch = document.querySelector("[data-product-search]");
    if (catalogSearch && catalogSearch !== input) {
      catalogSearch.value = rawVal;
      applyProductSearch();
    }

    if (!query) {
      dropdown.hidden = true;
      dropdown.innerHTML = "";
      return;
    }

    dropdown.hidden = false;
    if (!dropdown.innerHTML.trim()) {
      dropdown.innerHTML = `<div class="search-loading">Đang tìm kiếm…</div>`;
    }

    const products = await ensureCatalogProducts();
    const matched = products.filter((p) =>
      normalize(`${p.name} ${p.sku}`).includes(query)
    );

    if (!input.value.trim()) {
      dropdown.hidden = true;
      dropdown.innerHTML = "";
      return;
    }

    if (matched.length === 0) {
      dropdown.innerHTML = `
        <div class="search-empty">
          <p>Không tìm thấy sản phẩm cho <strong>${escapeHtml(rawVal)}</strong></p>
          <a href="/collections/all">Xem tất cả sản phẩm →</a>
        </div>
      `;
      dropdown.hidden = false;
      return;
    }

    const top = matched.slice(0, 6);
    const itemsHtml = top
      .map((p) => {
        const onSale = p.sale_price !== null && p.sale_price < p.price;
        return `
          <a class="search-item" href="/products/${encodeURIComponent(p.slug)}">
            <img class="search-item-img" src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.name)}" width="44" height="44" loading="lazy">
            <div class="search-item-content">
              <strong class="search-item-name">${escapeHtml(p.name)}</strong>
              <div class="search-item-meta">
                <span class="search-item-sku">SKU: ${escapeHtml(p.sku)}</span>
                <span class="search-item-price">${money(p.sale_price ?? p.price)}</span>
                ${onSale ? `<del class="search-item-del">${money(p.price)}</del>` : ""}
              </div>
            </div>
            <span class="search-item-stock ${p.stock > 0 ? "is-in-stock" : "is-out-stock"}">
              ${p.stock > 0 ? "Còn hàng" : "Hết hàng"}
            </span>
          </a>
        `;
      })
      .join("");

    const footerHtml = `
      <a class="search-footer" href="/collections/all?q=${encodeURIComponent(rawVal)}">
        Xem tất cả ${matched.length} sản phẩm cho "${escapeHtml(rawVal)}" →
      </a>
    `;

    dropdown.innerHTML = `<div class="search-list">${itemsHtml}</div>${footerHtml}`;
    dropdown.hidden = false;
  };

  input.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(renderDropdown, 120);
  });

  input.addEventListener("focus", () => {
    if (input.value.trim() && dropdown.innerHTML.trim()) {
      dropdown.hidden = false;
    }
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      dropdown.hidden = true;
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".header-search-wrapper")) {
      dropdown.hidden = true;
    }
  });
}
initLiveSearch();

// Toggle Show/Hide Password
document.addEventListener("click", (event) => {
  const btn = event.target.closest(".btn-toggle-password");
  if (!btn) return;
  const input = btn.closest(".password-field")?.querySelector("input");
  if (!input) return;
  const isPass = input.type === "password";
  input.type = isPass ? "text" : "password";
  btn.setAttribute("aria-label", isPass ? "Ẩn mật khẩu" : "Hiện mật khẩu");
  btn.innerHTML = isPass
    ? `<svg class="eye-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line></svg>`
    : `<svg class="eye-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
});

// Xử lý cập nhật thông tin cá nhân (Profile Form)
document.querySelector("[data-profile-form]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submitBtn = form.querySelector("button[type='submit']");
  const msgNode = form.querySelector("[data-profile-message]");
  const name = form.querySelector("input[name='name']")?.value.trim();
  const phone = form.querySelector("input[name='phone']")?.value.trim() || "";
  const address = form.querySelector("textarea[name='address']")?.value.trim() || "";
  const currentPassword = form.querySelector("input[name='current_password']")?.value || null;
  const newPassword = form.querySelector("input[name='new_password']")?.value || null;
  const confirmNewPassword = form.querySelector("input[name='confirm_new_password']")?.value || null;

  if (!name) {
    if (msgNode) {
      msgNode.textContent = "Họ và tên không được để trống.";
      msgNode.style.color = "#c62828";
    }
    return;
  }

  if (phone && !/^0\d{9}$/.test(phone)) {
    if (msgNode) {
      msgNode.textContent = "Số điện thoại nhận hàng không hợp lệ (cần 10 chữ số, bắt đầu bằng 0).";
      msgNode.style.color = "#c62828";
    }
    return;
  }

  if (newPassword || confirmNewPassword) {
    if (!currentPassword) {
      if (msgNode) {
        msgNode.textContent = "Vui lòng nhập mật khẩu hiện tại để đổi sang mật khẩu mới.";
        msgNode.style.color = "#c62828";
      }
      return;
    }
    if (newPassword !== confirmNewPassword) {
      if (msgNode) {
        msgNode.textContent = "Mật khẩu mới và mật khẩu xác nhận lại không khớp nhau.";
        msgNode.style.color = "#c62828";
      }
      return;
    }
    if (newPassword.length < 8) {
      if (msgNode) {
        msgNode.textContent = "Mật khẩu mới phải có tối thiểu 8 ký tự.";
        msgNode.style.color = "#c62828";
      }
      return;
    }
  }

  submitBtn.disabled = true;
  if (msgNode) {
    msgNode.textContent = "Đang lưu thay đổi…";
    msgNode.style.color = "var(--muted)";
  }

  try {
    const updated = await request("/api/v1/auth/me", {
      method: "PUT",
      body: JSON.stringify({
        name,
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    window.currentUser = updated;

    // Lưu thông tin địa chỉ giao hàng mặc định vào LocalStorage
    try {
      localStorage.setItem("electrohub_default_shipping", JSON.stringify({
        name: updated.name,
        phone,
        address,
      }));
    } catch {}

    const sidebarName = document.querySelector("[data-sidebar-name]");
    if (sidebarName) sidebarName.textContent = updated.name;
    const sidebarAvatar = document.querySelector("[data-sidebar-avatar]");
    if (sidebarAvatar) sidebarAvatar.textContent = (updated.name || "U").trim().charAt(0).toUpperCase();

    const navName = document.querySelector(".user-profile-link .user-name");
    if (navName) navName.textContent = updated.name;
    const navAvatar = document.querySelector(".user-profile-link .user-avatar");
    if (navAvatar) navAvatar.textContent = (updated.name || "U").trim().charAt(0).toUpperCase();

    const curPassInput = form.querySelector("input[name='current_password']");
    if (curPassInput) curPassInput.value = "";
    const newPassInput = form.querySelector("input[name='new_password']");
    if (newPassInput) newPassInput.value = "";
    const confirmPassInput = form.querySelector("input[name='confirm_new_password']");
    if (confirmPassInput) confirmPassInput.value = "";

    if (msgNode) {
      msgNode.textContent = "Cập nhật thông tin và địa chỉ giao hàng thành công!";
      msgNode.style.color = "#2e7d32";
    }
  } catch (error) {
    if (msgNode) {
      msgNode.textContent = error.message;
      msgNode.style.color = "#c62828";
    }
  } finally {
    submitBtn.disabled = false;
  }
});

// Báo cáo doanh thu (/manager)
async function loadRevenueReport() {
  const container = document.querySelector("[data-revenue-stats]");
  if (!container) return;
  try {
    const data = await request("/api/v1/auth/admin/revenue");
    const totalEl = document.querySelector("[data-rev-total]");
    if (totalEl) totalEl.textContent = money(data.total_revenue);

    const vnpayEl = document.querySelector("[data-rev-vnpay]");
    if (vnpayEl) vnpayEl.textContent = money(data.vnpay_revenue);

    const paypalEl = document.querySelector("[data-rev-paypal]");
    if (paypalEl) {
      const rate = 25000;
      const usd = (data.paypal_revenue / rate).toFixed(2);
      paypalEl.textContent = `${money(data.paypal_revenue)} (≈ $${usd})`;
    }

    const ordersEl = document.querySelector("[data-rev-orders]");
    if (ordersEl) ordersEl.textContent = `${data.total_orders} đơn`;

    // Phân bố trạng thái đơn
    const chipsContainer = document.querySelector("[data-status-chips]");
    if (chipsContainer && data.status_counts) {
      chipsContainer.innerHTML = Object.entries(statusNames).map(([key, label]) => {
        const count = data.status_counts[key] || 0;
        return `<span class="status-chip" style="padding:6px 14px;border-radius:20px;background:#f4f7f8;border:1px solid #dce3e5;font-size:0.86rem;"><strong>${count}</strong> ${label}</span>`;
      }).join("");
    }

    // Bảng đơn hàng phát sinh doanh thu gần đây
    const tableContainer = document.querySelector("[data-revenue-orders]");
    if (tableContainer) {
      if (!data.recent_orders || !data.recent_orders.length) {
        tableContainer.innerHTML = "<p>Chưa có đơn hàng nào phát sinh.</p>";
      } else {
        tableContainer.innerHTML = `
          <div style="overflow-x:auto;">
            <table class="admin-table" style="width:100%;border-collapse:collapse;font-size:0.88rem;text-align:left;">
              <thead>
                <tr style="border-bottom:2px solid #edf2f4;color:var(--muted);">
                  <th style="padding:10px 8px;">Mã đơn</th>
                  <th style="padding:10px 8px;">Thời gian</th>
                  <th style="padding:10px 8px;">Cổng thanh toán</th>
                  <th style="padding:10px 8px;">Trạng thái đơn</th>
                  <th style="padding:10px 8px;text-align:right;">Doanh thu</th>
                </tr>
              </thead>
              <tbody>
                ${data.recent_orders.map(o => `
                  <tr style="border-bottom:1px solid #edf2f4;">
                    <td style="padding:10px 8px;"><strong><a href="/cart/tracking?code=${encodeURIComponent(o.code)}">${escapeHtml(o.code)}</a></strong></td>
                    <td style="padding:10px 8px;color:var(--muted);">${new Date(o.created_at).toLocaleString("vi-VN")}</td>
                    <td style="padding:10px 8px;">${escapeHtml(o.payment_method)} (${escapeHtml(paymentStatusNames[o.payment_status] || o.payment_status)})</td>
                    <td style="padding:10px 8px;">${orderTag(o.status)}</td>
                    <td style="padding:10px 8px;text-align:right;font-weight:700;color:#b54c28;">${money(o.total)}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;
      }
    }
  } catch (error) {
    if (container) container.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

// Quản lý Phân quyền & Khóa người dùng (/admin/users)
let adminUsersList = [];

async function loadAdminUsers() {
  const container = document.querySelector("[data-admin-users]");
  if (!container) return;
  try {
    const users = await request("/api/v1/auth/admin/users");
    adminUsersList = users;
    renderAdminUsers();
  } catch (error) {
    container.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

function renderAdminUsers() {
  const container = document.querySelector("[data-admin-users]");
  if (!container) return;
  const currentUserId = window.currentUser?.id;
  const query = (document.querySelector("[data-user-search]")?.value || "").toLowerCase().trim();
  const filtered = adminUsersList.filter(u =>
    (u.name && u.name.toLowerCase().includes(query)) ||
    (u.email && u.email.toLowerCase().includes(query))
  );

  if (!filtered.length) {
    container.innerHTML = `<p style="padding:24px 0;text-align:center;color:var(--muted);">Không tìm thấy người dùng nào phù hợp.</p>`;
    return;
  }

  container.innerHTML = `
    <div style="overflow-x:auto;">
      <table class="admin-table user-table" style="width:100%;border-collapse:collapse;font-size:0.88rem;text-align:left;">
        <thead>
          <tr style="border-bottom:2px solid #edf2f4;color:var(--muted);">
            <th style="padding:10px 8px;">ID</th>
            <th style="padding:10px 8px;">Họ tên</th>
            <th style="padding:10px 8px;">Email</th>
            <th style="padding:10px 8px;">Phân quyền</th>
            <th style="padding:10px 8px;">Trạng thái</th>
            <th style="padding:10px 8px;text-align:right;">Thao tác</th>
          </tr>
        </thead>
        <tbody>
          ${filtered.map(u => {
            const isSelf = u.id === currentUserId;
            const blockedBadge = u.is_blocked
              ? `<span style="background:#ffebee;color:#c62828;padding:3px 8px;border-radius:12px;font-size:0.78rem;font-weight:600;">Đã khóa</span>`
              : `<span style="background:#e8f5e9;color:#2e7d32;padding:3px 8px;border-radius:12px;font-size:0.78rem;font-weight:600;">Hoạt động</span>`;
            return `
              <tr style="border-bottom:1px solid #edf2f4;">
                <td style="padding:12px 8px;font-weight:600;">#${u.id}</td>
                <td style="padding:12px 8px;">${escapeHtml(u.name)} ${isSelf ? '<small style="color:var(--muted);">(Bạn)</small>' : ''}</td>
                <td style="padding:12px 8px;color:var(--muted);">${escapeHtml(u.email)}</td>
                <td style="padding:12px 8px;">
                  <select data-user-role-select="${u.id}" ${isSelf ? 'disabled title="Không thể tự đổi vai trò của chính mình"' : ''} style="padding:4px 8px;border:1px solid #bcc8cc;border-radius:4px;font:inherit;font-size:0.84rem;">
                    <option value="customer" ${u.role === 'customer' ? 'selected' : ''}>Khách hàng</option>
                    <option value="staff" ${u.role === 'staff' ? 'selected' : ''}>Nhân viên (Staff)</option>
                    <option value="admin" ${u.role === 'admin' ? 'selected' : ''}>Quản lý (Admin)</option>
                  </select>
                </td>
                <td style="padding:12px 8px;">${blockedBadge}</td>
                <td style="padding:12px 8px;text-align:right;white-space:nowrap;">
                  ${!isSelf ? `
                    <button type="button" class="button-sm ${u.is_blocked ? 'button' : 'button-light'}" data-toggle-block="${u.id}" data-current-blocked="${u.is_blocked}" style="font-size:0.8rem;padding:4px 10px;${u.is_blocked ? 'background:#2e7d32;border-color:#2e7d32;color:#fff;' : 'color:#c62828;border-color:#ffcdd2;'}">
                      ${u.is_blocked ? 'Mở khóa' : 'Khóa tài khoản'}
                    </button>
                  ` : '<span style="font-size:0.78rem;color:var(--muted);">Tài khoản hiện tại</span>'}
                </td>
              </tr>
            `;
          }).join("")}
        </tbody>
      </table>
    </div>
  `;
}

// Lắng nghe đổi phân quyền người dùng
document.addEventListener("change", async (event) => {
  const roleSelect = event.target.closest("[data-user-role-select]");
  if (!roleSelect) return;
  const userId = roleSelect.dataset.userRoleSelect;
  const role = roleSelect.value;
  const msgEl = document.querySelector("[data-admin-user-message]");
  roleSelect.disabled = true;
  try {
    await request(`/api/v1/auth/admin/users/${userId}/role`, {
      method: "PATCH",
      body: JSON.stringify({ role }),
    });
    if (msgEl) {
      msgEl.textContent = `Đã cập nhật vai trò người dùng #${userId} thành "${role}".`;
      msgEl.style.color = "#2e7d32";
    }
    await loadAdminUsers();
  } catch (error) {
    if (msgEl) {
      msgEl.textContent = error.message;
      msgEl.style.color = "#c62828";
    }
    roleSelect.disabled = false;
  }
});

// Lắng nghe Khóa / Mở khóa người dùng
document.addEventListener("click", async (event) => {
  const blockBtn = event.target.closest("[data-toggle-block]");
  if (!blockBtn) return;
  const userId = blockBtn.dataset.toggleBlock;
  const currentlyBlocked = blockBtn.dataset.currentBlocked === "true";
  const newBlocked = !currentlyBlocked;
  const confirmMsg = newBlocked
    ? `Bạn có chắc muốn KHÓA tài khoản #${userId}? Người dùng này sẽ bị chặn đăng nhập ngay lập tức.`
    : `Mở khóa cho tài khoản #${userId}?`;
  if (!confirm(confirmMsg)) return;

  const msgEl = document.querySelector("[data-admin-user-message]");
  blockBtn.disabled = true;
  try {
    await request(`/api/v1/auth/admin/users/${userId}/block`, {
      method: "PATCH",
      body: JSON.stringify({ is_blocked: newBlocked }),
    });
    if (msgEl) {
      msgEl.textContent = newBlocked ? `Đã khóa tài khoản #${userId}.` : `Đã mở khóa tài khoản #${userId}.`;
      msgEl.style.color = newBlocked ? "#c62828" : "#2e7d32";
    }
    await loadAdminUsers();
  } catch (error) {
    if (msgEl) {
      msgEl.textContent = error.message;
      msgEl.style.color = "#c62828";
    }
    blockBtn.disabled = false;
  }
});

document.querySelector("[data-user-search]")?.addEventListener("input", () => {
  renderAdminUsers();
});

document.querySelector("[data-refresh-users]")?.addEventListener("click", () => {
  loadAdminUsers();
});
