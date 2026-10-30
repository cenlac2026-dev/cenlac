"""Alta de la mamá y el bebé: PDF de reconocimiento como mamá donante con pautas de cuidado.

El contenido de salud es información general basada en recomendaciones habituales de salud pública
(OMS/UNICEF y ministerios de salud). Debe ser revisado y validado por el equipo del centro.
"""
import os
from datetime import date, datetime

from fpdf import FPDF

CARPETA_IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "alta")

LAVANDA = (113, 89, 184)
LAVANDA_MEDIA = (143, 120, 208)
LAVANDA_CLARA = (240, 235, 251)
CELESTE = (143, 195, 230)
CELESTE_CLARO = (230, 242, 251)
AMARILLO = (255, 244, 207)
TEXTO = (74, 67, 96)
SUAVE = (127, 119, 153)
ROJO = (194, 69, 61)
ROJO_CLARO = (253, 236, 235)

IMPORTANCIA = [
    ("imp-proteccion", "Protege a tu bebé",
     "La leche materna tiene defensas que lo cuidan de infecciones, diarreas, bronquiolitis y alergias."),
    ("imp-vinculo", "Fortalece el vínculo",
     "Amamantar es contacto, calor y mirada. Le da seguridad y tranquilidad a tu bebé."),
    ("imp-mama", "También te cuida a vos",
     "Ayuda a que el útero vuelva a su tamaño y disminuye el riesgo de cáncer de mama y de ovario."),
    ("imp-donar", "Tu leche salva vidas",
     "La leche donada alimenta a bebés prematuros o enfermos que no pueden recibir la de su mamá."),
]

CONSEJOS_LACTANCIA = [
    "Leche materna sola, sin agua, té ni otras leches, durante los primeros 6 meses.",
    "Después de los 6 meses, seguí amamantando junto con otros alimentos hasta los 2 años o más.",
    "Ofrecé el pecho a libre demanda, de día y de noche: lo habitual son 8 a 12 tomas por día.",
    "Un buen agarre no duele: boca bien abierta, labios hacia afuera y gran parte de la areola dentro.",
    "Tomá agua cuando tengas sed, comé variado y descansá cuando tu bebé duerma.",
    "Si necesitás extraerte leche, lavate las manos y guardala en heladera o freezer en recipientes limpios.",
]



VACUNAS_MAMA = [
    "Todas las vacunas del calendario son compatibles con la lactancia.",
    "Si no las recibiste en el embarazo, consultá por la antigripal, la doble viral (sarampión y rubéola) y la de hepatitis B.",
]

VACUNAS_BEBE = [
    "Al nacer recibe la BCG y la primera dosis de hepatitis B.",
    "A los 2 meses empiezan las vacunas del calendario: llevá siempre su carnet a cada control.",
]

TACTO_PASOS = [
    ("tacto-espejo", "1. Mirate frente al espejo",
     "Con los brazos al costado del cuerpo y luego con las manos en la cintura, observá forma, tamaño y piel. "
     "Fijate si hay hundimientos, piel como cáscara de naranja, enrojecimiento o el pezón hacia adentro."),
    ("tacto-brazos", "2. Levantá los brazos",
     "Con los brazos arriba de la cabeza, volvé a mirar ambas mamas de frente y de costado, buscando cambios "
     "en el contorno o en la piel."),
    ("tacto-yemas", "3. Palpá con las yemas de los dedos",
     "Con las yemas de tres dedos de la mano contraria, hacé pequeños círculos presionando suave, medio y firme. "
     "Recorré toda la mama y la axila, sin dejar zonas. Hacelo también en la ducha, con la piel enjabonada."),
    ("tacto-acostada", "4. Repetí acostada",
     "Acostada boca arriba, con una almohada bajo el hombro y la mano detrás de la cabeza, palpá de nuevo toda "
     "la mama y la axila. Al final, apretá suavemente el pezón para ver si sale líquido que no sea leche."),
]

TACTO_CONSULTA = [
    "Un bulto o nódulo que no desaparece en una semana (durante la lactancia son frecuentes los conductos tapados, que mejoran al vaciar el pecho).",
    "Cambios en la piel: hundimientos, retracción del pezón o piel de naranja.",
    "Salida de líquido con sangre por el pezón.",
    "Un ganglio o bulto en la axila, o un dolor localizado que no cede.",
]

METODOS = [
    ("mac-implante", "Implante subdérmico",
     "Varilla pequeña bajo la piel del brazo. Dura 3 años y es muy eficaz. Se puede colocar durante la lactancia."),
    ("mac-diu", "DIU de cobre o DIU hormonal",
     "Se coloca en el útero en una consulta. Dura de 5 a 10 años. No afecta la leche."),
    ("mac-pastilla", "Pastilla solo de progestágeno",
     "Una pastilla todos los días a la misma hora, sin pausas. Compatible con la lactancia."),
    ("mac-inyectable", "Inyectable trimestral",
     "Una inyección cada 3 meses. Compatible con la lactancia."),
    ("mac-preservativo", "Preservativo",
     "El único método que también protege de infecciones de transmisión sexual. Se puede usar siempre."),
    ("mac-mela", "Lactancia (MELA)",
     "Protege solo si se cumplen las 3 condiciones: lactancia exclusiva de día y de noche, sin menstruación y bebé menor de 6 meses."),
]

REEMPLAZOS = {"•": "-", "–": "-", "—": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "≥": ">=", "…": "..."}


def limpiar(texto):
    texto = "" if texto is None else str(texto)
    for a, b in REEMPLAZOS.items():
        texto = texto.replace(a, b)
    return texto.encode("latin-1", "replace").decode("latin-1")


def datos_alta(db, madre_id):
    madre = db.execute("SELECT * FROM madres WHERE id = ?", (madre_id,)).fetchone()
    if madre is None:
        return None
    bebes = db.execute("SELECT * FROM bebes WHERE madre_id = ? ORDER BY id", (madre_id,)).fetchall()
    ext = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(cantidad_ml), 0), MIN(substr(fecha_hora, 1, 10)), MAX(substr(fecha_hora, 1, 10)) "
        "FROM extracciones WHERE madre_id = ? AND tipo = 'extraccion'", (madre_id,)).fetchone()
    dias = 0
    if ext[2] and ext[3]:
        dias = (date.fromisoformat(ext[3]) - date.fromisoformat(ext[2])).days + 1
    return {"madre": madre, "bebes": bebes, "extracciones": ext[0], "ml": ext[1],
            "desde": ext[2], "hasta": ext[3], "dias": dias}


def fecha_larga(iso):
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    d = date.fromisoformat(iso) if iso else date.today()
    return f"{d.day} de {meses[d.month - 1]} de {d.year}"


class PDFAlta(FPDF):
    def __init__(self):
        super().__init__(format="A4")
        self.set_auto_page_break(True, margin=20)
        self.set_margins(16, 16, 16)
        self.portada = True

    def header(self):
        if self.portada:
            return
        self.set_fill_color(*LAVANDA_MEDIA)
        self.rect(0, 0, self.w, 16, "F")
        self.set_fill_color(*CELESTE)
        self.rect(self.w * 0.62, 0, self.w * 0.38, 16, "F")
        self.set_xy(16, 4.5)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.cell(0, 7, limpiar("Centro de Lactancia N° 10 - Guía para tu alta"))
        self.set_y(24)
        self.set_text_color(*TEXTO)

    def footer(self):
        if self.page_no() == 1:  # la portada (reconocimiento) no lleva pie
            return
        self.set_y(-14)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(*SUAVE)
        self.cell(0, 4, limpiar("Información general de salud. No reemplaza la consulta con tu equipo de salud."), align="L")
        self.cell(0, 4, f"{self.page_no()}/{{nb}}", align="R")

    def titulo(self, texto, color=LAVANDA, tam=16):
        self.set_font("Helvetica", "B", tam)
        self.set_text_color(*color)
        self.multi_cell(0, tam * 0.5, limpiar(texto), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(*TEXTO)
        self.ln(1.5)

    def parrafo(self, texto, tam=10, alto=5.2):
        self.set_font("Helvetica", "", tam)
        self.multi_cell(0, alto, limpiar(texto), align="L", new_x="LMARGIN", new_y="NEXT")

    def vineta(self, texto, color=LAVANDA_MEDIA, ancho=None, x=None, tam=9.5):
        x = self.l_margin if x is None else x
        ancho = ancho or (self.w - self.r_margin - x)
        y = self.get_y()
        self.set_fill_color(*color)
        self.ellipse(x + 0.6, y + 1.7, 2, 2, "F")
        self.set_xy(x + 4.5, y)
        self.set_font("Helvetica", "", tam)
        self.multi_cell(ancho - 4.5, 4.7, limpiar(texto), align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(0.8)

    def imagen(self, nombre, x, y, w):
        self.image(os.path.join(CARPETA_IMG, nombre + ".svg"), x=x, y=y, w=w)

    def caja(self, x, y, w, h, color, radio=4):
        self.set_fill_color(*color)
        self.rect(x, y, w, h, "F", round_corners=True, corner_radius=radio)


def portada(pdf, d, fecha_alta):
    m = d["madre"]
    pdf.portada = True
    pdf.add_page()
    W, H = pdf.w, pdf.h
    pdf.set_fill_color(250, 248, 255)
    pdf.rect(0, 0, W, H, "F")
    pdf.set_draw_color(*LAVANDA_MEDIA)
    pdf.set_line_width(1.2)
    pdf.rect(9, 9, W - 18, H - 18, round_corners=True, corner_radius=8)
    pdf.set_draw_color(*CELESTE)
    pdf.set_line_width(0.5)
    pdf.rect(13, 13, W - 26, H - 26, round_corners=True, corner_radius=6)
    pdf.set_line_width(0.2)

    pdf.imagen("adorno", 40, 20, W - 80)
    pdf.imagen("ilustracion-bebe-pdf", W / 2 - 38, 34, 76)

    pdf.set_y(98)
    pdf.set_font("Helvetica", "B", 30)
    pdf.set_text_color(*LAVANDA)
    pdf.cell(0, 13, "Reconocimiento", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(*SUAVE)
    pdf.cell(0, 8, limpiar("Mamá donante de leche humana"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*TEXTO)
    pdf.cell(0, 6, limpiar("El Centro de Lactancia N° 10 entrega este reconocimiento a"), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(*LAVANDA)
    pdf.cell(0, 12, limpiar(f"{m['nombre']} {m['apellido']}"), align="C", new_x="LMARGIN", new_y="NEXT")
    y = pdf.get_y() + 1
    pdf.set_draw_color(*CELESTE)
    pdf.line(W / 2 - 50, y, W / 2 + 50, y)
    pdf.ln(7)

    bebes = " y ".join(f"{b['nombre']} {b['apellido_materno']}" for b in d["bebes"])
    texto = ("por su generosidad al donar su leche, un regalo de amor que ayuda a crecer y a recuperarse a bebés "
             "internados que la necesitan. Gracias por elegir compartir lo más valioso que tenés.")
    if bebes:
        texto = f"mamá de {bebes}, " + texto
    pdf.set_x(30)
    pdf.set_font("Helvetica", "", 11.5)
    pdf.set_text_color(*TEXTO)
    pdf.multi_cell(W - 60, 6.2, limpiar(texto), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(7)

    cifras = [(f"{d['ml']:,.0f}".replace(",", ".") + " ml", "de leche donada"),
              (str(d["extracciones"]), "extracciones"),
              (str(d["dias"]), "días como donante")]
    ancho, sep = 46, 6
    x0 = (W - (3 * ancho + 2 * sep)) / 2
    y = pdf.get_y()
    for i, (valor, etq) in enumerate(cifras):
        x = x0 + i * (ancho + sep)
        pdf.caja(x, y, ancho, 22, [LAVANDA_CLARA, CELESTE_CLARO, AMARILLO][i])
        pdf.set_xy(x, y + 3)
        pdf.set_font("Helvetica", "B", 15)
        pdf.set_text_color(*LAVANDA)
        pdf.cell(ancho, 8, limpiar(valor), align="C")
        pdf.set_xy(x, y + 12)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(*SUAVE)
        pdf.cell(ancho, 5, limpiar(etq), align="C")
    pdf.set_y(y + 27)
    if d["ml"]:
        pdf.set_font("Helvetica", "I", 9.5)
        pdf.cell(0, 5, limpiar(f"Equivale a unas {int(d['ml'] // 20)} tomas de 20 ml para bebés prematuros."),
                 align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(H - 62)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*TEXTO)
    pdf.cell(0, 6, limpiar(f"Fecha de alta: {fecha_larga(fecha_alta)}"), align="C", new_x="LMARGIN", new_y="NEXT")
    y = H - 36
    pdf.set_draw_color(*SUAVE)
    for x, etq in ((32, "Firma y sello del Centro de Lactancia N° 10"), (W - 97, "Equipo de salud")):
        pdf.line(x, y, x + 65, y)
        pdf.set_xy(x, y + 1.5)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(*SUAVE)
        pdf.cell(65, 5, limpiar(etq), align="C")
    pdf.portada = False


def pagina_lactancia(pdf, d, fecha_alta, observaciones):  # consejería en lactancia
    pdf.add_page()
    pdf.titulo("Querida mamá:")
    pdf.parrafo("Hoy es tu alta y la de tu bebé. Te preparamos esta guía con lo más importante para que sigas "
                "cuidándote y cuidándolo en casa. Guardala a mano y compartila con tu familia.")
    pdf.ln(3)
    m = d["madre"]
    y = pdf.get_y()
    pdf.caja(pdf.l_margin, y, pdf.w - 32, 24, LAVANDA_CLARA)
    pdf.set_xy(pdf.l_margin + 5, y + 3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, limpiar(f"Mamá: {m['nombre']} {m['apellido']}    DNI: {m['dni']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 5)
    pdf.set_font("Helvetica", "", 9.5)
    bebes = ", ".join(f"{b['nombre']} {b['apellido_materno']}" for b in d["bebes"]) or "-"
    pdf.cell(0, 5, limpiar(f"Bebé: {bebes}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 5)
    pdf.cell(0, 5, limpiar(f"Fecha de alta: {fecha_larga(fecha_alta)}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y + 27)
    if observaciones:
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.cell(0, 5, limpiar("Indicaciones del equipo:"), new_x="LMARGIN", new_y="NEXT")
        pdf.parrafo(observaciones, tam=9.5, alto=4.8)
        pdf.ln(2)

    pdf.titulo("La importancia de la lactancia", tam=14)
    ancho = (pdf.w - 32 - 6) / 2
    y0 = pdf.get_y()
    for i, (img, tit, txt) in enumerate(IMPORTANCIA):
        x = pdf.l_margin + (i % 2) * (ancho + 6)
        y = y0 + (i // 2) * 34
        pdf.caja(x, y, ancho, 31, [CELESTE_CLARO, LAVANDA_CLARA, AMARILLO, LAVANDA_CLARA][i])
        pdf.imagen(img, x + 3, y + 4, 23)
        pdf.set_xy(x + 29, y + 4)
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.set_text_color(*LAVANDA)
        pdf.cell(ancho - 32, 5, limpiar(tit))
        pdf.set_xy(x + 29, y + 10)
        pdf.set_font("Helvetica", "", 8.8)
        pdf.set_text_color(*TEXTO)
        pdf.multi_cell(ancho - 32, 4.3, limpiar(txt), align="L")
    pdf.set_y(y0 + 70)
    pdf.titulo("Consejería en lactancia", tam=12)
    for c in CONSEJOS_LACTANCIA:
        pdf.vineta(c)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.multi_cell(0, 5, limpiar("Si tenés dolor al amamantar, grietas, poca leche o cualquier duda, consultanos: "
                                 "te acompañamos."), align="L", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.cell(0, 7, limpiar("Teléfono del Centro de Lactancia N° 10: ______________________   Horario: ______________"),
             new_x="LMARGIN", new_y="NEXT")



def pagina_tacto(pdf):
    pdf.add_page()
    pdf.titulo("Autoexamen mamario (tacto mamario)")
    pdf.parrafo("Conocer tus mamas te ayuda a darte cuenta a tiempo de cualquier cambio. Hacelo una vez por mes. "
                "Si menstruás, entre 7 y 10 días después del comienzo de la menstruación; si no, elegí un mismo día "
                "de cada mes. Mientras amamantás, es más cómodo hacerlo después de dar el pecho o de extraerte leche.",
                tam=9.8, alto=5)
    pdf.ln(3)
    for img, tit, txt in TACTO_PASOS:
        y = pdf.get_y()
        pdf.caja(pdf.l_margin, y, pdf.w - 32, 33, LAVANDA_CLARA if TACTO_PASOS.index((img, tit, txt)) % 2 == 0 else CELESTE_CLARO)
        pdf.imagen(img, pdf.l_margin + 4, y + 3, 27)
        pdf.set_xy(pdf.l_margin + 36, y + 4)
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(*LAVANDA)
        pdf.cell(0, 5, limpiar(tit), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*TEXTO)
        pdf.set_xy(pdf.l_margin + 36, y + 11)
        pdf.set_font("Helvetica", "", 9.3)
        pdf.multi_cell(pdf.w - 32 - 40, 4.6, limpiar(txt), align="L")
        pdf.set_y(y + 36)
    pdf.titulo("Consultá con tu médica o médico si notás:", color=ROJO, tam=11)
    for t in TACTO_CONSULTA:
        pdf.vineta(t, color=ROJO, tam=9.3)
    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 8.8)
    pdf.set_text_color(*SUAVE)
    pdf.multi_cell(0, 4.4, limpiar("El autoexamen no reemplaza el control anual con tu equipo de salud ni los estudios "
                                   "(ecografía o mamografía) que te indiquen según tu edad."))
    pdf.set_text_color(*TEXTO)


def bloque_vacunas(pdf):
    pdf.titulo("Vacunas")
    y = pdf.get_y()
    alto = 40
    pdf.caja(pdf.l_margin, y, pdf.w - 32, alto, CELESTE_CLARO)
    pdf.imagen("vacuna", pdf.l_margin + 4, y + 6, 27)
    ancho = (pdf.w - 32 - 40) / 2
    for i, (tit, lista) in enumerate((("Para vos", VACUNAS_MAMA), ("Para tu bebé", VACUNAS_BEBE))):
        x = pdf.l_margin + 36 + i * (ancho + 3)
        pdf.set_xy(x, y + 4)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*LAVANDA)
        pdf.cell(ancho, 5, limpiar(tit), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*TEXTO)
        pdf.set_y(y + 10)
        for t in lista:
            pdf.vineta(t, x=x, ancho=ancho, tam=8.8)
    pdf.set_y(y + alto + 5)


def pagina_anticoncepcion(pdf):
    pdf.add_page()
    bloque_vacunas(pdf)
    pdf.titulo("Métodos anticonceptivos después del parto")
    pdf.parrafo("Podés volver a quedar embarazada antes de que vuelva la menstruación. Cuidarte te permite decidir "
                "cuándo tener otro hijo; lo ideal es esperar al menos 2 años entre un embarazo y el siguiente. "
                "Estos métodos son compatibles con la lactancia:", tam=9.8, alto=5)
    pdf.ln(3)
    ancho = (pdf.w - 32 - 6) / 2
    y0 = pdf.get_y()
    for i, (img, tit, txt) in enumerate(METODOS):
        x = pdf.l_margin + (i % 2) * (ancho + 6)
        y = y0 + (i // 2) * 33
        pdf.caja(x, y, ancho, 30, [LAVANDA_CLARA, CELESTE_CLARO, AMARILLO][i % 3])
        pdf.imagen(img, x + 3, y + 3.5, 23)
        pdf.set_xy(x + 29, y + 4)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*LAVANDA)
        pdf.cell(ancho - 32, 5, limpiar(tit))
        pdf.set_xy(x + 29, y + 10)
        pdf.set_font("Helvetica", "", 8.6)
        pdf.set_text_color(*TEXTO)
        pdf.multi_cell(ancho - 32, 4.1, limpiar(txt), align="L")
    pdf.set_y(y0 + 3 * 33 + 2)
    y = pdf.get_y()
    pdf.caja(pdf.l_margin, y, pdf.w - 32, 21, ROJO_CLARO)
    pdf.set_xy(pdf.l_margin + 5, y + 3)
    pdf.set_font("Helvetica", "B", 9.8)
    pdf.set_text_color(*ROJO)
    pdf.cell(0, 5, limpiar("Mientras amamantás, evitá los métodos con estrógenos"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(pdf.l_margin + 5)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*TEXTO)
    pdf.multi_cell(pdf.w - 42, 4.4, limpiar("Las pastillas combinadas, el inyectable mensual, el parche y el anillo no se "
                                            "recomiendan en las primeras semanas después del parto y pueden disminuir la "
                                            "producción de leche. Consultá antes de usarlos."))
    pdf.set_y(y + 25)
    for t in ("La pastilla de emergencia es compatible con la lactancia: tomala lo antes posible después de una relación sin protección.",
              "En los centros de salud públicos te asesoran y te dan los métodos en forma gratuita."):
        pdf.vineta(t, tam=9.3)


def generar_pdf(d, fecha_alta=None, observaciones=""):
    pdf = PDFAlta()
    pdf.alias_nb_pages()
    pdf.set_title(limpiar(f"Alta y reconocimiento - {d['madre']['nombre']} {d['madre']['apellido']}"))
    pdf.set_author("Centro de Lactancia N° 10")
    fecha_alta = fecha_alta or date.today().isoformat()
    portada(pdf, d, fecha_alta)
    pagina_lactancia(pdf, d, fecha_alta, observaciones)
    pagina_tacto(pdf)
    pagina_anticoncepcion(pdf)
    return bytes(pdf.output())
