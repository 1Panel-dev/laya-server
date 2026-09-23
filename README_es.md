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

Define `LAYA_ADMIN_USERNAME` y `LAYA_ADMIN_PASSWORD` (de al menos 10 caracteres) en `.env`; al iniciar el servicio se genera en memoria un hash Argon2id para validar el inicio de sesión. También puedes omitir la contraseña en claro y generar `LAYA_ADMIN_PASSWORD_HASH` con `.venv/bin/python scripts/hash-password.py`; se debe establecer exactamente una de las dos. Envuelve el valor del hash entre comillas simples para que Docker Compose conserve `$` literalmente. `LAYA_PUBLIC_ORIGIN` también es obligatorio; en producción debe ser un origen HTTPS, por ejemplo `https://console.example.com`. Para pruebas locales por HTTP se necesita `LAYA_ALLOW_INSECURE_LOCAL=1`. `.env` está ignorado por Git: no confirmes (commit) contraseñas reales.

```sh
cp .env.example .env
python3.12 -m venv .venv
.venv/bin/python -m pip install -e 'backend[test]'
# Edita .env y rellena LAYA_ADMIN_USERNAME y LAYA_ADMIN_PASSWORD
```

## Archivos de modelo

Los pesos de los modelos no se distribuyen con el repositorio ni con la imagen. `scripts/download-models.py` fija el repositorio de Hugging Face en el commit `1c5edc17a7acd8701df6fc341c0d179f1c62c982` y coloca los tres checkpoints en `/models/english`, `/models/multilingual` y `/models/typed-decisions` del volumen de modelos persistente. Cada directorio debe contener como mínimo `rl_agent_config.json`, `model.safetensors`, `tokenizer/` y `encoder/` del paquete de modelo upstream. La presencia de los archivos se comprueba con `GET /health/ready`; si faltan, la inferencia devuelve `503 MODEL_UNAVAILABLE`. Sigue siendo necesario hacer una prueba de humo de inferencia para confirmar que los modelos son realmente compatibles.

La inferencia de modelos de este proyecto no se descarga automáticamente al arrancar la aplicación; prepara el volumen de modelos antes del arranque. Un proceso de aplicación solo carga los modelos necesarios y, de forma predeterminada, conserva como máximo uno en memoria; ajusta el valor con `LAYA_MAX_LOADED_MODELS`. Este valor controla cuántos modelos mantiene la caché, no cuántas solicitudes se procesan simultáneamente. El servicio no define ranuras adicionales de concurrencia de inferencia; la concurrencia real depende del grupo de hilos de ejecución, de los modelos y de los recursos de la máquina. La imagen de inferencia por CPU usa la wheel de PyTorch para CPU; si despliegas en GPU, cambia a la base de PyTorch adecuada para tu dispositivo y valida el resultado.

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

Antes del primer arranque, construye la imagen y descarga los modelos de versión fija en el volumen de modelos; después inicia la aplicación:

```sh
docker compose build
docker compose run --rm app python /app/scripts/download-models.py
docker compose up -d
```

Compose solo inicia un servicio de aplicación y expone `127.0.0.1:8080` al host. La entrada de acceso público debe proveer HTTPS mediante un proxy inverso externo que reenvíe las solicitudes a ese puerto. Los datos de SQLite están en el volumen `laya-data` y los modelos en el volumen `laya-models`. La máquina de compilación necesita acceso a PyPI, al índice de paquetes PyTorch para CPU y al registry de npm; al arrancar una imagen ya compilada no hace falta descargar código fuente ni dependencias.

Si un proxy inverso 1Panel existente provee el HTTPS público, reenvía las solicitudes del dominio a `127.0.0.1:8080` del host y asegúrate de que `LAYA_PUBLIC_ORIGIN` coincida con el dominio HTTPS real. El proxy inverso no forma parte del contenedor de aplicación de este proyecto.

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

Abre `http://127.0.0.1:5173` e inicia sesión. Vite redirige `/internal` y `/v1` al puerto local 8000; en producción el frontend compilado lo sigue sirviendo el mismo contenedor de FastAPI. Si solo quieres un proceso local, ejecuta primero `pnpm build` en `frontend/`, establece `LAYA_PUBLIC_ORIGIN` en `http://127.0.0.1:8000`, arranca Uvicorn y abre el puerto 8000.

La consola admite chino simplificado, English, 繁體中文 y español. Puedes cambiar el idioma tanto en la página de inicio de sesión como en la barra superior una vez dentro; en la primera visita se elige el idioma del navegador y la elección manual se guarda en el navegador actual.

## Llamar a la API

Crea una clave en la página **API Keys** tras iniciar sesión en la consola. La clave completa solo se muestra una vez, en la respuesta de creación.

```sh
curl -X POST https://console.example.com/v1/systemone \
  -H 'Authorization: Bearer ***' \
  -H 'Content-Type: application/json' \
  -d '{"state":{"message":"I was charged twice"},"questions":{"refund":{"type":"noul","instructions":"Does the customer ask for a refund?"}}}'
```

En la solicitud, `state` puede ser una cadena, un objeto JSON o un array; `questions` es un mapa de identificadores de pregunta no vacío que admite `noul`, `choice` y `score`; `model` admite `auto` (predeterminado), `english`, `multilingual` o `typed-decisions`. La respuesta conserva `answers`, `model` y `usage` de upstream. Los errores usan `detail.code` y `detail.message`. Una clave no válida devuelve 401, un fallo de validación 422 y un modelo no disponible 503. El Playground de la consola usa la sesión de administrador y se registra como una fuente de consumo independiente.

## Datos y mantenimiento

SQLite está en modo WAL; al hacer copias de seguridad debes detener primero la aplicación y después copiar el archivo de base de datos o usar la API de copia de seguridad de SQLite, para no perder los datos del WAL. Para restaurar, detén la aplicación, sustituye la base de datos dentro del volumen persistente y vuelve a iniciar. Al actualizar Laya, actualiza el SHA completo en `scripts/check-upstream.sh` y en el Dockerfile, vuelve a chekear `laya/`, ejecuta las pruebas y haz una prueba de humo con modelos reales.

```sh
.venv/bin/python -m pytest backend/tests -q
git ls-files laya/
```

El segundo comando no debe producir salida.

Tras el despliegue, se recomienda visitar primero `GET /health/ready` para confirmar que los archivos de modelo están listos y, a continuación, iniciar sesión en la consola y lanzar una solicitud de prueba desde el Playground para comprobar que la inferencia real y las respuestas funcionan correctamente.
