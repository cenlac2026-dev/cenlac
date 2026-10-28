"""Conexión a la base de datos: SQLite (archivo local) o PostgreSQL de Supabase.

- Sin configurar nada se usa el archivo SQLite `registro.db` (o REGISTRO_DB).
- Con DATABASE_URL=postgresql://... se usa la base Postgres de Supabase (o cualquier Postgres).

El resto de la aplicación escribe las consultas con el estilo de SQLite (parámetros "?").
Para Postgres se traducen acá las pocas diferencias: parámetros, LIKE sin distinguir
mayúsculas, group_concat, COLLATE NOCASE y el id de la fila recién insertada.
"""
import os
import re
import sqlite3
from urllib.parse import quote, unquote


def _arreglar_url(url):
    """Si la contraseña tiene símbolos como @, # o / sin convertir, los convierte (%40, %23, %2F)."""
    m = re.match(r"^(postgres(?:ql)?://)([^:/@]*):(.*)@([^@]+)$", url)
    if not m:
        return url
    inicio, usuario, clave, resto = m.groups()
    return f"{inicio}{usuario}:{quote(unquote(clave), safe='')}@{resto}"


URL = _arreglar_url(os.environ.get("DATABASE_URL", "").strip().strip("'\""))
ES_POSTGRES = URL.startswith(("postgres://", "postgresql://"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("REGISTRO_DB", os.path.join(BASE_DIR, "registro.db"))

if ES_POSTGRES:
    import psycopg
    from psycopg.types.numeric import FloatLoader

    ErrorIntegridad = (sqlite3.IntegrityError, psycopg.IntegrityError)
else:
    ErrorIntegridad = (sqlite3.IntegrityError,)

# Tablas con columna id autoincremental: al insertar se devuelve el id nuevo.
_CON_ID = {"madres", "bebes", "controles_bebe", "padres", "extracciones", "actividades", "preparaciones", "usuarios", "novedades"}


class Fila(tuple):
    """Fila que se lee por posición (fila[0]) o por nombre (fila["apellido"]), como sqlite3.Row."""
    __slots__ = ()
    _columnas = {}

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return tuple.__getitem__(self, self._columnas[clave])
        return tuple.__getitem__(self, clave)

    def keys(self):
        return list(self._columnas)

    def get(self, clave, defecto=None):
        return self[clave] if clave in self._columnas else defecto


def _fabrica_filas(cursor):
    if cursor.description is None:
        return None
    columnas = {d.name: i for i, d in enumerate(cursor.description)}
    clase = type("FilaPg", (Fila,), {"__slots__": (), "_columnas": columnas})
    return lambda valores: clase(valores)


def traducir(sql, con_parametros=True):
    """Consulta escrita para SQLite -> consulta para Postgres."""
    if con_parametros:
        sql = sql.replace("%", "%%").replace("?", "%s")
    sql = re.sub(r"\bgroup_concat\(", "string_agg(", sql, flags=re.I)
    sql = re.sub(r"\bLIKE\b", "ILIKE", sql)
    sql = re.sub(r"([\w.]+)\s+COLLATE\s+NOCASE", r"lower(\1)", sql, flags=re.I)
    # En Postgres ROUND(x, n) solo acepta numeric (en SQLite AVG devuelve un real).
    sql = re.sub(r"\bROUND\(AVG\(([^()]*)\),", r"ROUND(AVG(\1)::numeric,", sql, flags=re.I)
    return sql


class Cursor:
    def __init__(self, cur, lastrowid=None):
        self._cur = cur
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur.fetchall() if self._cur.description else [])

    @property
    def rowcount(self):
        return self._cur.rowcount


class ConexionPostgres:
    def __init__(self):
        self._con = psycopg.connect(URL, row_factory=_fabrica_filas, prepare_threshold=None)
        # Los numeric (promedios, sumas) se leen como float, igual que en SQLite.
        self._con.adapters.register_loader("numeric", FloatLoader)

    def execute(self, sql, parametros=()):
        parametros = tuple(parametros) if parametros else None
        sql = traducir(sql, parametros is not None)
        tabla = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
        if tabla and tabla.group(1) in _CON_ID and "RETURNING" not in sql.upper():
            cur = self._con.execute(sql + " RETURNING id", parametros)
            fila = cur.fetchone()
            return Cursor(cur, fila[0] if fila else None)
        return Cursor(self._con.execute(sql, parametros))

    def executemany(self, sql, filas):
        with self._con.cursor() as cur:
            cur.executemany(traducir(sql), filas)

    def commit(self):
        self._con.commit()

    def rollback(self):
        self._con.rollback()

    def close(self):
        self._con.close()


def conectar():
    """Abre una conexión nueva (una por pedido web)."""
    if ES_POSTGRES:
        return ConexionPostgres()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def crear_tablas_postgres():
    """Crea las tablas en Postgres si no existen (mismo contenido que supabase/esquema.sql)."""
    ruta = os.path.join(BASE_DIR, "supabase", "esquema.sql")
    with open(ruta, encoding="utf-8") as f, psycopg.connect(URL, autocommit=True) as con:
        con.execute(f.read())


def descripcion():
    if ES_POSTGRES:
        return "Supabase / PostgreSQL (" + re.sub(r"//[^@]*@", "//***@", URL).split("?")[0] + ")"
    return f"SQLite ({DB_PATH})"
