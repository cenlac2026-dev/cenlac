"""Usuarios, ingreso con contraseña y permisos por perfil.

Perfiles:
- Administrador: todas las funciones, incluida la gestión de usuarios y la impresión del cierre mensual.
- Jefe: todas las funciones salvo el Cierre mensual (no lo ve) y la gestión de usuarios.
- Agente: registra y consulta madres, bebés, extracciones, preparaciones y actividades;
  no ve Estadísticas ni Cierre mensual.
- Consulta: vista mini (widget de escritorio) con información básica de las madres activas,
  sin datos personales ni de salud, y no puede modificar nada.
"""
import hmac
import os
import threading
import time
from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

ROLES = {
    "admin": "Administrador",
    "jefe": "Jefe",
    "agente": "Agente",
    "consulta": "Consulta",
}
DESCRIPCION_ROLES = {
    "admin": "Acceso a todas las funciones, gestión de usuarios e impresión del cierre mensual.",
    "jefe": "Acceso a todas las funciones, sin Cierre mensual ni gestión de usuarios.",
    "agente": "Carga y consulta de madres, bebés, extracciones, preparaciones y actividades. Sin Estadísticas ni Cierre mensual.",
    "consulta": "Vista mini para el escritorio de la PC con información básica de las madres activas, sin datos personales ni de salud. No puede modificar nada.",
}
PERMISOS = {
    "admin": {"basico", "completo", "editar", "eliminar", "estadisticas", "cierre", "cierre_imprimir", "usuarios"},
    "jefe": {"basico", "completo", "editar", "eliminar", "estadisticas"},
    "agente": {"basico", "completo", "editar"},
    "consulta": {"basico"},
}
# Permiso que pide cada pantalla. Lo que no figura acá pide "completo" para ver y "editar" para guardar.
PERMISO_PANTALLA = {
    "listado": "basico",
    "ver": "basico",
    "widget": "basico",
    "instalar": "basico",
    "envivo.novedades": "basico",
    "widget_acceso_directo": "basico",
    "usuarios.mi_clave": "basico",
    "nueva": "editar",
    "editar": "editar",
    "eliminar": "eliminar",
    "estadisticas": "estadisticas",
    "cierre_mensual": "cierre",
    "cierre_pdf": "cierre_imprimir",
    "usuarios.lista": "usuarios",
    "usuarios.guardar": "usuarios",
    "usuarios.cambiar": "usuarios",
}
LIBRES = {"static", "favicon", "service_worker", "usuarios.ingresar", "usuarios.configurar", "usuarios.salir"}
DURACION_SESION = timedelta(hours=12)

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('admin', 'jefe', 'agente', 'consulta')),
    clave_hash TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL,
    ultimo_ingreso TEXT
);
"""

bp = Blueprint("usuarios", __name__)
_get_db = None


def iniciar(app, get_db):
    """Conecta el control de acceso a la aplicación."""
    global _get_db
    _get_db = get_db
    app.register_blueprint(bp)
    app.permanent_session_lifetime = DURACION_SESION
    app.before_request(controlar_acceso)
    app.after_request(no_indexar)
    app.context_processor(lambda: {"usuario_actual": g.get("usuario"), "puede": puede, "ROLES": ROLES})


# Publicada en internet: el primer Administrador solo se puede crear con el código de alta
# (variable CODIGO_ALTA, que se carga en Render). Así nadie más puede adueñarse de la app.
EN_INTERNET = os.environ.get("EN_INTERNET") == "1"
CODIGO_ALTA = os.environ.get("CODIGO_ALTA", "").strip()

# Freno a quien prueba contraseñas: 5 intentos fallidos en 15 minutos bloquean ese usuario y esa conexión.
MAX_FALLOS = 5
VENTANA_FALLOS = 15 * 60
_fallos = {}
_fallos_lock = threading.Lock()


def _claves_fallo(usuario=""):
    claves = ["ip:" + (request.remote_addr or "?")]
    if usuario:
        claves.append("u:" + usuario.lower())
    return claves


def bloqueado(usuario=""):
    limite = time.time() - VENTANA_FALLOS
    with _fallos_lock:
        for clave in _claves_fallo(usuario):
            _fallos[clave] = [t for t in _fallos.get(clave, []) if t > limite]
            if len(_fallos[clave]) >= MAX_FALLOS:
                return True
    return False


def anotar_fallo(usuario=""):
    with _fallos_lock:
        for clave in _claves_fallo(usuario):
            _fallos.setdefault(clave, []).append(time.time())


def olvidar_fallos(usuario=""):
    with _fallos_lock:
        for clave in _claves_fallo(usuario):
            _fallos.pop(clave, None)


def no_indexar(respuesta):
    """Que los buscadores (Google, etc.) no muestren ninguna página de la app."""
    respuesta.headers["X-Robots-Tag"] = "noindex, nofollow"
    return respuesta


def puede(permiso):
    u = g.get("usuario")
    return bool(u) and permiso in PERMISOS.get(u["rol"], set())


def hay_usuarios():
    return _get_db().execute("SELECT 1 FROM usuarios LIMIT 1").fetchone() is not None


def controlar_acceso():
    g.usuario = None
    if session.get("usuario_id"):
        g.usuario = _get_db().execute("SELECT * FROM usuarios WHERE id = ? AND activo = 1",
                                      (session["usuario_id"],)).fetchone()
        if g.usuario is None:
            session.clear()
    if request.endpoint in LIBRES:
        return None
    if g.usuario is None:
        if not hay_usuarios():
            return redirect(url_for("usuarios.configurar"))
        return redirect(url_for("usuarios.ingresar", siguiente=request.full_path if request.method == "GET" else None))
    permiso = PERMISO_PANTALLA.get(request.endpoint, "editar" if request.method == "POST" else "completo")
    if not puede(permiso):
        abort(403)
    return None


def validar_clave(clave, repetir):
    if len(clave) < 6:
        return "La contraseña debe tener al menos 6 caracteres."
    if clave != repetir:
        return "Las contraseñas no coinciden."
    return None


@bp.route("/configurar", methods=["GET", "POST"])
def configurar():
    """Primer inicio: se crea el usuario administrador."""
    if hay_usuarios():
        return redirect(url_for("usuarios.ingresar"))
    sin_codigo = EN_INTERNET and not CODIGO_ALTA
    if request.method == "POST" and not sin_codigo:
        f = request.form
        usuario, nombre = (f.get("usuario") or "").strip(), (f.get("nombre") or "").strip()
        error = validar_clave(f.get("clave") or "", f.get("repetir") or "")
        if not usuario or not nombre:
            error = "Complete el usuario y el nombre."
        if CODIGO_ALTA:
            if bloqueado():
                error = "Demasiados intentos. Espere 15 minutos y vuelva a probar."
            elif not hmac.compare_digest((f.get("codigo") or "").strip().encode(), CODIGO_ALTA.encode()):
                anotar_fallo()
                error = "El código de alta no es correcto."
        if error:
            flash(error, "error")
        else:
            db = _get_db()
            cur = db.execute("INSERT INTO usuarios (usuario, nombre, rol, clave_hash, creado) VALUES (?, ?, 'admin', ?, ?)",
                             (usuario, nombre, generate_password_hash(f["clave"]), datetime.now().strftime("%Y-%m-%d %H:%M")))
            db.commit()
            session.clear()
            session.permanent = True
            session["usuario_id"] = cur.lastrowid
            flash("¡Bienvenida/o! Se creó el usuario administrador. Desde Usuarios puede crear las cuentas del equipo.")
            return redirect(url_for("listado"))
    return render_template("configurar.html", sin_codigo=sin_codigo, pide_codigo=bool(CODIGO_ALTA))


@bp.route("/ingresar", methods=["GET", "POST"])
def ingresar():
    if not hay_usuarios():
        return redirect(url_for("usuarios.configurar"))
    if request.method == "POST":
        usuario = (request.form.get("usuario") or "").strip()
        if bloqueado(usuario):
            flash("Demasiados intentos fallidos. Espere 15 minutos y vuelva a probar, o pida ayuda al Administrador.", "error")
            return render_template("ingresar.html"), 429
        fila = _get_db().execute("SELECT * FROM usuarios WHERE lower(usuario) = lower(?)", (usuario,)).fetchone()
        if fila and fila["activo"] and check_password_hash(fila["clave_hash"], request.form.get("clave") or ""):
            olvidar_fallos(usuario)
            session.clear()
            session.permanent = True
            session["usuario_id"] = fila["id"]
            db = _get_db()
            db.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE id = ?",
                       (datetime.now().strftime("%Y-%m-%d %H:%M"), fila["id"]))
            db.commit()
            siguiente = request.args.get("siguiente") or ""
            # Solo se redirige a direcciones internas de la app.
            if not siguiente.startswith("/") or siguiente.startswith("//"):
                siguiente = url_for("listado")
            return redirect(siguiente)
        anotar_fallo(usuario)
        flash("Usuario o contraseña incorrectos, o el usuario está desactivado.", "error")
    return render_template("ingresar.html")


@bp.route("/salir")
def salir():
    session.clear()
    flash("Sesión cerrada. ¡Hasta pronto!")
    return redirect(url_for("usuarios.ingresar"))


@bp.route("/mi-clave", methods=["GET", "POST"])
def mi_clave():
    if request.method == "POST":
        f = request.form
        error = validar_clave(f.get("clave") or "", f.get("repetir") or "")
        if not check_password_hash(g.usuario["clave_hash"], f.get("actual") or ""):
            error = "La contraseña actual no es correcta."
        if error:
            flash(error, "error")
        else:
            db = _get_db()
            db.execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?",
                       (generate_password_hash(f["clave"]), g.usuario["id"]))
            db.commit()
            flash("Contraseña cambiada.")
            return redirect(url_for("listado"))
    return render_template("mi_clave.html")


@bp.route("/usuarios")
def lista():
    filas = _get_db().execute("SELECT * FROM usuarios ORDER BY activo DESC, rol, nombre").fetchall()
    return render_template("usuarios.html", usuarios=filas, DESCRIPCION_ROLES=DESCRIPCION_ROLES)


def _admins_activos(db, excepto=None):
    return db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1 AND id <> ?",
                      (excepto or 0,)).fetchone()[0]


@bp.route("/usuarios", methods=["POST"])
def guardar():
    f = request.form
    usuario, nombre, rol = (f.get("usuario") or "").strip(), (f.get("nombre") or "").strip(), f.get("rol") or ""
    error = validar_clave(f.get("clave") or "", f.get("repetir") or "")
    if not usuario or not nombre:
        error = "Complete el usuario y el nombre."
    elif rol not in ROLES:
        error = "Elija el perfil del usuario."
    db = _get_db()
    if not error and db.execute("SELECT 1 FROM usuarios WHERE lower(usuario) = lower(?)", (usuario,)).fetchone():
        error = "Ya existe un usuario con ese nombre de usuario."
    if error:
        flash(error, "error")
    else:
        db.execute("INSERT INTO usuarios (usuario, nombre, rol, clave_hash, creado) VALUES (?, ?, ?, ?, ?)",
                   (usuario, nombre, rol, generate_password_hash(f["clave"]), datetime.now().strftime("%Y-%m-%d %H:%M")))
        db.commit()
        flash(f"Usuario {usuario} creado con perfil {ROLES[rol]}.")
    return redirect(url_for("usuarios.lista"))


@bp.route("/usuarios/<int:usuario_id>", methods=["POST"])
def cambiar(usuario_id):
    """Cambia el perfil, activa o desactiva, o asigna una contraseña nueva."""
    db = _get_db()
    u = db.execute("SELECT * FROM usuarios WHERE id = ?", (usuario_id,)).fetchone()
    if u is None:
        abort(404)
    f = request.form
    accion = f.get("accion")
    if accion == "rol":
        rol = f.get("rol")
        if rol not in ROLES:
            flash("Perfil no válido.", "error")
        elif u["rol"] == "admin" and rol != "admin" and not _admins_activos(db, excepto=usuario_id):
            flash("Tiene que quedar al menos un administrador activo.", "error")
        else:
            db.execute("UPDATE usuarios SET rol = ? WHERE id = ?", (rol, usuario_id))
            flash(f"{u['nombre']} ahora tiene perfil {ROLES[rol]}.")
    elif accion == "activo":
        activo = 0 if u["activo"] else 1
        if not activo and u["rol"] == "admin" and not _admins_activos(db, excepto=usuario_id):
            flash("Tiene que quedar al menos un administrador activo.", "error")
        else:
            db.execute("UPDATE usuarios SET activo = ? WHERE id = ?", (activo, usuario_id))
            flash(f"Usuario {u['usuario']} {'activado' if activo else 'desactivado'}.")
    elif accion == "clave":
        error = validar_clave(f.get("clave") or "", f.get("clave") or "")
        if error:
            flash(error, "error")
        else:
            db.execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (generate_password_hash(f["clave"]), usuario_id))
            flash(f"Se asignó una contraseña nueva a {u['usuario']}.")
    db.commit()
    return redirect(url_for("usuarios.lista"))
