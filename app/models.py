from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Number = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=4)]


class Line(BaseModel):
    model_config = ConfigDict(extra='forbid')
    line_id: str = Field(min_length=1, max_length=50)
    sku: str | None = Field(default=None, max_length=80)
    description: str = Field(default='', max_length=500)
    unit: str | None = Field(default=None, max_length=40)
    quantity: Number | None = None
    unit_price: Number | None = None
    stated_total: Number | None = None
    page: int = Field(default=1, ge=1, le=10)
    quote: str = Field(default='', max_length=1200)

    @field_validator('sku', 'unit')
    @classmethod
    def clean_key(cls, value):
        return value.strip() or None if value is not None else None


class Document(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['PO', 'INVOICE']
    number: str | None = Field(default=None, max_length=100)
    po_reference: str | None = Field(default=None, max_length=100)
    supplier: str | None = Field(default=None, max_length=200)
    currency: str | None = Field(default=None, max_length=3)
    lines: list[Line] = Field(default_factory=list, max_length=200)

    @field_validator('number', 'po_reference', 'supplier')
    @classmethod
    def clean_header(cls, value):
        return value.strip() or None if value is not None else None

    @field_validator('currency')
    @classmethod
    def currency_code(cls, value):
        if not value or not value.strip():
            return None
        value = value.strip().upper()
        if len(value) != 3 or not value.isascii() or not value.isalpha():
            raise ValueError('Currency must be a three-letter code')
        return value

    @field_validator('lines')
    @classmethod
    def unique_ids(cls, values):
        if len({line.line_id for line in values}) != len(values):
            raise ValueError('Duplicate line IDs')
        return values


class CompareRequest(BaseModel):
    po_id: str
    invoice_id: str
    po: Document
    invoice: Document
    reviewed: bool
