"""CENLAC - Registro de madres donantes del Centro de Lactancia N° 10."""
import base64
import os
import socket
import sqlite3
import unicodedata
from datetime import date, datetime

from flask import Flask, Response, abort, flash, g, redirect, render_template, request, send_from_directory, url_for
from werkzeug.exceptions import RequestEntityTooLarge

import segno

import alta
import archivos
import basedatos
import cierre
import crecimiento
import envivo
import usuarios

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = basedatos.DB_PATH

app = Flask(__name__)


def clave_secreta():
    """Clave para firmar las sesiones: SECRET_KEY, o una clave aleatoria guardada junto a la base."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    ruta = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "clave-secreta.txt")
    try:
        with open(ruta, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        import secrets
        clave = secrets.token_hex(32)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(clave)
        return clave


app.secret_key = clave_secreta()

# Publicada en internet (Render, Railway, etc.): el servicio de hosting atiende el https y le pasa los pedidos a la app.
if os.environ.get("EN_INTERNET") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix

    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")
# Fotos o PDF de los consentimientos informados: carpeta local o Supabase Storage (ver archivos.py).
EXTENSIONES_CONSENTIMIENTO = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}
MAX_CONSENTIMIENTO_MB = 15
app.config["MAX_CONTENT_LENGTH"] = MAX_CONSENTIMIENTO_MB * 1024 * 1024

SITUACIONES = {"internada": "Internada", "domicilio": "En domicilio"}
# Si la mamá dona su leche al banco o solo se extrae (por ejemplo, para su propio bebé).
MODALIDADES = {"donante": "Donante", "extraccion": "Solo extracción"}
INTERNACIONES = {"conjunta": "Internación conjunta en maternidad", "neonatologia": "Neonatología"}
TIPOS_REGISTRO = {"extraccion": "Extracción", "estimulo": "Estímulo"}
TIPOS_LECHE = {"calostro": "Calostro", "transicion": "De transición", "madura": "Madura"}
SERVICIOS = {"maternidad": "Maternidad", "neonatologia": "Neonatología"}
SUGERENCIAS_PREPARACION = ["Leche humana pasteurizada", "Leche humana fortificada", "Calostroterapia", "Leche de la propia madre", "Leche de fórmula"]
TIPOS_RAPIDOS = ["Leche humana pasteurizada", "Leche humana fortificada", "Calostroterapia", "Leche de fórmula"]
SUGERENCIAS_FORTIFICADOR = ["Fortificador de leche humana en polvo", "Fortificador líquido", "Módulo proteico",
                            "Triglicéridos de cadena media (TCM)"]
SUGERENCIAS_CONCENTRACION = ["1 sobre cada 25 ml", "1 sobre cada 50 ml", "Media dosis (1 sobre cada 50 ml)",
                             "4 g cada 100 ml"]
SUGERENCIAS_FRECUENCIA = ["Cada 2 horas", "Cada 3 horas", "Cada 4 horas", "Cada 6 horas", "Dosis única"]
# Cada actividad: nombre, ícono y texto de ayuda para la descripción.
ACTIVIDADES = {
    "educacion": ("Educación", "📚", "Tema tratado, por ejemplo técnica de extracción, conservación de la leche o posición para amamantar."),
    "limpieza": ("Limpieza del sector", "🧽", "Áreas y equipos limpiados, por ejemplo extractores, heladera, mesadas o pisos."),
    "difusion": ("Difusión", "📣", "Medio y alcance, por ejemplo charla en sala de espera, redes sociales o radio local."),
    "carteleria": ("Cartelería", "🪧", "Carteles colocados o renovados, con su ubicación y contenido."),
    "salida": ("Salidas", "🚐", "Motivo y resultado de la salida, por ejemplo retiro de leche a domicilio, visita a una mamá, charla en un centro de salud o escuela."),
    "envio_leche": ("Envío de leche a pasteurizar", "📤", "Leche cruda enviada (madura, calostro), estado de la cadena de frío y quién la recibió en la institución."),
    "recepcion_leche": ("Recepción de leche pasteurizada", "📥", "Leche pasteurizada que regresó: estado de los frascos y de la cadena de frío, y quién la entregó."),
}
# Circuito de pasteurización: la leche cruda se envía a otra institución para pasteurizarla y esa institución
# la devuelve pasteurizada. En los dos casos se registra la institución, los ml, los frascos y el lote.
ACTIVIDADES_LECHE = ("envio_leche", "recepcion_leche")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS madres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apellido TEXT NOT NULL,
    nombre TEXT NOT NULL,
    dni TEXT NOT NULL UNIQUE,
    fecha_nacimiento TEXT,
    telefono TEXT,
    direccion TEXT,
    barrio TEXT,
    localidad TEXT,
    situacion TEXT NOT NULL CHECK (situacion IN ('internada', 'domicilio')),
    modalidad TEXT NOT NULL DEFAULT 'donante' CHECK (modalidad IN ('donante', 'extraccion')),
    tipo_internacion TEXT CHECK (tipo_internacion IN ('conjunta', 'neonatologia')),
    observaciones TEXT,
    factores_riesgo TEXT,
    patologias_cronicas TEXT,
    fecha_alta TEXT,
    alta_observaciones TEXT,
    fecha_registro TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bebes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    madre_id INTEGER NOT NULL REFERENCES madres(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    apellido_materno TEXT NOT NULL,
    fecha_nacimiento TEXT,
    factores_riesgo TEXT,
    patologias_cronicas TEXT,
    sexo TEXT,
    eg_semanas TEXT,
    eg_dias TEXT,
    peso_nacimiento TEXT
);
-- Controles diarios de crecimiento del bebé durante la internación (uno por día)
CREATE TABLE IF NOT EXISTS controles_bebe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bebe_id INTEGER NOT NULL REFERENCES bebes(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    peso REAL,
    talla REAL,
    pc REAL,
    observaciones TEXT,
    UNIQUE (bebe_id, fecha)
);
CREATE TABLE IF NOT EXISTS padres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    madre_id INTEGER NOT NULL UNIQUE REFERENCES madres(id) ON DELETE CASCADE,
    nombre TEXT NOT NULL,
    apellido TEXT NOT NULL,
    edad INTEGER,
    convive INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS extracciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    madre_id INTEGER NOT NULL REFERENCES madres(id) ON DELETE CASCADE,
    fecha_hora TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('extraccion', 'estimulo')),
    cantidad_ml REAL,
    tipo_leche TEXT CHECK (tipo_leche IN ('calostro', 'transicion', 'madura')),
    caracteristicas TEXT
);
CREATE TABLE IF NOT EXISTS actividades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('educacion', 'limpieza', 'difusion', 'carteleria', 'salida', 'envio_leche', 'recepcion_leche')),
    destinatario_nombre TEXT,
    destinatario_apellido TEXT,
    material TEXT,
    descripcion TEXT,
    lugar TEXT,
    cantidad_ml REAL,
    frascos INTEGER,
    lote TEXT
);
CREATE TABLE IF NOT EXISTS preparaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha TEXT NOT NULL,
    hora_entrega TEXT NOT NULL,
    tipo_preparacion TEXT NOT NULL,
    dosis_ml REAL NOT NULL,
    frecuencia TEXT NOT NULL,
    cantidad_dosis INTEGER NOT NULL,
    bebe_nombre TEXT NOT NULL,
    bebe_apellido TEXT NOT NULL,
    servicio TEXT NOT NULL CHECK (servicio IN ('maternidad', 'neonatologia')),
    observaciones TEXT,
    fortificador TEXT,
    concentracion TEXT
);
CREATE INDEX IF NOT EXISTS idx_extracciones_madre ON extracciones(madre_id, fecha_hora);
"""


def get_db():
    if "db" not in g:
        g.db = basedatos.conectar()
    return g.db


usuarios.iniciar(app, get_db)
envivo.iniciar(app, get_db)


@app.errorhandler(403)
def sin_permiso(_e):
    return render_template("sin_permiso.html"), 403


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# Columnas agregadas después de la primera versión: se suman a bases ya existentes.
COLUMNAS_NUEVAS = {
    "madres": ["factores_riesgo", "patologias_cronicas", "fecha_alta", "alta_observaciones",
               "consentimiento_archivo", "consentimiento_fecha", "consentimiento_subido"],
    "preparaciones": ["fortificador", "concentracion"],
    "bebes": ["factores_riesgo", "patologias_cronicas", "sexo", "eg_semanas", "eg_dias", "peso_nacimiento"],
}

TABLAS_CON_USUARIO = ["madres", "extracciones", "preparaciones", "actividades", "controles_bebe"]


def deshacer(db):
    """Después de un error de integridad (DNI repetido) Postgres exige deshacer la transacción."""
    if hasattr(db, "rollback"):
        db.rollback()


def usuario_id_actual():
    return g.usuario["id"] if g.get("usuario") else None


def init_db():
    if basedatos.ES_POSTGRES:
        basedatos.crear_tablas_postgres()
        return
    with sqlite3.connect(DB_PATH) as db:
        db.executescript(ESQUEMA)
        db.executescript(usuarios.ESQUEMA)
        db.executescript(envivo.ESQUEMA_SQLITE)
        # Bases anteriores: la tabla de actividades no admitía "salida" ni envío/recepción de leche (restricción CHECK).
        # Se rehace conservando los datos.
        sql_act = db.execute("SELECT sql FROM sqlite_master WHERE name = 'actividades'").fetchone()[0]
        if "'recepcion_leche'" not in sql_act:
            anteriores = [(fila[1], fila[2]) for fila in db.execute("PRAGMA table_info(actividades)")]
            columnas = [nombre for nombre, _ in anteriores]
            db.execute("ALTER TABLE actividades RENAME TO actividades_anterior")
            db.executescript(ESQUEMA)
            # Columnas agregadas más tarde (por ejemplo usuario_id) que no están en ESQUEMA.
            nuevas = {fila[1] for fila in db.execute("PRAGMA table_info(actividades)")}
            for nombre, tipo_col in anteriores:
                if nombre not in nuevas:
                    db.execute(f"ALTER TABLE actividades ADD COLUMN {nombre} {tipo_col}")
            db.execute(f"INSERT INTO actividades ({', '.join(columnas)}) SELECT {', '.join(columnas)} FROM actividades_anterior")
            db.execute("DROP TABLE actividades_anterior")
        for tabla, columnas in COLUMNAS_NUEVAS.items():
            existentes = {fila[1] for fila in db.execute(f"PRAGMA table_info({tabla})")}
            for col in columnas:
                if col not in existentes:
                    db.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} TEXT")
        if "modalidad" not in {fila[1] for fila in db.execute("PRAGMA table_info(madres)")}:
            db.execute("ALTER TABLE madres ADD COLUMN modalidad TEXT NOT NULL DEFAULT 'donante'")
        # Quién cargó cada registro (para las estadísticas por agente del cierre mensual).
        for tabla in TABLAS_CON_USUARIO:
            if "usuario_id" not in {fila[1] for fila in db.execute(f"PRAGMA table_info({tabla})")}:
                db.execute(f"ALTER TABLE {tabla} ADD COLUMN usuario_id INTEGER REFERENCES usuarios(id)")


@app.template_filter("fecha")
def formato_fecha(valor):
    if not valor:
        return ""
    try:
        return date.fromisoformat(valor).strftime("%d/%m/%Y")
    except ValueError:
        return valor


@app.template_filter("edad")
def calcular_edad(valor):
    if not valor:
        return ""
    try:
        nac = date.fromisoformat(valor)
    except ValueError:
        return ""
    hoy = date.today()
    return hoy.year - nac.year - ((hoy.month, hoy.day) < (nac.month, nac.day))


@app.template_filter("hora")
def formato_hora(valor):
    return valor[11:16] if valor and len(valor) >= 16 else ""


@app.template_filter("mes")
def formato_mes(valor):
    """'2026-10' -> 'oct 2026'."""
    try:
        return f"{cierre.MESES_CORTOS[int(valor[5:7]) - 1]} {valor[:4]}"
    except (TypeError, ValueError, IndexError):
        return valor or ""


@app.template_filter("pct")
def formato_percentil(valor):
    """Percentil para mostrar: P1 a P99, o <P1 / >P99 en los extremos."""
    if valor is None:
        return ""
    if valor < 1:
        return "<P1"
    if valor > 99:
        return ">P99"
    return f"P{round(valor)}"


@app.template_filter("ml")
def formato_ml(valor):
    if valor is None:
        return "-"
    return f"{valor:g} ml"


@app.context_processor
def opciones():
    return {"SITUACIONES": SITUACIONES, "INTERNACIONES": INTERNACIONES, "MODALIDADES": MODALIDADES,
            "ACTIVIDADES_LECHE": ACTIVIDADES_LECHE,
            "TIPOS_REGISTRO": TIPOS_REGISTRO, "TIPOS_LECHE": TIPOS_LECHE, "ACTIVIDADES": ACTIVIDADES,
            "SERVICIOS": SERVICIOS, "SEXOS": crecimiento.SEXOS}


def leer_formulario(form):
    """Valida el formulario y devuelve (madre, padre, bebes, errores)."""
    texto = lambda k: (form.get(k) or "").strip()
    errores = []

    madre = {
        "apellido": texto("apellido"),
        "nombre": texto("nombre"),
        "dni": texto("dni"),
        "fecha_nacimiento": texto("fecha_nacimiento") or None,
        "telefono": texto("telefono"),
        "direccion": texto("direccion"),
        "barrio": texto("barrio"),
        "localidad": texto("localidad"),
        "situacion": texto("situacion"),
        "modalidad": texto("modalidad"),
        "tipo_internacion": texto("tipo_internacion") or None,
        "observaciones": texto("observaciones"),
        "factores_riesgo": texto("factores_riesgo"),
        "patologias_cronicas": texto("patologias_cronicas"),
    }
    for campo, etiqueta in (("apellido", "el apellido"), ("nombre", "el nombre"), ("dni", "el DNI")):
        if not madre[campo]:
            errores.append(f"Falta {etiqueta} de la madre.")
    if madre["modalidad"] not in MODALIDADES:
        errores.append("Indique si la madre es donante o solo realiza extracción.")
    if madre["situacion"] not in SITUACIONES:
        errores.append("Indique si la madre está internada o en domicilio.")
    if madre["situacion"] == "internada":
        if madre["tipo_internacion"] not in INTERNACIONES:
            errores.append("Indique si la internación es conjunta en maternidad o en neonatología.")
    else:
        madre["tipo_internacion"] = None

    padre = None
    if texto("padre_nombre") or texto("padre_apellido"):
        edad = texto("padre_edad")
        if edad and not edad.isdigit():
            errores.append("La edad del padre debe ser un número.")
        padre = {
            "nombre": texto("padre_nombre"),
            "apellido": texto("padre_apellido"),
            "edad": int(edad) if edad.isdigit() else None,
            "convive": 1 if form.get("padre_convive") == "si" else 0,
        }
        if not padre["nombre"] or not padre["apellido"]:
            errores.append("Complete nombre y apellido del padre, o deje ambos vacíos.")

    bebes = []
    nombres = form.getlist("bebe_nombre")
    apellidos = form.getlist("bebe_apellido")
    fechas = form.getlist("bebe_fecha")
    riesgos = form.getlist("bebe_riesgo")
    patologias = form.getlist("bebe_patologias")
    ids = form.getlist("bebe_id")
    sexos = form.getlist("bebe_sexo")
    eg_semanas = form.getlist("bebe_eg_semanas")
    eg_dias = form.getlist("bebe_eg_dias")
    pesos = form.getlist("bebe_peso_nacimiento")
    valor = lambda lista, i: (lista[i] if i < len(lista) else "").strip()
    for i, nombre in enumerate(nombres):
        nombre = nombre.strip()
        if not nombre:
            continue
        semanas, dias, peso = valor(eg_semanas, i), valor(eg_dias, i), valor(pesos, i).replace(",", ".")
        if semanas and not (semanas.isdigit() and 22 <= int(semanas) <= 44):
            errores.append(f"La edad gestacional de {nombre} debe estar entre 22 y 44 semanas.")
        if dias and not (dias.isdigit() and int(dias) <= 6):
            errores.append(f"Los días de edad gestacional de {nombre} van de 0 a 6.")
        try:
            peso_ok = not peso or 300 <= float(peso) <= 6500
        except ValueError:
            peso_ok = False
        if not peso_ok:
            errores.append(f"El peso al nacer de {nombre} va en gramos (entre 300 y 6500).")
        bebes.append({
            "id": int(valor(ids, i)) if valor(ids, i).isdigit() else None,
            "nombre": nombre,
            "apellido_materno": valor(apellidos, i) or madre["apellido"],
            "fecha_nacimiento": valor(fechas, i) or None,
            "factores_riesgo": valor(riesgos, i),
            "patologias_cronicas": valor(patologias, i),
            "sexo": valor(sexos, i) if valor(sexos, i) in crecimiento.SEXOS else None,
            "eg_semanas": semanas or None,
            "eg_dias": dias or None,
            "peso_nacimiento": peso or None,
        })

    return madre, padre, bebes, errores


def guardar(db, madre_id, madre, padre, bebes):
    columnas = list(madre.keys())
    if madre_id is None:
        madre["fecha_registro"] = date.today().isoformat()
        madre["usuario_id"] = usuario_id_actual()
        columnas += ["fecha_registro", "usuario_id"]
        cur = db.execute(
            f"INSERT INTO madres ({', '.join(columnas)}) VALUES ({', '.join('?' * len(columnas))})",
            [madre[c] for c in columnas],
        )
        madre_id = cur.lastrowid
    else:
        db.execute(
            f"UPDATE madres SET {', '.join(c + ' = ?' for c in columnas)} WHERE id = ?",
            [madre[c] for c in columnas] + [madre_id],
        )
        db.execute("DELETE FROM padres WHERE madre_id = ?", (madre_id,))

    # Los bebés se actualizan por id para no perder sus controles de crecimiento.
    existentes = {r[0] for r in db.execute("SELECT id FROM bebes WHERE madre_id = ?", (madre_id,))}
    campos = ["nombre", "apellido_materno", "fecha_nacimiento", "factores_riesgo", "patologias_cronicas",
              "sexo", "eg_semanas", "eg_dias", "peso_nacimiento"]
    conservados = set()
    for b in bebes:
        if b.get("id") in existentes:
            db.execute(f"UPDATE bebes SET {', '.join(c + ' = ?' for c in campos)} WHERE id = ?",
                       [b.get(c) for c in campos] + [b["id"]])
            conservados.add(b["id"])
        else:
            db.execute(f"INSERT INTO bebes (madre_id, {', '.join(campos)}) VALUES (?{', ?' * len(campos)})",
                       [madre_id] + [b.get(c) for c in campos])
    for bebe_id in existentes - conservados:
        db.execute("DELETE FROM bebes WHERE id = ?", (bebe_id,))
    if padre:
        db.execute(
            "INSERT INTO padres (madre_id, nombre, apellido, edad, convive) VALUES (?, ?, ?, ?, ?)",
            (madre_id, padre["nombre"], padre["apellido"], padre["edad"], padre["convive"]),
        )
    db.commit()
    return madre_id


def cargar_madre(madre_id):
    db = get_db()
    madre = db.execute("SELECT * FROM madres WHERE id = ?", (madre_id,)).fetchone()
    if madre is None:
        abort(404)
    padre = db.execute("SELECT * FROM padres WHERE madre_id = ?", (madre_id,)).fetchone()
    bebes = db.execute("SELECT * FROM bebes WHERE madre_id = ? ORDER BY id", (madre_id,)).fetchall()
    return madre, padre, bebes


def resumen_extracciones(madre_id):
    db = get_db()
    registros = db.execute(
        "SELECT * FROM extracciones WHERE madre_id = ? ORDER BY fecha_hora DESC, id DESC", (madre_id,)
    ).fetchall()
    dias = []
    for r in registros:
        dia = r["fecha_hora"][:10]
        if not dias or dias[-1]["dia"] != dia:
            dias.append({"dia": dia, "registros": [], "total_ml": 0})
        dias[-1]["registros"].append(r)
        dias[-1]["total_ml"] += r["cantidad_ml"] or 0
    total = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cantidad_ml), 0) FROM extracciones WHERE madre_id = ?", (madre_id,)
    ).fetchone()
    return {"dias": dias, "cantidad": total[0], "total_ml": total[1]}


VISTAS = {
    "": "Activas (sin alta)",
    "todas": "Todas",
    "internada": "Internadas",
    "domicilio": "En domicilio",
    "donante": "Donantes",
    "extraccion": "Solo extracción",
    "riesgo": "Con patologías o factores de riesgo",
}

SQL_RIESGO = """(COALESCE(m.factores_riesgo, '') <> '' OR COALESCE(m.patologias_cronicas, '') <> ''
                 OR EXISTS (SELECT 1 FROM bebes b WHERE b.madre_id = m.id
                            AND (COALESCE(b.factores_riesgo, '') <> '' OR COALESCE(b.patologias_cronicas, '') <> '')))"""


@app.route("/")
def listado():
    # El perfil Consulta trabaja con la vista mini (widget de escritorio).
    if not usuarios.puede("completo"):
        return redirect(url_for("widget"))
    q = (request.args.get("q") or "").strip()
    ver = request.args.get("ver") or ""
    # El perfil Consulta no ve datos de salud: no puede filtrar por riesgo.
    if ver not in VISTAS or (ver == "riesgo" and not usuarios.puede("completo")):
        ver = ""
    inicio_mes = date.today().replace(day=1).isoformat()
    sql = f"""SELECT m.*, (SELECT COUNT(*) FROM bebes b WHERE b.madre_id = m.id) AS cant_bebes,
                    (SELECT SUM(e.cantidad_ml) FROM extracciones e WHERE e.madre_id = m.id) AS total_ml,
                    {SQL_RIESGO} AS con_riesgo
             FROM madres m WHERE 1 = 1"""
    params = []
    if q:
        campos = ["m.apellido", "m.nombre", "m.barrio", "m.localidad"] + (["m.dni"] if usuarios.puede("completo") else [])
        sql += " AND (" + " OR ".join(f"{c} LIKE ?" for c in campos) + ")"
        params += [f"%{q}%"] * len(campos)
    # La pantalla principal muestra solo las madres sin alta (del mes actual y anteriores).
    # Las dadas de alta se ven en "Todas" y en la búsqueda por texto, que busca en todo el histórico.
    if ver != "todas" and not q:
        sql += " AND (m.fecha_alta IS NULL OR m.fecha_alta = '')"
    if ver in SITUACIONES:
        sql += " AND m.situacion = ?"
        params.append(ver)
    elif ver in MODALIDADES:
        sql += " AND m.modalidad = ?"
        params.append(ver)
    elif ver == "riesgo":
        sql += " AND " + SQL_RIESGO
    sql += " ORDER BY m.fecha_registro DESC, m.id DESC"
    db = get_db()
    madres = db.execute(sql, params).fetchall()
    return render_template("listado.html", madres=madres, q=q, ver=ver, vistas=VISTAS,
                           inicio_mes=inicio_mes, resumen=resumen_inicio(db))


def resumen_inicio(db):
    """Contadores del mes en curso y del año actual (el año arranca de cero cada 1 de enero, sin borrar datos)."""
    hoy = date.today()
    desde = {"mes": hoy.strftime("%Y-%m"), "anio": str(hoy.year)}
    resumen = {}
    for periodo, prefijo in desde.items():
        largo = len(prefijo)
        resumen[periodo] = {
            "madres": db.execute("SELECT COUNT(*) FROM madres WHERE substr(fecha_registro, 1, ?) = ?",
                                 (largo, prefijo)).fetchone()[0],
            "bebes": db.execute("""SELECT COUNT(*) FROM bebes b JOIN madres m ON m.id = b.madre_id
                                   WHERE substr(m.fecha_registro, 1, ?) = ?""", (largo, prefijo)).fetchone()[0],
            "extracciones": db.execute("SELECT COUNT(*) FROM extracciones WHERE substr(fecha_hora, 1, ?) = ?",
                                       (largo, prefijo)).fetchone()[0],
            "ml": db.execute("SELECT COALESCE(SUM(cantidad_ml), 0) FROM extracciones WHERE substr(fecha_hora, 1, ?) = ?",
                             (largo, prefijo)).fetchone()[0],
        }
    resumen["nombre_mes"] = cierre.MESES[hoy.month - 1]
    resumen["anio_actual"] = hoy.year
    resumen["madres_total"] = db.execute("SELECT COUNT(*) FROM madres").fetchone()[0]
    return resumen


@app.route("/widget")
def widget():
    """Vista mini para dejar abierta en el escritorio de la PC (pantalla principal del perfil Consulta).
    Solo datos básicos: sin DNI, teléfono, domicilio ni datos de salud."""
    db = get_db()
    madres = db.execute("""SELECT m.id, m.apellido, m.nombre, m.barrio, m.localidad, m.situacion, m.tipo_internacion,
                                  m.fecha_registro,
                                  (SELECT COALESCE(SUM(e.cantidad_ml), 0) FROM extracciones e WHERE e.madre_id = m.id) AS total_ml,
                                  (SELECT MAX(e.fecha_hora) FROM extracciones e WHERE e.madre_id = m.id) AS ultima
                           FROM madres m WHERE m.fecha_alta IS NULL OR m.fecha_alta = ''
                           ORDER BY m.apellido COLLATE NOCASE, m.nombre COLLATE NOCASE""").fetchall()
    bebes = {}
    for b in db.execute("SELECT madre_id, nombre, apellido_materno FROM bebes ORDER BY id"):
        bebes.setdefault(b["madre_id"], []).append(f"{b['nombre']} {b['apellido_materno'] or ''}".strip())
    return render_template("widget.html", madres=madres, bebes=bebes, resumen=resumen_inicio(db),
                           ahora=datetime.now())


@app.route("/sw.js")
def service_worker():
    """El service worker se sirve desde la raíz para que la app instalada abarque todas las pantallas."""
    r = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript", max_age=0)
    r.headers["Service-Worker-Allowed"] = "/"
    return r


def direccion_red():
    """Dirección con la que otros dispositivos del WiFi llegan a este servidor (http://IP:puerto)."""
    host = request.host
    nombre = host.split(":")[0]
    if nombre not in ("localhost", "127.0.0.1", "::1", "[::1]"):
        return request.host_url.rstrip("/")
    puerto = host.split(":")[1] if ":" in host else "80"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no envía nada: solo elige la placa de red
            ip = s.getsockname()[0]
    except OSError:
        return request.host_url.rstrip("/")
    return f"http://{ip}" + ("" if puerto == "80" else f":{puerto}")


@app.route("/instalar")
def instalar():
    """Cómo instalar CENLAC como aplicación en la PC y en el celular, con un QR para abrirla desde el celular."""
    url = direccion_red() + url_for("listado")
    qr = segno.make(url, error="m").svg_inline(scale=5, border=2, dark="#4a4360", omitsize=True)
    return render_template("instalar.html", url=url, qr=qr, en_internet=os.environ.get("EN_INTERNET") == "1", segura=request.is_secure or request.host.startswith(("localhost", "127.0.0.1")))


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.static_folder, "iconos"), "centro-lactancia.ico",
                               mimetype="image/vnd.microsoft.icon")


@app.route("/widget/acceso-directo.bat")
def widget_acceso_directo():
    """Acceso directo para Windows. Al ejecutarlo crea en el escritorio el ícono "CENLAC"
    (con la gota) que abre el widget en una ventana chica, sin barras del navegador, y lo abre."""
    url = request.host_url.rstrip("/") + url_for("widget")
    icono = request.host_url.rstrip("/") + url_for("favicon")
    ps = f"""
$d = Join-Path $env:LOCALAPPDATA 'CentroLactanciaWidget'
New-Item -ItemType Directory -Force $d | Out-Null
$ico = Join-Path $d 'centro-lactancia.ico'
try {{ Invoke-WebRequest -UseBasicParsing '{icono}' -OutFile $ico }} catch {{}}
$nav = @("${{env:ProgramFiles(x86)}}\\Microsoft\\Edge\\Application\\msedge.exe", "$env:ProgramFiles\\Microsoft\\Edge\\Application\\msedge.exe",
         "$env:ProgramFiles\\Google\\Chrome\\Application\\chrome.exe", "${{env:ProgramFiles(x86)}}\\Google\\Chrome\\Application\\chrome.exe",
         "$env:LOCALAPPDATA\\Google\\Chrome\\Application\\chrome.exe") | Where-Object {{ Test-Path $_ }} | Select-Object -First 1
if (-not $nav) {{ Start-Process '{url}'; exit }}
$argumentos = '--app={url} --user-data-dir="' + $d + '" --window-size=380,640 --window-position=40,40'
$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'CENLAC.lnk'))
$s.TargetPath = $nav
$s.Arguments = $argumentos
if (Test-Path $ico) {{ $s.IconLocation = $ico }}
$s.Description = 'CENLAC - Centro de Lactancia N° 10'
$s.Save()
Start-Process $nav -ArgumentList $argumentos
"""
    codificado = base64.b64encode(ps.encode("utf-16-le")).decode()
    texto = "\r\n".join([
        "@echo off",
        "rem CENLAC: crea en el escritorio el icono de la gota que abre el widget",
        "rem en una ventana chica, sin barras del navegador. Alcanza con ejecutarlo una vez.",
        f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {codificado}",
        "",
    ])
    return Response(texto, mimetype="application/x-bat",
                    headers={"Content-Disposition": "attachment; filename=cenlac-acceso-directo.bat"})


def validar_consentimiento(archivo):
    """Devuelve un mensaje de error, o None si el archivo es válido (o no se cargó ninguno)."""
    if not archivo or not archivo.filename:
        return None
    ext = os.path.splitext(archivo.filename)[1].lower()
    if ext not in EXTENSIONES_CONSENTIMIENTO:
        return "El consentimiento debe ser una foto (JPG, PNG, WEBP o HEIC) o un PDF."
    return None


def guardar_consentimiento(db, madre_id, archivo, fecha_firma):
    """Guarda el archivo del consentimiento informado y reemplaza al anterior, si había."""
    if archivo and archivo.filename:
        ext = os.path.splitext(archivo.filename)[1].lower()
        nombre = f"consentimiento-madre-{madre_id}-{datetime.now():%Y%m%d%H%M%S}{ext}"
        archivos.guardar(nombre, archivo)
        anterior = db.execute("SELECT consentimiento_archivo FROM madres WHERE id = ?", (madre_id,)).fetchone()[0]
        db.execute("UPDATE madres SET consentimiento_archivo = ?, consentimiento_subido = ? WHERE id = ?",
                   (nombre, datetime.now().strftime("%Y-%m-%d %H:%M"), madre_id))
        borrar_archivo_consentimiento(anterior)
    if fecha_firma is not None:
        db.execute("UPDATE madres SET consentimiento_fecha = ? WHERE id = ?", (fecha_firma or None, madre_id))
    db.commit()


def borrar_archivo_consentimiento(nombre):
    archivos.borrar(nombre)


@app.errorhandler(RequestEntityTooLarge)
def archivo_muy_grande(_e):
    flash(f"El archivo es demasiado grande (máximo {MAX_CONSENTIMIENTO_MB} MB). Pruebe con una foto de menor resolución.",
          "error")
    return redirect(request.referrer or url_for("listado"))


@app.route("/madres/<int:madre_id>/consentimiento")
def ver_consentimiento(madre_id):
    madre, _, _ = cargar_madre(madre_id)
    if not madre["consentimiento_archivo"]:
        abort(404)
    contenido = archivos.leer(madre["consentimiento_archivo"])
    if contenido is None:
        abort(404)
    datos, tipo = contenido
    return Response(datos, mimetype=tipo, headers={"Cache-Control": "private, no-store"})


@app.route("/madres/<int:madre_id>/consentimiento", methods=["POST"])
def subir_consentimiento(madre_id):
    cargar_madre(madre_id)
    archivo = request.files.get("consentimiento")
    error = validar_consentimiento(archivo)
    if not archivo or not archivo.filename:
        error = "Elija la foto o el PDF del consentimiento."
    if error:
        flash(error, "error")
    else:
        # Si no se indica la fecha de firma, se conserva la que ya estaba cargada.
        guardar_consentimiento(get_db(), madre_id, archivo,
                               (request.form.get("consentimiento_fecha") or "").strip() or None)
        flash("Consentimiento informado cargado.")
    return redirect(url_for("ver", madre_id=madre_id) + "#consentimiento")


@app.route("/madres/<int:madre_id>/consentimiento/eliminar", methods=["POST"])
def eliminar_consentimiento(madre_id):
    madre, _, _ = cargar_madre(madre_id)
    db = get_db()
    db.execute("UPDATE madres SET consentimiento_archivo = NULL, consentimiento_subido = NULL WHERE id = ?", (madre_id,))
    db.commit()
    borrar_archivo_consentimiento(madre["consentimiento_archivo"])
    flash("Se quitó el archivo del consentimiento.")
    return redirect(url_for("ver", madre_id=madre_id) + "#consentimiento")


@app.route("/madres/nueva", methods=["GET", "POST"])
def nueva():
    if request.method == "POST":
        madre, padre, bebes, errores = leer_formulario(request.form)
        archivo = request.files.get("consentimiento")
        if validar_consentimiento(archivo):
            errores.append(validar_consentimiento(archivo))
        if not errores:
            try:
                madre_id = guardar(get_db(), None, madre, padre, bebes)
            except basedatos.ErrorIntegridad:
                deshacer(get_db())
                errores.append("Ya existe una madre registrada con ese DNI.")
            else:
                guardar_consentimiento(get_db(), madre_id, archivo,
                                       (request.form.get("consentimiento_fecha") or "").strip())
                flash("¡Listo! La mamá donante quedó registrada. Gracias por sumarla.")
                return redirect(url_for("ver", madre_id=madre_id))
        for e in errores:
            flash(e, "error")
        return render_template("formulario.html", madre=madre, padre=padre, bebes=bebes, titulo="Nueva madre donante")
    return render_template("formulario.html", madre={}, padre=None, bebes=[], titulo="Nueva madre donante")


@app.route("/madres/<int:madre_id>")
def ver(madre_id):
    madre, padre, bebes = cargar_madre(madre_id)
    ahora = datetime.now()
    return render_template(
        "ver.html", madre=madre, padre=padre, bebes=bebes, ext=resumen_extracciones(madre_id),
        crec=resumen_crecimiento(get_db(), bebes), SEXOS=crecimiento.SEXOS,
        etiqueta_nueva=etiqueta_de_madre(request.args.get("etiqueta", type=int), madre_id),
        hoy=ahora.strftime("%Y-%m-%d"), ahora=ahora.strftime("%H:%M"),
    )


@app.route("/madres/<int:madre_id>/extracciones", methods=["POST"])
def nueva_extraccion(madre_id):
    cargar_madre(madre_id)
    f = request.form
    fecha, hora = (f.get("fecha") or "").strip(), (f.get("hora") or "").strip()
    tipo = f.get("tipo") or ""
    tipo_leche = f.get("tipo_leche") or None
    cantidad = (f.get("cantidad_ml") or "").strip().replace(",", ".")
    errores = []
    try:
        fecha_hora = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        errores.append("Indique fecha y hora válidas.")
    if tipo not in TIPOS_REGISTRO:
        errores.append("Indique si es extracción o estímulo.")
    if tipo_leche is not None and tipo_leche not in TIPOS_LECHE:
        errores.append("Tipo de leche no válido.")
    try:
        cantidad_ml = float(cantidad) if cantidad else None
        if cantidad_ml is not None and not 0 <= cantidad_ml <= 2000:
            raise ValueError
    except ValueError:
        errores.append("La cantidad debe ser un número de mililitros (0 a 2000).")
    if tipo == "extraccion" and not cantidad:
        errores.append("Indique la cantidad extraída en mililitros.")
    if errores:
        for e in errores:
            flash(e, "error")
    else:
        db = get_db()
        cur = db.execute(
            "INSERT INTO extracciones (madre_id, fecha_hora, tipo, cantidad_ml, tipo_leche, caracteristicas, usuario_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (madre_id, fecha_hora, tipo, cantidad_ml, tipo_leche, (f.get("caracteristicas") or "").strip(),
             usuario_id_actual()),
        )
        db.commit()
        flash(f"{TIPOS_REGISTRO[tipo]} registrada. Ya está lista su etiqueta con código QR.")
        # Se vuelve a la ficha mostrando la etiqueta QR del registro recién guardado.
        return redirect(url_for("ver", madre_id=madre_id, etiqueta=cur.lastrowid) + "#etiqueta-nueva")
    return redirect(url_for("ver", madre_id=madre_id) + "#extracciones")


def datos_etiqueta(ext_id):
    """Datos de la etiqueta de una extracción: texto legible y código QR en SVG."""
    fila = get_db().execute(
        "SELECT e.*, m.nombre, m.apellido FROM extracciones e JOIN madres m ON m.id = e.madre_id WHERE e.id = ?",
        (ext_id,)).fetchone()
    if fila is None:
        return None
    fecha_hora = datetime.strptime(fila["fecha_hora"], "%Y-%m-%d %H:%M")
    leche = TIPOS_LECHE.get(fila["tipo_leche"], "Sin indicar")
    cantidad = formato_ml(fila["cantidad_ml"]) if fila["cantidad_ml"] is not None else "Sin indicar"
    texto = "\n".join([
        f"CENTRO DE LACTANCIA N° 10 - {TIPOS_REGISTRO[fila['tipo']]} N° {fila['id']}",
        f"Madre: {fila['apellido']}, {fila['nombre']}",
        f"Leche: {leche}",
        f"Cantidad: {cantidad}",
        f"Fecha y hora: {fecha_hora:%d/%m/%Y %H:%M}",
    ])
    qr = segno.make(texto, error="m")
    return {
        "id": fila["id"], "madre_id": fila["madre_id"], "madre": f"{fila['apellido']}, {fila['nombre']}",
        "tipo": TIPOS_REGISTRO[fila["tipo"]], "leche": leche, "tipo_leche": fila["tipo_leche"],
        "cantidad": cantidad, "fecha": f"{fecha_hora:%d/%m/%Y}", "hora": f"{fecha_hora:%H:%M}", "texto": texto,
        "svg": qr.svg_inline(border=2, dark="#2b2440", omitsize=True),
    }


def etiqueta_de_madre(ext_id, madre_id):
    e = datos_etiqueta(ext_id) if ext_id else None
    return e if e and e["madre_id"] == madre_id else None


@app.route("/extracciones/<int:ext_id>/etiqueta")
def etiqueta_extraccion(ext_id):
    e = datos_etiqueta(ext_id)
    if e is None:
        abort(404)
    return render_template("etiqueta.html", e=e, imprimir=request.args.get("imprimir") == "1")


@app.route("/madres/<int:madre_id>/alta", methods=["POST"])
def dar_alta(madre_id):
    cargar_madre(madre_id)
    fecha = (request.form.get("fecha_alta") or "").strip()
    try:
        fecha = date.fromisoformat(fecha).isoformat()
    except ValueError:
        flash("Indique una fecha de alta válida.", "error")
        return redirect(url_for("ver", madre_id=madre_id) + "#alta")
    db = get_db()
    db.execute("UPDATE madres SET fecha_alta = ?, alta_observaciones = ? WHERE id = ?",
               (fecha, (request.form.get("alta_observaciones") or "").strip(), madre_id))
    db.commit()
    flash("¡Alta registrada! Ya podés descargar el reconocimiento con la guía de cuidados.")
    return redirect(url_for("ver", madre_id=madre_id) + "#alta")


@app.route("/madres/<int:madre_id>/alta/anular", methods=["POST"])
def anular_alta(madre_id):
    cargar_madre(madre_id)
    db = get_db()
    db.execute("UPDATE madres SET fecha_alta = NULL WHERE id = ?", (madre_id,))
    db.commit()
    flash("Se anuló el alta. La mamá vuelve a figurar como activa.")
    return redirect(url_for("ver", madre_id=madre_id) + "#alta")


@app.route("/madres/<int:madre_id>/alta.pdf")
def alta_pdf(madre_id):
    d = alta.datos_alta(get_db(), madre_id)
    if d is None:
        abort(404)
    m = d["madre"]
    pdf = alta.generar_pdf(d, m["fecha_alta"], m["alta_observaciones"] or "")
    base = unicodedata.normalize("NFKD", f"{m['apellido']}-{m['nombre']}").encode("ascii", "ignore").decode()
    nombre = f"alta-reconocimiento-{base}.pdf".replace(" ", "-")
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@app.route("/extracciones/<int:ext_id>/eliminar", methods=["POST"])
def eliminar_extraccion(ext_id):
    db = get_db()
    fila = db.execute("SELECT madre_id FROM extracciones WHERE id = ?", (ext_id,)).fetchone()
    if fila is None:
        abort(404)
    db.execute("DELETE FROM extracciones WHERE id = ?", (ext_id,))
    db.commit()
    flash("Registro de extracción eliminado.")
    return redirect(url_for("ver", madre_id=fila["madre_id"]) + "#extracciones")


@app.route("/madres/<int:madre_id>/editar", methods=["GET", "POST"])
def editar(madre_id):
    madre_db, padre_db, bebes_db = cargar_madre(madre_id)
    if request.method == "POST":
        madre, padre, bebes, errores = leer_formulario(request.form)
        archivo = request.files.get("consentimiento")
        if validar_consentimiento(archivo):
            errores.append(validar_consentimiento(archivo))
        if not errores:
            try:
                guardar(get_db(), madre_id, madre, padre, bebes)
            except basedatos.ErrorIntegridad:
                deshacer(get_db())
                errores.append("Ya existe otra madre registrada con ese DNI.")
            else:
                guardar_consentimiento(get_db(), madre_id, archivo,
                                       (request.form.get("consentimiento_fecha") or "").strip())
                flash("¡Listo! Guardamos los cambios.")
                return redirect(url_for("ver", madre_id=madre_id))
        for e in errores:
            flash(e, "error")
        madre["id"] = madre_id
        madre["consentimiento_archivo"] = madre_db["consentimiento_archivo"]
        return render_template("formulario.html", madre=madre, padre=padre, bebes=bebes, titulo="Editar madre donante")
    return render_template(
        "formulario.html", madre=dict(madre_db), padre=padre_db and dict(padre_db),
        bebes=[dict(b) for b in bebes_db], titulo="Editar madre donante",
    )


@app.route("/madres/<int:madre_id>/eliminar", methods=["POST"])
def eliminar(madre_id):
    madre, _, _ = cargar_madre(madre_id)
    db = get_db()
    db.execute("DELETE FROM madres WHERE id = ?", (madre_id,))
    db.commit()
    borrar_archivo_consentimiento(madre["consentimiento_archivo"])
    flash("Registro eliminado.")
    return redirect(url_for("listado"))


@app.route("/actividades", methods=["GET", "POST"])
def actividades():
    db = get_db()
    if request.method == "POST":
        f = request.form
        texto = lambda k: (f.get(k) or "").strip()
        tipo = texto("tipo")
        errores = []
        try:
            fecha_hora = datetime.strptime(f"{texto('fecha')} {texto('hora')}", "%Y-%m-%d %H:%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            errores.append("Indique fecha y hora válidas.")
        if tipo not in ACTIVIDADES:
            errores.append("Elija el tipo de actividad.")
        nombre, apellido, material = texto("destinatario_nombre"), texto("destinatario_apellido"), texto("material")
        if tipo == "educacion" and not (nombre and apellido):
            errores.append("En educación, indique nombre y apellido de la persona a quien se dirige.")
        if tipo == "limpieza" and not material:
            errores.append("En limpieza, indique el material utilizado.")
        lugar = texto("lugar")
        if tipo == "salida" and not lugar:
            errores.append("En salidas, indique el lugar o destino.")
        cantidad_ml = frascos = None
        if tipo in ACTIVIDADES_LECHE:
            if not lugar:
                errores.append("Indique la institución " + ("a la que se envió la leche a pasteurizar." if tipo == "envio_leche" else "que devolvió la leche pasteurizada."))
            try:
                cantidad_ml = float(texto("cantidad_ml").replace(",", "."))
                if cantidad_ml <= 0:
                    raise ValueError
            except ValueError:
                errores.append("Indique la cantidad de leche en ml (un número mayor que cero).")
            if texto("frascos"):
                if texto("frascos").isdigit():
                    frascos = int(texto("frascos"))
                else:
                    errores.append("La cantidad de frascos debe ser un número entero.")
        if errores:
            for e in errores:
                flash(e, "error")
        else:
            db.execute(
                "INSERT INTO actividades (fecha_hora, tipo, destinatario_nombre, destinatario_apellido, material, "
                "descripcion, lugar, cantidad_ml, frascos, lote, usuario_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (fecha_hora, tipo,
                 nombre if tipo == "educacion" else None, apellido if tipo == "educacion" else None,
                 material if tipo == "limpieza" else None, texto("descripcion"),
                 lugar if tipo == "salida" or tipo in ACTIVIDADES_LECHE else None,
                 cantidad_ml, frascos, (texto("lote") or None) if tipo in ACTIVIDADES_LECHE else None,
                 usuario_id_actual()),
            )
            db.commit()
            if tipo in ACTIVIDADES_LECHE:
                flash(f"Envío a pasteurizar registrado: {formato_ml(cantidad_ml)} a {lugar}." if tipo == "envio_leche"
                      else f"Recepción de leche pasteurizada registrada: {formato_ml(cantidad_ml)} de {lugar}.")
            else:
                flash(f"Actividad de {ACTIVIDADES[tipo][0].lower()} registrada.")
            return redirect(url_for("actividades"))
        return redirect(url_for("actividades", tipo=tipo))

    filtro = request.args.get("filtro") or ""
    sql, params = "SELECT * FROM actividades", []
    if filtro in ACTIVIDADES:
        sql += " WHERE tipo = ?"
        params.append(filtro)
    lista = db.execute(sql + " ORDER BY fecha_hora DESC, id DESC LIMIT 200", params).fetchall()
    conteo = dict(db.execute("SELECT tipo, COUNT(*) FROM actividades GROUP BY tipo").fetchall())
    mes = datetime.now().strftime("%Y-%m")
    leche_mes = dict(db.execute("SELECT tipo, COALESCE(SUM(cantidad_ml), 0) FROM actividades "
                                "WHERE tipo IN ('envio_leche', 'recepcion_leche') AND substr(fecha_hora, 1, 7) = ? GROUP BY tipo",
                                (mes,)).fetchall())
    # Leche que salió a pasteurizar y todavía no volvió (todo el histórico) e instituciones ya usadas.
    leche_total = dict(db.execute("SELECT tipo, COALESCE(SUM(cantidad_ml), 0) FROM actividades "
                                  "WHERE tipo IN ('envio_leche', 'recepcion_leche') GROUP BY tipo").fetchall())
    en_pasteurizacion = max(leche_total.get("envio_leche", 0) - leche_total.get("recepcion_leche", 0), 0)
    instituciones = [f[0] for f in db.execute(
        "SELECT lugar FROM actividades WHERE tipo IN ('envio_leche', 'recepcion_leche') AND lugar IS NOT NULL "
        "GROUP BY lugar ORDER BY MAX(fecha_hora) DESC LIMIT 20").fetchall()]
    ahora = datetime.now()
    return render_template(
        "actividades.html", actividades=lista, filtro=filtro, conteo=conteo, leche_mes=leche_mes,
        en_pasteurizacion=en_pasteurizacion, instituciones=instituciones,
        tipo_elegido=request.args.get("tipo") or "educacion",
        hoy=ahora.strftime("%Y-%m-%d"), ahora=ahora.strftime("%H:%M"),
    )


@app.route("/actividades/<int:act_id>/eliminar", methods=["POST"])
def eliminar_actividad(act_id):
    db = get_db()
    db.execute("DELETE FROM actividades WHERE id = ?", (act_id,))
    db.commit()
    flash("Actividad eliminada.")
    return redirect(url_for("actividades"))


def es_fortificada(tipo):
    return "fortific" in (tipo or "").lower()


@app.route("/preparaciones", methods=["GET", "POST"])
def preparaciones():
    db = get_db()
    if request.method == "POST":
        f = request.form
        texto = lambda k: (f.get(k) or "").strip()
        errores = []
        try:
            fecha = datetime.strptime(texto("fecha"), "%Y-%m-%d").strftime("%Y-%m-%d")
            hora = datetime.strptime(texto("hora_entrega"), "%H:%M").strftime("%H:%M")
        except ValueError:
            errores.append("Indique la fecha y la hora de entrega.")
        for campo, etiqueta in (("tipo_preparacion", "el tipo de preparación"), ("frecuencia", "la frecuencia"),
                                ("bebe_nombre", "el nombre del bebé"), ("bebe_apellido", "el apellido del bebé")):
            if not texto(campo):
                errores.append(f"Falta {etiqueta}.")
        try:
            dosis = float(texto("dosis_ml").replace(",", "."))
            if not 0 < dosis <= 500:
                raise ValueError
        except ValueError:
            errores.append("La dosis por vez debe ser un número de mililitros (mayor que 0).")
        cantidad = texto("cantidad_dosis")
        if not cantidad.isdigit() or int(cantidad) < 1:
            errores.append("La cantidad de dosis debe ser un número entero mayor que 0.")
        fortificada = es_fortificada(texto("tipo_preparacion"))
        if fortificada and not texto("fortificador"):
            errores.append("Indique el fortificador usado en la leche fortificada.")
        servicio = texto("servicio")
        if servicio not in SERVICIOS:
            errores.append("Indique si el bebé está internado en maternidad o en neonatología.")
        if errores:
            for e in errores:
                flash(e, "error")
            return redirect(url_for("preparaciones"))
        db.execute(
            "INSERT INTO preparaciones (fecha, hora_entrega, tipo_preparacion, dosis_ml, frecuencia, cantidad_dosis, "
            "bebe_nombre, bebe_apellido, servicio, observaciones, fortificador, concentracion, usuario_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (fecha, hora, texto("tipo_preparacion"), dosis, texto("frecuencia"), int(cantidad),
             texto("bebe_nombre"), texto("bebe_apellido"), servicio, texto("observaciones"),
             texto("fortificador") if fortificada else None, texto("concentracion") if fortificada else None,
             usuario_id_actual()),
        )
        db.commit()
        flash("Preparación registrada.")
        return redirect(url_for("preparaciones"))

    filtro = request.args.get("servicio") or ""
    sql, params = "SELECT *, dosis_ml * cantidad_dosis AS total_ml FROM preparaciones", []
    if filtro in SERVICIOS:
        sql += " WHERE servicio = ?"
        params.append(filtro)
    lista = db.execute(sql + " ORDER BY fecha DESC, hora_entrega DESC, id DESC LIMIT 200", params).fetchall()
    hoy = date.today().isoformat()
    resumen = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cantidad_dosis), 0), COALESCE(SUM(dosis_ml * cantidad_dosis), 0) "
        "FROM preparaciones WHERE fecha = ?", (hoy,)
    ).fetchone()
    bebes = db.execute(
        "SELECT DISTINCT nombre, apellido_materno FROM bebes ORDER BY apellido_materno, nombre"
    ).fetchall()
    return render_template(
        "preparaciones.html", preparaciones=lista, filtro=filtro, bebes=bebes,
        resumen={"cantidad": resumen[0], "dosis": resumen[1], "ml": resumen[2]},
        sug_preparacion=SUGERENCIAS_PREPARACION, sug_frecuencia=SUGERENCIAS_FRECUENCIA, tipos_rapidos=TIPOS_RAPIDOS,
        sug_fortificador=SUGERENCIAS_FORTIFICADOR, sug_concentracion=SUGERENCIAS_CONCENTRACION,
        hoy=hoy, ahora=datetime.now().strftime("%H:%M"),
    )


@app.route("/preparaciones/<int:prep_id>/eliminar", methods=["POST"])
def eliminar_preparacion(prep_id):
    db = get_db()
    db.execute("DELETE FROM preparaciones WHERE id = ?", (prep_id,))
    db.commit()
    flash("Preparación eliminada.")
    return redirect(url_for("preparaciones"))


MESES_CORTOS = cierre.MESES_CORTOS
MESES_HISTORIA = cierre.MESES_HISTORIA
MESES_PROYECCION = cierre.MESES_PROYECCION


sumar_meses = cierre.sumar_meses
proyectar = cierre.proyectar


def escala_bonita(maximo):
    """Devuelve (tope, paso) redondeados para el eje vertical."""
    if maximo <= 0:
        return 4, 1
    bruto = maximo / 4
    mag = 10 ** (len(str(int(bruto))) - 1)
    for m in (1, 2, 2.5, 5, 10):
        if m * mag >= bruto:
            paso = m * mag
            break
    tope = paso * -(-maximo // paso)
    return tope, paso


def grafico_proyeccion(titulo, unidad, historia, futuro, etiquetas):
    """Calcula las coordenadas del gráfico SVG (historia sólida + proyección punteada)."""
    ancho, alto = 640, 240
    izq, der, arr, aba = 56, 16, 16, 34
    valores = historia + futuro
    tope, paso = escala_bonita(max(valores) * 1.1 if valores else 0)
    n = len(valores)
    x = lambda i: izq + (ancho - izq - der) * (i + 0.5) / n
    y = lambda v: arr + (alto - arr - aba) * (1 - v / tope)
    puntos = [{"x": round(x(i), 1), "y": round(y(v), 1), "valor": round(v), "mes": etiquetas[i],
               "proyectado": i >= len(historia)} for i, v in enumerate(valores)]
    linea = lambda pts: " ".join(f"{'M' if j == 0 else 'L'}{p['x']},{p['y']}" for j, p in enumerate(pts))
    h = len(historia)
    ultimo_real, ultimo_proy = historia[-1] if historia else 0, futuro[-1] if futuro else 0
    variacion = ((ultimo_proy - ultimo_real) / ultimo_real * 100) if ultimo_real else None
    marcas, v = [], 0
    while v <= tope + 1e-9:
        marcas.append({"y": round(y(v), 1), "texto": f"{v:,.0f}".replace(",", ".")})
        v += paso
    return {
        "titulo": titulo, "unidad": unidad, "ancho": ancho, "alto": alto, "izq": izq, "der": der,
        "puntos": puntos, "marcas": marcas, "base": round(y(0), 1),
        "linea_real": linea(puntos[:h]), "linea_proy": linea(puntos[h - 1:]) if h else "",
        "area_proy_x": round((x(h - 1) + x(h)) / 2, 1) if h else izq,
        "ultimo_real": round(ultimo_real), "ultimo_proy": round(ultimo_proy), "variacion": variacion,
    }


def datos_proyeccion(db):
    hoy = date.today()
    p = cierre.series_proyeccion(db, hoy.year, hoy.month)
    etiquetas = p["etiquetas"]
    iconos = {"extraida": "🍼", "entregada": "🧪", "madres": "🤱"}
    graficos = [grafico_proyeccion(f"{iconos[m['clave']]} {m['titulo']}", m["unidad"], m["historia"], m["futuro"], etiquetas)
                for m in p["metricas"]]
    return {
        "graficos": graficos,
        "desde": etiquetas[0], "hasta": etiquetas[MESES_HISTORIA - 1],
        "proy_desde": etiquetas[MESES_HISTORIA], "proy_hasta": etiquetas[-1],
        "hay_datos": any(p["valor"] for g in graficos for p in g["puntos"][:MESES_HISTORIA]),
    }


def meses_disponibles(db):
    """Meses con algún registro, del más reciente al más antiguo."""
    filas = db.execute(
        "SELECT substr(fecha_registro, 1, 7) FROM madres UNION SELECT substr(fecha_hora, 1, 7) FROM extracciones "
        "UNION SELECT substr(fecha, 1, 7) FROM preparaciones UNION SELECT substr(fecha_hora, 1, 7) FROM actividades "
        "ORDER BY 1 DESC"
    ).fetchall()
    return [f[0] for f in filas if f[0]]


def leer_mes(texto):
    try:
        d = datetime.strptime(texto, "%Y-%m")
    except (TypeError, ValueError):
        return None
    return d.year, d.month


def obtener_cierre(db, anio, mes):
    return cierre.datos_cierre(db, anio, mes, TIPOS_LECHE, SERVICIOS, ACTIVIDADES)


@app.route("/cierre")
def cierre_mensual():
    db = get_db()
    meses = meses_disponibles(db)
    hoy = date.today()
    por_defecto = "%d-%02d" % cierre.mes_anterior(hoy.year, hoy.month)
    elegido = leer_mes(request.args.get("mes") or por_defecto) or cierre.mes_anterior(hoy.year, hoy.month)
    return render_template(
        "cierre.html", c=obtener_cierre(db, *elegido), meses=meses,
        nombre_mes=lambda k: cierre.nombre_mes(*leer_mes(k)), variacion=cierre.variacion,
    )


@app.route("/cierre/<mes>.pdf")
def cierre_pdf(mes):
    elegido = leer_mes(mes)
    if elegido is None:
        abort(404)
    pdf = cierre.generar_pdf(obtener_cierre(get_db(), *elegido))
    nombre = f"cierre-mensual-{elegido[0]}-{elegido[1]:02d}.pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def controles_con_nacimiento(bebe, controles):
    """Controles del bebé, sumando el peso al nacer como primer punto si no hay control ese día."""
    lista = [dict(c) for c in controles]
    try:
        peso_nac = float(bebe["peso_nacimiento"]) if bebe["peso_nacimiento"] else None
    except ValueError:
        peso_nac = None
    if peso_nac and bebe["fecha_nacimiento"] and not any(c["fecha"] == bebe["fecha_nacimiento"] for c in lista):
        lista.insert(0, {"id": None, "fecha": bebe["fecha_nacimiento"], "peso": peso_nac, "talla": None, "pc": None,
                         "observaciones": "Peso al nacer", "nacimiento": True})
    return sorted(lista, key=lambda c: c["fecha"])


def resumen_crecimiento(db, bebes):
    """Último control y percentil de peso de cada bebé, para la ficha de la madre."""
    resumen = {}
    for b in bebes:
        controles = controles_con_nacimiento(b, db.execute(
            "SELECT * FROM controles_bebe WHERE bebe_id = ? ORDER BY fecha", (b["id"],)).fetchall())
        info = crecimiento.datos_bebe(b)
        ultimo = next((c for c in reversed(controles) if c["peso"]), None)
        resumen[b["id"]] = {
            "cantidad": len(controles),
            "ultimo": ultimo,
            "p": crecimiento.calcular(info, "peso", date.fromisoformat(ultimo["fecha"]), ultimo["peso"])
                 if ultimo and info["nacimiento"] else None,
            "info": info,
        }
    return resumen


@app.route("/bebes/<int:bebe_id>/crecimiento")
def crecimiento_bebe(bebe_id):
    db = get_db()
    bebe = db.execute("SELECT * FROM bebes WHERE id = ?", (bebe_id,)).fetchone()
    if bebe is None:
        abort(404)
    madre = db.execute("SELECT * FROM madres WHERE id = ?", (bebe["madre_id"],)).fetchone()
    controles = controles_con_nacimiento(
        bebe, db.execute("SELECT * FROM controles_bebe WHERE bebe_id = ? ORDER BY fecha", (bebe_id,)).fetchall())
    info = crecimiento.datos_bebe(bebe)
    alta = date.fromisoformat(madre["fecha_alta"]) if madre["fecha_alta"] else None
    graficos = [g for g in (crecimiento.grafico(info, controles, m, hasta=alta) for m in crecimiento.MEDIDAS) if g]
    return render_template(
        "crecimiento.html", bebe=bebe, madre=madre, info=info, alta=alta, graficos=graficos,
        filas=list(reversed(crecimiento.tabla_controles(info, controles))) if info["nacimiento"] else
              [dict(c) for c in reversed(controles)],
        faltan=crecimiento.faltantes(info), referencia=crecimiento.referencia(info),
        hoy=date.today().isoformat(), percentiles=crecimiento.PERCENTILES,
        SEXOS=crecimiento.SEXOS, MEDIDAS=crecimiento.MEDIDAS, UNIDADES=crecimiento.UNIDADES,
    )


@app.route("/bebes/<int:bebe_id>/controles", methods=["POST"])
def agregar_control(bebe_id):
    db = get_db()
    bebe = db.execute("SELECT * FROM bebes WHERE id = ?", (bebe_id,)).fetchone()
    if bebe is None:
        abort(404)
    f = request.form
    fecha = (f.get("fecha") or "").strip()
    valores = {}
    errores = []
    try:
        date.fromisoformat(fecha)
    except ValueError:
        errores.append("Indique la fecha del control.")
    if bebe["fecha_nacimiento"] and fecha and fecha < bebe["fecha_nacimiento"]:
        errores.append("La fecha del control es anterior al nacimiento.")
    rangos = {"peso": (300, 9000, "El peso va en gramos"), "talla": (25, 75, "La talla va en centímetros"),
              "pc": (18, 50, "El perímetro cefálico va en centímetros")}
    for campo, (minimo, maximo, mensaje) in rangos.items():
        texto = (f.get(campo) or "").strip().replace(",", ".")
        if not texto:
            valores[campo] = None
            continue
        try:
            valores[campo] = float(texto)
            if not minimo <= valores[campo] <= maximo:
                raise ValueError
        except ValueError:
            errores.append(f"{mensaje} (entre {minimo} y {maximo}).")
    if not errores and not any(valores.values()):
        errores.append("Cargue al menos el peso, la talla o el perímetro cefálico.")
    if errores:
        for e in errores:
            flash(e, "error")
    else:
        # Un control por día: si ya había uno en esa fecha, se reemplaza.
        db.execute(
            "INSERT INTO controles_bebe (bebe_id, fecha, peso, talla, pc, observaciones, usuario_id) VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (bebe_id, fecha) DO UPDATE SET peso = excluded.peso, talla = excluded.talla, "
            "pc = excluded.pc, observaciones = excluded.observaciones, usuario_id = excluded.usuario_id",
            (bebe_id, fecha, valores["peso"], valores["talla"], valores["pc"], (f.get("observaciones") or "").strip(),
             usuario_id_actual()),
        )
        db.commit()
        flash("Control registrado.")
    return redirect(url_for("crecimiento_bebe", bebe_id=bebe_id))


@app.route("/controles/<int:control_id>/eliminar", methods=["POST"])
def eliminar_control(control_id):
    db = get_db()
    fila = db.execute("SELECT bebe_id FROM controles_bebe WHERE id = ?", (control_id,)).fetchone()
    if fila is None:
        abort(404)
    db.execute("DELETE FROM controles_bebe WHERE id = ?", (control_id,))
    db.commit()
    flash("Control eliminado.")
    return redirect(url_for("crecimiento_bebe", bebe_id=fila["bebe_id"]))


def leche_por_tipo(db):
    """Registros y ml por tipo de leche, separados en mes en curso y año actual (el año se reinicia cada 1/1)."""
    hoy = date.today()
    periodos = {"mes": hoy.strftime("%Y-%m"), "anio": str(hoy.year)}
    filas = {k: {"clave": k, "mes": {"total": 0, "ml": 0}, "anio": {"total": 0, "ml": 0}} for k in TIPOS_LECHE}
    total = {"mes": {"total": 0, "ml": 0}, "anio": {"total": 0, "ml": 0}}
    for periodo, prefijo in periodos.items():
        for r in db.execute(
            "SELECT tipo_leche, COUNT(*), COALESCE(SUM(cantidad_ml), 0) FROM extracciones "
            "WHERE tipo_leche IS NOT NULL AND substr(fecha_hora, 1, ?) = ? GROUP BY tipo_leche",
            (len(prefijo), prefijo),
        ):
            if r[0] in filas:
                filas[r[0]][periodo] = {"total": r[1], "ml": r[2]}
                total[periodo]["total"] += r[1]
                total[periodo]["ml"] += r[2]
    for f in filas.values():
        for periodo in periodos:
            ml_total = total[periodo]["ml"]
            f[periodo]["pct"] = round(f[periodo]["ml"] * 100 / ml_total) if ml_total else 0
    return {"filas": list(filas.values()), "total": total,
            "nombre_mes": cierre.MESES[hoy.month - 1], "anio": hoy.year}


@app.route("/estadisticas")
def estadisticas():
    db = get_db()
    contar = lambda sql, p=(): db.execute(sql, p).fetchone()[0]
    agrupar = lambda col: db.execute(
        f"SELECT COALESCE(NULLIF({col}, ''), 'Sin dato') AS clave, COUNT(*) AS total "
        f"FROM madres GROUP BY clave ORDER BY total DESC"
    ).fetchall()
    datos = {
        "total": contar("SELECT COUNT(*) FROM madres"),
        "internadas": contar("SELECT COUNT(*) FROM madres WHERE situacion = 'internada'"),
        "domicilio": contar("SELECT COUNT(*) FROM madres WHERE situacion = 'domicilio'"),
        "donantes": contar("SELECT COUNT(*) FROM madres WHERE modalidad = 'donante'"),
        "solo_extraccion": contar("SELECT COUNT(*) FROM madres WHERE modalidad = 'extraccion'"),
        "conjunta": contar("SELECT COUNT(*) FROM madres WHERE tipo_internacion = 'conjunta'"),
        "neonatologia": contar("SELECT COUNT(*) FROM madres WHERE tipo_internacion = 'neonatologia'"),
        "bebes": contar("SELECT COUNT(*) FROM bebes"),
        "padres": contar("SELECT COUNT(*) FROM padres"),
        "padres_conviven": contar("SELECT COUNT(*) FROM padres WHERE convive = 1"),
        "edad_padres": db.execute("SELECT ROUND(AVG(edad), 1) FROM padres WHERE edad IS NOT NULL").fetchone()[0],
        "por_barrio": agrupar("barrio"),
        "por_localidad": agrupar("localidad"),
        "extracciones": contar("SELECT COUNT(*) FROM extracciones WHERE tipo = 'extraccion'"),
        "estimulos": contar("SELECT COUNT(*) FROM extracciones WHERE tipo = 'estimulo'"),
        "total_ml": contar("SELECT COALESCE(SUM(cantidad_ml), 0) FROM extracciones"),
        "promedio_ml": db.execute(
            "SELECT ROUND(AVG(cantidad_ml), 1) FROM extracciones WHERE tipo = 'extraccion' AND cantidad_ml IS NOT NULL"
        ).fetchone()[0],
        "por_leche": leche_por_tipo(db),
        "ml_por_mes": db.execute(
            "SELECT substr(fecha_hora, 1, 7) AS mes, COALESCE(SUM(cantidad_ml), 0) AS total FROM extracciones "
            "GROUP BY mes ORDER BY mes DESC LIMIT 12"
        ).fetchall(),
        "actividades": dict(db.execute("SELECT tipo, COUNT(*) FROM actividades GROUP BY tipo").fetchall()),
        "actividades_mes": contar(
            "SELECT COUNT(*) FROM actividades WHERE substr(fecha_hora, 1, 7) = ?", (date.today().strftime("%Y-%m"),)
        ),
        "madres_riesgo": contar("SELECT COUNT(*) FROM madres WHERE COALESCE(factores_riesgo, '') <> ''"),
        "madres_cronicas": contar("SELECT COUNT(*) FROM madres WHERE COALESCE(patologias_cronicas, '') <> ''"),
        "bebes_riesgo": contar("SELECT COUNT(*) FROM bebes WHERE COALESCE(factores_riesgo, '') <> ''"),
        "bebes_cronicas": contar("SELECT COUNT(*) FROM bebes WHERE COALESCE(patologias_cronicas, '') <> ''"),
        "preparaciones": contar("SELECT COUNT(*) FROM preparaciones"),
        "prep_dosis": contar("SELECT COALESCE(SUM(cantidad_dosis), 0) FROM preparaciones"),
        "prep_ml": contar("SELECT COALESCE(SUM(dosis_ml * cantidad_dosis), 0) FROM preparaciones"),
        "prep_formula": contar("SELECT COUNT(*) FROM preparaciones WHERE lower(tipo_preparacion) LIKE '%rmula%'"),
        "prep_fortificadas": contar("SELECT COUNT(*) FROM preparaciones WHERE lower(tipo_preparacion) LIKE '%fortific%'"),
        "prep_bebes": contar("SELECT COUNT(DISTINCT lower(bebe_nombre || ' ' || bebe_apellido)) FROM preparaciones"),
        "prep_servicio": dict(db.execute("SELECT servicio, COUNT(*) FROM preparaciones GROUP BY servicio").fetchall()),
        "prep_tipo": db.execute(
            "SELECT MIN(tipo_preparacion) AS clave, COUNT(*) AS total, SUM(dosis_ml * cantidad_dosis) AS ml "
            "FROM preparaciones GROUP BY lower(tipo_preparacion) ORDER BY total DESC"
        ).fetchall(),
        "por_mes": db.execute(
            "SELECT substr(fecha_registro, 1, 7) AS mes, COUNT(*) AS total FROM madres GROUP BY mes ORDER BY mes DESC LIMIT 12"
        ).fetchall(),
    }
    riesgo = db.execute(
        """SELECT m.id, m.apellido, m.nombre, m.direccion, m.barrio, m.localidad, m.telefono,
                  m.factores_riesgo AS riesgo_madre,
                  (SELECT group_concat(b.nombre || ' ' || b.apellido_materno || ': ' || b.factores_riesgo, ' | ')
                     FROM bebes b WHERE b.madre_id = m.id AND COALESCE(b.factores_riesgo, '') <> '') AS riesgo_bebes
             FROM madres m
            WHERE COALESCE(m.factores_riesgo, '') <> ''
               OR EXISTS (SELECT 1 FROM bebes b WHERE b.madre_id = m.id AND COALESCE(b.factores_riesgo, '') <> '')
            ORDER BY m.apellido, m.nombre"""
    ).fetchall()
    return render_template("estadisticas.html", d=datos, proy=datos_proyeccion(db), riesgo=riesgo)


init_db()

if __name__ == "__main__":
    puerto = int(os.environ.get("PORT", 5000))
    print(f"CENLAC funcionando. Base de datos: {basedatos.descripcion()}. Consentimientos: {archivos.descripcion()}.")
    if os.environ.get("EN_INTERNET") != "1":
        print(f"En esta PC: http://localhost:{puerto}  ·  Para instalar en otros equipos: http://localhost:{puerto}/instalar")
        print("No cierre esta ventana mientras se use la aplicación.")
    try:
        from waitress import serve  # servidor recomendado para uso diario (varias PC y celulares a la vez)
        serve(app, host="0.0.0.0", port=puerto, threads=8)
    except ImportError:
        app.run(host="0.0.0.0", port=puerto, debug=False)
