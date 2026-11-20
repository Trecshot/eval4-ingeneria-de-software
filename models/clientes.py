"""
Módulo de Dominio: Clientes, Direcciones de Despacho, Crédito y Vendedores (RF-01, RF-25)
Sistema DistriGest - DistriSur Araucanía SpA
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


def validar_rut_modulo11(rut_str: str) -> bool:
    """Valida el dígito verificador módulo 11 de un RUT chileno."""
    if not isinstance(rut_str, str):
        return False
    rut_limpio = rut_str.replace(".", "").replace("-", "").strip().upper()
    if len(rut_limpio) < 2:
        return False

    cuerpo = rut_limpio[:-1]
    dv = rut_limpio[-1]
    if not cuerpo.isdigit():
        return False

    suma = 0
    multiplo = 2
    for c in reversed(cuerpo):
        suma += int(c) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1

    esperado_num = 11 - (suma % 11)
    if esperado_num == 11:
        esperado_dv = "0"
    elif esperado_num == 10:
        esperado_dv = "K"
    else:
        esperado_dv = str(esperado_num)

    return dv == esperado_dv


class _InstanceOrClassMethod:
    """Permite invocar un método tanto desde la clase como desde una instancia."""

    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner=None):
        if instance is None:
            return lambda rut: self.func(None, rut)
        return lambda rut=None: self.func(instance, rut)


@dataclass
class DireccionDespacho:
    """Dirección de entrega asociada a un cliente (composición 1..* desde Cliente)."""

    idDireccion: int
    calle: str
    numero: str
    comuna: str
    observacionesEntrega: str = ""

    def formatearDireccion(self) -> str:
        base = f"{self.calle} {self.numero}, {self.comuna}"
        if self.observacionesEntrega:
            return f"{base} ({self.observacionesEntrega})"
        return base


@dataclass
class Cliente:
    """Entidad Cliente con control de cupo de crédito, mora y validación RUT (RF-01)."""

    idCliente: int
    rut: str
    razonSocial: str
    giroComercial: str = ""
    zonaGeografica: str = ""
    cupoCredito: Decimal = Decimal("0")
    saldoAdeudado: Decimal = Decimal("0")
    diasMora: int = 0
    estadoBloqueo: bool = False
    direcciones: list[DireccionDespacho] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cupoCredito = Decimal(str(self.cupoCredito))
        self.saldoAdeudado = Decimal(str(self.saldoAdeudado))

    @property
    def bloqueado(self) -> bool:
        """Alias compatible con atributo `bloqueado` del diagrama UML."""
        return self.estadoBloqueo

    @bloqueado.setter
    def bloqueado(self, valor: bool) -> None:
        self.estadoBloqueo = bool(valor)

    @_InstanceOrClassMethod
    def validarRutModulo11(self: Optional[Cliente], rut: Optional[str] = None) -> bool:
        """Valida el RUT provisto o el RUT de la instancia mediante Módulo 11."""
        objetivo = rut if rut is not None else (self.rut if self is not None else "")
        return validar_rut_modulo11(objetivo)

    def evaluarBloqueoCrediticio(
        self,
        monto_pedido: Decimal | int | float = 0,
        umbral_mora: int = 30,
    ) -> bool:
        """
        Evalúa si el cliente debe quedar bloqueado preventivamente:
        - Por mora superior al umbral (`diasMora > umbral_mora`).
        - Por sobregiro (`saldoAdeudado + monto_pedido > cupoCredito`).
        """
        monto = Decimal(str(monto_pedido))
        sobregiro = (self.saldoAdeudado + monto) > self.cupoCredito
        moroso = self.diasMora > umbral_mora
        self.estadoBloqueo = sobregiro or moroso
        return self.estadoBloqueo

    def calcularSobregiro(self, monto_pedido: Decimal | int | float = 0) -> Decimal:
        """Retorna el monto de sobregiro (> 0) o Decimal('0') si está dentro del cupo."""
        monto = Decimal(str(monto_pedido))
        exceso = (self.saldoAdeudado + monto) - self.cupoCredito
        return exceso if exceso > Decimal("0") else Decimal("0")

    def actualizarSaldo(self, monto: Decimal | int | float) -> None:
        """Actualiza el saldo adeudado del cliente."""
        self.saldoAdeudado += Decimal(str(monto))


@dataclass
class Vendedor:
    """Entidad Vendedor para asignación de cartera y cálculo de comisiones (RF-01, RF-25)."""

    idVendedor: int
    rut: str
    nombreCompleto: str
    correo: str
    porcentajeBase: Decimal = Decimal("0.03")

    def __post_init__(self) -> None:
        self.porcentajeBase = Decimal(str(self.porcentajeBase))

    def calcularComisionPeriodo(
        self,
        mes: int,
        anio: int,
        total_cobrado: Decimal | int | float = 0,
    ) -> Decimal:
        """Calcula la comisión del período sobre el monto efectivamente cobrado."""
        cobrado = Decimal(str(total_cobrado))
        comision = (cobrado * self.porcentajeBase).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return comision
