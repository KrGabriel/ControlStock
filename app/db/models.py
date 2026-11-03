"""Modelo relacional de ControlStock (SQLAlchemy 2)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain import (
    COUNT_DRAFT,
    DELIVERY_ACTIVE,
    ICLASS_PENDING,
    ITEM_REUSABLE,
    STATE_AVAILABLE,
    STATE_ASSIGNED,
    STATE_DAMAGED,
    STATE_LOST,
    STATE_OUT_OF_SERVICE,
    STATE_REPAIR,
)
from app.utils.dates import now


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    deliveries: Mapped[list["Delivery"]] = relationship(
        back_populates="created_by_user", foreign_keys="Delivery.created_by_id"
    )
    returns: Mapped[list["ReturnRecord"]] = relationship(back_populates="created_by_user")
    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="user", foreign_keys="StockMovement.user_id"
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(250), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)

    items: Mapped[list["Item"]] = relationship(back_populates="category")


class Crew(Base):
    __tablename__ = "crews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    notes: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)

    deliveries: Mapped[list["Delivery"]] = relationship(back_populates="crew")
    returns: Mapped[list["ReturnRecord"]] = relationship(back_populates="crew")
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="crew")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("qty_available >= 0", name="ck_item_available_nonneg"),
        CheckConstraint("qty_assigned >= 0", name="ck_item_assigned_nonneg"),
        CheckConstraint("qty_repair >= 0", name="ck_item_repair_nonneg"),
        CheckConstraint("qty_damaged >= 0", name="ck_item_damaged_nonneg"),
        CheckConstraint("qty_lost >= 0", name="ck_item_lost_nonneg"),
        CheckConstraint("qty_out_of_service >= 0", name="ck_item_out_nonneg"),
        CheckConstraint("stock_min >= 0", name="ck_item_min_nonneg"),
        Index("ix_items_name", "name"),
        Index("ix_items_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="unidades")
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, default=ITEM_REUSABLE)
    stock_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_assigned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_repair: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_damaged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_lost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    qty_out_of_service: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now, onupdate=now)

    category: Mapped["Category"] = relationship(back_populates="items")
    delivery_details: Mapped[list["DeliveryDetail"]] = relationship(back_populates="item")
    return_details: Mapped[list["ReturnDetail"]] = relationship(back_populates="item")
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="item")
    count_details: Mapped[list["InventoryCountDetail"]] = relationship(back_populates="item")

    @property
    def total_units(self) -> int:
        return (
            self.qty_available
            + self.qty_assigned
            + self.qty_repair
            + self.qty_damaged
            + self.qty_lost
            + self.qty_out_of_service
        )

    @property
    def primary_status(self) -> str:
        if self.qty_available <= 0:
            return "NO_STOCK"
        if self.qty_available <= self.stock_min:
            return "LOW"
        if self.qty_repair > 0:
            return "REPAIR"
        if self.qty_out_of_service > 0:
            return "OUT_OF_SERVICE"
        if self.qty_damaged > 0:
            return "DAMAGED"
        if self.qty_lost > 0:
            return "LOST"
        return "OK"

    def qty_for_state(self, state: str) -> int:
        return int(getattr(self, f"qty_{state.lower()}"))


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint("code", name="uq_delivery_code"),
        Index("ix_deliveries_created", "created_at"),
        Index("ix_deliveries_crew", "crew_id"),
        Index("ix_deliveries_iclass", "iclass_status"),
        Index("ix_deliveries_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    crew_id: Mapped[int] = mapped_column(ForeignKey("crews.id", ondelete="RESTRICT"), nullable=False)
    technician: Mapped[str] = mapped_column(String(150), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DELIVERY_ACTIVE)
    iclass_status: Mapped[str] = mapped_column(String(20), nullable=False, default=ICLASS_PENDING)
    iclass_loaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    iclass_loaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    iclass_reference: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    iclass_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    crew: Mapped["Crew"] = relationship(back_populates="deliveries")
    created_by_user: Mapped["User | None"] = relationship(
        back_populates="deliveries", foreign_keys=[created_by_id]
    )
    loaded_by_user: Mapped["User | None"] = relationship(foreign_keys=[iclass_loaded_by_id])
    details: Mapped[list["DeliveryDetail"]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan", order_by="DeliveryDetail.id"
    )
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="delivery")
    iclass_history: Mapped[list["IClassRegistration"]] = relationship(
        back_populates="delivery", order_by="IClassRegistration.id.desc()"
    )

    @property
    def total_units(self) -> int:
        return sum(d.quantity for d in self.details)


class DeliveryDetail(Base):
    __tablename__ = "delivery_details"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_delivery_detail_qty_positive"),
        CheckConstraint("qty_returned >= 0", name="ck_delivery_detail_returned_nonneg"),
        CheckConstraint("qty_returned <= quantity", name="ck_delivery_detail_returned_lte"),
        Index("ix_delivery_details_delivery", "delivery_id"),
        Index("ix_delivery_details_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    qty_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_reusable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    item_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    item_brand_snapshot: Mapped[str] = mapped_column(String(100), nullable=False, default="")

    delivery: Mapped["Delivery"] = relationship(back_populates="details")
    item: Mapped["Item"] = relationship(back_populates="delivery_details")
    return_details: Mapped[list["ReturnDetail"]] = relationship(back_populates="delivery_detail")

    @property
    def pending_qty(self) -> int:
        return max(0, self.quantity - self.qty_returned)


class ReturnRecord(Base):
    __tablename__ = "returns"
    __table_args__ = (
        UniqueConstraint("code", name="uq_return_code"),
        Index("ix_returns_created", "created_at"),
        Index("ix_returns_crew", "crew_id"),
        Index("ix_returns_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    crew_id: Mapped[int] = mapped_column(ForeignKey("crews.id", ondelete="RESTRICT"), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=DELIVERY_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    void_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    crew: Mapped["Crew"] = relationship(back_populates="returns")
    created_by_user: Mapped["User | None"] = relationship(back_populates="returns")
    details: Mapped[list["ReturnDetail"]] = relationship(
        back_populates="return_record", cascade="all, delete-orphan", order_by="ReturnDetail.id"
    )
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="return_record")

    @property
    def total_units(self) -> int:
        return sum(d.quantity for d in self.details)


class ReturnDetail(Base):
    __tablename__ = "return_details"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_return_detail_qty_positive"),
        Index("ix_return_details_return", "return_id"),
        Index("ix_return_details_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    return_id: Mapped[int] = mapped_column(
        ForeignKey("returns.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    delivery_detail_id: Mapped[int | None] = mapped_column(
        ForeignKey("delivery_details.id", ondelete="RESTRICT"), nullable=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(String(250), nullable=False, default="")

    return_record: Mapped["ReturnRecord"] = relationship(back_populates="details")
    item: Mapped["Item"] = relationship(back_populates="return_details")
    delivery_detail: Mapped["DeliveryDetail | None"] = relationship(back_populates="return_details")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_movement_qty_positive"),
        Index("ix_movements_created", "created_at"),
        Index("ix_movements_item", "item_id"),
        Index("ix_movements_crew", "crew_id"),
        Index("ix_movements_type", "movement_type"),
        Index("ix_movements_delivery", "delivery_id"),
        Index("ix_movements_return", "return_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    item_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_delta: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stock_before: Mapped[int] = mapped_column(Integer, nullable=False)
    stock_after: Mapped[int] = mapped_column(Integer, nullable=False)
    crew_id: Mapped[int | None] = mapped_column(
        ForeignKey("crews.id", ondelete="RESTRICT"), nullable=True
    )
    technician: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    delivery_id: Mapped[int | None] = mapped_column(
        ForeignKey("deliveries.id", ondelete="RESTRICT"), nullable=True
    )
    return_id: Mapped[int | None] = mapped_column(
        ForeignKey("returns.id", ondelete="RESTRICT"), nullable=True
    )
    inventory_count_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_counts.id", ondelete="RESTRICT"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    from_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_state: Mapped[str | None] = mapped_column(String(20), nullable=True)
    observations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    is_voided: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    void_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    related_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="RESTRICT"), nullable=True
    )

    item: Mapped["Item"] = relationship(back_populates="movements")
    crew: Mapped["Crew | None"] = relationship(back_populates="movements")
    user: Mapped["User | None"] = relationship(back_populates="movements", foreign_keys=[user_id])
    delivery: Mapped["Delivery | None"] = relationship(back_populates="movements")
    return_record: Mapped["ReturnRecord | None"] = relationship(back_populates="movements")
    inventory_count: Mapped["InventoryCount | None"] = relationship(back_populates="movements")


class StockAdjustment(Base):
    __tablename__ = "stock_adjustments"
    __table_args__ = (
        Index("ix_adjustments_item", "item_id"),
        Index("ix_adjustments_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    adjustment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    previous_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_movements.id", ondelete="RESTRICT"), nullable=True
    )
    inventory_count_id: Mapped[int | None] = mapped_column(
        ForeignKey("inventory_counts.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)


class InventoryCount(Base):
    __tablename__ = "inventory_counts"
    __table_args__ = (
        UniqueConstraint("code", name="uq_count_code"),
        Index("ix_counts_status", "status"),
        Index("ix_counts_created", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=COUNT_DRAFT)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    total_differences: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    details: Mapped[list["InventoryCountDetail"]] = relationship(
        back_populates="inventory_count",
        cascade="all, delete-orphan",
        order_by="InventoryCountDetail.id",
    )
    movements: Mapped[list["StockMovement"]] = relationship(back_populates="inventory_count")

    @property
    def difference_units(self) -> int:
        return sum(d.difference or 0 for d in self.details)


class InventoryCountDetail(Base):
    __tablename__ = "inventory_count_details"
    __table_args__ = (
        Index("ix_count_details_count", "count_id"),
        Index("ix_count_details_item", "item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    count_id: Mapped[int] = mapped_column(
        ForeignKey("inventory_counts.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    item_name_snapshot: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    system_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    physical_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difference: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(String(250), nullable=False, default="")

    inventory_count: Mapped["InventoryCount"] = relationship(back_populates="details")
    item: Mapped["Item"] = relationship(back_populates="count_details")


class IClassRegistration(Base):
    __tablename__ = "iclass_registration"
    __table_args__ = (Index("ix_iclass_delivery", "delivery_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(
        ForeignKey("deliveries.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)

    delivery: Mapped["Delivery"] = relationship(back_populates="iclass_history")
    user: Mapped["User | None"] = relationship()


class Backup(Base):
    __tablename__ = "backups"
    __table_args__ = (Index("ix_backups_created", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now)

    user: Mapped["User | None"] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=now, onupdate=now)


STATE_ATTRS = {
    STATE_AVAILABLE: "qty_available",
    STATE_ASSIGNED: "qty_assigned",
    STATE_REPAIR: "qty_repair",
    STATE_DAMAGED: "qty_damaged",
    STATE_LOST: "qty_lost",
    STATE_OUT_OF_SERVICE: "qty_out_of_service",
}
