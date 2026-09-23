# Laya Server

Servicio HTTP independiente de Laya System One y consola de un solo administrador. El backend usa FastAPI + SQLite; el frontend usa React + Vite + TypeScript con shadcn/ui. Tras la compilación, un único contenedor de aplicación sirve tanto la interfaz web como la API.

## Código fuente upstream

Este repositorio no rastrea el código fuente de Laya. Antes de compilar, chequea la versión fija v0.3.7 en el directorio raíz del repositorio:

```sh
git clone https://github.com/NandhaKishorM/laya.git laya
git -C laya checkout --detach 010bacef009c855ccba814b51f7c8e1d38ab5e3f
sh scripts/check-upstream.sh
```

`laya/` está añadido a `.gitignore`, pero sí forma parte del contexto de compilación de Docker. El Dockerfile verifica el SHA completo y un árbol de trabajo limpio; la imagen final solo incluye los paquetes upstream y las licencias necesarios para ejecutar, sin `.git`.

## Administrador y configuración

Docker Compose recibe solo `LAYA_ADMIN_USERNAME` y `LAYA_ADMIN_PASSWORD` del shell o de la plataforma de despliegue; no necesita un archivo `.env`. La contraseña debe tener al menos 10 caracteres. Las operaciones administrativas siguen requiriendo sesión y token CSRF. Los demás parámetros usan los valores predeterminados del backend. `.env.example` se usa solo para el script de desarrollo local; no confirmes contraseñas reales.

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'backend[test]'
```

## Archivos de modelo

El repositorio no incluye pesos. El Dockerfile descarga el checkpoint **multilingual** desde el commit fijo de Hugging Face `1c5edc17a7acd8701df6fc341c0d179f1c62c982` durante la compilación y lo incorpora a `/opt/models/multilingual` en la imagen final. La compilación comprueba la inferencia sin conexión en inglés y chino. Al arrancar el contenedor no hay que descargar ni montar modelos. `GET /health/ready` comprueba los archivos incluidos.

La imagen publicada usa `LAYA_MODEL_PROFILE=multilingual`: `model=auto` y `model=multilingual` utilizan ese checkpoint; solicitar `english` o `typed-decisions` devuelve `422 MODEL_NOT_AVAILABLE`. `LAYA_MAX_LOADED_MODELS` controla cuántos modelos permanecen en memoria, no el número de solicitudes simultáneas. La imagen usa PyTorch para CPU y el workflow construye `linux/amd64`.

En local, instala primero las dependencias de ejecución upstream y el checkout de Laya ignorado por Git, descarga los tres modelos en sus versiones fijas y ejecuta una prueba de humo con solicitudes reales que cubra inglés, selección explícita en chino, enrutado automático en chino y typed-decisions:

```sh
.venv/bin/python -m pip install torch==2.5.1 transformers==4.48.3 safetensors==0.5.3 huggingface-hub==0.29.3 numpy==1.26.4
.venv/bin/python -m pip install --no-deps -e ./laya
LAYA_MODEL_DIR=models .venv/bin/python scripts/download-models.py --model english
LAYA_MODEL_DIR=models .venv/bin/python scripts/download-models.py --model multilingual
LAYA_MODEL_DIR=models .venv/bin/python scripts/download-models.py --model typed-decisions
LAYA_MODEL_DIR=models .venv/bin/python scripts/smoke-real-model.py
```

La descarga de modelos y la ejecución dependen de PyTorch, Transformers, Safetensors, Hugging Face Hub y NumPy upstream.

## Arranque

Exporta las variables desde el shell y arranca la imagen publicada:

```sh
export LAYA_ADMIN_USERNAME=admin
export LAYA_ADMIN_PASSWORD='replace-with-a-password-of-at-least-10-characters'
export LAYA_IMAGE_TAG=dev
docker compose pull
docker compose up -d
```

Compose transmite las variables del proceso que lo ejecuta, inicia un único servicio y expone `127.0.0.1:8080` al host. Un proxy inverso externo debe proporcionar HTTPS y reenviar las solicitudes a ese puerto. Los datos de SQLite se conservan en el volumen `laya-data`. La máquina de compilación necesita acceso a PyPI, al índice de PyTorch para CPU, al registry de npm y a Hugging Face; la imagen ya compilada no descarga código, dependencias ni modelos al arrancar.

Si un proxy inverso 1Panel existente provee el HTTPS público, reenvía las solicitudes del dominio a `127.0.0.1:8080` del host. Durante el inicio de sesión, el servicio establece el atributo `Secure` de las cookies según si la solicitud usa HTTPS; configura el proxy para que transmita correctamente el protocolo. El proxy inverso no forma parte del contenedor de aplicación de este proyecto.

### Desarrollo local (recarga en caliente)

La primera vez ejecuta `cp .env.example .env` y rellena `LAYA_ADMIN_USERNAME` y `LAYA_ADMIN_PASSWORD` en `.env`. Si usas la configuración por hash, deja `LAYA_ADMIN_PASSWORD` vacío y rellena `LAYA_ADMIN_PASSWORD_HASH='...'` (conserva las comillas simples). `scripts/dev-backend.sh` establece el origen local, la ruta de SQLite y la ruta de modelos en valores de desarrollo. Asegúrate de que las dependencias de Python/frontend anteriores y los tres modelos ya estén listos.

Abre dos terminales y ejecuta en el directorio raíz del repositorio:

```sh
# Terminal 1: FastAPI y SQLite
sh scripts/dev-backend.sh
```

```sh
# Terminal 2: React/Vite
cd frontend
pnpm dev
```

Abre `http://127.0.0.1:5173` e inicia sesión. Vite redirige `/internal` y `/v1` al puerto local 8000; en producción el frontend compilado lo sigue sirviendo el mismo contenedor de FastAPI. Si solo quieres un proceso local, ejecuta primero `pnpm build` en `frontend/`, arranca Uvicorn y abre el puerto 8000.

La consola admite chino simplificado, inglés y chino tradicional. Puedes cambiar el idioma tanto en la página de inicio de sesión como en la barra superior una vez dentro; en la primera visita se elige el idioma del navegador y la elección manual se guarda en el navegador actual.

## Llamar a la API

Crea una clave en la página **API Keys** tras iniciar sesión en la consola. La clave completa solo se muestra una vez, en la respuesta de creación. Sustituye `TU_CLAVE_API` en el siguiente ejemplo por esa clave.

```sh
curl -X POST https://console.example.com/v1/systemone \
  -H 'Authorization: Bearer TU_CLAVE_API' \
  -H 'Content-Type: application/json' \
  -d '{"state":{"message":"I was charged twice"},"questions":{"refund":{"type":"noul","instructions":"Does the customer ask for a refund?"}}}'
```

En la solicitud, `state` puede ser una cadena, un objeto JSON o un array; `questions` es un mapa no vacío que admite `noul`, `choice` y `score`. En la imagen publicada, `model` admite `auto` (predeterminado) o `multilingual`; pedir otro modelo devuelve `422 MODEL_NOT_AVAILABLE`. El desarrollo local admite los tres modelos si se han descargado. La respuesta conserva `answers`, `model` y `usage` de upstream. Los errores usan `detail.code` y `detail.message`. Una clave no válida devuelve 401, un fallo de validación 422 y un modelo no disponible 503. El Playground de la consola usa la sesión de administrador y se registra como una fuente de consumo independiente.

## Datos y mantenimiento

SQLite está en modo WAL; al hacer copias de seguridad debes detener primero la aplicación y después copiar el archivo de base de datos o usar la API de copia de seguridad de SQLite, para no perder los datos del WAL. Para restaurar, detén la aplicación, sustituye la base de datos dentro del volumen persistente y vuelve a iniciar. Al actualizar Laya, actualiza el SHA completo en `scripts/check-upstream.sh` y en el Dockerfile, vuelve a chekear `laya/`, ejecuta las pruebas y haz una prueba de humo con modelos reales.

```sh
.venv/bin/python -m pytest backend/tests -q
git ls-files laya/
```

El segundo comando no debe producir salida.

Tras el despliegue, se recomienda visitar primero `GET /health/ready` para confirmar que los archivos de modelo están listos y, a continuación, iniciar sesión en la consola y lanzar una solicitud de prueba desde el Playground para comprobar que la inferencia real y las respuestas funcionan correctamente.
