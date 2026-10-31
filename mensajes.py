"""Mensajes del equipo: un espacio arriba del listado de madres para dejar avisos entre agentes, jefes y administradores.

- Un mensaje fijado (📌) dura 36 horas; uno sin fijar, 18 horas. Después se borra solo.
- Cada mensaje publicado queda registrado como actividad de Difusión (Otras actividades), con su texto.
- Lo puede publicar cualquier perfil que carga datos (no el perfil Consulta). Quien lo escribió, un Jefe o el
  Administrador pueden fijarlo, desfijarlo o borrarlo antes de tiempo.
"""
from datetime import datetime, timedelta

from flask import Blueprint, flash, g, redirect, request, url_for

ESQUEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creado TEXT NOT NULL,
    usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    texto TEXT NOT NULL,
    fijado INTEGER NOT NULL DEFAULT 0
);
"""
HORAS_FIJADO = 36
HORAS_SIN_FIJAR = 18
MAX_CARACTERES = 500
FORMATO = "%Y-%m-%d %H:%M:%S"

bp = Blueprint("mensajes", __name__)
_get_db = None
_usuario_id_actual = None


def iniciar(app, get_db, usuario_id_actual):
    global _get_db, _usuario_id_actual
    _get_db, _usuario_id_actual = get_db, usuario_id_actual
    app.register_blueprint(bp)


def _vence(creado, fijado):
    return datetime.strptime(creado, FORMATO) + timedelta(hours=HORAS_FIJADO if fijado else HORAS_SIN_FIJAR)


def borrar_vencidos(db):
    """Los fijados se borran a las 36 h de publicados y los demás a las 18 h."""
    ahora = datetime.now()
    db.execute("DELETE FROM mensajes WHERE (fijado = 1 AND creado < ?) OR (fijado = 0 AND creado < ?)",
               ((ahora - timedelta(hours=HORAS_FIJADO)).strftime(FORMATO),
                (ahora - timedelta(hours=HORAS_SIN_FIJAR)).strftime(FORMATO)))
    db.commit()


def _resta(vence):
    seg = int((vence - datetime.now()).total_seconds())
    if seg <= 0:
        return "a punto de borrarse"
    h, m = seg // 3600, (seg % 3600) // 60
    return f"se borra en {h} h {m:02d} min" if h else f"se borra en {m} min"


def puede_manejar(mensaje):
    u = g.get("usuario")
    return bool(u) and (u["rol"] in ("admin", "jefe") or mensaje["usuario_id"] == u["id"])


def vigentes(db):
    """Mensajes que todavía no vencieron: primero los fijados, después los más nuevos."""
    borrar_vencidos(db)
    filas = db.execute(
        "SELECT ms.id, ms.creado, ms.texto, ms.fijado, ms.usuario_id, u.nombre, u.rol FROM mensajes ms "
        "LEFT JOIN usuarios u ON u.id = ms.usuario_id ORDER BY ms.fijado DESC, ms.creado DESC, ms.id DESC").fetchall()
    lista = []
    for f in filas:
        creado = datetime.strptime(f["creado"], FORMATO)
        lista.append({"id": f["id"], "texto": f["texto"], "fijado": bool(f["fijado"]), "autor": f["nombre"] or "Alguien",
                      "rol": f["rol"], "usuario_id": f["usuario_id"], "creado": creado,
                      "resta": _resta(_vence(f["creado"], f["fijado"])), "puede": puede_manejar(f)})
    return lista


def _volver():
    return redirect(url_for("listado") + "#mensajes")


@bp.route("/mensajes", methods=["POST"])
def publicar():
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        flash("Escriba el mensaje antes de publicarlo.", "error")
        return _volver()
    if len(texto) > MAX_CARACTERES:
        flash(f"El mensaje puede tener hasta {MAX_CARACTERES} caracteres.", "error")
        return _volver()
    fijado = 1 if request.form.get("fijado") else 0
    ahora = datetime.now()
    db = _get_db()
    db.execute("INSERT INTO mensajes (creado, usuario_id, texto, fijado) VALUES (?, ?, ?, ?)",
               (ahora.strftime(FORMATO), _usuario_id_actual(), texto, fijado))
    # Cada aporte cuenta como actividad de Difusión (queda aunque el mensaje se borre).
    db.execute("INSERT INTO actividades (fecha_hora, tipo, descripcion, lugar, usuario_id) VALUES (?, 'difusion', ?, ?, ?)",
               (ahora.strftime("%Y-%m-%d %H:%M"), texto, "Mensajes del equipo (CENLAC)", _usuario_id_actual()))
    db.commit()
    flash("Mensaje publicado" + (" y fijado por 36 horas" if fijado else " por 18 horas")
          + ". Quedó registrado como actividad de difusión.")
    return _volver()


def _cargar(mensaje_id):
    db = _get_db()
    fila = db.execute("SELECT * FROM mensajes WHERE id = ?", (mensaje_id,)).fetchone()
    if fila is None:
        flash("Ese mensaje ya no existe (puede haberse borrado solo).", "error")
        return db, None
    if not puede_manejar(fila):
        flash("Solo quien lo escribió, un Jefe o el Administrador pueden cambiar este mensaje.", "error")
        return db, None
    return db, fila


@bp.route("/mensajes/<int:mensaje_id>/fijar", methods=["POST"])
def fijar(mensaje_id):
    db, fila = _cargar(mensaje_id)
    if fila is not None:
        nuevo = 0 if fila["fijado"] else 1
        db.execute("UPDATE mensajes SET fijado = ? WHERE id = ?", (nuevo, mensaje_id))
        db.commit()
        borrar_vencidos(db)
        flash("Mensaje fijado: dura 36 horas desde que se publicó." if nuevo
              else "Mensaje desfijado: dura 18 horas desde que se publicó.")
    return _volver()


@bp.route("/mensajes/<int:mensaje_id>/eliminar", methods=["POST"])
def eliminar(mensaje_id):
    db, fila = _cargar(mensaje_id)
    if fila is not None:
        db.execute("DELETE FROM mensajes WHERE id = ?", (mensaje_id,))
        db.commit()
        flash("Mensaje borrado. La actividad de difusión registrada se conserva.")
    return _volver()
