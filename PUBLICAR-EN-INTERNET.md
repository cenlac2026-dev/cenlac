# Publicar CENLAC en internet con Supabase

Con estos pasos, CENLAC queda en una dirección https (por ejemplo `https://cenlac.onrender.com`) y se usa como aplicación en la PC y en el celular desde cualquier lugar. Hay dos partes:

- **Supabase** guarda los datos (base PostgreSQL) y las fotos de los consentimientos (Storage privado).
- **Render** (u otro servicio similar) ejecuta la aplicación y le da la dirección https.

> Son datos personales y de salud. Antes de publicar, conviene que la institución lo autorice. Las claves de Supabase van solo en Render, nunca por chat ni por correo.

## 1. Crear el proyecto en Supabase
1. Entrar a https://supabase.com, crear una cuenta y luego **New project**.
2. Nombre: `cenlac`. Región: **South America (São Paulo)**. Elegir una **contraseña de base de datos** fuerte y guardarla.
3. Esperar a que el proyecto termine de crearse (1 o 2 minutos).

## 2. Crear las tablas
1. En Supabase: **SQL Editor > New query**.
2. Pegar todo el contenido de `supabase/esquema.sql` y tocar **Run**.

Crea las tablas, activa la protección (RLS) para que nadie pueda leerlas con la clave pública y crea el depósito privado `consentimientos`. La app también lo ejecuta sola al iniciar, así que este paso es opcional.

## 3. Copiar los datos de conexión
- **DATABASE_URL:** botón **Connect** (arriba) > pestaña **Connection string** > **Session pooler**. Copiar la dirección `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:5432/postgres` y reemplazar `[YOUR-PASSWORD]` por la contraseña del paso 1. Hay que usar el *Session pooler*, porque la conexión directa no funciona desde Render.
- **SUPABASE_URL:** **Project Settings > Data API > Project URL** (`https://xxxx.supabase.co`).
- **SUPABASE_SERVICE_KEY:** **Project Settings > API Keys > service_role** (o *secret key*). Es secreta: da acceso total.

## 4. Pasar los datos que ya están cargados (opcional)
Si ya usan CENLAC en una PC con el archivo `registro.db`, en esa PC, desde la carpeta de la app (Windows, en una ventana de comandos):

```
set DATABASE_URL=postgresql://postgres.xxxx:CONTRASEÑA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
set SUPABASE_URL=https://xxxx.supabase.co
set SUPABASE_SERVICE_KEY=la-clave-service-role
python supabase\migrar_a_supabase.py
```

Copia usuarios, madres, bebés, padres, controles, extracciones, actividades y preparaciones con sus mismos números, y sube las fotos de los consentimientos. No borra nada de `registro.db`. Si Supabase ya tiene datos, no copia nada, para no duplicar.

## 5. Publicar la aplicación en Render
1. Subir la carpeta de la app a un repositorio **privado** de GitHub (en github.com: **New repository** > *Private* > **uploading an existing file**, y arrastrar el contenido de la carpeta, sin `registro.db` ni la carpeta `consentimientos`).
2. En https://render.com: crear una cuenta, **New > Blueprint** y elegir ese repositorio. Render lee `render.yaml`.
3. Completar las tres variables del paso 3: `DATABASE_URL`, `SUPABASE_URL` y `SUPABASE_SERVICE_KEY`. La clave de sesiones (`SECRET_KEY`) se genera sola.
4. **Apply / Deploy**. En unos minutos queda la dirección, por ejemplo `https://cenlac.onrender.com`.
5. Abrirla. Si la base está vacía, pide crear el usuario **Administrador**; si se migraron datos, entrar con los usuarios de siempre.

Sobre los planes:
- **Render gratis:** se "duerme" después de 15 minutos sin uso y la primera apertura tarda alrededor de un minuto. Para uso diario conviene el plan **Starter** (unos USD 7 por mes).
- **Supabase gratis:** 500 MB de base y 1 GB de archivos, suficiente para varios años de registros. Si pasa una semana sin ningún uso, el proyecto se pausa y se reactiva desde el panel. El plan **Pro** (USD 25 por mes) suma copias de seguridad diarias.

El mismo `Dockerfile` sirve para Railway, Fly.io o un servidor propio: hay que configurar las mismas variables más `EN_INTERNET=1`.

## 6. Instalar en la PC y en el celular
Abrir la dirección https, ingresar y tocar **📲 Instalar** (arriba a la derecha). Ahí está el código QR para el celular y los pasos para Android, iPhone, Chrome y Edge. Con https la instalación es completa en todos los equipos, con el ícono de la gota.

## Seguridad y copias
- Todo viaja cifrado (https), y la base solo acepta la contraseña configurada en Render.
- Las fotos de los consentimientos quedan en un depósito privado: solo se ven desde CENLAC, con un usuario que tenga permiso.
- Copia de seguridad: en Supabase, **Database > Backups** (plan Pro), o con `pg_dump` usando la misma `DATABASE_URL`.
- Si alguna vez se filtra una clave: en Supabase, cambiar la contraseña de la base y la service_role key, y actualizarlas en Render.

## Seguir usando la versión local
Si no se configura `DATABASE_URL`, CENLAC sigue funcionando como siempre con `registro.db` en la PC del centro (ver LEEME.md).
