# CENLAC: registro de madres donantes (Centro de Lactancia)

App web en Python + Flask + SQLite. Registra madres donantes, sus bebés y el padre, y muestra estadísticas.

## Cómo ejecutarla
**En Windows (lo más fácil):**
1. Instalar Python 3.10 o superior desde https://www.python.org/downloads/ (marcar "Add python.exe to PATH").
2. Doble clic en `iniciar-cenlac.bat`. La primera vez instala lo necesario. Abre CENLAC en el navegador. No cerrar la ventana negra mientras se use.
3. Opcional: doble clic en `inicio-automatico.bat` para que CENLAC arranque solo cada vez que se enciende esa PC.

**En cualquier sistema:** `pip install -r requirements.txt` y después `python app.py`. Abrir http://localhost:5000 (desde otros equipos del WiFi: http://IP-DE-ESTA-PC:5000).

Esa PC es el **servidor**: tiene la base de datos y tiene que estar encendida para que funcione en los demás equipos. Usa el servidor `waitress` (incluido en `requirements.txt`), preparado para varias PC y celulares a la vez.

## En vivo: varios usuarios a la vez
Todos los usuarios pueden consultar y cargar datos al mismo tiempo desde distintas PC y celulares. Cuando alguien guarda un cambio, las pantallas abiertas por los demás se actualizan solas en unos segundos y muestran un aviso con quién hizo el cambio, por ejemplo "🍼 Paula Sosa registró una extracción de Natalia Acosta". Si en ese momento la persona está escribiendo en un formulario, la pantalla no se recarga: aparece el aviso con el botón **Actualizar**, para no perder lo que se estaba cargando.

Arriba a la derecha, **● En vivo** indica la conexión (verde: conectada; naranja: sin conexión con el servidor) y cuántos usuarios hay conectados. Al tocarlo se abre la lista de los últimos cambios. El widget de escritorio también se actualiza solo. Los avisos se guardan 60 días en la tabla `novedades`; funciona igual en la PC del centro y en Supabase.

## Usar CENLAC desde cualquier lugar (Supabase)
CENLAC puede guardar los datos en **Supabase** (PostgreSQL en la nube) y las fotos de los consentimientos en Supabase Storage, y publicarse en internet con https. Así la app de PC y celular funciona desde cualquier lugar. Los pasos completos están en **PUBLICAR-EN-INTERNET.md**. En resumen:
- `DATABASE_URL`: conexión de Supabase (Session pooler). Sin esta variable se usa `registro.db`, como siempre.
- `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`: para guardar los consentimientos en Storage. Sin ellas se usa la carpeta local.
- `supabase/esquema.sql`: tablas para Supabase (la app las crea sola). `supabase/migrar_a_supabase.py`: pasa los datos de `registro.db` a Supabase.
- `Dockerfile` y `render.yaml`: para publicar en Render (o Railway, Fly.io, etc.).

## Aplicación para PC y celular
En 📲 Instalar (arriba a la derecha) están los pasos y un código QR para abrir CENLAC desde el celular. Se instala desde el navegador, sin tiendas:
- **Celular Android:** Chrome > menú ⋮ > Agregar a la pantalla principal / Instalar aplicación.
- **iPhone:** Safari > Compartir > Agregar a inicio.
- **PC:** Chrome (ícono de instalar en la barra de direcciones, o menú > Transmitir, guardar y compartir > Instalar página como aplicación / Crear acceso directo con "Abrir como ventana") o Edge (menú > Aplicaciones > Instalar este sitio como una aplicación).

Queda la gota de CENLAC en el escritorio o en la pantalla de inicio, y se abre en su propia ventana. Los celulares tienen que estar en el WiFi del centro. La app no guarda datos de las madres en el dispositivo: si no hay conexión con el servidor, muestra un aviso para reintentar. En la PC servidor (http://localhost) la instalación es completa. En los otros equipos de la red el navegador, por seguridad, a veces solo ofrece "Agregar a la pantalla principal" o "Crear acceso directo", que funciona igual. Para usarla fuera del centro hay que publicarla en internet con https.

Los datos se guardan en el archivo `registro.db` de esta carpeta. Si ya tenía una base de una versión anterior, la app le agrega sola las columnas nuevas al iniciar. Las fotos o PDF de los consentimientos informados se guardan en la carpeta `consentimientos` junto a la base. Para hacer copia de seguridad, copiar el archivo `registro.db` (incluye los usuarios) y la carpeta `consentimientos`. El archivo `clave-secreta.txt` que se crea junto a la base firma las sesiones: no compartirlo; si se borra, todos deben volver a ingresar. Son datos personales y de salud: guardar las copias en un lugar protegido.

## Usuarios y perfiles
La primera vez que se abre la app pide crear el usuario **Administrador** (pantalla "Configuración inicial"). Después, cada persona entra con su usuario y contraseña; la sesión dura 12 horas. El administrador crea las cuentas del equipo en 👥 Usuarios, les asigna el perfil, puede cambiarlo, desactivar una cuenta o asignar una contraseña nueva. Cada uno cambia la suya en "Mi contraseña". Siempre queda al menos un administrador activo.

**Solo entran las personas que habilita el Administrador.** No hay registro libre: sin un usuario creado en 👥 Usuarios no se ve ninguna pantalla, y al desactivar una cuenta esa persona queda afuera en el acto, aunque tenga la app abierta. Después de 5 contraseñas incorrectas en 15 minutos, ese usuario y esa conexión quedan bloqueados 15 minutos. Los buscadores no muestran la app. Publicada en internet, el primer Administrador solo se puede crear con el **código de alta** (variable `CODIGO_ALTA`), para que nadie más se adelante.

| Perfil | Puede |
|---|---|
| Administrador | Todo: carga, edición, eliminación, Estadísticas, Cierre mensual con descarga e impresión del PDF, y gestión de usuarios. |
| Jefe | Todo lo anterior salvo el Cierre mensual (no le aparece en el menú ni puede abrirlo) y la gestión de usuarios. |
| Agente | Registrar y consultar madres, bebés, extracciones, etiquetas QR, curvas, preparaciones y actividades. No ve Estadísticas ni Cierre mensual y no puede eliminar madres. |
| Consulta | Trabaja con la vista mini (widget de escritorio): contadores del mes y del año y madres activas con barrio, localidad, situación, leche donada, bebés y última extracción. No ve datos personales ni de salud y no puede modificar nada. |

### Widget de escritorio (vista mini)
Al ingresar con perfil Consulta se abre la vista mini (`/widget`), pensada para dejarla abierta en un costado del escritorio de la PC: muestra la hora, los contadores de madres, bebés y extracciones (mes y año), los ml donados y la lista de madres activas con buscador; tocando un nombre se ven sus datos básicos. Se actualiza sola cada 2 minutos (salvo mientras se busca o se mira un detalle). Los demás perfiles también pueden abrirla con "🗔 Mini" arriba a la derecha.

Para que quede como ventanita propia en Windows: en el widget tocar "📌 Acceso directo" y ejecutar una vez el archivo `cenlac-acceso-directo.bat` que se descarga. Crea en el escritorio el ícono **CENLAC** (la gota) que abre el widget en Edge (o Chrome) en modo aplicación, sin barras, en una ventana de 380 × 640 px. Si Windows muestra un aviso de SmartScreen, elegir "Más información > Ejecutar de todas formas". La ventana se puede mover y achicar como cualquier otra; la primera vez pide usuario y contraseña y después recuerda la sesión por 12 horas.

Los permisos se controlan en el servidor (no solo se ocultan botones): si alguien escribe la dirección de una pantalla no permitida, la app responde "Sin permiso".

## Ícono de la aplicación
El ícono es la gota que se ve al lado del título. Está en `static/iconos/`: `centro-lactancia.ico` (Windows, de 16 a 256 px), `icono.svg` y PNG de 16, 32, 48, 192 y 512 px, `apple-touch-icon.png` (iPhone/iPad) e `icono-maskable-512.png` (Android). Aparece en la pestaña del navegador, en el acceso directo del widget y al instalar la app desde Chrome o Edge (menú > "Instalar CENLAC"; en la red local el navegador solo lo ofrece desde la PC servidor, en http://localhost:5000).

## Pantallas
- Madres donantes: arriba, contadores de madres, bebés y extracciones (con ml) del mes en curso y del año actual; el acumulado anual vuelve a cero el 1 de enero porque se calcula por fecha (no se borra nada). La pantalla principal muestra solo las madres que todavía no tienen alta (del mes actual y anteriores); las dadas de alta se ven en Todas y en la búsqueda. El selector permite ver Todas (histórico completo), Internadas, En domicilio o Con patologías o factores de riesgo (propios de la madre o de su bebé, marcadas con ⚠️ Riesgo). La búsqueda (apellido, nombre, DNI, barrio, localidad) busca en todo el histórico.
- Consentimiento informado: en la ficha de la madre (y en Nueva madre / Editar) se sube la foto o el PDF del consentimiento firmado, con la fecha de firma; desde el celular se puede sacar la foto en el momento. Se ve en miniatura, se abre completo y se puede reemplazar o quitar. Si falta, la ficha lo avisa en rojo. Formatos: JPG, PNG, WEBP, HEIC o PDF, hasta 15 MB.
- Nueva madre / Editar: datos filiatorios, domicilio, situación (internada: conjunta en maternidad o neonatología; o en domicilio), factores de riesgo y patologías crónicas de la madre, bebés (nombre, apellido materno, factores de riesgo y patologías crónicas) y padre (nombre, apellido, edad, si convive).
- Ficha de la madre: registro de cada extracción o estímulo con fecha, hora, mililitros, tipo de leche (calostro, de transición, madura) y características, agrupado por día con totales. Al guardar cada registro se muestra su etiqueta con código QR (nombre y apellido de la madre, tipo de leche, cantidad en ml, fecha y hora), lista para imprimir en 70 × 45 mm y pegar en el frasco; el botón "🏷️ QR" de cada fila vuelve a abrirla. El QR es texto común: lo lee cualquier lector de QR del celular. Usa la librería `segno` (incluida en `requirements.txt`).
- Preparaciones realizadas: tipo de preparación (botones rápidos para leche humana pasteurizada, leche humana fortificada, calostroterapia y leche de fórmula (etiqueta 🍼), o texto libre; la leche fortificada pide fortificador y concentración y se marca con 💪), dosis por vez, frecuencia, cantidad de dosis (calcula el total), bebé con nombre y apellido, internado en maternidad o neonatología, fecha y hora de entrega.
- Otras actividades: educación (a quién se dirige, nombre y apellido), limpieza del sector (material utilizado), difusión, cartelería y salidas (lugar o destino, por ejemplo retiro de leche a domicilio o charla en un centro de salud), con descripción libre que se adapta a la actividad elegida.
- Estadísticas: tabla en rojo de madres y bebés con factores de riesgo (dirección, barrio, teléfono, factores); gráficos de proyección (6 meses previos + 3 próximos, tendencia lineal) de leche extraída, leche entregada y madres nuevas; preparaciones, dosis y ml entregados, por servicio y por tipo; actividades por tipo; leche extraída total, por tipo de leche (registros, ml y % del mes en curso y del año actual por separado; el año vuelve a cero el 1 de enero) y por mes; totales, internadas vs. domicilio, conjunta vs. neonatología, padres que conviven, edad promedio, por barrio, por localidad y por mes.

## Curva de percentiles del bebé
En la ficha de la madre, cada bebé tiene el botón "Curva de percentiles". Ahí se carga un control por día durante la internación (peso en gramos; talla y perímetro cefálico opcionales) y se ven:
- el gráfico de peso (y de talla y perímetro cefálico si se cargan) con las curvas P3, P10, P50, P90 y P97, desde el nacimiento hasta el alta (o hasta hoy si sigue internado);
- la tabla diaria con edad, percentil, puntaje z y ganancia de peso en g/día.

Para calcular los percentiles hay que completar en la ficha del bebé el sexo y la fecha de nacimiento; la edad gestacional y el peso al nacer son muy recomendables. Referencias:
- Bebés de 37 semanas o más (o sin edad gestacional cargada): OMS, Patrones de crecimiento infantil, tablas diarias (archivo `referencias/oms_0_182_dias.json`).
- Prematuros (menos de 37 semanas): INTERGROWTH-21st, estándar de crecimiento posnatal para prematuros (Villar y col., Lancet Glob Health 2015), según edad posmenstrual, de 27 a 64 semanas. Antes de las 27 semanas no se calcula el percentil.
El cálculo está en `crecimiento.py`. El equipo de neonatología debe validar las referencias elegidas antes del uso clínico.

## Alta de la mamá y el bebé
En la ficha de la madre, "Dar de alta" registra la fecha y las indicaciones del equipo, y permite descargar un PDF con:
reconocimiento y agradecimiento como mamá donante (leche donada, extracciones y días), consejería en lactancia,
tacto mamario paso a paso, una breve descripción de vacunas para la mamá y el bebé, y métodos anticonceptivos compatibles con la lactancia, con ilustraciones.
Los textos de salud están en `alta.py` (listas al principio del archivo) para que el equipo los revise y ajuste; las ilustraciones están en `static/alta/`.

## Cierre mensual
En "Cierre mensual" se elige el mes y se descarga el informe en PDF (resumen con variaciones respecto del mes anterior, gráficos de proyección de 6 meses registrados y 3 proyectados, extracciones con gráfico por día, madres registradas, preparaciones, otras actividades, actividades por agente, altas de mamás y bebés, tabla roja de factores de riesgo y espacio para firma; si es el mes en curso, aclara que los datos son parciales). Usa la librería `fpdf2`, que se instala con `requirements.txt`.

**Actividades por agente:** desde esta versión cada madre registrada, extracción o estímulo, preparación, otra actividad y control de bebé queda firmado con el usuario que lo cargó. El cierre (en pantalla y en el PDF) muestra un gráfico de barras con el porcentaje del total de registros del mes que cargó cada usuario, separado por tipo de tarea con colores, y una tabla con las cantidades. Los registros cargados antes de esta versión aparecen como "Sin usuario (registros anteriores)".

## Datos de simulación
Para probar las estadísticas y la proyección con datos de ejemplo de los últimos 6 meses:
- Cargar: `python generar_datos_simulacion.py`
- Quitar solo los datos simulados: `python generar_datos_simulacion.py --borrar`
- Repartir los registros simulados entre los usuarios creados (para ver el gráfico por agente): `python generar_datos_simulacion.py --usuarios`

Los bebés simulados de madres internadas incluyen controles diarios de peso (y semanales de talla y perímetro cefálico) hasta el alta. Los registros simulados quedan marcados ("SIM" en el DNI y "Dato de simulación" en las notas), así que borrarlos no afecta los datos reales.

## Configuración opcional
- `REGISTRO_DB`: ruta del archivo de base de datos SQLite.
- `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_BUCKET`, `EN_INTERNET`: ver PUBLICAR-EN-INTERNET.md.
- `SECRET_KEY`: clave de la aplicación. Si no se indica, se genera una al azar y se guarda en `clave-secreta.txt` junto a la base.
- `PORT`: puerto (por defecto 5000).
- `REGISTRO_CONSENTIMIENTOS`: carpeta donde se guardan los consentimientos (por defecto, `consentimientos` junto a la base).
