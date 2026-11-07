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
  const headers = { ...(options.body ? {"Content-Type":"application/json"} : {}), ...options.headers };
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
    const roleLinks = user.role === "admin"
      ? `<a href="/manager">Quản lý</a>`
      : user.role === "staff" ? `<a href="/staff/orders">Xử lý đơn</a>` : `<a href="/account/orders">Đơn hàng của tôi</a>`;
    const roleName = user.role === "admin" ? "Quản lý" : user.role === "staff" ? "Nhân viên" : "Khách hàng";
    refreshCartCount();
    nav.innerHTML = `${roleLinks}<span class="role-pill">${roleName}</span><button type="button" class="button-light" data-logout>Đăng xuất</button>`;
  } catch { /* Người dùng chưa đăng nhập; giữ liên kết mặc định. */ }
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
  try { const form = new FormData(event.currentTarget); const data = await request("/api/v1/newsletter/subscribe", {method:"POST", body:JSON.stringify({email:form.get("email"),consent:form.has("consent")})}); output.textContent = data.detail; event.currentTarget.reset(); }
  catch (error) { output.textContent = error.message; }
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
    location.href = user.role === "admin" ? "/manager" : user.role === "staff" ? "/staff/orders" : "/";
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
  let order;
  try { order = await request("/api/v1/orders", {method:"POST", body:JSON.stringify(Object.fromEntries(new FormData(form)))}); }
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

async function loadAdminProducts() {
  const list = document.querySelector("[data-admin-products]");
  if (!list) return;
  try {
    const result = await request("/api/v1/admin/products");
    list.innerHTML = result.items.map((product) => `<article class="product-card"><img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" width="560" height="420" loading="lazy"><h2>${escapeHtml(product.name)}</h2><p>${escapeHtml(product.slug)} · ${escapeHtml(product.sku)}</p><p>${money(product.sale_price ?? product.price)} · Tồn: ${product.stock}</p><button type="button" data-edit-product="${product.id}">Sửa</button></article>`).join("") || "<p>Chưa có sản phẩm.</p>";
    window.adminProducts = result.items;
  } catch (error) { message(error.message); }
}

document.querySelector("[data-admin-product]")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const id = form.get("id");
  const product = Object.fromEntries(form);
  product.price = Number(product.price);
  product.sale_price = product.sale_price === "" ? null : Number(product.sale_price);
  product.stock = Number(product.stock);
  delete product.id;
  try {
    await request(id ? `/api/v1/admin/products/${id}` : "/api/v1/admin/products", {method:id ? "PUT" : "POST", body:JSON.stringify(product)});
    event.currentTarget.reset();
    event.currentTarget.elements.image_url.value = "/static/img/product-placeholder.svg";
    message("Đã lưu sản phẩm.");
    await loadAdminProducts();
  } catch (error) { message(error.message); }
});

document.querySelector("[data-admin-products]")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-edit-product]");
  if (!button) return;
  const product = window.adminProducts?.find((item) => item.id === Number(button.dataset.editProduct));
  if (!product) return;
  const form = document.querySelector("[data-admin-product]");
  for (const [key, value] of Object.entries(product)) if (form.elements[key]) form.elements[key].value = value ?? "";
  form.scrollIntoView({behavior:"smooth",block:"start"});
});

document.querySelector("[data-reset-product]")?.addEventListener("click", () => {
  const form = document.querySelector("[data-admin-product]");
  form.reset();
  form.elements.image_url.value = "/static/img/product-placeholder.svg";
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
loadUserNav();
loadManagerStats();
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
