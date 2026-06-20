# Bot de aviso de stock - Barras de sonido Samsung Argentina

Chequea 2 veces por día si hay stock de estos modelos y te avisa por Telegram
apenas alguno pase de "sin stock" a "con stock":

- Barra de Sonido HW-B450
- Barra de Sonido HW-C450
- Barra de Sonido HW-B555

Corre gratis en GitHub Actions (no necesitás tener ninguna PC prendida).

---

## Paso 1: Crear el bot de Telegram (3 minutos)

1. Abrí Telegram y buscá el usuario **@BotFather**.
2. Mandale `/newbot`.
3. Elegí un nombre (lo que quieras) y un username que termine en `bot`
   (ej: `samsung_stock_franco_bot`).
4. BotFather te va a dar un **token**, algo como:
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   Guardalo, es el `TELEGRAM_BOT_TOKEN`.
5. Ahora buscá tu bot por el username que le pusiste y mandale cualquier
   mensaje (ej: "hola") para iniciar la conversación.
6. Para conseguir tu `chat_id`, abrí en el navegador (reemplazando el token):
   ```
   https://api.telegram.org/bot<TU_TOKEN>/getUpdates
   ```
   Vas a ver un JSON. Buscá `"chat":{"id":NUMERO, ...}` — ese `NUMERO`
   (puede ser negativo) es tu `TELEGRAM_CHAT_ID`.

   Si te devuelve `"result":[]` vacío, es porque no le mandaste un mensaje
   primero al bot. Mandale un mensaje y volvé a refrescar esa URL.

## Paso 2: Subir este proyecto a GitHub

1. Creá un repositorio nuevo en GitHub (puede ser privado).
2. Subí estos archivos tal cual están (incluida la carpeta `.github/workflows`).

   Si nunca usaste git, lo más fácil es:
   - Entrá a github.com → "New repository"
   - Subí los archivos directamente arrastrándolos desde la web ("uploading
     an existing file")

## Paso 3: Configurar los secrets

Esto es para que el token de Telegram no quede expuesto en el código:

1. En tu repo de GitHub: **Settings → Secrets and variables → Actions**
2. Click en **New repository secret**, creá:
   - `TELEGRAM_BOT_TOKEN` → pegá el token de BotFather
   - `TELEGRAM_CHAT_ID` → pegá tu chat id

## Paso 4: Probarlo

1. Andá a la pestaña **Actions** de tu repo.
2. Seleccioná el workflow "Chequeo de stock - Barras de sonido Samsung".
3. Click en **Run workflow** (botón a la derecha) para probarlo manualmente,
   sin esperar al horario programado.
4. Mirá los logs: te va a decir el estado de cada producto.
5. Como ya viste que B555 está sin stock, no deberías recibir mensaje en esa
   corrida (todo bien, es el comportamiento esperado). El bot solo avisa
   cuando un producto *pasa* a tener stock, no en cada chequeo.

## ¿Cómo sé que funciona de verdad?

Para forzar una prueba de aviso real, podés editar momentáneamente
`check_stock.py` y cambiar el marcador `OUT_OF_STOCK_MARKER` por un texto
que sepas que SÍ está en el HTML actual (eso simula "no hay marca de sin
stock" → en stock). O simplemente esperá a que algún modelo efectivamente
recupere stock.

## Horarios

Por defecto corre a las 12:00 y 20:00 (hora Argentina). Para cambiarlos,
editá los valores `cron` en `.github/workflows/check-stock.yml` (están en
UTC, Argentina es UTC-3 todo el año).

## Agregar o quitar modelos

Editá la lista `PRODUCTS` en `check_stock.py`. Cada producto necesita:
- `name`: como querés que aparezca en el aviso
- `url`: la URL de la página del producto en shop.samsung.com/ar o
  samsung.com/ar

## Notas técnicas

- El script descarga el HTML de cada página y busca el texto exacto
  `"Producto sin stock"`. Si no aparece, asume que hay stock.
- Esto puede romperse si Samsung cambia el texto o la estructura de su
  sitio. Si un día notás que el bot deja de avisar correctamente, avisame
  y ajustamos el detector.
- El estado (`stock_state.json`) se guarda en el propio repo para que el
  bot recuerde qué ya avisó y no te mande el mismo mensaje en cada corrida.
