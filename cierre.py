"""Cierre mensual: reúne los datos de un mes y genera el informe en PDF."""
import calendar
from datetime import date, datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Colores del informe (RGB), en línea con la interfaz
ROSA = (113, 89, 184)
ROSA_CLARO = (240, 235, 251)
MENTA = (230, 242, 251)
TEXTO = (74, 67, 96)
SUAVE = (127, 119, 153)
ROJO = (194, 69, 61)
ROJO_CLARO = (253, 236, 235)

# Tareas que se cuentan por agente en el cierre: (clave, nombre, tabla, columna de fecha, color)
TAREAS_AGENTE = [
    ("madres", "Madres registradas", "madres", "fecha_registro", (113, 89, 184)),
    ("extracciones", "Extracciones y estímulos", "extracciones", "fecha_hora", (143, 195, 230)),
    ("preparaciones", "Preparaciones", "preparaciones", "fecha", (230, 185, 60)),
    ("actividades", "Otras actividades", "actividades", "fecha_hora", (108, 191, 143)),
    ("controles", "Controles de bebés", "controles_bebe", "fecha", (242, 155, 181)),
]
ROLES_AGENTE = {"admin": "Administrador", "jefe": "Jefe", "agente": "Agente", "consulta": "Consulta"}


def por_agente(db, clave):
    """Registros cargados por cada usuario en el mes, por tipo de tarea, con su porcentaje del total."""
    union = " UNION ALL ".join(
        f"SELECT usuario_id, '{k}' FROM {tabla} WHERE substr({col}, 1, 7) = ?" for k, _, tabla, col, _ in TAREAS_AGENTE)
    conteo = {}
    for uid, tarea in db.execute(union, [clave] * len(TAREAS_AGENTE)):
        conteo.setdefault(uid, {k: 0 for k, *_ in TAREAS_AGENTE})[tarea] += 1
    usuarios = {u[0]: u for u in db.execute("SELECT id, nombre, rol FROM usuarios")}
    total = sum(sum(c.values()) for c in conteo.values())
    filas = []
    for uid, cant in conteo.items():
        u = usuarios.get(uid)
        n = sum(cant.values())
        filas.append({
            "nombre": u[1] if u else "Sin usuario (registros anteriores)",
            "rol": ROLES_AGENTE.get(u[2], u[2]) if u else "",
            "cantidades": cant, "total": n,
            "pct": round(100 * n / total, 1) if total else 0,
            "pct_tareas": {k: round(100 * v / n, 1) if n else 0 for k, v in cant.items()},
        })
    # Primero quienes más cargaron; los registros sin usuario al final.
    filas.sort(key=lambda f: (f["rol"] == "", -f["total"], f["nombre"]))
    return {"filas": filas, "total": total,
            "tareas": [(k, nombre, "#%02x%02x%02x" % color) for k, nombre, _, _, color in TAREAS_AGENTE]}



MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MESES_HISTORIA = 6
MESES_PROYECCION = 3
METRICAS_PROYECCION = [
    ("extraida", "Leche extraída por mes", "ml",
     "SELECT substr(fecha_hora, 1, 7), SUM(cantidad_ml) FROM extracciones GROUP BY 1"),
    ("entregada", "Leche entregada en preparaciones por mes", "ml",
     "SELECT substr(fecha, 1, 7), SUM(dosis_ml * cantidad_dosis) FROM preparaciones GROUP BY 1"),
    ("madres", "Madres donantes nuevas por mes", "madres",
     "SELECT substr(fecha_registro, 1, 7), COUNT(*) FROM madres GROUP BY 1"),
]


def sumar_meses(anio, mes, n):
    total = anio * 12 + (mes - 1) + n
    return total // 12, total % 12 + 1


def proyectar(valores, n):
    """Recta de mínimos cuadrados sobre los valores; devuelve los n meses siguientes (nunca negativos)."""
    k = len(valores)
    xm, ym = (k - 1) / 2, sum(valores) / k
    den = sum((x - xm) ** 2 for x in range(k)) or 1
    pendiente = sum((x - xm) * (y - ym) for x, y in enumerate(valores)) / den
    return [max(0.0, ym + pendiente * (k + i - xm)) for i in range(n)], pendiente


def series_proyeccion(db, anio, mes):
    """Series de los 6 meses anteriores a (anio, mes) y proyección de ese mes y los 2 siguientes."""
    pasados = [sumar_meses(anio, mes, -MESES_HISTORIA + i) for i in range(MESES_HISTORIA)]
    futuros = [sumar_meses(anio, mes, i) for i in range(MESES_PROYECCION)]
    claves = [f"{a}-{m:02d}" for a, m in pasados]
    etiquetas = [f"{MESES_CORTOS[m - 1]} {str(a)[2:]}" for a, m in pasados + futuros]
    metricas = []
    for clave, titulo, unidad, sql in METRICAS_PROYECCION:
        filas = dict(db.execute(sql).fetchall())
        historia = [float(filas.get(k) or 0) for k in claves]
        futuro, _ = proyectar(historia, MESES_PROYECCION)
        metricas.append({"clave": clave, "titulo": titulo, "unidad": unidad, "historia": historia, "futuro": futuro})
    return {"etiquetas": etiquetas, "metricas": metricas}


def nombre_mes(anio, mes):
    return f"{MESES[mes - 1].capitalize()} {anio}"


def mes_anterior(anio, mes):
    return (anio - 1, 12) if mes == 1 else (anio, mes - 1)


def _resumen(db, clave):
    uno = lambda sql, *p: db.execute(sql, p).fetchone()[0]
    return {
        "madres_nuevas": uno("SELECT COUNT(*) FROM madres WHERE substr(fecha_registro, 1, 7) = ?", clave),
        "madres_activas": uno("SELECT COUNT(DISTINCT madre_id) FROM extracciones WHERE substr(fecha_hora, 1, 7) = ?", clave),
        "extracciones": uno("SELECT COUNT(*) FROM extracciones WHERE tipo = 'extraccion' AND substr(fecha_hora, 1, 7) = ?", clave),
        "estimulos": uno("SELECT COUNT(*) FROM extracciones WHERE tipo = 'estimulo' AND substr(fecha_hora, 1, 7) = ?", clave),
        "ml_extraidos": uno("SELECT COALESCE(SUM(cantidad_ml), 0) FROM extracciones WHERE substr(fecha_hora, 1, 7) = ?", clave),
        "preparaciones": uno("SELECT COUNT(*) FROM preparaciones WHERE substr(fecha, 1, 7) = ?", clave),
        "dosis": uno("SELECT COALESCE(SUM(cantidad_dosis), 0) FROM preparaciones WHERE substr(fecha, 1, 7) = ?", clave),
        "ml_entregados": uno("SELECT COALESCE(SUM(dosis_ml * cantidad_dosis), 0) FROM preparaciones WHERE substr(fecha, 1, 7) = ?", clave),
        "bebes_receptores": uno("SELECT COUNT(DISTINCT lower(bebe_nombre || ' ' || bebe_apellido)) FROM preparaciones "
                                "WHERE substr(fecha, 1, 7) = ?", clave),
        "actividades": uno("SELECT COUNT(*) FROM actividades WHERE substr(fecha_hora, 1, 7) = ?", clave),
        "altas": uno("SELECT COUNT(*) FROM madres WHERE substr(fecha_alta, 1, 7) = ?", clave),
    }


def datos_cierre(db, anio, mes, tipos_leche, servicios, actividades):
    clave = f"{anio}-{mes:02d}"
    clave_ant = "%d-%02d" % mes_anterior(anio, mes)
    actual, anterior = _resumen(db, clave), _resumen(db, clave_ant)
    dias_mes = calendar.monthrange(anio, mes)[1]
    por_dia = dict(db.execute(
        "SELECT CAST(substr(fecha_hora, 9, 2) AS INTEGER), SUM(cantidad_ml) FROM extracciones "
        "WHERE substr(fecha_hora, 1, 7) = ? GROUP BY 1", (clave,)).fetchall())
    return {
        "anio": anio, "mes": mes, "clave": clave, "titulo": nombre_mes(anio, mes),
        "titulo_anterior": nombre_mes(*mes_anterior(anio, mes)),
        "actual": actual, "anterior": anterior,
        "ml_por_dia": [float(por_dia.get(d) or 0) for d in range(1, dias_mes + 1)],
        "por_leche": [(tipos_leche.get(k, k), n, ml) for k, n, ml in db.execute(
            "SELECT tipo_leche, COUNT(*), SUM(cantidad_ml) FROM extracciones WHERE tipo_leche IS NOT NULL "
            "AND substr(fecha_hora, 1, 7) = ? GROUP BY tipo_leche ORDER BY 3 DESC", (clave,)).fetchall()],
        "madres_ml": db.execute(
            "SELECT m.apellido || ', ' || m.nombre, m.barrio, COUNT(*), SUM(e.cantidad_ml) FROM extracciones e "
            "JOIN madres m ON m.id = e.madre_id WHERE e.tipo = 'extraccion' AND substr(e.fecha_hora, 1, 7) = ? "
            "GROUP BY m.id ORDER BY 4 DESC", (clave,)).fetchall(),
        "nuevas": db.execute(
            "SELECT fecha_registro, apellido || ', ' || nombre, barrio, localidad, situacion, tipo_internacion "
            "FROM madres WHERE substr(fecha_registro, 1, 7) = ? ORDER BY fecha_registro", (clave,)).fetchall(),
        "prep_tipo": db.execute(
            "SELECT MIN(tipo_preparacion), COUNT(*), SUM(cantidad_dosis), SUM(dosis_ml * cantidad_dosis) FROM preparaciones "
            "WHERE substr(fecha, 1, 7) = ? GROUP BY lower(tipo_preparacion) ORDER BY 4 DESC", (clave,)).fetchall(),
        "prep_servicio": [(servicios.get(k, k), n, ml) for k, n, ml in db.execute(
            "SELECT servicio, COUNT(*), SUM(dosis_ml * cantidad_dosis) FROM preparaciones "
            "WHERE substr(fecha, 1, 7) = ? GROUP BY servicio", (clave,)).fetchall()],
        "act_tipo": [(actividades[k][0], n) for k, n in db.execute(
            "SELECT tipo, COUNT(*) FROM actividades WHERE substr(fecha_hora, 1, 7) = ? GROUP BY tipo ORDER BY 2 DESC",
            (clave,)).fetchall()],
        "educacion": db.execute(
            "SELECT fecha_hora, destinatario_nombre || ' ' || destinatario_apellido, descripcion FROM actividades "
            "WHERE tipo = 'educacion' AND substr(fecha_hora, 1, 7) = ? ORDER BY fecha_hora", (clave,)).fetchall(),
        "leche_mov": db.execute(
            "SELECT fecha_hora, tipo, lugar, cantidad_ml, frascos, lote FROM actividades "
            "WHERE tipo IN ('envio_leche', 'recepcion_leche') AND substr(fecha_hora, 1, 7) = ? ORDER BY fecha_hora",
            (clave,)).fetchall(),
        "salidas": db.execute(
            "SELECT fecha_hora, lugar, descripcion FROM actividades "
            "WHERE tipo = 'salida' AND substr(fecha_hora, 1, 7) = ? ORDER BY fecha_hora", (clave,)).fetchall(),
        "altas": db.execute(
            """SELECT m.fecha_alta, m.apellido || ', ' || m.nombre,
                      (SELECT group_concat(b.nombre, ', ') FROM bebes b WHERE b.madre_id = m.id),
                      m.fecha_registro,
                      (SELECT COALESCE(SUM(e.cantidad_ml), 0) FROM extracciones e WHERE e.madre_id = m.id)
                 FROM madres m WHERE substr(m.fecha_alta, 1, 7) = ? ORDER BY m.fecha_alta""", (clave,)).fetchall(),
        "agentes": por_agente(db, clave),
        "parcial_hasta": date.today().isoformat() if clave == date.today().strftime("%Y-%m") else None,
        # Mes cerrado: historia hasta ese mes y proyección de los 3 siguientes.
        # Mes en curso: historia hasta el mes anterior (el actual está incompleto) y se proyecta desde el actual.
        "proyeccion": series_proyeccion(db, *(sumar_meses(anio, mes, 1)
                                              if clave < date.today().strftime("%Y-%m") else (anio, mes))),
        "riesgo": db.execute(
            """SELECT m.apellido || ', ' || m.nombre, m.direccion, m.barrio, m.telefono, m.factores_riesgo,
                      (SELECT group_concat(b.nombre || ': ' || b.factores_riesgo, '; ') FROM bebes b
                        WHERE b.madre_id = m.id AND COALESCE(b.factores_riesgo, '') <> '')
                 FROM madres m
                WHERE (substr(m.fecha_registro, 1, 7) = ?
                       OR EXISTS (SELECT 1 FROM extracciones e WHERE e.madre_id = m.id AND substr(e.fecha_hora, 1, 7) = ?))
                  AND (COALESCE(m.factores_riesgo, '') <> ''
                       OR EXISTS (SELECT 1 FROM bebes b WHERE b.madre_id = m.id AND COALESCE(b.factores_riesgo, '') <> ''))
                ORDER BY m.apellido, m.nombre""", (clave, clave)).fetchall(),
    }


def num(v, unidad=""):
    texto = f"{v:,.0f}".replace(",", ".")
    return f"{texto} {unidad}".strip()


def variacion(actual, anterior):
    if not anterior:
        return "-" if not actual else "nuevo"
    p = (actual - anterior) / anterior * 100
    return f"{'+' if p >= 0 else ''}{p:.0f}%"


class InformePDF(FPDF):
    def __init__(self, titulo):
        super().__init__(format="A4")
        self.titulo_informe = titulo
        self.set_auto_page_break(True, margin=18)
        self.set_margins(15, 15, 15)

    def header(self):
        self.set_fill_color(*ROSA)
        self.rect(0, 0, self.w, 24, "F")
        self.set_xy(15, 6)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 15)
        self.cell(0, 7, "Centro de Lactancia N° 10 - Banco de leche humana")
        self.set_xy(15, 13)
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, f"Cierre mensual: {self.titulo_informe}")
        self.set_y(30)
        self.set_text_color(*TEXTO)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*SUAVE)
        self.cell(0, 5, f"Generado el {datetime.now():%d/%m/%Y %H:%M}", align="L")
        self.cell(0, 5, f"Página {self.page_no()} de {{nb}}", align="R")

    def seccion(self, texto):
        if self.get_y() > self.h - 50:
            self.add_page()
        self.ln(3)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*ROSA)
        self.cell(0, 8, texto, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*ROSA)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_text_color(*TEXTO)

    def subtitulo(self, texto):
        if self.get_y() > self.h - 45:  # evita que el subtítulo quede solo al pie de la página
            self.add_page()
        self.set_font("Helvetica", "B", 9)
        self.cell(0, 6, texto, new_x="LMARGIN", new_y="NEXT")

    def tarjetas(self, items):
        """Fila de cifras destacadas: [(valor, etiqueta, nota)]."""
        ancho = (self.w - self.l_margin - self.r_margin - 3 * (len(items) - 1)) / len(items)
        y = self.get_y()
        for i, (valor, etiqueta, nota) in enumerate(items):
            x = self.l_margin + i * (ancho + 3)
            self.set_fill_color(*ROSA_CLARO)
            self.rect(x, y, ancho, 20, "F")
            self.set_xy(x + 3, y + 2)
            self.set_font("Helvetica", "B", 13)
            self.cell(ancho - 6, 7, valor)
            self.set_xy(x + 3, y + 9)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*SUAVE)
            self.cell(ancho - 6, 4, etiqueta)
            self.set_xy(x + 3, y + 13.5)
            self.cell(ancho - 6, 4, nota)
            self.set_text_color(*TEXTO)
        self.set_y(y + 23)

    def tabla(self, encabezados, filas, anchos, alinear=None, rojo=False, vacio="Sin registros en el mes."):
        if not filas:
            self.set_font("Helvetica", "I", 9)
            self.set_text_color(*SUAVE)
            self.cell(0, 6, vacio, new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(*TEXTO)
            return
        color_enc = ROJO if rojo else ROSA
        color_fila = ROJO_CLARO if rojo else (250, 248, 255)
        self.set_font("Helvetica", "", 8.5)
        self.set_fill_color(*color_fila)
        self.set_draw_color(*(239, 194, 189) if rojo else (231, 224, 245))
        with self.table(
            col_widths=anchos, text_align=alinear or "LEFT", line_height=4.6,
            headings_style=FontFace(emphasis="BOLD", color=(255, 255, 255), fill_color=color_enc),
            cell_fill_color=color_fila, cell_fill_mode="ROWS",
            padding=1.4, first_row_as_headings=True,
        ) as t:
            fila = t.row()
            for e in encabezados:
                fila.cell(e)
            for f in filas:
                fila = t.row()
                for v in f:
                    fila.cell("" if v is None else str(v))
        self.ln(2)

    def grafico_proyeccion(self, titulo, unidad, historia, futuro, etiquetas, alto=46):
        """Línea continua para los meses registrados y punteada para la proyección."""
        x0, ancho = self.l_margin, self.w - self.l_margin - self.r_margin
        if self.get_y() + alto + 12 > self.h - 18:
            self.add_page()
        ult, proy = historia[-1], futuro[-1]
        var = variacion(proy, ult)
        self.set_font("Helvetica", "B", 9.5)
        self.cell(ancho * 0.55, 6, titulo)
        self.set_font("Helvetica", "", 8.5)
        self.set_text_color(*SUAVE)
        self.cell(ancho * 0.45, 6, f"Último mes: {num(ult, unidad)}  ·  {etiquetas[-1]}: {num(proy, unidad)} ({var})",
                  align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*TEXTO)
        valores = historia + futuro
        maximo = max(valores) * 1.15 or 1
        paso = 10 ** (len(str(int(maximo / 4))) - 1) if maximo >= 4 else 1
        for m in (1, 2, 2.5, 5, 10):
            if m * paso >= maximo / 4:
                paso *= m
                break
        tope = paso * 4
        while tope < maximo:
            tope += paso
        izq, y0 = x0 + 14, self.get_y() + 2
        ancho_g, alto_g = ancho - 16, alto - 10
        n, h = len(valores), len(historia)
        px = lambda i: izq + ancho_g * (i + 0.5) / n
        py = lambda v: y0 + alto_g * (1 - v / tope)
        # zona proyectada
        self.set_fill_color(*MENTA)
        xz = (px(h - 1) + px(h)) / 2
        self.rect(xz, y0, izq + ancho_g - xz, alto_g, "F")
        self.set_font("Helvetica", "B", 6.5)
        self.set_text_color(47, 100, 136)
        self.set_xy(izq + ancho_g - 30, y0 + 0.5)
        self.cell(29, 3.5, "PROYECCIÓN", align="R")
        # grilla y eje
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*SUAVE)
        self.set_line_width(0.15)
        v = 0
        while v <= tope + 1e-9:
            y = py(v)
            self.set_draw_color(*((200, 190, 225) if v == 0 else (234, 228, 246)))
            self.line(izq, y, izq + ancho_g, y)
            self.set_xy(x0, y - 1.8)
            self.cell(12.5, 3.6, num(v), align="R")
            v += paso
        for i, etq in enumerate(etiquetas):
            self.set_xy(px(i) - 9, y0 + alto_g + 1)
            self.set_font("Helvetica", "I" if i >= h else "", 6.5)
            self.cell(18, 3.6, etq, align="C")
        # líneas
        self.set_draw_color(*ROSA)
        self.set_line_width(0.6)
        for i in range(h - 1):
            self.line(px(i), py(valores[i]), px(i + 1), py(valores[i + 1]))
        self.set_dash_pattern(dash=1.4, gap=1.1)
        for i in range(h - 1, n - 1):
            self.line(px(i), py(valores[i]), px(i + 1), py(valores[i + 1]))
        self.set_dash_pattern()
        # puntos (llenos = registrados, huecos = proyectados)
        self.set_line_width(0.45)
        for i, v in enumerate(valores):
            self.set_fill_color(*(ROSA if i < h else (255, 255, 255)))
            self.ellipse(px(i) - 1.1, py(v) - 1.1, 2.2, 2.2, "FD")
        for i in (h - 1, n - 1):
            self.set_xy(px(i) - 12, py(valores[i]) - 5)
            self.set_font("Helvetica", "B", 7)
            self.set_text_color(*TEXTO)
            self.cell(24, 3.6, num(valores[i]), align="C")
        self.set_line_width(0.2)
        self.set_text_color(*TEXTO)
        self.set_y(y0 + alto_g + 7)

    def grafico_agentes(self, agentes):
        """Barras horizontales: porcentaje del total de registros del mes que cargó cada agente,
        con los colores de cada tipo de tarea."""
        ancho = self.w - self.l_margin - self.r_margin
        x_barra, ancho_etq = self.l_margin + 52, 52
        ancho_barra = ancho - ancho_etq - 24
        maximo = max(f["pct"] for f in agentes["filas"])
        # Leyenda
        self.set_font("Helvetica", "", 7)
        x = self.l_margin
        for k, nombre, _, _, color in TAREAS_AGENTE:
            if x + 6 + self.get_string_width(nombre) > self.l_margin + ancho:
                x = self.l_margin
                self.ln(4.5)
            self.set_fill_color(*color)
            self.rect(x, self.get_y() + 0.8, 3, 3, "F")
            self.set_xy(x + 4, self.get_y())
            self.cell(self.get_string_width(nombre) + 2, 4.6, nombre)
            x += 6 + self.get_string_width(nombre) + 4
        self.ln(7)
        for f in agentes["filas"]:
            if self.get_y() > self.h - 25:
                self.add_page()
            y = self.get_y()
            self.set_font("Helvetica", "B" if f["rol"] else "I", 8)
            self.set_text_color(*(TEXTO if f["rol"] else SUAVE))
            self.set_xy(self.l_margin, y)
            self.cell(ancho_etq - 2, 4, f["nombre"][:30])
            self.set_font("Helvetica", "", 6.5)
            self.set_text_color(*SUAVE)
            self.set_xy(self.l_margin, y + 3.6)
            self.cell(ancho_etq - 2, 3.4, f["rol"])
            largo = ancho_barra * f["pct"] / (maximo or 1)
            xi = x_barra
            self.set_fill_color(245, 242, 252)
            self.rect(x_barra, y + 0.6, ancho_barra, 6, "F")
            for k, *_, color in TAREAS_AGENTE:
                parte = largo * f["cantidades"][k] / f["total"] if f["total"] else 0
                if parte > 0:
                    self.set_fill_color(*color)
                    self.rect(xi, y + 0.6, parte, 6, "F")
                    xi += parte
            self.set_font("Helvetica", "B", 8.5)
            self.set_text_color(*TEXTO)
            self.set_xy(xi + 1.5, y + 0.8)
            self.cell(22, 5.6, f"{f['pct']:g} %".replace(".", ",") + f"  ({num(f['total'])})")
            self.set_y(y + 9)
        self.set_text_color(*TEXTO)
        self.ln(2)

    def barras(self, valores, alto=32):
        """Gráfico de barras simple (ml extraídos por día)."""
        ancho_total = self.w - self.l_margin - self.r_margin
        maximo = max(valores) or 1
        x0, y0 = self.l_margin, self.get_y()
        paso = ancho_total / len(valores)
        self.set_fill_color(*ROSA)
        for i, v in enumerate(valores):
            h = (alto - 6) * v / maximo
            if h > 0:
                self.rect(x0 + i * paso + 0.4, y0 + alto - 6 - h, paso - 0.8, h, "F")
        self.set_draw_color(200, 190, 225)
        self.line(x0, y0 + alto - 6, x0 + ancho_total, y0 + alto - 6)
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*SUAVE)
        for i in range(len(valores)):
            if i == 0 or (i + 1) % 5 == 0:
                self.set_xy(x0 + i * paso, y0 + alto - 5)
                self.cell(paso, 4, str(i + 1), align="C")
        self.set_xy(x0, y0 - 1)
        self.cell(0, 4, f"máx. {num(maximo, 'ml')}/día", align="R")
        self.set_text_color(*TEXTO)
        self.set_y(y0 + alto + 1)


def generar_pdf(d):
    a, b = d["actual"], d["anterior"]
    pdf = InformePDF(d["titulo"])
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 9, f"Cierre mensual de {d['titulo']}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*SUAVE)
    pdf.cell(0, 5, f"Período: 01/{d['mes']:02d}/{d['anio']} al {calendar.monthrange(d['anio'], d['mes'])[1]}/{d['mes']:02d}/{d['anio']}. "
                   f"Variaciones respecto de {d['titulo_anterior'].lower()}.", new_x="LMARGIN", new_y="NEXT")
    if d["parcial_hasta"]:
        pdf.set_text_color(*ROJO)
        pdf.cell(0, 5, f"Mes en curso: datos registrados hasta el {datetime.strptime(d['parcial_hasta'], '%Y-%m-%d'):%d/%m/%Y}. "
                       "La comparación con el mes anterior es parcial.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*TEXTO)
    pdf.ln(3)

    pdf.tarjetas([
        (num(a["ml_extraidos"], "ml"), "Leche extraída", variacion(a["ml_extraidos"], b["ml_extraidos"])),
        (num(a["ml_entregados"], "ml"), "Leche entregada", variacion(a["ml_entregados"], b["ml_entregados"])),
        (num(a["madres_nuevas"]), "Madres nuevas", variacion(a["madres_nuevas"], b["madres_nuevas"])),
        (num(a["madres_activas"]), "Madres que donaron", variacion(a["madres_activas"], b["madres_activas"])),
    ])

    pdf.seccion("1. Resumen del mes")
    filas = [
        ("Madres donantes nuevas", a["madres_nuevas"], b["madres_nuevas"]),
        ("Madres que donaron en el mes", a["madres_activas"], b["madres_activas"]),
        ("Extracciones", a["extracciones"], b["extracciones"]),
        ("Estímulos", a["estimulos"], b["estimulos"]),
        ("Leche extraída (ml)", a["ml_extraidos"], b["ml_extraidos"]),
        ("Preparaciones realizadas", a["preparaciones"], b["preparaciones"]),
        ("Dosis entregadas", a["dosis"], b["dosis"]),
        ("Leche entregada (ml)", a["ml_entregados"], b["ml_entregados"]),
        ("Bebés que recibieron leche", a["bebes_receptores"], b["bebes_receptores"]),
        ("Otras actividades", a["actividades"], b["actividades"]),
        ("Altas de mamás y bebés", a["altas"], b["altas"]),
    ]
    pdf.tabla(["Indicador", d["titulo"], d["titulo_anterior"], "Variación"],
              [(n, num(x), num(y), variacion(x, y)) for n, x, y in filas],
              (80, 35, 35, 30), ("LEFT", "RIGHT", "RIGHT", "RIGHT"))

    p = d["proyeccion"]
    et = p["etiquetas"]
    pdf.seccion("2. Proyección")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*SUAVE)
    pdf.multi_cell(0, 4.2, f"Registrado de {et[0]} a {et[MESES_HISTORIA - 1]} (6 meses) y proyección de {et[MESES_HISTORIA]} "
                           f"a {et[-1]} (3 meses), calculada con la tendencia lineal de los meses registrados. "
                           "Línea continua: registrado. Línea punteada: proyectado.", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*TEXTO)
    pdf.ln(2)
    for m in p["metricas"]:
        pdf.grafico_proyeccion(m["titulo"], m["unidad"], m["historia"], m["futuro"], et)

    pdf.seccion("3. Extracciones")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 5, "Leche extraída por día del mes", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.barras(d["ml_por_dia"])
    pdf.tabla(["Tipo de leche", "Registros", "Mililitros"],
              [(t, num(n), num(ml, "ml")) for t, n, ml in d["por_leche"]],
              (90, 45, 45), ("LEFT", "RIGHT", "RIGHT"))
    pdf.subtitulo("Donación por madre")
    pdf.tabla(["Madre donante", "Barrio", "Extracciones", "Mililitros"],
              [(m, br or "", num(n), num(ml, "ml")) for m, br, n, ml in d["madres_ml"]],
              (70, 50, 30, 30), ("LEFT", "LEFT", "RIGHT", "RIGHT"))

    pdf.seccion("4. Madres donantes registradas en el mes")
    sit = {"internada": "Internada", "domicilio": "En domicilio"}
    tipo = {"conjunta": "conjunta", "neonatologia": "neonatología"}
    pdf.tabla(["Fecha", "Madre donante", "Barrio", "Localidad", "Situación"],
              [(datetime.strptime(f, "%Y-%m-%d").strftime("%d/%m"), n, br or "", lo or "",
                sit.get(s, s) + (f" ({tipo.get(t, t)})" if t else "")) for f, n, br, lo, s, t in d["nuevas"]],
              (18, 55, 35, 30, 42))

    pdf.seccion("5. Preparaciones entregadas")
    pdf.tabla(["Tipo de preparación", "Veces", "Dosis", "Mililitros"],
              [(t, num(n), num(ds), num(ml, "ml")) for t, n, ds, ml in d["prep_tipo"]],
              (90, 30, 30, 30), ("LEFT", "RIGHT", "RIGHT", "RIGHT"))
    pdf.tabla(["Servicio", "Preparaciones", "Mililitros"],
              [(s, num(n), num(ml, "ml")) for s, n, ml in d["prep_servicio"]],
              (90, 45, 45), ("LEFT", "RIGHT", "RIGHT"), vacio="")

    pdf.seccion("6. Otras actividades")
    pdf.tabla(["Actividad", "Cantidad"], [(t, num(n)) for t, n in d["act_tipo"]], (130, 50), ("LEFT", "RIGHT"))
    if d["educacion"]:
        pdf.subtitulo("Educación: personas alcanzadas")
        pdf.tabla(["Fecha", "Dirigida a", "Tema"],
                  [(datetime.strptime(f[:10], "%Y-%m-%d").strftime("%d/%m"), q, (t or "").replace("Dato de simulación. ", ""))
                   for f, q, t in d["educacion"]], (18, 55, 107))
    if d.get("salidas"):
        pdf.subtitulo("Salidas")
        pdf.tabla(["Fecha", "Lugar o destino", "Motivo"],
                  [(datetime.strptime(f[:10], "%Y-%m-%d").strftime("%d/%m"), lg or "", (t or "").replace("Dato de simulación. ", ""))
                   for f, lg, t in d["salidas"]], (18, 55, 107))

    if d.get("leche_mov"):
        pdf.subtitulo("Pasteurización: leche enviada y leche pasteurizada recibida")
        totales = {"envio_leche": 0, "recepcion_leche": 0}
        for f in d["leche_mov"]:
            totales[f[1]] += f[3] or 0
        pdf.tabla(["Fecha", "Movimiento", "Institución", "Mililitros", "Frascos", "Lote"],
                  [(datetime.strptime(f[:10], "%Y-%m-%d").strftime("%d/%m"), "Enviada" if t == "envio_leche" else "Recibida",
                    lg or "", num(ml, "ml"), num(fr) if fr else "", lt or "")
                   for f, t, lg, ml, fr, lt in d["leche_mov"]],
                  (16, 24, 66, 28, 18, 28), ("LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT", "LEFT"))
        pdf.tabla(["Total del mes", "Mililitros"],
                  [("Leche cruda enviada a pasteurizar", num(totales["envio_leche"], "ml")),
                   ("Leche pasteurizada recibida", num(totales["recepcion_leche"], "ml"))],
                  (130, 50), ("LEFT", "RIGHT"))

    pdf.seccion("7. Actividades por agente")
    ag = d["agentes"]
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*SUAVE)
    pdf.multi_cell(0, 4.2, f"Porcentaje del total de registros del mes ({num(ag['total'])}) que cargó cada usuario: madres registradas, "
                           "extracciones y estímulos, preparaciones, otras actividades y controles de bebés.",
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(*TEXTO)
    pdf.ln(2)
    if ag["filas"]:
        pdf.grafico_agentes(ag)
        pdf.tabla(["Agente", "Madres", "Extracc.", "Prepar.", "Activ.", "Controles", "Total", "%"],
                  [(f["nombre"][:34], *(num(f["cantidades"][k]) for k, *_ in TAREAS_AGENTE), num(f["total"]),
                    f"{f['pct']:g} %".replace(".", ",")) for f in ag["filas"]],
                  (56, 18, 18, 18, 18, 18, 17, 17), ("LEFT",) + ("RIGHT",) * 7)
    else:
        pdf.tabla(["Agente", "Total"], [], (130, 50))

    pdf.seccion("8. Altas de mamás y bebés")
    pdf.tabla(["Fecha de alta", "Madre donante", "Bebé", "Días en el programa", "Leche donada"],
              [(datetime.strptime(fa, "%Y-%m-%d").strftime("%d/%m"), n, bb or "-",
                num((date.fromisoformat(fa) - date.fromisoformat(fr)).days + 1), num(ml, "ml"))
               for fa, n, bb, fr, ml in d["altas"]],
              (24, 52, 40, 32, 32), ("LEFT", "LEFT", "LEFT", "RIGHT", "RIGHT"), vacio="No hubo altas en el mes.")

    pdf.seccion("9. Madres y bebés con factores de riesgo")
    pdf.tabla(["Madre donante", "Dirección", "Barrio", "Teléfono", "Factores de riesgo (madre)", "Bebé"],
              [(n, dr or "", br or "", tel or "", fm or "-", fb or "-") for n, dr, br, tel, fm, fb in d["riesgo"]],
              (34, 32, 24, 24, 33, 33), rojo=True, vacio="No hay madres ni bebés con factores de riesgo en el mes.")

    if pdf.get_y() > pdf.h - 45:
        pdf.add_page()
    pdf.ln(14)
    y = pdf.get_y()
    pdf.set_draw_color(*SUAVE)
    for x, texto in ((25, "Firma y sello del responsable"), (120, "Fecha de cierre")):
        pdf.line(x, y, x + 65, y)
        pdf.set_xy(x, y + 1)
        pdf.set_font("Helvetica", "", 8)
        pdf.cell(65, 5, texto, align="C")
    return bytes(pdf.output())
