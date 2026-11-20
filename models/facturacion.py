"""
Módulo de Dominio: Pedidos, Facturación Electrónica DTE y Comisiones (RF-17, RF-23, RF-25)
Sistema DistriGest - DistriSur Araucanía SpA
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from models.clientes import Cliente, Vendedor
from models.inventario import Producto


TASA_IVA = Decimal("0.19")


@dataclass
class DetallePedido:
    """Línea de detalle de un pedido comercial."""

    idDetalle: int
    cantidad: int
    precioUnitario: Decimal
    producto: Optional[Producto] = None
    subtotal: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.precioUnitario = Decimal(str(self.precioUnitario))
        if self.subtotal == Decimal("0") and self.cantidad > 0:
            self.calcularSubtotal()
        else:
            self.subtotal = Decimal(str(self.subtotal))

    def calcularSubtotal(self) -> Decimal:
        """Calcula y almacena el subtotal de la línea."""
        self.subtotal = Decimal(self.cantidad) * self.precioUnitario
        return self.subtotal


@dataclass
class Pedido:
    """Pedido comercial con cálculo de IVA (19%) y validación de stock (RF-17)."""

    idPedido: str | int
    fechaEmision: datetime = field(default_factory=datetime.now)
    estado: str = "Pendiente"
    montoNeto: Decimal = Decimal("0")
    montoIva: Decimal = Decimal("0")
    montoTotal: Decimal = Decimal("0")
    detalles: list[DetallePedido] = field(default_factory=list)
    cliente: Optional[Cliente] = None

    def __post_init__(self) -> None:
        self.montoNeto = Decimal(str(self.montoNeto))
        self.montoIva = Decimal(str(self.montoIva))
        self.montoTotal = Decimal(str(self.montoTotal))

    def calcularTotales(self) -> None:
        """Calcula montoNeto (desde detalles si existen), IVA (19%) y montoTotal."""
        if self.detalles:
            self.montoNeto = sum(
                (det.calcularSubtotal() for det in self.detalles),
                Decimal("0"),
            )
        self.montoIva = (self.montoNeto * TASA_IVA).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        self.montoTotal = self.montoNeto + self.montoIva

    def validarDisponibilidadStock(self) -> bool:
        """Verifica que todos los productos en detalle tengan stock disponible suficiente."""
        if not self.detalles:
            return True
        for det in self.detalles:
            if det.producto is None:
                continue
            disponible = sum(lote.calcularStockDisponible() for lote in det.producto.lotes)
            if disponible < det.cantidad:
                return False
        return True

    def cambiarEstado(self, nuevo_estado: str) -> None:
        """Actualiza el estado del pedido."""
        self.estado = nuevo_estado


@dataclass
class DocumentoTributario:
    """Documento Tributario Electrónico (DTE) con emisión simulada ante SII (RF-17)."""

    idDte: int
    tipoDocumento: str = "Factura Electrónica (33)"
    folioSii: Optional[int] = None
    fechaTimbrado: Optional[datetime] = None
    estadoSii: str = "Pendiente Confirmación"
    montoNeto: Decimal = Decimal("0")
    montoIva: Decimal = Decimal("0")
    montoTotal: Decimal = Decimal("0")
    pedido: Optional[Pedido] = None

    def __post_init__(self) -> None:
        if self.pedido is not None and self.montoNeto == Decimal("0"):
            if self.pedido.montoTotal == Decimal("0") and (
                self.pedido.montoNeto > Decimal("0") or self.pedido.detalles
            ):
                self.pedido.calcularTotales()
            self.montoNeto = self.pedido.montoNeto
            self.montoIva = self.pedido.montoIva
            self.montoTotal = self.pedido.montoTotal
        else:
            self.montoNeto = Decimal(str(self.montoNeto))
            self.montoIva = Decimal(str(self.montoIva))
            self.montoTotal = Decimal(str(self.montoTotal))

    def emitirAnteSii(self, confirmado: bool = False, folio_simulado: int = 104928) -> bool:
        """
        Emite el DTE ante el SII simulado.
        Exige `confirmado=True` (confirmación modal previa) antes de asignar folio SII.
        """
        if not confirmado:
            self.estadoSii = "Requiere Confirmación Modal"
            return False

        self.folioSii = int(folio_simulado)
        self.fechaTimbrado = datetime.now()
        self.estadoSii = "Timbrado (Simulado SII)"
        return True

    def generarPdf(self, ruta_salida: Optional[str | Path] = None) -> bytes:
        """Genera una representación PDF simulada del DTE timbrado."""
        folio_txt = str(self.folioSii) if self.folioSii is not None else "SIN-FOLIO"
        contenido = (
            f"%PDF-1.4\n"
            f"% DistriGest DTE Simulado\n"
            f"% Tipo: {self.tipoDocumento}\n"
            f"% Folio SII: {folio_txt}\n"
            f"% Neto: {self.montoNeto} | IVA: {self.montoIva} | Total: {self.montoTotal}\n"
            f"%%EOF\n"
        ).encode("utf-8")
        if ruta_salida is not None:
            Path(ruta_salida).write_bytes(contenido)
        return contenido


@dataclass
class LiquidacionComision:
    """Liquidación mensual de comisiones cruzada con cobranza efectiva (RF-25)."""

    idLiquidacion: int
    periodoMes: int
    periodoAnio: int
    totalFacturado: Decimal
    totalCobradoEnPlazo: Decimal
    montoComisionFinal: Decimal = Decimal("0")
    aprobadaRrhh: bool = False
    vendedor: Optional[Vendedor] = None

    def __post_init__(self) -> None:
        self.totalFacturado = Decimal(str(self.totalFacturado))
        self.totalCobradoEnPlazo = Decimal(str(self.totalCobradoEnPlazo))
        self.montoComisionFinal = Decimal(str(self.montoComisionFinal))

    def recalcularLiquidacion(self, tasa_base: Optional[Decimal | float | str] = None) -> Decimal:
        """
        Recalcula la comisión según cobranza efectiva en plazo:
        - Si recuperación >= 90%: tasa base (3.0% por defecto).
        - Si recuperación < 90%: tasa ajustada (2.5% o tasa_base - 0.005).
        """
        base = (
            Decimal(str(tasa_base))
            if tasa_base is not None
            else (self.vendedor.porcentajeBase if self.vendedor is not None else Decimal("0.03"))
        )
        if self.totalFacturado <= Decimal("0"):
            self.montoComisionFinal = Decimal("0")
            return self.montoComisionFinal

        ratio_cobranza = self.totalCobradoEnPlazo / self.totalFacturado
        tasa_aplicada = base if ratio_cobranza >= Decimal("0.90") else max(Decimal("0"), base - Decimal("0.005"))
        self.montoComisionFinal = (self.totalCobradoEnPlazo * tasa_aplicada).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
        return self.montoComisionFinal

    def aprobarParaRrhh(self) -> bool:
        """Marca la liquidación como aprobada para envío a RRHH si tiene monto calculado."""
        if self.montoComisionFinal < Decimal("0"):
            return False
        self.aprobadaRrhh = True
        return True
