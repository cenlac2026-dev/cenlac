"""Archivos de los consentimientos informados: carpeta local o Supabase Storage.

- Sin configurar nada: carpeta `consentimientos` junto a la base (o REGISTRO_CONSENTIMIENTOS).
- Con SUPABASE_URL y SUPABASE_SERVICE_KEY: depósito privado de Supabase Storage
  (por defecto "consentimientos", o SUPABASE_BUCKET). Los archivos nunca son públicos:
  la app los descarga del depósito y se los muestra solo a usuarios con permiso.
"""
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "consentimientos")
EN_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)


def _carpeta():
    from basedatos import DB_PATH
    return os.environ.get("REGISTRO_CONSENTIMIENTOS", os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "consentimientos"))


def _pedido(metodo, nombre, datos=None, tipo=None):
    url = f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{urllib.parse.quote(os.path.basename(nombre))}"
    encabezados = {"Authorization": f"Bearer {SUPABASE_KEY}", "apikey": SUPABASE_KEY}
    if tipo:
        encabezados["Content-Type"] = tipo
        encabezados["x-upsert"] = "true"
    return urllib.request.urlopen(urllib.request.Request(url, data=datos, method=metodo, headers=encabezados), timeout=60)


def guardar(nombre, archivo):
    """Guarda el archivo subido (FileStorage de Flask) con ese nombre."""
    if EN_SUPABASE:
        tipo = archivo.mimetype or mimetypes.guess_type(nombre)[0] or "application/octet-stream"
        with _pedido("POST", nombre, archivo.read(), tipo):
            pass
        return
    os.makedirs(_carpeta(), exist_ok=True)
    archivo.save(os.path.join(_carpeta(), os.path.basename(nombre)))


def leer(nombre):
    """Devuelve (contenido, tipo) o None si no existe."""
    tipo = mimetypes.guess_type(nombre)[0] or "application/octet-stream"
    if EN_SUPABASE:
        try:
            with _pedido("GET", nombre) as r:
                return r.read(), tipo
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            raise
    ruta = os.path.join(_carpeta(), os.path.basename(nombre))
    if not os.path.exists(ruta):
        return None
    with open(ruta, "rb") as f:
        return f.read(), tipo


def borrar(nombre):
    if not nombre:
        return
    try:
        if EN_SUPABASE:
            with _pedido("DELETE", nombre):
                pass
        else:
            os.remove(os.path.join(_carpeta(), os.path.basename(nombre)))
    except (OSError, urllib.error.URLError):
        pass


def descripcion():
    return f"Supabase Storage (depósito {BUCKET})" if EN_SUPABASE else f"carpeta {_carpeta()}"
