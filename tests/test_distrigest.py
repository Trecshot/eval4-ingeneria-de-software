"""
Suite de Pruebas Unitarias - DistriGest (Evaluación N° 4 - Ingeniería de Software)
Cubre los casos de prueba CP-01 a CP-06 y métodos críticos del modelo de dominio.
Todos los datos utilizados son 100% ficticios.
"""
from __future__ import annotations

import sys
import types
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from models import (
    Cliente,
    DetallePedido,
    DireccionDespacho,
    DocumentoTributario,
    LiquidacionComision,
    Lote,
    OrdenCompra,
    Pedido,
    Producto,
    Proveedor,
    UbicacionBodega,
    Vendedor,
)
import theme as th


def _importar_bodega_view():
    """Importa BodegaView, proveyendo un stub mínimo si customtkinter no está instalado."""
    try:
        from views.bodega_view import BodegaView
        return BodegaView
    except ModuleNotFoundError:
        ctk_stub = types.ModuleType("customtkinter")
        ctk_stub.CTkFrame = type("CTkFrame", (), {})
        sys.modules["customtkinter"] = ctk_stub
        from views.bodega_view import BodegaView
        return BodegaView


# ==============================================================================
# CP-01: Partición de Equivalencia — Validación RUT Módulo 11 (RF-01)
# ==============================================================================
def test_cp01_validar_rut_modulo11_rechaza_dv_invalido():
    """CP-01: validarRutModulo11() rechaza 76.111.222-9 (DV inválido)."""
    assert Cliente.validarRutModulo11("76.111.222-9") is False

    cliente = Cliente(
        idCliente=1,
        rut="76.111.222-9",
        razonSocial="Comercializadora Ejemplo Sur Ltda.",
    )
    assert cliente.validarRutModulo11() is False


@pytest.mark.parametrize(
    "rut_valido",
    [
        "76.000.101-5",  # RUT ficticio válido (Módulo 11)
        "77.000.202-8",  # RUT ficticio válido (Módulo 11)
        "96.000.303-9",  # RUT ficticio válido (Módulo 11)
        "11.111.111-1",  # Usuario QA ficticio (Tabla 6)
        "22.222.222-2",  # RUT ficticio válido (Módulo 11)
    ],
)
def test_cp01_validar_rut_modulo11_acepta_ruts_ficticios_validos(rut_valido: str):
    """Partición válida: RUTs ficticios matemáticamente válidos bajo Módulo 11."""
    assert Cliente.validarRutModulo11(rut_valido) is True


# ==============================================================================
# CP-02 / CP-03: Valores Límite FEFO (< 30 días para vencer) (RF-11)
# ==============================================================================
def test_cp02_lote_29_dias_es_critico_fefo():
    """CP-02: Lote LOT-901 con vencimiento en 29 días -> Crítico FEFO."""
    fecha_ref = date(2026, 11, 1)
    lote = Lote(
        codigoLote="LOT-901",
        fechaVencimiento=fecha_ref + timedelta(days=29),
        stockFisico=120,
    )
    assert lote.diasParaVencer(fecha_ref) == 29
    assert lote.esCriticoFefo(fecha_ref) is True


def test_cp03_lote_31_dias_es_normal_fefo():
    """CP-03: Lote LOT-902 con vencimiento en 31 días -> Normal (no crítico)."""
    fecha_ref = date(2026, 11, 1)
    lote = Lote(
        codigoLote="LOT-902",
        fechaVencimiento=fecha_ref + timedelta(days=31),
        stockFisico=120,
    )
    assert lote.diasParaVencer(fecha_ref) == 31
    assert lote.esCriticoFefo(fecha_ref) is False


def test_fefo_frontera_exacta_30_dias_no_es_critico():
    """Valor frontera exacto: 30 días no cumple `< 30`, por lo tanto es Normal."""
    fecha_ref = date(2026, 11, 1)
    lote = Lote(
        codigoLote="LOT-900",
        fechaVencimiento=fecha_ref + timedelta(days=30),
        stockFisico=50,
    )
    assert lote.diasParaVencer(fecha_ref) == 30
    assert lote.esCriticoFefo(fecha_ref) is False


# ==============================================================================
# CP-04: Tabla de Decisión — Bloqueo Crediticio por Sobregiro o Mora (RF-01)
# ==============================================================================
def test_cp04_bloqueo_crediticio_por_sobregiro_50000():
    """
    CP-04: Cupo $1.000.000, Saldo $800.000, Pedido $250.000, Mora 0 días
    -> Bloqueo preventivo de venta por sobregiro de $50.000.
    """
    cliente = Cliente(
        idCliente=10,
        rut="76.000.101-8",
        razonSocial="Comercializadora Ejemplo Sur Ltda.",
        zonaGeografica="Temuco Centro",
        cupoCredito=Decimal("1000000"),
        saldoAdeudado=Decimal("800000"),
        diasMora=0,
    )
    bloqueado = cliente.evaluarBloqueoCrediticio(monto_pedido=Decimal("250000"))

    assert bloqueado is True
    assert cliente.estadoBloqueo is True
    assert cliente.bloqueado is True
    assert cliente.calcularSobregiro(Decimal("250000")) == Decimal("50000")


def test_cp04_bloqueo_crediticio_por_mora_y_caso_aprobado():
    """Tabla de decisión: bloqueo por mora (52 días) y aprobación dentro de cupo."""
    cliente_moroso = Cliente(
        idCliente=11,
        rut="77.000.202-K",
        razonSocial="Abarrotes Prueba Malleco SpA",
        zonaGeografica="Angol",
        cupoCredito=Decimal("500000"),
        saldoAdeudado=Decimal("100000"),
        diasMora=52,
    )
    assert cliente_moroso.evaluarBloqueoCrediticio(monto_pedido=Decimal("50000")) is True

    cliente_ok = Cliente(
        idCliente=12,
        rut="76.000.101-8",
        razonSocial="Comercializadora Ejemplo Sur Ltda.",
        cupoCredito=Decimal("2000000"),
        saldoAdeudado=Decimal("500000"),
        diasMora=0,
    )
    assert cliente_ok.evaluarBloqueoCrediticio(monto_pedido=Decimal("300000")) is False
    assert cliente_ok.calcularSobregiro(Decimal("300000")) == Decimal("0")


# ==============================================================================
# CP-05: Caja Blanca (Cobertura de 3 Ramas) en calcularDiscrepancias() (RF-08)
# ==============================================================================
def test_cp05_caja_blanca_calcular_discrepancias_tres_ramas_vista():
    """
    CP-05: Caja blanca en BodegaView.calcularDiscrepancias():
    - OC-5001: Comprada 100, Recibida 95 -> diferencia -5 (faltante rojo)
    - Rama == 0 -> conforme (verde)
    - Rama > 0 -> excedente (amarillo)
    """
    BodegaView = _importar_bodega_view()

    dif_falt, msg_falt, color_falt = BodegaView.calcularDiscrepancias(100, 95)
    assert dif_falt == -5
    assert "Faltante" in msg_falt
    assert color_falt == th.COLOR_DANGER

    dif_ok, msg_ok, color_ok = BodegaView.calcularDiscrepancias(100, 100)
    assert dif_ok == 0
    assert "Conforme" in msg_ok
    assert color_ok == th.COLOR_SUCCESS

    dif_exc, msg_exc, color_exc = BodegaView.calcularDiscrepancias(100, 108)
    assert dif_exc == 8
    assert "Excedente" in msg_exc
    assert color_exc == th.COLOR_WARNING


def test_cp05_orden_compra_registrar_recepcion_y_discrepancias():
    """CP-05 en modelo OrdenCompra: OC-5001 comprada 100, recibida 95 -> diferencia -5."""
    prod = Producto(sku="SKU-ARR-001", descripcion="Arroz Grado 1 Saco 25 kg (Ficticio)", stockMinimo=50)
    ubic = UbicacionBodega(bodega="TEM", pasillo="P04", estante="E02")
    lote = Lote(
        codigoLote="LOT-5001",
        fechaVencimiento=date(2027, 6, 30),
        stockFisico=95,
        ubicacion=ubic,
        producto=prod,
    )
    oc = OrdenCompra(
        numeroOc="OC-5001",
        fechaEmision=date(2026, 11, 15),
        bodegaDestino="TEM",
        itemsEsperados={"SKU-ARR-001": 100},
    )
    assert oc.registrarRecepcion([lote]) is True
    discrepancias = oc.calcularDiscrepancias()
    assert discrepancias["SKU-ARR-001"]["diferencia"] == -5
    assert discrepancias["SKU-ARR-001"]["estado"] == "faltante"
    assert oc.estado == "Recibida con Discrepancias"


# ==============================================================================
# CP-06: Facturación DTE PED-800 (IVA 19% + Confirmación Modal SII) (RF-17)
# ==============================================================================
def test_cp06_facturacion_ped_800_iva_y_confirmacion_modal_sii():
    """
    CP-06: Pedido PED-800, Neto $100.000 -> IVA $19.000, Total $119.000;
    exige confirmación modal antes de asignar Folio SII simulado.
    """
    pedido = Pedido(
        idPedido="PED-800",
        fechaEmision=datetime(2026, 11, 20, 10, 0),
        detalles=[
            DetallePedido(idDetalle=1, cantidad=10, precioUnitario=Decimal("10000")),
        ],
    )
    pedido.calcularTotales()

    assert pedido.montoNeto == Decimal("100000")
    assert pedido.montoIva == Decimal("19000")
    assert pedido.montoTotal == Decimal("119000")

    dte = DocumentoTributario(idDte=800, tipoDocumento="Factura Electrónica (33)", pedido=pedido)

    # Sin confirmación modal previa no debe asignar folio
    assert dte.emitirAnteSii(confirmado=False) is False
    assert dte.folioSii is None

    # Con confirmación modal asigna folio simulado SII y permite generar PDF
    assert dte.emitirAnteSii(confirmado=True, folio_simulado=104928) is True
    assert dte.folioSii == 104928
    assert "Timbrado" in dte.estadoSii

    pdf_bytes = dte.generarPdf()
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"104928" in pdf_bytes


# ==============================================================================
# Pruebas Complementarias del Modelo de Dominio (RF-01, RF-10, RF-11, RF-20, RF-25)
# ==============================================================================
def test_inventario_ubicacion_stock_disponible_y_quiebre():
    """Verifica obtenerCodigoFormateado(), calcularStockDisponible() y verificarQuiebreStock()."""
    ubic = UbicacionBodega(bodega="tem", pasillo="p04", estante="e02")
    assert ubic.obtenerCodigoFormateado() == "TEM-P04-E02"

    prod = Producto(sku="SKU-ARR-001", descripcion="Arroz Grado 1 Saco 25 kg (Ficticio)", stockMinimo=50)
    lote = Lote(
        codigoLote="LOT-100",
        fechaVencimiento=date(2027, 1, 15),
        stockFisico=60,
        stockComprometido=20,
        ubicacion=ubic,
        producto=prod,
    )
    prod.lotes.append(lote)

    assert lote.calcularStockDisponible() == 40
    assert prod.verificarQuiebreStock() is True


def test_proveedor_actualizar_condiciones_y_direccion():
    """Verifica actualizarCondiciones() de Proveedor y formatearDireccion() de DireccionDespacho."""
    prov = Proveedor(
        idProveedor=1,
        rut="96.000.303-5",
        razonSocial="Alimentos Ficticios del Sur S.A.",
        plazoPagoDias=30,
        descuentoProntoPago=Decimal("3.0"),
    )
    prov.actualizarCondiciones(plazo_pago_dias=45, descuento_pronto_pago=Decimal("4.5"), monto_minimo_flete=150000)
    assert prov.plazoPagoDias == 45
    assert prov.descuentoProntoPago == Decimal("4.5")
    assert prov.montoMinimoFlete == Decimal("150000")

    dir_despacho = DireccionDespacho(
        idDireccion=1,
        calle="Av. Ejemplo",
        numero="1234",
        comuna="Temuco",
        observacionesEntrega="Portón lateral",
    )
    assert dir_despacho.formatearDireccion() == "Av. Ejemplo 1234, Temuco (Portón lateral)"


def test_liquidacion_comision_y_aprobacion_rrhh():
    """Verifica recalcularLiquidacion() y aprobarParaRrhh() para RF-25."""
    vendedor = Vendedor(
        idVendedor=1,
        rut="11.111.111-1",
        nombreCompleto="Operario Prueba Comercial",
        correo="qa.comercial@ejemplo.cl",
        porcentajeBase=Decimal("0.03"),
    )
    liq = LiquidacionComision(
        idLiquidacion=1,
        periodoMes=11,
        periodoAnio=2026,
        totalFacturado=Decimal("10000000"),
        totalCobradoEnPlazo=Decimal("9300000"),
        vendedor=vendedor,
    )
    comision = liq.recalcularLiquidacion()
    assert comision == Decimal("279000")
    assert liq.aprobarParaRrhh() is True
    assert liq.aprobadaRrhh is True
