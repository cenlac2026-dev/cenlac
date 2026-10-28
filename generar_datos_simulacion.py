"""Carga datos simulados de los últimos 6 meses para probar estadísticas y proyección.

Uso:
    python generar_datos_simulacion.py           # agrega los datos simulados
    python generar_datos_simulacion.py --borrar  # quita solo los datos simulados
    python generar_datos_simulacion.py --usuarios  # reparte los registros simulados entre los usuarios creados

Los registros simulados se reparten entre los usuarios que existan (más carga para los agentes), así el cierre
mensual muestra el gráfico de actividades por agente. Si se crean usuarios después, correr con --usuarios.

Todos los registros simulados quedan marcados ("SIM" en el DNI y "Simulación" en las notas)
para poder borrarlos sin tocar los datos reales.
"""
import random
import re
import sqlite3
import sys
from datetime import date, datetime, timedelta

import basedatos
import crecimiento
from app import DB_PATH, MESES_HISTORIA, init_db, sumar_meses

MARCA = "Dato de simulación"
NOMBRES = ["Ana", "María", "Carla", "Julieta", "Paula", "Sofía", "Lucía", "Valeria", "Romina", "Florencia",
           "Camila", "Daniela", "Gabriela", "Natalia", "Belén", "Micaela", "Agustina", "Noelia", "Silvina", "Rocío"]
APELLIDOS = ["Gómez", "Fernández", "López", "Martínez", "Sosa", "Rodríguez", "Pérez", "Díaz", "Acosta", "Romero",
             "Benítez", "Ruiz", "Álvarez", "Torres", "Flores", "Medina", "Herrera", "Castro", "Vargas", "Ríos"]
BEBES = ["Luz", "Tomás", "Mía", "Benjamín", "Valentino", "Emma", "Thiago", "Olivia", "Bautista", "Martina",
         "Joaquín", "Catalina", "Felipe", "Isabella", "Lautaro", "Alma", "Santino", "Renata"]
PADRES = ["Juan", "Carlos", "Diego", "Martín", "Lucas", "Matías", "Pablo", "Nicolás", "Sergio", "Gustavo"]
BARRIOS = [("Centro", "Ciudad"), ("Villa Norte", "Ciudad"), ("Barrio Sur", "Ciudad"), ("San Martín", "Ciudad"),
           ("Los Álamos", "San Pedro"), ("El Progreso", "San Pedro"), ("La Loma", "Villa Nueva")]
RIESGO_MADRE = ["Hipertensión gestacional", "Diabetes gestacional", "Tabaquismo", "Anemia", "Cesárea reciente"]
CRONICA_MADRE = ["Hipotiroidismo", "Asma", "Diabetes tipo 1", "Obesidad"]
RIESGO_BEBE = ["Prematurez", "Bajo peso al nacer", "Ictericia", "Sepsis neonatal", "Prematurez y bajo peso"]
CRONICA_BEBE = ["Cardiopatía congénita", "Displasia broncopulmonar", "Síndrome de Down"]
VARONES = {"Tomás", "Benjamín", "Valentino", "Thiago", "Bautista", "Joaquín", "Felipe", "Lautaro", "Santino"}
CARACT = ["Amarillenta, espesa", "Blanca, aspecto normal", "Blanca azulada", "Amarillo claro", "", ""]


def conectar():
    init_db()
    return basedatos.conectar()


def borrar(db):
    db.execute("DELETE FROM madres WHERE dni LIKE 'SIM%'")
    db.execute("DELETE FROM preparaciones WHERE observaciones = ?", (MARCA,))
    db.execute("DELETE FROM actividades WHERE descripcion LIKE ?", (f"{MARCA}%",))
    db.commit()


def simular_crecimiento(db, bebe_id, rnd, hasta):
    """Completa sexo, edad gestacional y peso al nacer, y carga un control diario de peso hasta el alta
    (talla y perímetro cefálico una vez por semana)."""
    b = db.execute("SELECT nombre, fecha_nacimiento, factores_riesgo FROM bebes WHERE id = ?", (bebe_id,)).fetchone()
    nombre, nacimiento, riesgo = b[0], date.fromisoformat(b[1]), (b[2] or "").lower()
    sexo = "M" if nombre in VARONES else "F"
    eg_texto = re.search(r"(\d{2}) semanas", riesgo)
    if eg_texto:
        semanas = int(eg_texto.group(1))
    elif "prematurez" in riesgo:
        semanas = rnd.randint(29, 35)
    else:
        semanas = rnd.choice([37, 38, 38, 39, 39, 39, 40, 40, 41])
    dias_eg = rnd.randint(0, 6)
    info = {"sexo": sexo, "eg_semanas": semanas, "eg_dias": dias_eg, "eg_total_dias": semanas * 7 + dias_eg,
            "nacimiento": nacimiento, "prematuro": semanas < crecimiento.SEMANAS_TERMINO}
    z = rnd.gauss(-1.6 if "bajo peso" in riesgo else -0.2, 0.6)
    z_talla, z_pc = z + rnd.gauss(0, 0.4), z + rnd.gauss(0, 0.4)
    peso_nac = round(crecimiento.valor_z(info, "peso", nacimiento, z) or 1000)
    db.execute("UPDATE bebes SET sexo = ?, eg_semanas = ?, eg_dias = ?, peso_nacimiento = ? WHERE id = ?",
               (sexo, str(semanas), str(dias_eg), str(peso_nac), bebe_id))
    peso = peso_nac
    minimo = None
    for d in range(1, (hasta - nacimiento).days + 1):
        dia = nacimiento + timedelta(days=d)
        if d <= 4:
            peso *= 1 - rnd.uniform(0.012, 0.025)  # descenso fisiológico de los primeros días
        elif info["prematuro"]:
            peso *= 1 + rnd.uniform(0.010, 0.019)  # unos 15 g/kg/día
        else:
            peso += rnd.uniform(18, 38)
        talla = pc = None
        if d % 7 == 0:
            z_talla += rnd.gauss(-0.05, 0.08)
            z_pc += rnd.gauss(-0.03, 0.06)
            talla = crecimiento.valor_z(info, "talla", dia, z_talla)
            pc = crecimiento.valor_z(info, "pc", dia, z_pc)
            talla = round(talla, 1) if talla else None
            pc = round(pc, 1) if pc else None
        obs = "Descenso fisiológico" if d == 3 else ""
        db.execute("INSERT INTO controles_bebe (bebe_id, fecha, peso, talla, pc, observaciones) VALUES (?,?,?,?,?,?)",
                   (bebe_id, dia.isoformat(), round(peso), talla, pc, obs))


def generar(db, semilla=7):
    rnd = random.Random(semilla)
    hoy = date.today()
    dni = 40000000
    for i in range(MESES_HISTORIA + 1):  # 6 meses previos + el mes en curso hasta hoy
        anio, mes = sumar_meses(hoy.year, hoy.month, -MESES_HISTORIA + i)
        primero = date(anio, mes, 1)
        ultimo = min(date(*sumar_meses(anio, mes, 1), 1) - timedelta(days=1), hoy)
        dias = (ultimo - primero).days + 1
        crecimiento = 1 + 0.09 * i  # el centro crece mes a mes
        nuevas = max(1, round((6 * crecimiento + rnd.uniform(-1, 1)) * dias / 30))

        for _ in range(nuevas):
            dni += rnd.randint(1, 900)
            alta = primero + timedelta(days=rnd.randrange(dias))
            barrio, localidad = rnd.choice(BARRIOS)
            situacion = rnd.choice(["internada", "internada", "domicilio"])
            apellido = rnd.choice(APELLIDOS)
            cur = db.execute(
                "INSERT INTO madres (apellido, nombre, dni, fecha_nacimiento, telefono, direccion, barrio, localidad, "
                "situacion, tipo_internacion, observaciones, fecha_registro) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (apellido, rnd.choice(NOMBRES), f"SIM{dni}", f"{rnd.randint(1985, 2006)}-{rnd.randint(1, 12):02d}-15",
                 f"387 {rnd.randint(400, 599)}-{rnd.randint(1000, 9999)}", f"Calle {rnd.randint(1, 99)} N° {rnd.randint(10, 2500)}", barrio, localidad,
                 situacion, rnd.choice(["conjunta", "neonatologia"]) if situacion == "internada" else None,
                 MARCA, alta.isoformat()),
            )
            madre_id = cur.lastrowid
            db.execute("UPDATE madres SET factores_riesgo = ?, patologias_cronicas = ? WHERE id = ?",
                       (rnd.choice(RIESGO_MADRE) if rnd.random() < 0.35 else "",
                        rnd.choice(CRONICA_MADRE) if rnd.random() < 0.15 else "", madre_id))
            bebe = rnd.choice(BEBES)
            cur_bebe = db.execute("INSERT INTO bebes (madre_id, nombre, apellido_materno, fecha_nacimiento, factores_riesgo, "
                       "patologias_cronicas) VALUES (?,?,?,?,?,?)",
                       (madre_id, bebe, apellido, (alta - timedelta(days=rnd.randint(0, 10))).isoformat(),
                        rnd.choice(RIESGO_BEBE) if rnd.random() < 0.45 else "",
                        rnd.choice(CRONICA_BEBE) if rnd.random() < 0.1 else ""))
            if rnd.random() < 0.8:
                db.execute("INSERT INTO padres (madre_id, nombre, apellido, edad, convive) VALUES (?,?,?,?,?)",
                           (madre_id, rnd.choice(PADRES), rnd.choice(APELLIDOS), rnd.randint(19, 45),
                            1 if rnd.random() < 0.7 else 0))
            # Alta de la mamá y el bebé unas 2 a 3 semanas después del registro
            fecha_alta = alta + timedelta(days=rnd.randint(12, 21))
            con_alta = fecha_alta <= hoy and rnd.random() < 0.85
            if con_alta:
                db.execute("UPDATE madres SET fecha_alta = ?, alta_observaciones = ? WHERE id = ?",
                           (fecha_alta.isoformat(), "Control en el centro de salud a las 72 horas.", madre_id))
            # Crecimiento del bebé durante la internación (generador aparte para no alterar el resto de los datos)
            if situacion == "internada":
                simular_crecimiento(db, cur_bebe.lastrowid, random.Random(semilla * 1000 + madre_id),
                                    fecha_alta if con_alta else hoy)
            # Extracciones durante las semanas siguientes al alta (calostro -> transición -> madura)
            for d in range(rnd.randint(10, 13)):
                dia = alta + timedelta(days=d)
                if dia > hoy:
                    break
                leche, base = ("calostro", 8) if d < 3 else ("transicion", 35) if d < 7 else ("madura", 70)
                for hora in rnd.sample(["06:30", "09:00", "12:00", "15:00", "18:00", "21:00"], rnd.randint(3, 4)):
                    db.execute(
                        "INSERT INTO extracciones (madre_id, fecha_hora, tipo, cantidad_ml, tipo_leche, caracteristicas) "
                        "VALUES (?,?,?,?,?,?)",
                        (madre_id, f"{dia.isoformat()} {hora}", "extraccion",
                         round(base * rnd.uniform(0.6, 1.4) * (1 + 0.04 * i)), leche, rnd.choice(CARACT)))
                if rnd.random() < 0.3:
                    db.execute("INSERT INTO extracciones (madre_id, fecha_hora, tipo, caracteristicas) VALUES (?,?,?,?)",
                               (madre_id, f"{dia.isoformat()} 22:00", "estimulo", "Estímulo manual"))

        # Preparaciones entregadas a bebés internados
        for _ in range(round(30 * crecimiento * dias / 30 + rnd.uniform(-4, 4))):
            dia = primero + timedelta(days=rnd.randrange(dias))
            tipo = rnd.choice(["Leche humana pasteurizada"] * 3 + ["Leche humana fortificada", "Calostroterapia"])
            dosis = 0.5 if tipo == "Calostroterapia" else rnd.choice([10, 15, 20, 25, 30])
            frecuencia, cantidad = rnd.choice([("Cada 3 horas", 8), ("Cada 2 horas", 12), ("Cada 4 horas", 6)])
            db.execute(
                "INSERT INTO preparaciones (fecha, hora_entrega, tipo_preparacion, dosis_ml, frecuencia, cantidad_dosis, "
                "bebe_nombre, bebe_apellido, servicio, observaciones) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (dia.isoformat(), f"{rnd.randint(7, 20):02d}:{rnd.choice(['00', '15', '30', '45'])}", tipo, dosis,
                 frecuencia, cantidad, rnd.choice(BEBES), rnd.choice(APELLIDOS),
                 rnd.choice(["neonatologia", "neonatologia", "maternidad"]), MARCA))

        # Otras actividades
        for _ in range(round(8 * crecimiento * dias / 30)):
            dia = primero + timedelta(days=rnd.randrange(dias))
            tipo = rnd.choice(["educacion", "educacion", "limpieza", "limpieza", "difusion", "carteleria"])
            db.execute(
                "INSERT INTO actividades (fecha_hora, tipo, destinatario_nombre, destinatario_apellido, material, descripcion) "
                "VALUES (?,?,?,?,?,?)",
                (f"{dia.isoformat()} {rnd.randint(8, 17):02d}:00", tipo,
                 rnd.choice(NOMBRES) if tipo == "educacion" else None,
                 rnd.choice(APELLIDOS) if tipo == "educacion" else None,
                 "Alcohol al 70%, detergente enzimático" if tipo == "limpieza" else None,
                 f"{MARCA}. Actividad de ejemplo."))
    completar_fortificadas(db)
    completar_salidas(db)
    # Algunas preparaciones de leche de fórmula (cuando no alcanza la leche humana)
    db.execute("UPDATE preparaciones SET tipo_preparacion = 'Leche de fórmula' WHERE observaciones = ? "
               "AND tipo_preparacion = 'Leche humana pasteurizada' AND id % 9 = 0", (MARCA,))
    completar_usuarios(db)
    db.commit()


def completar_usuarios(db, semilla=11):
    """Asigna quién cargó cada registro simulado: los agentes cargan la mayoría, el jefe y el administrador menos."""
    peso_rol = {"agente": 6, "jefe": 2, "admin": 1}
    usuarios = [(uid, peso_rol[rol]) for uid, rol in
                db.execute("SELECT id, rol FROM usuarios WHERE activo = 1 AND rol IN ('agente', 'jefe', 'admin')")]
    if not usuarios:
        return 0
    rnd = random.Random(semilla)
    ids, pesos = [u for u, _ in usuarios], [p for _, p in usuarios]
    simulados = {
        "madres": "SELECT id FROM madres WHERE dni LIKE 'SIM%'",
        "extracciones": "SELECT e.id FROM extracciones e JOIN madres m ON m.id = e.madre_id WHERE m.dni LIKE 'SIM%'",
        "preparaciones": f"SELECT id FROM preparaciones WHERE observaciones = '{MARCA}'",
        "actividades": f"SELECT id FROM actividades WHERE descripcion LIKE '{MARCA}%'",
        "controles_bebe": "SELECT c.id FROM controles_bebe c JOIN bebes b ON b.id = c.bebe_id "
                          "JOIN madres m ON m.id = b.madre_id WHERE m.dni LIKE 'SIM%'",
    }
    total = 0
    for tabla, sql in simulados.items():
        filas = [r[0] for r in db.execute(sql)]
        db.executemany(f"UPDATE {tabla} SET usuario_id = ? WHERE id = ?",
                       [(rnd.choices(ids, pesos)[0], i) for i in filas])
        total += len(filas)
    db.commit()
    return total


def completar_salidas(db):
    """Convierte algunas actividades simuladas de difusión en salidas, con lugar y motivo."""
    destinos = [("Domicilio de una mamá donante, Barrio Sur", "Retiro de leche extraída en domicilio"),
                ("CAPS Villa Norte", "Charla sobre donación de leche humana"),
                ("Domicilio de una mamá donante, Los Álamos", "Visita de seguimiento y retiro de frascos"),
                ("Escuela N° 12", "Taller de lactancia para estudiantes")]
    for (act_id,) in db.execute("SELECT id FROM actividades WHERE tipo = 'difusion' AND descripcion LIKE ? "
                                "AND id % 2 = 0", (f"{MARCA}%",)).fetchall():
        lugar, motivo = destinos[act_id % len(destinos)]
        db.execute("UPDATE actividades SET tipo = 'salida', lugar = ?, descripcion = ? WHERE id = ?",
                   (lugar, f"{MARCA}. {motivo}.", act_id))


def completar_fortificadas(db):
    """Fortificador y concentración de las preparaciones simuladas de leche fortificada."""
    opciones = [("Fortificador de leche humana en polvo", "1 sobre cada 25 ml"),
                ("Fortificador de leche humana en polvo", "Media dosis (1 sobre cada 50 ml)"),
                ("Fortificador líquido", "1 sobre cada 25 ml"), ("Módulo proteico", "4 g cada 100 ml")]
    for (prep_id,) in db.execute("SELECT id FROM preparaciones WHERE observaciones = ? AND fortificador IS NULL "
                                 "AND lower(tipo_preparacion) LIKE '%fortific%'", (MARCA,)).fetchall():
        fortificador, concentracion = opciones[prep_id % len(opciones)]
        db.execute("UPDATE preparaciones SET fortificador = ?, concentracion = ? WHERE id = ?",
                   (fortificador, concentracion, prep_id))


if __name__ == "__main__":
    conexion = conectar()
    if "--usuarios" not in sys.argv:
        borrar(conexion)
    if "--usuarios" in sys.argv:
        print(f"Registros simulados repartidos entre los usuarios: {completar_usuarios(conexion)}.")
    elif "--borrar" in sys.argv:
        print("Datos simulados eliminados.")
    else:
        generar(conexion)
        print(f"Datos simulados cargados en {basedatos.descripcion()} ({datetime.now():%d/%m/%Y %H:%M}).")
