"""Layer 2: normalised tables.

Statement lines are stored long (field_name, value) rather than as wide columns.
Schema discovery found four families whose P&L field sets overlap by as little
as three fields, and life insurers alone carry 67. A wide table would need
several hundred mostly-null columns and a migration every time FinEdge adds a
line. See app/ingest/schemas.py.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
)

layer2_metadata = MetaData()


company = Table(
    "company",
    layer2_metadata,
    Column("symbol", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("nse_code", String),
    Column("bse_code", String),
    Column("consolidated_ind", Boolean, nullable=False, server_default="0"),
    # FinEdge's own labels, kept verbatim for traceability.
    Column("macro_sector_raw", String),
    Column("sector_raw", String),
    Column("industry_raw", String),
    Column("sub_industry_raw", String),
    # Normalised hierarchy, broad to narrow. FinEdge's `sector` is narrower than
    # its `industry`, which inverts the conventional order - see normalise.py.
    Column("macro_sector", String),
    Column("industry", String),
    Column("sector", String),
    Column("sub_industry", String),
    Column("schema_kind", String),
    Column("schema_confidence", Float),
    Column("website", String),
    Column("description", String),
    Column("market_cap", Float),
    Column("updated_at", String, nullable=False),
    Index("idx_company_sector", "sector"),
    Index("idx_company_industry", "industry"),
    Index("idx_company_market_cap", "market_cap"),
)


quote = Table(
    "quote",
    layer2_metadata,
    Column("symbol", String, primary_key=True),
    Column("current_price", Float),
    Column("open_price", Float),
    Column("high_price", Float),
    Column("low_price", Float),
    Column("volume", Float),
    Column("change_pct", Float),
    Column("high52", Float),
    Column("low52", Float),
    Column("market_cap", Float),
    Column("shares", Float),
    Column("trade_time", String),
    Column("updated_at", String, nullable=False),
    Index("idx_quote_market_cap", "market_cap"),
)


statement_period = Table(
    "statement_period",
    layer2_metadata,
    Column("id", Integer, primary_key=True),
    Column("symbol", String, nullable=False),
    Column("statement_type", String, nullable=False),  # s | c
    Column("statement_code", String, nullable=False),  # pl | bs | cf
    Column("period_kind", String, nullable=False),  # annual | quarterly | ttm | halfyearly
    Column("header", String),  # "Mar 2026", "TTM"
    Column("year", Integer),
    Column("period_start", String),
    Column("period_end", String),
    Column("result_date", String),
    Column("schema_kind", String),
    UniqueConstraint(
        "symbol",
        "statement_type",
        "statement_code",
        "period_kind",
        "header",
        name="uq_statement_period",
    ),
    Index("idx_period_symbol", "symbol", "statement_code", "period_kind"),
)


statement_line = Table(
    "statement_line",
    layer2_metadata,
    Column(
        "period_id",
        Integer,
        ForeignKey("statement_period.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("field_name", String, primary_key=True),
    Column("value", Float),
    Index("idx_line_field", "field_name"),
)


price_daily = Table(
    "price_daily",
    layer2_metadata,
    Column("symbol", String, primary_key=True),
    Column("quote_date", String, primary_key=True),
    Column("open", Float),
    Column("high", Float),
    Column("low", Float),
    Column("close", Float),
    Column("volume", Float),
    Index("idx_price_date", "quote_date"),
)


index_master = Table(
    "index_master",
    layer2_metadata,
    Column("index_symbol", String, primary_key=True),
    Column("index_name", String, nullable=False),
    Column("exchange", String),
    Column("index_type", String),
    Column("index_sub_type", String),
    Column("market_cap", Float),
    Column("updated_at", String, nullable=False),
)


index_constituent = Table(
    "index_constituent",
    layer2_metadata,
    Column("index_symbol", String, primary_key=True),
    Column("symbol", String, primary_key=True),
    Index("idx_constituent_symbol", "symbol"),
)


index_quote_daily = Table(
    "index_quote_daily",
    layer2_metadata,
    Column("index_symbol", String, primary_key=True),
    Column("quote_date", String, primary_key=True),
    Column("close_price", Float),
    Column("open_price", Float),
    Column("high_price", Float),
    Column("low_price", Float),
    Column("change_pct", Float),
    Column("points_change", Float),
    Column("pe", Float),
    Column("pb", Float),
    Column("div_yield", Float),
    Column("market_cap", Float),
    Column("turnover", Float),
    Column("volume", Float),
)


index_return = Table(
    "index_return",
    layer2_metadata,
    Column("index_symbol", String, primary_key=True),
    Column("horizon", String, primary_key=True),  # 1M, 3M, 6M, 1Y, 3Y, 5Y, 7Y, 10Y
    Column("return_pct", Float),
    Column("as_of", String),
)


def create_layer2(engine: object) -> None:
    layer2_metadata.create_all(engine)  # type: ignore[arg-type]
