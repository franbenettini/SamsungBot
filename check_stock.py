#!/usr/bin/env python3
"""
Bot de aviso de stock - Barras de sonido Samsung Argentina

Chequea si ciertos modelos de barra de sonido tienen stock en
shop.samsung.com/ar y samsung.com/ar, y en CADA corrida te manda por
Telegram un resumen del estado de los 3 modelos (con o sin stock).

Si alguno pasó de "sin stock" a "con stock" desde la corrida anterior,
ese ítem se destaca arriba de todo con 🟢 para que no se pierda entre
el resto.

El estado anterior se guarda en stock_state.json, que el workflow
de GitHub Actions commitea de vuelta al repo en cada corrida.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

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

# Frase que aparece en la página cuando el producto NO tiene stock.
# Si esta frase NO aparece en el HTML, asumimos que hay stock.
OUT_OF_STOCK_MARKER = "Producto sin stock"

STATE_FILE = Path(__file__).parent / "stock_state.json"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def check_product_in_stock(url: str) -> bool | None:
    """
    Devuelve True si hay stock, False si no hay, None si no se pudo
    determinar (error de red, página caída, etc).
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [ERROR] No se pudo descargar {url}: {exc}")
        return None

    html = resp.text
    if OUT_OF_STOCK_MARKER in html:
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
    results = []  # (product, in_stock, just_changed_to_in_stock)
    any_check_failed = False

    for product in PRODUCTS:
        name = product["name"]
        url = product["url"]
        print(f"Chequeando: {name} -> {url}")

        in_stock = check_product_in_stock(url)

        if in_stock is None:
            any_check_failed = True
            # No se pudo chequear, no tocamos el estado guardado,
            # pero lo mostramos igual en el resumen como "no se pudo chequear".
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