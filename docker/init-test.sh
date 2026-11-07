#!/bin/sh
set -e

echo "=== Đang khởi tạo cơ sở dữ liệu ElectroHub cho container Test môn học ==="
for f in /sql/01_ddl_tables.sql /sql/02_rules_defaults.sql /sql/03_triggers.sql /sql/04_stored_procedures.sql /sql/05_cursors.sql /sql/06_views_and_functions.sql /sql/07_transactions_concurrency.sql /sql/08_seed_data.sql; do
  echo "Executing $f..."
  /opt/mssql-tools18/bin/sqlcmd -S sqlserver-test -U sa -C -b -i "$f"
done
echo "=== Khởi tạo cơ sở dữ liệu Test thành công 100%! ==="
