IF DB_ID(N'invoice_reconciliation') IS NULL
    CREATE DATABASE invoice_reconciliation;
GO
USE invoice_reconciliation;
GO
IF OBJECT_ID(N'dbo.documents', N'U') IS NULL
CREATE TABLE dbo.documents (
    document_id uniqueidentifier PRIMARY KEY,
    kind varchar(7) NOT NULL CHECK (kind IN ('PO', 'INVOICE')),
    filename nvarchar(260) NOT NULL,
    sha256 char(64) NOT NULL,
    extraction_method varchar(20) NOT NULL,
    original_json nvarchar(max) NOT NULL CHECK (ISJSON(original_json) = 1),
    created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
IF OBJECT_ID(N'dbo.review_runs', N'U') IS NULL
CREATE TABLE dbo.review_runs (
    run_id uniqueidentifier PRIMARY KEY,
    po_id uniqueidentifier NOT NULL REFERENCES dbo.documents(document_id),
    invoice_id uniqueidentifier NOT NULL REFERENCES dbo.documents(document_id),
    currency char(3) NULL,
    net_difference decimal(28, 4) NULL,
    reviewed bit NOT NULL,
    complete bit NOT NULL,
    snapshot_json nvarchar(max) NOT NULL CHECK (ISJSON(snapshot_json) = 1),
    result_json nvarchar(max) NOT NULL CHECK (ISJSON(result_json) = 1),
    created_at datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
IF OBJECT_ID(N'dbo.review_lines', N'U') IS NULL
CREATE TABLE dbo.review_lines (
    run_id uniqueidentifier NOT NULL REFERENCES dbo.review_runs(run_id),
    document_kind varchar(7) NOT NULL CHECK (document_kind IN ('PO', 'INVOICE')),
    line_id nvarchar(50) NOT NULL,
    sku nvarchar(80) NULL,
    description nvarchar(500) NOT NULL,
    unit nvarchar(40) NULL,
    quantity decimal(18, 4) NULL,
    unit_price decimal(18, 4) NULL,
    stated_total decimal(18, 4) NULL,
    source_page int NOT NULL,
    source_quote nvarchar(1200) NOT NULL,
    PRIMARY KEY (run_id, document_kind, line_id)
);
GO
