"""Pasa los datos de CENLAC de la base SQLite (registro.db) a Supabase.

Uso (desde la carpeta de la app):
    set DATABASE_URL=postgresql://...            (Windows; en Linux/Mac: export DATABASE_URL=...)
    set SUPABASE_URL=https://xxxx.supabase.co     (opcional: para subir también los consentimientos)
    set SUPABASE_SERVICE_KEY=...                  (opcional, junto con SUPABASE_URL)
    python supabase/migrar_a_supabase.py

Copia usuarios, madres, bebés, padres, controles, extracciones, actividades y preparaciones
conservando los números de registro. No borra nada de la base SQLite. Si Supabase ya tiene datos,
no hace nada (para no duplicar), salvo que se agregue --reemplazar, que vacía Supabase antes de copiar.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import basedatos  # noqa: E402

TABLAS = ["usuarios", "madres", "bebes", "padres", "controles_bebe", "extracciones", "actividades", "preparaciones"]


def main():
    if not basedatos.ES_POSTGRES:
        sys.exit("Falta DATABASE_URL con la conexión de Supabase (Project Settings > Database > Connection string).")
    if not os.path.exists(basedatos.DB_PATH):
        sys.exit(f"No se encontró la base SQLite: {basedatos.DB_PATH}")
    import psycopg

    origen = sqlite3.connect(basedatos.DB_PATH)
    origen.row_factory = sqlite3.Row
    basedatos.crear_tablas_postgres()
    with psycopg.connect(basedatos.URL) as destino:
        ocupadas = [t for t in TABLAS if destino.execute(f"SELECT EXISTS (SELECT 1 FROM {t})").fetchone()[0]]
        if ocupadas and "--reemplazar" not in sys.argv:
            sys.exit("Supabase ya tiene datos en: " + ", ".join(ocupadas) +
                     ". No se copió nada. Use --reemplazar para vaciar Supabase y copiar de nuevo.")
        if ocupadas:
            destino.execute("TRUNCATE " + ", ".join(TABLAS) + " RESTART IDENTITY CASCADE")
        for tabla in TABLAS:
            columnas_destino = {r[0] for r in destino.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
                (tabla,))}
            filas = origen.execute(f"SELECT * FROM {tabla}").fetchall()
            if not filas:
                print(f"  {tabla}: 0")
                continue
            columnas = [c for c in filas[0].keys() if c in columnas_destino]
            sql = (f"INSERT INTO {tabla} ({', '.join(columnas)}) OVERRIDING SYSTEM VALUE "
                   f"VALUES ({', '.join(['%s'] * len(columnas))})")
            with destino.cursor() as cur:
                cur.executemany(sql, [[f[c] for c in columnas] for f in filas])
            # Los números nuevos siguen después del último copiado.
            destino.execute(f"SELECT setval(pg_get_serial_sequence('{tabla}', 'id'), "
                            f"(SELECT COALESCE(MAX(id), 1) FROM {tabla}))")
            print(f"  {tabla}: {len(filas)}")
        destino.commit()

    subir_consentimientos(origen)
    print("Listo. Los datos ya están en Supabase.")


def subir_consentimientos(origen):
    import archivos

    nombres = [r[0] for r in origen.execute(
        "SELECT consentimiento_archivo FROM madres WHERE COALESCE(consentimiento_archivo, '') <> ''")]
    if not nombres:
        return
    if not archivos.EN_SUPABASE:
        print(f"Hay {len(nombres)} consentimiento(s) en la carpeta local. Para subirlos a Supabase Storage "
              "configure SUPABASE_URL y SUPABASE_SERVICE_KEY y vuelva a correr el script con --reemplazar.")
        return
    carpeta = os.environ.get("REGISTRO_CONSENTIMIENTOS",
                             os.path.join(os.path.dirname(os.path.abspath(basedatos.DB_PATH)), "consentimientos"))

    class Archivo:
        def __init__(self, ruta):
            self.ruta, self.mimetype = ruta, None

        def read(self):
            with open(self.ruta, "rb") as f:
                return f.read()

    subidos = 0
    for nombre in nombres:
        ruta = os.path.join(carpeta, os.path.basename(nombre))
        if os.path.exists(ruta):
            archivos.guardar(nombre, Archivo(ruta))
            subidos += 1
        else:
            print(f"  No se encontró el archivo {ruta}")
    print(f"  consentimientos subidos a Supabase Storage: {subidos}")


if __name__ == "__main__":
    main()
