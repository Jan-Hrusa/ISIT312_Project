
-- Task 22: Synthetic sample data for warehouse OLAP queries.
-- All data is fictional. Currency: CZK.

-- ------------------------------------------------------------
-- 1. Projects
-- ------------------------------------------------------------

INSERT INTO TABLE ${DW_DB}.dim_project
SELECT
    1, 'FVE-2024-01', 'Solar Project Alpha', 'Brno', 'South Moravia',
    CAST(2.00 AS DECIMAL(5,2)), FALSE,
    CAST(3000000.00 AS DECIMAL(14,2)),
    'COMPLETED', 2024,
    CAST('2024-03-01' AS DATE), CAST('2025-10-31' AS DATE)
UNION ALL
SELECT
    2, 'FVE-2025-02', 'Solar Project Beta', 'Olomouc', 'Olomouc',
    CAST(1.50 AS DECIMAL(5,2)), FALSE,
    CAST(2500000.00 AS DECIMAL(14,2)),
    'COMPLETED', 2025,
    CAST('2025-04-01' AS DATE), CAST('2026-09-30' AS DATE)
UNION ALL
SELECT
    3, 'FVE-2026-03', 'Solar Project Gamma', 'Zlin', 'Zlin',
    CAST(1.00 AS DECIMAL(5,2)), TRUE,
    CAST(1800000.00 AS DECIMAL(14,2)),
    'ACTIVE', 2026,
    CAST('2026-02-01' AS DATE), CAST('2027-06-30' AS DATE);

-- ------------------------------------------------------------
-- 2. Suppliers
-- ------------------------------------------------------------

INSERT INTO TABLE ${DW_DB}.dim_supplier
SELECT 1, '10000001', 'Fictional Solar Supplies', 'PANELS'
UNION ALL
SELECT 2, '10000002', 'Fictional Electrical Works', 'INVERTERS'
UNION ALL
SELECT 3, '10000003', 'Fictional Design Services', 'DESIGN'
UNION ALL
SELECT 4, '10000004', 'Fictional Mounting Works', 'STRUCTURES';
-- ------------------------------------------------------------
-- 3. Cost categories
-- ------------------------------------------------------------

INSERT INTO TABLE ${DW_DB}.dim_cost_category
SELECT 1, 'PANELS', 'Panels', 'technology'
UNION ALL
SELECT 2, 'INVERTERS', 'Inverters', 'technology'
UNION ALL
SELECT 3, 'STRUCTURES', 'Mounting structures', 'construction'
UNION ALL
SELECT 4, 'DESIGN', 'Design', 'services';

-- ------------------------------------------------------------
-- 4. Dates
-- Includes project signing dates and invoice issue/due dates.
-- date_key uses YYYYMMDD.
-- ------------------------------------------------------------

INSERT INTO TABLE ${DW_DB}.dim_date
SELECT
    20240301, CAST('2024-03-01' AS DATE),
    1, 3, 'March', 1, 2024, '2024-W09'
UNION ALL
SELECT
    20250401, CAST('2025-04-01' AS DATE),
    1, 4, 'April', 2, 2025, '2025-W14'
UNION ALL
SELECT
    20260201, CAST('2026-02-01' AS DATE),
    1, 2, 'February', 1, 2026, '2026-W05'
UNION ALL
SELECT
    20251115, CAST('2025-11-15' AS DATE),
    15, 11, 'November', 4, 2025, '2025-W46'
UNION ALL
SELECT
    20251215, CAST('2025-12-15' AS DATE),
    15, 12, 'December', 4, 2025, '2025-W51'
UNION ALL
SELECT
    20260115, CAST('2026-01-15' AS DATE),
    15, 1, 'January', 1, 2026, '2026-W03'
UNION ALL
SELECT
    20260215, CAST('2026-02-15' AS DATE),
    15, 2, 'February', 1, 2026, '2026-W07';

-- ------------------------------------------------------------
-- 5. Budget lines
-- One budget amount per project and category.
-- Partitioned by the project's signed year.
-- ------------------------------------------------------------

-- FVE-2024-01: total budget = 2,000 CZK
INSERT INTO TABLE ${DW_DB}.fact_budget_line
PARTITION (signed_year=2024)
SELECT
    1, 1, 20240301, CAST(1000.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    1, 2, 20240301, CAST(500.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    1, 3, 20240301, CAST(300.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    1, 4, 20240301, CAST(200.00 AS DECIMAL(14,2));

-- FVE-2025-02: total budget = 2,000 CZK
INSERT INTO TABLE ${DW_DB}.fact_budget_line
PARTITION (signed_year=2025)
SELECT
    2, 1, 20250401, CAST(1000.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    2, 2, 20250401, CAST(500.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    2, 3, 20250401, CAST(300.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    2, 4, 20250401, CAST(200.00 AS DECIMAL(14,2));

-- FVE-2026-03: total budget = 2,000 CZK
INSERT INTO TABLE ${DW_DB}.fact_budget_line
PARTITION (signed_year=2026)
SELECT
    3, 1, 20260201, CAST(1000.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    3, 2, 20260201, CAST(500.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    3, 3, 20260201, CAST(300.00 AS DECIMAL(14,2))
UNION ALL
SELECT
    3, 4, 20260201, CAST(200.00 AS DECIMAL(14,2));

-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 6. Invoice lines
-- 36 synthetic invoice lines across November 2025-February 2026.
-- Supplier keys: 1=PANELS, 2=INVERTERS, 3=DESIGN, 4=STRUCTURES.
-- ------------------------------------------------------------

-- November and December 2025
INSERT INTO TABLE ${DW_DB}.fact_invoice_line
PARTITION (issue_year=2025)
SELECT 'A01', 1, 1, 1, 1, 20251115, 20251115, 300.00, 63.00, 363.00, 'PAID', 0
UNION ALL
SELECT 'A02', 1, 1, 2, 2, 20251115, 20251115, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'A03', 1, 1, 4, 3, 20251115, 20251115, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'A04', 1, 1, 1, 1, 20251215, 20251215, 400.00, 84.00, 484.00, 'PAID', 0
UNION ALL
SELECT 'A05', 1, 1, 2, 2, 20251215, 20251215, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'A06', 1, 1, 4, 3, 20251215, 20251215, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'B01', 1, 2, 1, 1, 20251115, 20251115, 300.00, 63.00, 363.00, 'PAID', 0
UNION ALL
SELECT 'B02', 1, 2, 2, 2, 20251115, 20251115, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'B03', 1, 2, 4, 3, 20251115, 20251115, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'B04', 1, 2, 1, 1, 20251215, 20251215, 300.00, 63.00, 363.00, 'PAID', 0
UNION ALL
SELECT 'B05', 1, 2, 2, 2, 20251215, 20251215, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'B06', 1, 2, 4, 3, 20251215, 20251215, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'C01', 1, 3, 1, 1, 20251115, 20251115, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'C02', 1, 3, 2, 2, 20251115, 20251115, 110.00, 23.10, 133.10, 'PAID', 0
UNION ALL
SELECT 'C03', 1, 3, 4, 3, 20251115, 20251115, 90.00, 18.90, 108.90, 'PAID', 0
UNION ALL
SELECT 'C04', 1, 3, 1, 1, 20251215, 20251215, 250.00, 52.50, 302.50, 'PAID', 0
UNION ALL
SELECT 'C05', 1, 3, 2, 2, 20251215, 20251215, 110.00, 23.10, 133.10, 'PAID', 0
UNION ALL
SELECT 'C06', 1, 3, 4, 3, 20251215, 20251215, 90.00, 18.90, 108.90, 'PAID', 0;

-- January and February 2026
INSERT INTO TABLE ${DW_DB}.fact_invoice_line
PARTITION (issue_year=2026)
SELECT 'A07', 1, 1, 1, 1, 20260115, 20260115, 300.00, 63.00, 363.00, 'PAID', 0
UNION ALL
SELECT 'A08', 1, 1, 2, 2, 20260115, 20260115, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'A09', 1, 1, 4, 3, 20260115, 20260115, 100.00, 21.00, 121.00, 'PAID', 0
UNION ALL
SELECT 'A10', 1, 1, 1, 1, 20260215, 20260215, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'A11', 1, 1, 2, 2, 20260215, 20260215, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'A12', 1, 1, 3, 4, 20260215, 20260215, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'B07', 1, 2, 1, 1, 20260115, 20260115, 280.00, 58.80, 338.80, 'PAID', 0
UNION ALL
SELECT 'B08', 1, 2, 2, 2, 20260115, 20260115, 105.00, 22.05, 127.05, 'PAID', 0
UNION ALL
SELECT 'B09', 1, 2, 4, 3, 20260115, 20260115, 115.00, 24.15, 139.15, 'PAID', 0
UNION ALL
SELECT 'B10', 1, 2, 1, 1, 20260215, 20260215, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'B11', 1, 2, 2, 2, 20260215, 20260215, 195.00, 40.95, 235.95, 'PAID', 0
UNION ALL
SELECT 'B12', 1, 2, 3, 4, 20260215, 20260215, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'C07', 1, 3, 1, 1, 20260115, 20260115, 250.00, 52.50, 302.50, 'PAID', 0
UNION ALL
SELECT 'C08', 1, 3, 2, 2, 20260115, 20260115, 110.00, 23.10, 133.10, 'PAID', 0
UNION ALL
SELECT 'C09', 1, 3, 4, 3, 20260115, 20260115, 90.00, 18.90, 108.90, 'PAID', 0
UNION ALL
SELECT 'C10', 1, 3, 1, 1, 20260215, 20260215, 200.00, 42.00, 242.00, 'PAID', 0
UNION ALL
SELECT 'C11', 1, 3, 2, 2, 20260215, 20260215, 120.00, 25.20, 145.20, 'PAID', 0
UNION ALL
SELECT 'C12', 1, 3, 3, 4, 20260215, 20260215, 180.00, 37.80, 217.80, 'PAID', 0;
