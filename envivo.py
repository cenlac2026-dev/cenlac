"""CENLAC en vivo: las pantallas abiertas por los distintos usuarios se actualizan solas.

Cada cambio que alguien guarda (alta de madre, extracción, preparación, etc.) queda anotado en la
tabla "novedades". Los navegadores preguntan cada pocos segundos si hay novedades nuevas
(/novedades?desde=N): si las hay, muestran quién hizo el cambio y actualizan la pantalla.
Además se registra quién está conectado (tabla "presencia").
Funciona igual con SQLite en la PC del centro y con Postgres de Supabase.
"""
from datetime import datetime, timedelta

from flask import Blueprint, g, jsonify, request, session, url_for

ESQUEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS novedades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    momento TEXT NOT NULL,
    usuario_id INTEGER,
    accion TEXT NOT NULL,
    enlace TEXT
);
CREATE TABLE IF NOT EXISTS presencia (
    usuario_id INTEGER PRIMARY KEY,
    visto TEXT NOT NULL
);
"""

# Qué se anota según la pantalla donde se guardó: (texto, ícono, a dónde lleva el aviso)
ACCIONES = {
    "nueva": ("registró a la mamá {madre}", "🤱", "ver"),
    "editar": ("actualizó los datos de {madre}", "✏️", "ver"),
    "eliminar": ("eliminó el registro de una madre", "🗑️", None),
    "nueva_extraccion": ("registró una extracción de {madre}", "🍼", "ver"),
    "eliminar_extraccion": ("quitó una extracción", "🍼", None),
    "subir_consentimiento": ("cargó el consentimiento de {madre}", "📝", "ver"),
    "eliminar_consentimiento": ("quitó el consentimiento de {madre}", "📝", "ver"),
    "dar_alta": ("dio el alta a {madre}", "🎓", "ver"),
    "anular_alta": ("anuló el alta de {madre}", "🎓", "ver"),
    "actividades": ("registró {detalle}", "🌼", "actividades"),
    "eliminar_actividad": ("quitó una actividad", "🌼", "actividades"),
    "preparaciones": ("registró {detalle}", "🧪", "preparaciones"),
    "eliminar_preparacion": ("quitó una preparación", "🧪", "preparaciones"),
    "agregar_control": ("cargó un control de crecimiento de {bebe}", "📈", "crecimiento_bebe"),
    "eliminar_control": ("quitó un control de crecimiento", "📈", None),
    "usuarios.guardar": ("creó un usuario", "👥", None),
    "usuarios.cambiar": ("modificó un usuario", "👥", None),
}
TIPOS_ACTIVIDAD = {"educacion": "una actividad de educación", "limpieza": "una limpieza del sector",
                   "difusion": "una actividad de difusión", "carteleria": "una actividad de cartelería",
                   "salida": "una salida"}
CONECTADO_SEGUNDOS = 45
GUARDAR_DIAS = 60

bp = Blueprint("envivo", __name__)
_get_db = None


def iniciar(app, get_db):
    global _get_db
    _get_db = get_db
    app.register_blueprint(bp)
    app.after_request(anotar_cambio)
    app.context_processor(lambda: {"ultima_novedad": ultima_novedad() if g.get("usuario") else 0})


def ahora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ultima_novedad():
    try:
        return _get_db().execute("SELECT COALESCE(MAX(id), 0) FROM novedades").fetchone()[0]
    except Exception:  # base recién creada, antes de init_db
        return 0


def _hubo_error():
    return any(categoria == "error" for categoria, _ in session.get("_flashes", []))


def anotar_cambio(respuesta):
    """Después de cada cambio guardado con éxito, deja la novedad para los demás usuarios."""
    try:
        return _anotar(respuesta)
    except Exception:  # el aviso en vivo nunca debe impedir guardar
        from flask import current_app
        current_app.logger.exception("No se pudo anotar la novedad")
        return respuesta


def _anotar(respuesta):
    accion = ACCIONES.get(request.endpoint)
    if (request.method != "POST" or accion is None or respuesta.status_code not in (302, 303)
            or not g.get("usuario") or _hubo_error()):
        return respuesta
    texto, icono, destino = accion
    db = _get_db()
    args = dict(request.view_args or {})
    madre_id = args.get("madre_id")
    if request.endpoint == "nueva":  # el id nuevo está en la dirección a la que se redirige
        try:
            madre_id = int(respuesta.location.rstrip("/").split("/madres/")[1].split("?")[0].split("#")[0])
        except (IndexError, ValueError):
            madre_id = None
    madre = bebe = ""
    if madre_id:
        fila = db.execute("SELECT nombre, apellido FROM madres WHERE id = ?", (madre_id,)).fetchone()
        madre = f"{fila[0]} {fila[1]}" if fila else "una madre"
    if args.get("bebe_id"):
        fila = db.execute("SELECT nombre FROM bebes WHERE id = ?", (args["bebe_id"],)).fetchone()
        bebe = fila[0] if fila else "un bebé"
    detalle = ""
    if request.endpoint == "actividades":
        detalle = TIPOS_ACTIVIDAD.get(request.form.get("tipo"), "una actividad")
    elif request.endpoint == "preparaciones":
        tipo, bebe_prep = (request.form.get("tipo_preparacion") or "").strip(), (request.form.get("bebe_nombre") or "").strip()
        detalle = "una preparación" + (f" de {tipo.lower()}" if tipo else "") + (f" para {bebe_prep}" if bebe_prep else "")
    enlace = None
    if destino == "ver" and madre_id:
        enlace = url_for("ver", madre_id=madre_id)
    elif destino == "crecimiento_bebe" and args.get("bebe_id"):
        enlace = url_for("crecimiento_bebe", bebe_id=args["bebe_id"])
    elif destino in ("actividades", "preparaciones"):
        enlace = url_for(destino)
    db.execute("INSERT INTO novedades (momento, usuario_id, accion, enlace) VALUES (?, ?, ?, ?)",
               (ahora(), g.usuario["id"], f"{icono} " + texto.format(madre=madre or "una madre", bebe=bebe or "un bebé", detalle=detalle),
                enlace))
    # Se guardan solo las novedades de los últimos 60 días.
    db.execute("DELETE FROM novedades WHERE momento < ?",
               ((datetime.now() - timedelta(days=GUARDAR_DIAS)).strftime("%Y-%m-%d %H:%M:%S"),))
    db.commit()
    return respuesta


def _hace(momento):
    try:
        seg = int((datetime.now() - datetime.strptime(momento, "%Y-%m-%d %H:%M:%S")).total_seconds())
    except ValueError:
        return ""
    if seg < 60:
        return "recién"
    if seg < 3600:
        return f"hace {seg // 60} min"
    if seg < 86400:
        return f"hace {seg // 3600} h"
    return datetime.strptime(momento, "%Y-%m-%d %H:%M:%S").strftime("%d/%m %H:%M")


@bp.route("/novedades")
def novedades():
    """Novedades posteriores a 'desde' y usuarios conectados. Lo consultan los navegadores cada pocos segundos."""
    from usuarios import puede

    db = _get_db()
    yo = g.usuario["id"]
    db.execute("INSERT INTO presencia (usuario_id, visto) VALUES (?, ?) "
               "ON CONFLICT (usuario_id) DO UPDATE SET visto = excluded.visto", (yo, ahora()))
    db.commit()
    try:
        desde = int(request.args.get("desde", ""))
        filas = db.execute("""SELECT n.id, n.momento, n.accion, n.enlace, n.usuario_id, u.nombre
                                FROM novedades n LEFT JOIN usuarios u ON u.id = n.usuario_id
                               WHERE n.id > ? ORDER BY n.id DESC LIMIT 20""", (desde,)).fetchall()
    except ValueError:  # sin 'desde': las últimas 15, para el panel de últimos cambios
        filas = db.execute("""SELECT n.id, n.momento, n.accion, n.enlace, n.usuario_id, u.nombre
                                FROM novedades n LEFT JOIN usuarios u ON u.id = n.usuario_id
                               ORDER BY n.id DESC LIMIT 15""").fetchall()
    limite = (datetime.now() - timedelta(seconds=CONECTADO_SEGUNDOS)).strftime("%Y-%m-%d %H:%M:%S")
    conectados = [f[0] for f in db.execute(
        "SELECT u.nombre FROM presencia p JOIN usuarios u ON u.id = p.usuario_id "
        "WHERE p.visto >= ? AND u.activo = 1 ORDER BY u.nombre", (limite,))]
    ver_enlaces = puede("completo")
    return jsonify({
        "ultimo": ultima_novedad(),
        "conectados": conectados,
        "novedades": [{
            "id": f[0], "hace": _hace(f[1]), "texto": f[2], "quien": f[5] or "Alguien",
            "enlace": f[3] if ver_enlaces else None, "mio": f[4] == yo,
        } for f in filas],
    })
