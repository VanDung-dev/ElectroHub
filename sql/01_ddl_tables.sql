-- ============================================================================
-- ELECTROHUB - HỆ QUẢN TRỊ CƠ SỞ DỮ LIỆU (SQL SERVER 2022)
-- File: 01_ddl_tables.sql
-- Mục đích: Tạo Database và toàn bộ cấu trúc bảng (Tables, PK, FK, Constraints)
-- ============================================================================

USE master;
GO

IF DB_ID(N'ElectroHub') IS NULL
BEGIN
    CREATE DATABASE [ElectroHub];
    PRINT N'Đã tạo cơ sở dữ liệu ElectroHub thành công.';
END
GO

USE [ElectroHub];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

-- 1. BẢNG USERS (Người dùng hệ thống)
IF OBJECT_ID(N'dbo.users', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.users (
        id INT IDENTITY(1,1) NOT NULL,
        email VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        name NVARCHAR(100) NOT NULL,
        role VARCHAR(20) NOT NULL CONSTRAINT df_users_role DEFAULT 'customer',
        is_blocked BIT NOT NULL CONSTRAINT df_users_is_blocked DEFAULT 0,
        created_at DATETIME2 NOT NULL CONSTRAINT df_users_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_users PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_users_email UNIQUE NONCLUSTERED (email),
        CONSTRAINT ck_users_role CHECK (role IN ('admin', 'staff', 'customer'))
    );
    CREATE NONCLUSTERED INDEX ix_users_role ON dbo.users (role);
    PRINT N'Đã tạo bảng users.';
END
ELSE
BEGIN
    IF COL_LENGTH(N'dbo.users', N'is_blocked') IS NULL
    BEGIN
        ALTER TABLE dbo.users ADD is_blocked BIT NOT NULL CONSTRAINT df_users_is_blocked DEFAULT 0;
        PRINT N'Đã bổ sung cột is_blocked vào bảng users.';
    END
END
GO

-- 2. BẢNG PRODUCTS (Danh mục sản phẩm & linh kiện điện tử)
IF OBJECT_ID(N'dbo.products', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.products (
        id INT IDENTITY(1,1) NOT NULL,
        slug VARCHAR(200) NOT NULL,
        sku VARCHAR(32) NOT NULL,
        name NVARCHAR(200) NOT NULL,
        description NVARCHAR(MAX) NULL,
        image_url VARCHAR(500) NOT NULL CONSTRAINT df_products_image DEFAULT '/static/img/product-placeholder.svg',
        price INT NOT NULL,
        sale_price INT NULL,
        stock INT NOT NULL CONSTRAINT df_products_stock DEFAULT 0,
        created_at DATETIME2 NOT NULL CONSTRAINT df_products_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_products PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_products_slug UNIQUE NONCLUSTERED (slug),
        CONSTRAINT uq_products_sku UNIQUE NONCLUSTERED (sku),
        CONSTRAINT ck_products_price CHECK (price >= 0),
        CONSTRAINT ck_products_sale_price CHECK (sale_price IS NULL OR (sale_price >= 0 AND sale_price <= price)),
        CONSTRAINT ck_products_stock CHECK (stock >= 0)
    );
    CREATE NONCLUSTERED INDEX ix_products_name ON dbo.products (name);
    PRINT N'Đã tạo bảng products.';
END
GO

-- 3. BẢNG VOUCHERS (Mã giảm giá khuyến mãi)
IF OBJECT_ID(N'dbo.vouchers', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.vouchers (
        id INT IDENTITY(1,1) NOT NULL,
        code VARCHAR(32) NOT NULL,
        [percent] INT NOT NULL,
        max_discount INT NOT NULL,
        qty_left INT NOT NULL,
        expired_at DATETIME2 NOT NULL,
        CONSTRAINT pk_vouchers PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_vouchers_code UNIQUE NONCLUSTERED (code),
        CONSTRAINT ck_vouchers_percent CHECK ([percent] BETWEEN 1 AND 100),
        CONSTRAINT ck_vouchers_max_discount CHECK (max_discount >= 0),
        CONSTRAINT ck_vouchers_qty_left CHECK (qty_left >= 0)
    );
    PRINT N'Đã tạo bảng vouchers.';
END
GO

-- 4. BẢNG CART_ITEMS (Giỏ hàng của khách)
IF OBJECT_ID(N'dbo.cart_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.cart_items (
        id INT IDENTITY(1,1) NOT NULL,
        user_id INT NOT NULL,
        product_id INT NOT NULL,
        qty INT NOT NULL CONSTRAINT df_cart_items_qty DEFAULT 1,
        CONSTRAINT pk_cart_items PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_cart_items_user_product UNIQUE NONCLUSTERED (user_id, product_id),
        CONSTRAINT fk_cart_items_users FOREIGN KEY (user_id) REFERENCES dbo.users(id) ON DELETE CASCADE,
        CONSTRAINT fk_cart_items_products FOREIGN KEY (product_id) REFERENCES dbo.products(id) ON DELETE CASCADE,
        CONSTRAINT ck_cart_items_qty CHECK (qty BETWEEN 1 AND 99)
    );
    CREATE NONCLUSTERED INDEX ix_cart_items_user_id ON dbo.cart_items (user_id);
    PRINT N'Đã tạo bảng cart_items.';
END
GO

-- 5. BẢNG ORDERS (Đơn đặt hàng)
IF OBJECT_ID(N'dbo.orders', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.orders (
        id INT IDENTITY(1,1) NOT NULL,
        code VARCHAR(12) NOT NULL,
        user_id INT NOT NULL,
        status VARCHAR(16) NOT NULL CONSTRAINT df_orders_status DEFAULT 'pending',
        subtotal INT NOT NULL,
        discount INT NOT NULL CONSTRAINT df_orders_discount DEFAULT 0,
        vat INT NOT NULL CONSTRAINT df_orders_vat DEFAULT 0,
        shipping_fee INT NOT NULL CONSTRAINT df_orders_shipping DEFAULT 30000,
        total INT NOT NULL,
        voucher_code VARCHAR(32) NULL,
        address NVARCHAR(MAX) NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_orders_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_orders PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_orders_code UNIQUE NONCLUSTERED (code),
        CONSTRAINT fk_orders_users FOREIGN KEY (user_id) REFERENCES dbo.users(id),
        CONSTRAINT ck_orders_status CHECK (status IN ('pending', 'confirmed', 'shipping', 'done', 'cancelled')),
        CONSTRAINT ck_orders_amounts CHECK (subtotal >= 0 AND discount >= 0 AND vat >= 0 AND shipping_fee >= 0 AND total >= 0)
    );
    CREATE NONCLUSTERED INDEX ix_orders_user_id ON dbo.orders (user_id);
    CREATE NONCLUSTERED INDEX ix_orders_status ON dbo.orders (status);
    CREATE NONCLUSTERED INDEX ix_orders_created_at ON dbo.orders (created_at DESC);
    PRINT N'Đã tạo bảng orders.';
END
GO

-- 6. BẢNG ORDER_ITEMS (Chi tiết các mặt hàng trong đơn)
IF OBJECT_ID(N'dbo.order_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.order_items (
        id INT IDENTITY(1,1) NOT NULL,
        order_id INT NOT NULL,
        product_id INT NOT NULL,
        price INT NOT NULL,
        qty INT NOT NULL,
        CONSTRAINT pk_order_items PRIMARY KEY CLUSTERED (id),
        CONSTRAINT fk_order_items_orders FOREIGN KEY (order_id) REFERENCES dbo.orders(id) ON DELETE CASCADE,
        CONSTRAINT fk_order_items_products FOREIGN KEY (product_id) REFERENCES dbo.products(id),
        CONSTRAINT ck_order_items_qty CHECK (qty BETWEEN 1 AND 99),
        CONSTRAINT ck_order_items_price CHECK (price >= 0)
    );
    CREATE NONCLUSTERED INDEX ix_order_items_order_id ON dbo.order_items (order_id);
    CREATE NONCLUSTERED INDEX ix_order_items_product_id ON dbo.order_items (product_id);
    PRINT N'Đã tạo bảng order_items.';
END
GO

-- 7. BẢNG PAYMENTS (Giao dịch thanh toán cổng hoặc mô phỏng)
IF OBJECT_ID(N'dbo.payments', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.payments (
        id INT IDENTITY(1,1) NOT NULL,
        order_id INT NOT NULL,
        method VARCHAR(32) NOT NULL,
        status VARCHAR(20) NOT NULL CONSTRAINT df_payments_status DEFAULT 'pending',
        provider VARCHAR(32) NOT NULL CONSTRAINT df_payments_provider DEFAULT 'mock',
        currency VARCHAR(8) NOT NULL CONSTRAINT df_payments_currency DEFAULT 'VND',
        amount_minor BIGINT NULL,
        attempt INT NOT NULL CONSTRAINT df_payments_attempt DEFAULT 1,
        txn_ref VARCHAR(64) NULL,
        provider_order_id VARCHAR(128) NULL,
        provider_txn_id VARCHAR(128) NULL,
        provider_status VARCHAR(64) NULL,
        raw_payload NVARCHAR(MAX) NULL,
        paid_at DATETIME2 NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_payments_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_payments PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_payments_order_id UNIQUE NONCLUSTERED (order_id),
        CONSTRAINT fk_payments_orders FOREIGN KEY (order_id) REFERENCES dbo.orders(id) ON DELETE CASCADE,
        CONSTRAINT ck_payments_status CHECK (status IN ('pending', 'paid', 'failed', 'refund_pending', 'refunded'))
    );
    -- Filtered unique index: chỉ bắt buộc unique khi txn_ref không null
    CREATE UNIQUE NONCLUSTERED INDEX uq_payments_txn_ref ON dbo.payments (txn_ref) WHERE txn_ref IS NOT NULL;
    CREATE NONCLUSTERED INDEX ix_payments_status ON dbo.payments (status);
    PRINT N'Đã tạo bảng payments.';
END
GO

-- 8. BẢNG REFUNDS (Yêu cầu hoàn tiền giữ trong 72 giờ)
IF OBJECT_ID(N'dbo.refunds', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.refunds (
        id INT IDENTITY(1,1) NOT NULL,
        order_id INT NOT NULL,
        payment_id INT NOT NULL,
        status VARCHAR(20) NOT NULL CONSTRAINT df_refunds_status DEFAULT 'scheduled',
        amount BIGINT NOT NULL,
        currency VARCHAR(8) NOT NULL CONSTRAINT df_refunds_currency DEFAULT 'VND',
        reason NVARCHAR(255) NULL,
        requested_by INT NULL,
        confirmed_by INT NULL,
        requested_at DATETIME2 NOT NULL CONSTRAINT df_refunds_requested_at DEFAULT SYSUTCDATETIME(),
        due_at DATETIME2 NOT NULL,
        confirmed_at DATETIME2 NULL,
        provider_refund_id VARCHAR(128) NULL,
        raw_payload NVARCHAR(MAX) NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_refunds_created_at DEFAULT SYSUTCDATETIME(),
        updated_at DATETIME2 NOT NULL CONSTRAINT df_refunds_updated_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_refunds PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_refunds_order_id UNIQUE NONCLUSTERED (order_id),
        CONSTRAINT fk_refunds_orders FOREIGN KEY (order_id) REFERENCES dbo.orders(id),
        CONSTRAINT fk_refunds_payments FOREIGN KEY (payment_id) REFERENCES dbo.payments(id),
        CONSTRAINT fk_refunds_requested_by FOREIGN KEY (requested_by) REFERENCES dbo.users(id),
        CONSTRAINT fk_refunds_confirmed_by FOREIGN KEY (confirmed_by) REFERENCES dbo.users(id),
        CONSTRAINT ck_refunds_status CHECK (status IN ('scheduled', 'processing', 'succeeded', 'failed', 'rejected')),
        CONSTRAINT ck_refunds_amount CHECK (amount > 0)
    );
    CREATE NONCLUSTERED INDEX ix_refunds_status_due_at ON dbo.refunds (status, due_at);
    PRINT N'Đã tạo bảng refunds.';
END
GO

-- 9. BẢNG NEWSLETTER_SUBSCRIBERS (Người đăng ký nhận bản tin)
IF OBJECT_ID(N'dbo.newsletter_subscribers', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.newsletter_subscribers (
        id INT IDENTITY(1,1) NOT NULL,
        email VARCHAR(255) NOT NULL,
        created_at DATETIME2 NOT NULL CONSTRAINT df_subscribers_created_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_newsletter_subscribers PRIMARY KEY CLUSTERED (id),
        CONSTRAINT uq_newsletter_subscribers_email UNIQUE NONCLUSTERED (email)
    );
    PRINT N'Đã tạo bảng newsletter_subscribers.';
END
GO

-- 10. BẢNG EMAIL_CAMPAIGNS (Lịch sử gửi email marketing)
IF OBJECT_ID(N'dbo.email_campaigns', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.email_campaigns (
        id INT IDENTITY(1,1) NOT NULL,
        subject NVARCHAR(255) NOT NULL,
        body NVARCHAR(MAX) NOT NULL,
        recipient_count INT NOT NULL CONSTRAINT df_campaigns_count DEFAULT 0,
        status VARCHAR(32) NOT NULL CONSTRAINT df_campaigns_status DEFAULT 'sending',
        sent_at DATETIME2 NOT NULL CONSTRAINT df_campaigns_sent_at DEFAULT SYSUTCDATETIME(),
        CONSTRAINT pk_email_campaigns PRIMARY KEY CLUSTERED (id)
    );
    PRINT N'Đã tạo bảng email_campaigns.';
END
GO

-- 11. BẢNG PRODUCT_IMAGES (Bộ sưu tập hình ảnh chi tiết sản phẩm)
IF OBJECT_ID(N'dbo.product_images', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.product_images (
        id INT IDENTITY(1,1) NOT NULL,
        product_id INT NOT NULL,
        url VARCHAR(500) NOT NULL,
        alt NVARCHAR(200) NOT NULL CONSTRAINT df_product_images_alt DEFAULT N'',
        sort INT NOT NULL CONSTRAINT df_product_images_sort DEFAULT 0,
        CONSTRAINT pk_product_images PRIMARY KEY CLUSTERED (id),
        CONSTRAINT fk_product_images_products FOREIGN KEY (product_id) REFERENCES dbo.products(id) ON DELETE CASCADE
    );
    CREATE NONCLUSTERED INDEX ix_product_images_product_id ON dbo.product_images (product_id);
    PRINT N'Đã tạo bảng product_images.';
END
GO

PRINT N'=== HOÀN TẤT TẠO TOÀN BỘ CẤU TRÚC BẢNG ELECTROHUB ===';
GO
