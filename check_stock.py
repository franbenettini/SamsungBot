#!/usr/bin/env python3
"""
Bot de aviso de stock - Barras de sonido Samsung Argentina

Chequea si ciertos modelos de barra de sonido tienen stock en
shop.samsung.com/ar y samsung.com/ar, y en CADA corrida te manda por
Telegram un resumen del estado de los 3 modelos (con o sin stock).

Si alguno pasó de "sin stock" a "con stock" desde la corrida anterior,
ese ítem se destaca arriba de todo con 🟢 para que no se pierda entre
el resto.

IMPORTANTE: estas páginas son aplicaciones de una sola página (SPA/React,
motor VTEX). El estado real de stock (botón de compra vs. formulario de
"avisame cuando haya stock") se arma con JavaScript DESPUÉS de la carga
inicial. Por eso este script usa Playwright (un navegador headless real)
en vez de simplemente descargar el HTML con requests: si usáramos
requests, nunca veríamos el contenido que JS agrega y el chequeo de stock
sería incorrecto.

El estado anterior se guarda en stock_state.json, que el workflow
de GitHub Actions commitea de vuelta al repo en cada corrida.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Configuración: agregá / quitá modelos acá
# ---------------------------------------------------------------------------
PRODUCTS = [
    {
        "name": "Barra de Sonido HW-B450",
        "url": "https://shop.samsung.com/ar/barra-de-sonido-hw-b450-con-subwoofer/p?skuId=140026",
    },
    {
        "name": "Barra de Sonido HW-C450",
        "url": "https://shop.samsung.com/ar/barra-de-sonido-2-1ch-hw-c450/p",
    },
    {
        "name": "Barra de Sonido HW-B555",
        "url": "https://www.samsung.com/ar/audio-devices/soundbar/b550-black-hw-b555-zb/",
    },
]

# Frases que aparecen en la página cuando el producto NO tiene stock.
# Si CUALQUIERA de estas frases aparece en el HTML ya renderizado, asumimos
# que no hay stock, sin importar lo que diga el metadato "instock" (que no
# refleja el stock real disponible para compra).
OUT_OF_STOCK_MARKERS = [
    "Producto sin stock",
    "Dejanos tus datos para contactarte cuando vuelva a estar disponible",
    "Recibí una alerta de stock",
    "We will email you when inventory is added",
]

STATE_FILE = Path(__file__).parent / "stock_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def check_product_in_stock(url: str, browser) -> bool | None:
    """
    Abre la página con un navegador headless, espera a que JS termine de
    renderizar el contenido, y busca las frases de "sin stock".

    Devuelve True si hay stock, False si no hay, None si no se pudo
    determinar (error de red, timeout, página caída, etc).
    """
    page = None
    try:
        page = browser.new_page(user_agent=USER_AGENT, locale="es-AR")
        # OJO: no usamos wait_until="networkidle" porque estas páginas
        # (Samsung/VTEX) tienen scripts de tracking, chat, banners, etc.
        # que siguen pidiendo cosas a la red sin parar, y networkidle
        # nunca llega a cumplirse -> termina en timeout siempre.
        # En cambio esperamos a que el HTML esté cargado y le damos un
        # margen fijo para que los componentes de React terminen de
        # pintar el estado real de stock.
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(6000)
        html = page.content()
    except Exception as exc:
        print(f"  [ERROR] No se pudo cargar {url}: {exc}")
        return None
    finally:
        if page is not None:
            page.close()

    for marker in OUT_OF_STOCK_MARKERS:
        if marker in html:
            return False
    return True


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [WARN] Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID, no se envía mensaje.")
        print(f"  Mensaje que se hubiera enviado:\n{text}")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(api_url, json=payload, timeout=20)
        r.raise_for_status()
        print("  [OK] Aviso enviado por Telegram.")
    except requests.RequestException as exc:
        print(f"  [ERROR] No se pudo enviar el mensaje de Telegram: {exc}")


def main() -> None:
    state = load_state()
    results = []  # (product, in_stock_or_None, just_changed, had_error)
    any_check_failed = False

    with sync_playwright() as p:
        browser = p.chromium.launch()

        for product in PRODUCTS:
            name = product["name"]
            url = product["url"]
            print(f"Chequeando: {name} -> {url}")

            in_stock = check_product_in_stock(url, browser)

            if in_stock is None:
                any_check_failed = True
                previous = state.get(url, {}).get("in_stock")
                results.append((product, previous, False, True))
                continue

            previous = state.get(url, {}).get("in_stock")
            just_changed = in_stock and previous is not True

            status_str = "CON STOCK" if in_stock else "sin stock"
            print(f"  -> {status_str}")

            results.append((product, in_stock, just_changed, False))

            state[url] = {
                "name": name,
                "in_stock": in_stock,
                "last_checked": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

        browser.close()

    save_state(state)

    # --- Armar el mensaje de resumen ---
    newly_in_stock = [p for p, st, just, err in results if just]
    in_stock_now = [p for p, st, just, err in results if st is True]
    out_of_stock_now = [p for p, st, just, err in results if st is False]
    unknown_now = [p for p, st, just, err in results if err]

    timestamp = time.strftime("%d/%m/%Y %H:%M")
    lines = [f"📋 <b>Chequeo de stock</b> - {timestamp}", ""]

    if newly_in_stock:
        lines.append("🟢 <b>¡Acaba de entrar en stock!</b>")
        for p in newly_in_stock:
            lines.append(f"• <b>{p['name']}</b>\n  {p['url']}")
        lines.append("")

    lines.append("<b>Estado actual:</b>")
    for p in in_stock_now:
        lines.append(f"✅ {p['name']} - con stock")
    for p in out_of_stock_now:
        lines.append(f"⛔ {p['name']} - sin stock")
    for p in unknown_now:
        lines.append(f"⚠️ {p['name']} - no se pudo chequear")

    message = "\n".join(lines)
    send_telegram_message(message)

    if any_check_failed:
        print("Atención: alguna URL no se pudo chequear en esta corrida.")


if __name__ == "__main__":
    sys.exit(main())