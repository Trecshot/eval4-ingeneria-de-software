"""
Módulo de Dominio: Inventario FEFO, Bodega y Compras (RF-08, RF-10, RF-11, RF-20)
Sistema DistriGest - DistriSur Araucanía SpA
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


UMBRAL_CRITICO_FEFO_DIAS = 30


@dataclass
class UbicacionBodega:
    """Ubicación física en bodega bajo codificación BOD-PAS-EST (RF-10)."""

    bodega: str = ""
    pasillo: str = ""
    estante: str = ""
    codigoUbicacion: str = ""

    def __post_init__(self) -> None:
        if self.codigoUbicacion and not (self.bodega and self.pasillo and self.estante):
            partes = self.codigoUbicacion.split("-")
            if len(partes) == 3:
                self.bodega, self.pasillo, self.estante = partes
        if not self.codigoUbicacion and (self.bodega or self.pasillo or self.estante):
            self.codigoUbicacion = self.obtenerCodigoFormateado()

    def obtenerCodigoFormateado(self) -> str:
        """Retorna el código estandarizado en formato BOD-PAS-EST."""
        return f"{self.bodega}-{self.pasillo}-{self.estante}".upper()


@dataclass
class Producto:
    """Entidad Producto del catálogo maestro con control de quiebre de stock (RF-10, RF-11)."""

    sku: str
    descripcion: str
    categoria: str = "General"
    precioLista: Decimal = Decimal("0")
    stockMinimo: int = 0
    lotes: list[Lote] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.precioLista = Decimal(str(self.precioLista))

    def verificarQuiebreStock(self, stock_actual: Optional[int] = None) -> bool:
        """Retorna True si el stock disponible total es inferior al umbral mínimo."""
        if stock_actual is None:
            total = sum(lote.calcularStockDisponible() for lote in self.lotes)
        else:
            total = int(stock_actual)
        return total < self.stockMinimo


@dataclass
class Lote:
    """Lote físico con trazabilidad de vencimiento para política FEFO (RF-08, RF-10, RF-11)."""

    codigoLote: str
    fechaVencimiento: date
    stockFisico: int
    stockComprometido: int = 0
    ubicacion: Optional[UbicacionBodega] = None
    producto: Optional[Producto] = None

    def calcularStockDisponible(self) -> int:
        """Retorna el stock físico menos el stock comprometido (mínimo 0)."""
        disponible = self.stockFisico - self.stockComprometido
        return max(0, disponible)

    def diasParaVencer(self, fecha_referencia: Optional[date] = None) -> int:
        """Calcula los días restantes hasta la fecha de vencimiento del lote."""
        ref = fecha_referencia if fecha_referencia is not None else date.today()
        return (self.fechaVencimiento - ref).days

    def esCriticoFefo(self, fecha_referencia: Optional[date] = None) -> bool:
        """Determina si el lote está en estado crítico FEFO (< 30 días para vencer)."""
        return self.diasParaVencer(fecha_referencia) < UMBRAL_CRITICO_FEFO_DIAS


@dataclass
class Proveedor:
    """Entidad Proveedor y condiciones comerciales de abastecimiento (RF-20)."""

    idProveedor: int
    rut: str
    razonSocial: str
    nombreFantasia: str = ""
    plazoPagoDias: int = 30
    descuentoProntoPago: Decimal = Decimal("0")
    montoMinimoFlete: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.descuentoProntoPago = Decimal(str(self.descuentoProntoPago))
        self.montoMinimoFlete = Decimal(str(self.montoMinimoFlete))

    def actualizarCondiciones(
        self,
        plazo_pago_dias: int,
        descuento_pronto_pago: Decimal | float | int,
        monto_minimo_flete: Optional[Decimal | float | int] = None,
    ) -> None:
        """Actualiza las condiciones comerciales pactadas con el proveedor."""
        self.plazoPagoDias = int(plazo_pago_dias)
        self.descuentoProntoPago = Decimal(str(descuento_pronto_pago))
        if monto_minimo_flete is not None:
            self.montoMinimoFlete = Decimal(str(monto_minimo_flete))


@dataclass
class OrdenCompra:
    """Orden de Compra para recepción contra documento y control de discrepancias (RF-08)."""

    numeroOc: str | int
    fechaEmision: date
    bodegaDestino: str
    estado: str = "Emitida"
    proveedor: Optional[Proveedor] = None
    itemsEsperados: dict[str, int] = field(default_factory=dict)
    lotes: list[Lote] = field(default_factory=list)

    def registrarRecepcion(self, lotes: list[Lote]) -> bool:
        """Registra los lotes recibidos en la orden de compra y actualiza su estado."""
        if not lotes:
            return False
        self.lotes.extend(lotes)
        discrepancias = self.calcularDiscrepancias()
        hay_descuadre = any(info["diferencia"] != 0 for info in discrepancias.values())
        self.estado = "Recibida con Discrepancias" if hay_descuadre else "Recibida Conforme"
        return True

    def calcularDiscrepancias(
        self,
        cantidades_recibidas: Optional[dict[str, int]] = None,
    ) -> dict[str, dict[str, int | str]]:
        """
        Compara cantidades compradas vs. recibidas y clasifica cada ítem en 3 ramas:
        - diferencia < 0: faltante
        - diferencia == 0: conforme
        - diferencia > 0: excedente
        """
        if cantidades_recibidas is None:
            recibidas: dict[str, int] = {}
            for lote in self.lotes:
                clave = lote.producto.sku if lote.producto is not None else lote.codigoLote
                recibidas[clave] = recibidas.get(clave, 0) + lote.stockFisico
        else:
            recibidas = dict(cantidades_recibidas)

        claves = set(self.itemsEsperados.keys()) | set(recibidas.keys())
        resultado: dict[str, dict[str, int | str]] = {}

        for clave in sorted(claves):
            esperada = int(self.itemsEsperados.get(clave, 0))
            recibida = int(recibidas.get(clave, 0))
            diferencia = recibida - esperada
            if diferencia < 0:
                estado = "faltante"
            elif diferencia > 0:
                estado = "excedente"
            else:
                estado = "conforme"

            resultado[clave] = {
                "esperada": esperada,
                "recibida": recibida,
                "diferencia": diferencia,
                "estado": estado,
            }

        return resultado
