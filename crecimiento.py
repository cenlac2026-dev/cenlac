"""Curvas de percentiles de los bebés durante la internación.

Referencias usadas:
- Bebés de término (37 semanas o más, o sin edad gestacional cargada): OMS, Patrones de
  crecimiento infantil 2006, tablas diarias de peso, talla y perímetro cefálico para la
  edad (método LMS), días 0 a 182 de vida. Archivo referencias/oms_0_182_dias.json.
- Bebés prematuros (menos de 37 semanas): INTERGROWTH-21st, estándares de crecimiento
  posnatal de prematuros (Villar J et al., Lancet Glob Health 2015;3:e681-91), ecuaciones
  según edad posmenstrual, válidas de 27 a 64 semanas.
"""
import json
import math
import os
from datetime import date, timedelta

PERCENTILES = [3, 10, 50, 90, 97]
MEDIDAS = {"peso": "Peso", "talla": "Talla", "pc": "Perímetro cefálico"}
UNIDADES = {"peso": "g", "talla": "cm", "pc": "cm"}
SEXOS = {"F": "Femenino", "M": "Masculino"}
SEMANAS_TERMINO = 37
PNG_DESDE, PNG_HASTA = 27, 64  # semanas de edad posmenstrual cubiertas por INTERGROWTH-21st

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "referencias", "oms_0_182_dias.json"),
          encoding="utf-8") as _f:
    _OMS = json.load(_f)["medidas"]
_CLAVE_OMS = {"peso": "peso_kg", "talla": "talla_cm", "pc": "pc_cm"}

# z de cada percentil de la curva (inversa de la normal estándar)
_Z = {3: -1.880794, 10: -1.281552, 50: 0.0, 90: 1.281552, 97: 1.880794}


def _fi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def _entero(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _fecha(valor):
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return None


def datos_bebe(bebe):
    """Sexo, edad gestacional y fecha de nacimiento normalizados."""
    semanas = _entero(bebe["eg_semanas"])
    dias = _entero(bebe["eg_dias"]) or 0
    return {
        "sexo": bebe["sexo"] if bebe["sexo"] in SEXOS else None,
        "eg_semanas": semanas,
        "eg_dias": dias,
        "eg_total_dias": semanas * 7 + dias if semanas else None,
        "nacimiento": _fecha(bebe["fecha_nacimiento"]),
        "prematuro": bool(semanas and semanas < SEMANAS_TERMINO),
    }


def referencia(info):
    if info["prematuro"]:
        return "INTERGROWTH-21st (prematuros, según edad posmenstrual)"
    return "OMS (según días de vida)"


def faltantes(info):
    falta = []
    if not info["sexo"]:
        falta.append("el sexo")
    if not info["nacimiento"]:
        falta.append("la fecha de nacimiento")
    return falta


# --- OMS (LMS) -----------------------------------------------------------------

def _oms_lms(medida, sexo, dia):
    return _OMS[_CLAVE_OMS[medida]][sexo][dia]


def _oms_valor(l, m, s, z):
    return m * (1 + l * s * z) ** (1 / l) if l else m * math.exp(s * z)


def _oms_z(medida, l, m, s, y):
    z = ((y / m) ** l - 1) / (l * s) if l else math.log(y / m) / s
    if medida != "talla" and abs(z) > 3:
        # Ajuste de la OMS para valores extremos de peso y perímetro cefálico
        signo = 1 if z > 0 else -1
        sd3 = _oms_valor(l, m, s, 3 * signo)
        sd23 = sd3 - _oms_valor(l, m, s, 2 * signo)
        z = signo * 3 + (y - sd3) / abs(sd23)
    return z


# --- INTERGROWTH-21st prematuros ------------------------------------------------

def _png_mu_sigma(medida, sexo, pma):
    varon = 1 if sexo == "M" else 0
    x = pma
    if medida == "peso":  # log(kg)
        return (2.591277 - 0.01155 * x ** 0.5 - 2201.705 * x ** -2 + 0.0911639 * varon,
                0.1470258 + 505.92394 / x ** 2 - 140.0576 / x ** 2 * math.log(x))
    if medida == "talla":  # log(cm)
        return (4.136244 - 547.0018 * x ** -2 + 0.0026066 * x + 0.0314961 * varon,
                0.050489 + 310.44761 * x ** -2 - 90.0742 * x ** -2 * math.log(x))
    return (55.53617 - 852.0059 / x + 0.7957903 * varon,  # cm
            3.0582292 + 3910.05 * x ** -2 - 180.5625 / x)


# --- API --------------------------------------------------------------------------

def _a_unidad_ref(medida, valor):
    return valor / 1000 if medida == "peso" else valor


def _de_unidad_ref(medida, valor):
    return valor * 1000 if medida == "peso" else valor


def calcular(info, medida, fecha, valor):
    """Devuelve {'z', 'percentil'} o {'motivo'} si no se puede calcular."""
    if valor in (None, ""):
        return None
    if faltantes(info):
        return {"motivo": "Faltan datos del bebé"}
    dia = (fecha - info["nacimiento"]).days
    if dia < 0:
        return {"motivo": "Fecha anterior al nacimiento"}
    y = _a_unidad_ref(medida, float(valor))
    if info["prematuro"]:
        pma = (info["eg_total_dias"] + dia) / 7
        if pma < PNG_DESDE:
            return {"motivo": f"Edad posmenstrual menor a {PNG_DESDE} semanas"}
        if pma > PNG_HASTA:
            return {"motivo": f"Edad posmenstrual mayor a {PNG_HASTA} semanas"}
        mu, sigma = _png_mu_sigma(medida, info["sexo"], pma)
        z = ((math.log(y) if medida != "pc" else y) - mu) / sigma
    else:
        if dia > 182:
            return {"motivo": "Más de 6 meses de vida"}
        l, m, s = _oms_lms(medida, info["sexo"], dia)
        z = _oms_z(medida, l, m, s, y)
    return {"z": round(z, 2), "percentil": max(0.1, min(99.9, round(_fi(z) * 100, 1)))}


def valor_z(info, medida, fecha, z):
    """Valor de la medida que corresponde a un z dado, o None fuera del rango de la referencia."""
    dia = (fecha - info["nacimiento"]).days
    if info["prematuro"]:
        pma = (info["eg_total_dias"] + dia) / 7
        if not PNG_DESDE <= pma <= PNG_HASTA:
            return None
        mu, sigma = _png_mu_sigma(medida, info["sexo"], pma)
        y = mu + z * sigma
        y = math.exp(y) if medida != "pc" else y
    else:
        if not 0 <= dia <= 182:
            return None
        y = _oms_valor(*_oms_lms(medida, info["sexo"], dia), z)
    return _de_unidad_ref(medida, y)


def valor_percentil(info, medida, fecha, p):
    return valor_z(info, medida, fecha, _Z[p])


def edad_texto(info, fecha):
    dia = (fecha - info["nacimiento"]).days
    texto = f"{dia} día{'s' if dia != 1 else ''} de vida"
    if info["prematuro"]:
        pma = info["eg_total_dias"] + dia
        texto += f" · EPM {pma // 7}+{pma % 7}"
    return texto


def tabla_controles(info, controles):
    """Agrega a cada control la edad, los percentiles y la ganancia de peso diaria."""
    filas = []
    anterior = None
    for c in controles:
        f = _fecha(c["fecha"])
        fila = dict(c)
        fila["edad"] = edad_texto(info, f) if info["nacimiento"] and f >= info["nacimiento"] else ""
        for medida in MEDIDAS:
            fila["p_" + medida] = calcular(info, medida, f, c[medida]) if info["nacimiento"] else None
        fila["ganancia"] = None
        if anterior and c["peso"] and anterior["peso"]:
            dias = (f - _fecha(anterior["fecha"])).days
            if dias > 0:
                fila["ganancia"] = round((c["peso"] - anterior["peso"]) / dias)
        if c["peso"]:
            anterior = c
        filas.append(fila)
    return filas


def grafico(info, controles, medida="peso", hasta=None, ancho=760, alto=360):
    """Datos para dibujar la curva de percentiles en SVG, del nacimiento al alta (o a hoy)."""
    puntos_bebe = [(_fecha(c["fecha"]), c[medida]) for c in controles if c[medida]]
    if faltantes(info) or not puntos_bebe:
        return None
    inicio = info["nacimiento"]
    fin = max([hasta or date.today()] + [f for f, _ in puntos_bebe])
    fin = max(fin, inicio + timedelta(days=7))
    dias = (fin - inicio).days
    fechas = [inicio + timedelta(days=d) for d in range(dias + 1)]
    curvas = {p: [(f, valor_percentil(info, medida, f, p)) for f in fechas] for p in PERCENTILES}

    valores = [v for p in PERCENTILES for _, v in curvas[p] if v is not None] + [v for _, v in puntos_bebe]
    paso = {"peso": 250, "talla": 1, "pc": 1}[medida]
    minimo = math.floor(min(valores) / paso) * paso
    maximo = math.ceil(max(valores) / paso) * paso
    if maximo - minimo > paso * 12:
        paso *= 2
        minimo = math.floor(min(valores) / paso) * paso
        maximo = math.ceil(max(valores) / paso) * paso
    izq, der, arr, aba = 62, 54, 16, 46
    ax = lambda f: izq + (f - inicio).days * (ancho - izq - der) / dias
    ay = lambda v: arr + (maximo - v) * (alto - arr - aba) / (maximo - minimo)

    lineas = []
    for p in PERCENTILES:
        tramos, actual = [], []
        for f, v in curvas[p]:
            if v is None:
                if actual:
                    tramos.append(actual)
                actual = []
            else:
                actual.append(f"{ax(f):.1f},{ay(v):.1f}")
        if actual:
            tramos.append(actual)
        ultimo = next((v for f, v in reversed(curvas[p]) if v is not None), None)
        lineas.append({
            "p": p,
            "d": " ".join("M" + " L".join(t) for t in tramos),
            "etq_y": ay(ultimo) + 4 if ultimo is not None else None,
        })
    # Separar etiquetas de percentiles que queden muy juntas
    con_etq = [l for l in lineas if l["etq_y"] is not None]
    for i in range(1, len(con_etq)):
        if con_etq[i - 1]["etq_y"] - con_etq[i]["etq_y"] < 11:
            con_etq[i]["etq_y"] = con_etq[i - 1]["etq_y"] - 11

    marcas_y = []
    v = minimo
    while v <= maximo + 1e-9:
        marcas_y.append({"y": ay(v), "texto": f"{v:,.0f}".replace(",", ".") if medida == "peso" else f"{v:g}"})
        v += paso
    salto = max(1, math.ceil(dias / 10))
    marcas_x = [{"x": ax(f), "texto": f.strftime("%d/%m"), "dia": (f - inicio).days}
                for f in fechas[::salto]]

    puntos = []
    for f, val in puntos_bebe:
        r = calcular(info, medida, f, val)
        puntos.append({"x": ax(f), "y": ay(val), "fecha": f.strftime("%d/%m/%Y"),
                       "valor": f"{val:,.0f}".replace(",", ".") if medida == "peso" else f"{val:g}",
                       "percentil": r.get("percentil") if r else None})
    return {
        "ancho": ancho, "alto": alto, "izq": izq, "der": der, "arr": arr, "base": alto - aba,
        "lineas": lineas, "marcas_y": marcas_y, "marcas_x": marcas_x, "puntos": puntos,
        "linea_bebe": "M" + " L".join(f"{p['x']:.1f},{p['y']:.1f}" for p in puntos),
        "unidad": UNIDADES[medida], "titulo": MEDIDAS[medida],
        "x_alta": ax(hasta) if hasta and inicio <= hasta <= fin else None,
    }
