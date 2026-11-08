"""Service for revenue analytics, periodic reports, and data exports.

Supports filtering and comparisons by month, quarter, year, or all-time,
extracting KPI metrics, top-selling products, and timeline comparisons.
"""

from __future__ import annotations

import calendar
import csv
import io
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.order import Order
from app.models.product import Product


def _normalize_dt(dt: datetime | None) -> datetime | None:
    """Ensure datetime is tz-naive UTC for consistent comparisons."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(UTC).replace(tzinfo=None)
    return dt


def resolve_period_dates(
    period_type: str = "month",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
) -> dict[str, Any]:
    """Calculate date boundaries and readable labels for the current and previous comparison periods."""
    now = datetime.now(UTC).replace(tzinfo=None)
    current_year = now.year
    current_month = now.month
    current_quarter = (current_month - 1) // 3 + 1

    period_type = (period_type or "month").lower()

    if period_type == "month":
        y = year if (year and 2000 <= year <= 2100) else current_year
        m = month if (month and 1 <= month <= 12) else current_month
        start_dt = datetime(y, m, 1)
        if m == 12:
            end_dt = datetime(y + 1, 1, 1)
        else:
            end_dt = datetime(y, m + 1, 1)

        # Previous month
        if m == 1:
            prev_start_dt = datetime(y - 1, 12, 1)
            prev_end_dt = datetime(y, 1, 1)
            prev_label = f"Tháng 12/{y - 1}"
        else:
            prev_start_dt = datetime(y, m - 1, 1)
            prev_end_dt = datetime(y, m, 1)
            prev_label = f"Tháng {m - 1:02d}/{y}"

        label = f"Tháng {m:02d}/{y}"
        filename_part = f"thang-{m:02d}-{y}"
        q = (m - 1) // 3 + 1

    elif period_type == "quarter":
        y = year if (year and 2000 <= year <= 2100) else current_year
        q = quarter if (quarter and 1 <= quarter <= 4) else current_quarter
        start_m = (q - 1) * 3 + 1
        start_dt = datetime(y, start_m, 1)
        if q == 4:
            end_dt = datetime(y + 1, 1, 1)
        else:
            end_dt = datetime(y, start_m + 3, 1)

        # Previous quarter
        if q == 1:
            prev_start_dt = datetime(y - 1, 10, 1)
            prev_end_dt = datetime(y, 1, 1)
            prev_label = f"Quý 4/{y - 1}"
        else:
            prev_start_dt = datetime(y, start_m - 3, 1)
            prev_end_dt = datetime(y, start_m, 1)
            prev_label = f"Quý {q - 1}/{y}"

        label = f"Quý {q}/{y}"
        filename_part = f"quy-{q}-{y}"
        m = start_m

    elif period_type == "year":
        y = year if (year and 2000 <= year <= 2100) else current_year
        start_dt = datetime(y, 1, 1)
        end_dt = datetime(y + 1, 1, 1)
        prev_start_dt = datetime(y - 1, 1, 1)
        prev_end_dt = datetime(y, 1, 1)
        label = f"Năm {y}"
        prev_label = f"Năm {y - 1}"
        filename_part = f"nam-{y}"
        m = current_month
        q = current_quarter

    else:
        period_type = "all"
        y = current_year
        m = current_month
        q = current_quarter
        start_dt = None
        end_dt = None
        prev_start_dt = None
        prev_end_dt = None
        label = "Tất cả thời gian"
        prev_label = "Kỳ trước"
        filename_part = "tat-ca"

    return {
        "period_type": period_type,
        "year": y,
        "month": m,
        "quarter": q,
        "start_dt": start_dt,
        "end_dt": end_dt,
        "prev_start_dt": prev_start_dt,
        "prev_end_dt": prev_end_dt,
        "label": label,
        "prev_label": prev_label,
        "filename_part": filename_part,
    }


def _is_order_paid(o: Order) -> bool:
    """An order counts as paid revenue if its payment succeeded or it is confirmed/shipped/completed and not cancelled."""
    if o.status == "cancelled":
        return False
    if o.payment and o.payment.status == "paid":
        return True
    return o.status in {"confirmed", "shipping", "done"}


def get_revenue_analytics(
    db: Session,
    period_type: str = "month",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
) -> dict[str, Any]:
    """Compile comprehensive revenue statistics, comparisons, and top-selling products for the specified period."""
    period = resolve_period_dates(
        period_type=period_type, year=year, month=month, quarter=quarter
    )

    all_orders = db.scalars(select(Order).order_by(Order.created_at.desc())).all()

    # Distinct years for period selection filter dropdown
    order_years = {
        odt.year
        for o in all_orders
        if (odt := _normalize_dt(o.created_at)) is not None
    }
    current_year = datetime.now(UTC).year
    if current_year not in order_years:
        order_years.add(current_year)
    available_years = sorted(list(order_years), reverse=True)

    # Filter orders by current period
    start_dt = period["start_dt"]
    end_dt = period["end_dt"]
    prev_start = period["prev_start_dt"]
    prev_end = period["prev_end_dt"]

    current_orders: list[Order] = []
    prev_orders: list[Order] = []

    for o in all_orders:
        odt = _normalize_dt(o.created_at)
        if odt is None:
            # If created_at is somehow null, include in current if period is all
            if start_dt is None and end_dt is None:
                current_orders.append(o)
            continue
        if (start_dt is None or odt >= start_dt) and (end_dt is None or odt < end_dt):
            current_orders.append(o)
        if prev_start and prev_end and (prev_start <= odt < prev_end):
            prev_orders.append(o)

    # Current period metrics calculation
    total_revenue = 0
    paypal_revenue = 0
    vnpay_revenue = 0
    cod_revenue = 0
    paypal_count = 0
    vnpay_count = 0
    cod_count = 0
    total_discount = 0
    total_items_sold = 0
    by_status = {"pending": 0, "confirmed": 0, "shipping": 0, "done": 0, "cancelled": 0}

    product_sales: dict[int, dict[str, int]] = {}

    for o in current_orders:
        st = o.status
        by_status[st] = by_status.get(st, 0) + 1

        if _is_order_paid(o):
            total_revenue += o.total
            total_discount += o.discount or 0

            method = (o.payment.method if o.payment else "COD").upper()
            if "PAYPAL" in method:
                paypal_revenue += o.total
                paypal_count += 1
            elif "VNPAY" in method:
                vnpay_revenue += o.total
                vnpay_count += 1
            else:
                cod_revenue += o.total
                cod_count += 1

            for item in o.items:
                total_items_sold += item.qty
                if item.product_id not in product_sales:
                    product_sales[item.product_id] = {"qty": 0, "revenue": 0, "orders": 0}
                product_sales[item.product_id]["qty"] += item.qty
                product_sales[item.product_id]["revenue"] += item.price * item.qty
                product_sales[item.product_id]["orders"] += 1

    total_orders_count = len(current_orders)
    completed_orders = by_status.get("confirmed", 0) + by_status.get("shipping", 0) + by_status.get("done", 0)
    cancelled_orders = by_status.get("cancelled", 0)
    completion_rate = (
        round((completed_orders / total_orders_count * 100), 1)
        if total_orders_count > 0
        else 0.0
    )
    aov = round(total_revenue / completed_orders) if completed_orders > 0 else 0

    # Previous period metrics for comparison
    prev_total_revenue = 0
    prev_by_status = {"pending": 0, "confirmed": 0, "shipping": 0, "done": 0, "cancelled": 0}
    for o in prev_orders:
        prev_by_status[o.status] = prev_by_status.get(o.status, 0) + 1
        if _is_order_paid(o):
            prev_total_revenue += o.total

    prev_total_orders = len(prev_orders)
    prev_completed = (
        prev_by_status.get("confirmed", 0)
        + prev_by_status.get("shipping", 0)
        + prev_by_status.get("done", 0)
    )
    prev_aov = round(prev_total_revenue / prev_completed) if prev_completed > 0 else 0

    # Growth calculations
    if prev_total_revenue > 0:
        revenue_growth = round(((total_revenue - prev_total_revenue) / prev_total_revenue * 100), 1)
    else:
        revenue_growth = 100.0 if total_revenue > 0 else 0.0

    if prev_total_orders > 0:
        orders_growth = round(((total_orders_count - prev_total_orders) / prev_total_orders * 100), 1)
    else:
        orders_growth = 100.0 if total_orders_count > 0 else 0.0

    if prev_aov > 0:
        aov_growth = round(((aov - prev_aov) / prev_aov * 100), 1)
    else:
        aov_growth = 0.0

    # Top selling products in this period
    top_products = []
    if product_sales:
        product_ids = list(product_sales.keys())
        products = db.scalars(select(Product).where(Product.id.in_(product_ids))).all()
        pmap = {p.id: p for p in products}

        sorted_sales = sorted(
            product_sales.items(),
            key=lambda it: (it[1]["revenue"], it[1]["qty"]),
            reverse=True,
        )
        for rank, (pid, stats) in enumerate(sorted_sales[:10], start=1):
            p = pmap.get(pid)
            if not p:
                continue
            share = (
                round((stats["revenue"] / total_revenue * 100), 1)
                if total_revenue > 0
                else 0.0
            )
            top_products.append(
                {
                    "rank": rank,
                    "id": p.id,
                    "name": p.name,
                    "slug": p.slug,
                    "sku": p.sku or f"SKU-{p.id}",
                    "image_url": p.image_url or "/static/img/product-placeholder.svg",
                    "stock": p.stock,
                    "price": p.price,
                    "sale_price": p.sale_price,
                    "quantity_sold": stats["qty"],
                    "revenue": stats["revenue"],
                    "revenue_share": share,
                    "order_count": stats["orders"],
                }
            )

    # Comparison timeline for charts
    timeline = _build_timeline_comparison(
        period_type=period["period_type"],
        year=period["year"],
        month=period["month"],
        quarter=period["quarter"],
        current_orders=current_orders,
        prev_orders=prev_orders,
        all_orders=all_orders,
    )

    # Payment breakdown percentages
    vnpay_pct = round((vnpay_revenue / total_revenue * 100), 1) if total_revenue > 0 else 0.0
    paypal_pct = round((paypal_revenue / total_revenue * 100), 1) if total_revenue > 0 else 0.0
    cod_pct = round((cod_revenue / total_revenue * 100), 1) if total_revenue > 0 else 0.0

    recent = [
        {
            "code": o.code,
            "total": o.total,
            "status": o.status,
            "payment_method": o.payment.method if o.payment else "COD",
            "payment_status": o.payment.status if o.payment else "pending",
            "created_at": o.created_at.isoformat() if o.created_at else "",
            "items_count": len(o.items) if o.items else 0,
            "customer_name": (o.address or {}).get("name", "Khách hàng"),
        }
        for o in current_orders[:20]
    ]

    return {
        # Standard top-level backward compatible fields
        "total_revenue": total_revenue,
        "paypal_revenue": paypal_revenue,
        "vnpay_revenue": vnpay_revenue,
        "cod_revenue": cod_revenue,
        "total_orders": total_orders_count,
        "status_counts": by_status,
        "recent_orders": recent,
        # Enhanced analytics & reporting fields
        "period": {
            "type": period["period_type"],
            "year": period["year"],
            "month": period["month"],
            "quarter": period["quarter"],
            "label": period["label"],
            "prev_label": period["prev_label"],
            "filename_part": period["filename_part"],
        },
        "kpis": {
            "total_revenue": total_revenue,
            "prev_revenue": prev_total_revenue,
            "revenue_growth": revenue_growth,
            "total_orders": total_orders_count,
            "prev_orders": prev_total_orders,
            "orders_growth": orders_growth,
            "completed_orders": completed_orders,
            "cancelled_orders": cancelled_orders,
            "completion_rate": completion_rate,
            "aov": aov,
            "prev_aov": prev_aov,
            "aov_growth": aov_growth,
            "total_items_sold": total_items_sold,
            "total_discount": total_discount,
        },
        "payment_breakdown": {
            "vnpay": {"revenue": vnpay_revenue, "count": vnpay_count, "percentage": vnpay_pct},
            "paypal": {"revenue": paypal_revenue, "count": paypal_count, "percentage": paypal_pct},
            "cod": {"revenue": cod_revenue, "count": cod_count, "percentage": cod_pct},
        },
        "top_products": top_products,
        "timeline_comparison": timeline,
        "available_years": available_years,
    }


def _build_timeline_comparison(
    period_type: str,
    year: int,
    month: int,
    quarter: int,
    current_orders: list[Order],
    prev_orders: list[Order],
    all_orders: list[Order],
) -> dict[str, Any]:
    """Construct data series for comparison charts between current and previous periods."""
    if period_type == "year":
        labels = [f"T{m}" for m in range(1, 13)]
        current_series = [0] * 12
        prev_series = [0] * 12

        for o in current_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                idx = odt.month - 1
                if 0 <= idx < 12:
                    current_series[idx] += o.total

        for o in prev_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                idx = odt.month - 1
                if 0 <= idx < 12:
                    prev_series[idx] += o.total

        return {
            "labels": labels,
            "current_series": current_series,
            "previous_series": prev_series,
            "current_name": f"Năm {year}",
            "prev_name": f"Năm {year - 1}",
            "granularity": "monthly",
        }

    elif period_type == "quarter":
        start_m = (quarter - 1) * 3 + 1
        labels = [f"Tháng {m}" for m in range(start_m, start_m + 3)]
        current_series = [0, 0, 0]
        prev_series = [0, 0, 0]

        for o in current_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                idx = odt.month - start_m
                if 0 <= idx < 3:
                    current_series[idx] += o.total

        prev_q = 4 if quarter == 1 else quarter - 1
        prev_start_m = (prev_q - 1) * 3 + 1
        for o in prev_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                idx = odt.month - prev_start_m
                if 0 <= idx < 3:
                    prev_series[idx] += o.total

        return {
            "labels": labels,
            "current_series": current_series,
            "previous_series": prev_series,
            "current_name": f"Quý {quarter}/{year}",
            "prev_name": f"Quý {prev_q}/{year - 1 if quarter == 1 else year}",
            "granularity": "quarter_months",
        }

    elif period_type == "month":
        num_days = calendar.monthrange(year, month)[1]
        labels = [str(d) for d in range(1, num_days + 1)]
        current_series = [0] * num_days
        prev_series = [0] * num_days

        for o in current_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                idx = odt.day - 1
                if 0 <= idx < num_days:
                    current_series[idx] += o.total

        for o in prev_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                idx = odt.day - 1
                if 0 <= idx < num_days:
                    prev_series[idx] += o.total

        prev_m = 12 if month == 1 else month - 1
        prev_y = year - 1 if month == 1 else year
        return {
            "labels": labels,
            "current_series": current_series,
            "previous_series": prev_series,
            "current_name": f"Tháng {month:02d}/{year}",
            "prev_name": f"Tháng {prev_m:02d}/{prev_y}",
            "granularity": "daily",
        }

    else:
        # All-time view: group by the last 12 calendar months
        now = datetime.now(UTC)
        months_list = []
        for i in range(11, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            months_list.append((y, m))

        labels = [f"T{m}/{y % 100}" for y, m in months_list]
        current_series = [0] * 12
        prev_series = [0] * 12

        for o in all_orders:
            odt = _normalize_dt(o.created_at)
            if _is_order_paid(o) and odt:
                for idx, (y, m) in enumerate(months_list):
                    if odt.year == y and odt.month == m:
                        current_series[idx] += o.total
                        break
                    elif odt.year == (y - 1) and odt.month == m:
                        prev_series[idx] += o.total
                        break

        return {
            "labels": labels,
            "current_series": current_series,
            "previous_series": prev_series,
            "current_name": "12 tháng gần nhất",
            "prev_name": "12 tháng trước đó",
            "granularity": "trend_12m",
        }


def generate_revenue_csv(
    db: Session,
    period_type: str = "month",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
) -> tuple[str, str]:
    """Generate a clean, structured UTF-8 CSV report with Vietnamese headers and formatting."""
    data = get_revenue_analytics(
        db, period_type=period_type, year=year, month=month, quarter=quarter
    )
    period = data["period"]
    kpis = data["kpis"]
    pbreakdown = data["payment_breakdown"]
    top_products = data["top_products"]
    recent_orders = data["recent_orders"]

    output = io.StringIO()
    writer = csv.writer(output)

    now_str = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Header section
    writer.writerow(["BÁO CÁO DOANH THU & HOẠT ĐỘNG KINH DOANH - ELECTROHUB"])
    writer.writerow(["Thời gian xuất báo cáo", now_str])
    writer.writerow(["Kỳ báo cáo", period["label"]])
    writer.writerow(["Kỳ so sánh", period["prev_label"]])
    writer.writerow([])

    # KPI summary section
    writer.writerow(["1. TỔNG HỢP CHỈ SỐ KINH DOANH CHÍNH"])
    writer.writerow(["Chỉ số", "Kỳ này", "Kỳ trước", "Tăng trưởng (%)", "Ghi chú"])
    writer.writerow([
        "Tổng doanh thu thực tế (VNĐ)",
        f"{kpis['total_revenue']:,}",
        f"{kpis['prev_revenue']:,}",
        f"{kpis['revenue_growth']:+.1f}%",
        "Đơn đã thanh toán hoặc hoàn tất",
    ])
    writer.writerow([
        "Tổng số đơn hàng phát sinh",
        kpis["total_orders"],
        kpis["prev_orders"],
        f"{kpis['orders_growth']:+.1f}%",
        "Bao gồm mọi trạng thái",
    ])
    writer.writerow([
        "Số đơn hoàn tất thành công",
        kpis["completed_orders"],
        "-",
        "-",
        "Trạng thái xác nhận / giao hàng / thành công",
    ])
    writer.writerow([
        "Số đơn hàng đã hủy",
        kpis["cancelled_orders"],
        "-",
        "-",
        "Đơn khách hoặc hệ thống hủy",
    ])
    writer.writerow([
        "Tỷ lệ hoàn tất đơn hàng",
        f"{kpis['completion_rate']:.1f}%",
        "-",
        "-",
        "Số đơn hoàn tất / Tổng đơn",
    ])
    writer.writerow([
        "Giá trị trung bình đơn - AOV (VNĐ)",
        f"{kpis['aov']:,}",
        f"{kpis['prev_aov']:,}",
        f"{kpis['aov_growth']:+.1f}%",
        "Doanh thu / Đơn hoàn tất",
    ])
    writer.writerow([
        "Tổng sản phẩm đã bán (cái)",
        kpis["total_items_sold"],
        "-",
        "-",
        "Số lượng linh kiện / thiết bị xuất kho",
    ])
    writer.writerow([
        "Tổng chiết khấu khuyến mãi (VNĐ)",
        f"{kpis['total_discount']:,}",
        "-",
        "-",
        "Giá trị voucher đã giảm cho khách",
    ])
    writer.writerow([
        "Doanh thu qua cổng VNPAY (VNĐ)",
        f"{pbreakdown['vnpay']['revenue']:,}",
        "-",
        f"Chiếm {pbreakdown['vnpay']['percentage']:.1f}%",
        f"{pbreakdown['vnpay']['count']} giao dịch VNPAY",
    ])
    writer.writerow([
        "Doanh thu qua cổng PayPal (VNĐ)",
        f"{pbreakdown['paypal']['revenue']:,}",
        "-",
        f"Chiếm {pbreakdown['paypal']['percentage']:.1f}%",
        f"{pbreakdown['paypal']['count']} giao dịch PayPal",
    ])
    writer.writerow([
        "Doanh thu COD / Phương thức khác (VNĐ)",
        f"{pbreakdown['cod']['revenue']:,}",
        "-",
        f"Chiếm {pbreakdown['cod']['percentage']:.1f}%",
        f"{pbreakdown['cod']['count']} giao dịch COD",
    ])
    writer.writerow([])

    # Top products section
    writer.writerow(["2. TOP SẢN PHẨM BÁN CHẠY NHẤT TRONG KỲ"])
    writer.writerow([
        "Hạng",
        "Mã SKU",
        "Tên sản phẩm",
        "Số lượng đã bán",
        "Doanh thu (VNĐ)",
        "Tỷ trọng doanh thu (%)",
        "Tồn kho hiện tại",
    ])
    if top_products:
        for p in top_products:
            writer.writerow([
                p["rank"],
                p["sku"],
                p["name"],
                p["quantity_sold"],
                f"{p['revenue']:,}",
                f"{p['revenue_share']:.1f}%",
                p["stock"],
            ])
    else:
        writer.writerow(["-", "-", "Chưa có dữ liệu sản phẩm trong kỳ", 0, 0, "0%", 0])
    writer.writerow([])

    # Orders list section
    writer.writerow(["3. DANH SÁCH ĐƠN HÀNG TRONG KỲ"])
    writer.writerow([
        "Mã đơn",
        "Thời gian tạo",
        "Khách hàng",
        "Phương thức thanh toán",
        "Trạng thái thanh toán",
        "Trạng thái đơn hàng",
        "Số lượng mặt hàng",
        "Tổng tiền (VNĐ)",
    ])
    if recent_orders:
        for o in recent_orders:
            writer.writerow([
                o["code"],
                o["created_at"],
                o.get("customer_name", "Khách hàng"),
                o["payment_method"],
                o["payment_status"],
                o["status"],
                o["items_count"],
                f"{o['total']:,}",
            ])
    else:
        writer.writerow(["-", "-", "-", "-", "-", "-", 0, 0])

    filename = f"electrohub-bao-cao-doanh-thu-{period['filename_part']}.csv"
    return output.getvalue(), filename
