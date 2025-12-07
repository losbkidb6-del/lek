import os, shutil, asyncio, logging, re
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("TOKEN")

# Buscar en Deezer usando su API pública (no requiere login
async def buscar_en_deezer(query):
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.deezer.com/search?q={query}&limit=10") as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("data", [])
    return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Envía:\n• Un enlace de Deezer/Spotify/YouTube\n• O escribe directamente el nombre del artista, álbum o canción\n\n"
        "Calidad actual: FLAC (cambia con /mp3 o /flac)"
    )

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()

    # Si parece enlace → descargar directo
    if texto.startswith(("http://", "www.", "deezer.", "spotify.", "open.spotify.", "soundcloud.", "youtube.", "youtu.be")):
        await descargar_enlace(update, context, texto)
        return

    # Si NO es enlace → buscar en Deezer
    await update.message.reply_text("Buscando en Deezer…")
    resultados = await buscar_en_deezer(texto)

    if not resultados:
        await update.message.reply_text("No encontré nada con ese nombre")
        return

    keyboard = []
    for item in resultados[:10]:  # máximo 10 resultados
        tipo = item["type"]
        titulo = item["title"] if tipo == "track" else item["title"]
        artista = item["artist"]["name"]
        url = item["link"]

        emoji = "🎵" if tipo == "track" else "💿" if tipo == "album" else "🎤"
        texto_boton = f"{emoji} {artista} - {titulo}" if tipo == "track" else f"{emoji} {titulo} – {artista}"

        keyboard.append([InlineKeyboardButton(texto_boton, callback_data=url)])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Elige lo que quieres descargar:", reply_markup=reply_markup)

async def boton_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = query.data
    await query.edit_message_text(f"Descargando:\n{url}")
    # Reusamos la misma función de descarga por enlace
    await descargar_enlace(query, context, url)

async def descargar_enlace(update_or_query, context, url):
    # Detectamos si es mensaje o callback
    if hasattr(update_or_query, "message"):
        mensaje = update_or_query.message
    else:
        mensaje = update_or_query.message

    fmt = context.user_data.get("fmt", "flac")
    status_msg = await mensaje.reply_text("Descargando con streamrip…")

    carpeta = Path(f"tmp_{mensaje.from_user.id}_{asyncio.current_task().get_name()[:8]}")
    carpeta.mkdir(exist_ok=True)

    try:
        proc = await asyncio.create_subprocess_exec(
            "rip", "url", url, "--config-folder", str(carpeta), "--format", fmt,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        archivos_enviados = 0
        for root, _, files in os.walk(carpeta):
            for file in sorted(files):
                if file.endswith((".flac", ".mp3")):
                    path = Path(root) / file
                    if path.stat().st_size > 49_000_000:
                        await status_msg.edit_text("Archivo muy grande, lo salto…")
                        continue
                    with open(path, "rb") as f:
                        await mensaje.reply_audio(
                            audio=f,
                            title=file.rsplit(".", 1)[0],
                            caption=f"Calidad: {fmt.upper()}"
                        )
                    archivos_enviados += 1

        if archivos_enviados == 0:
            await status_msg.edit_text("No se pudo descargar nada o el contenido está bloqueado")
        else:
            await status_msg.edit_text(f"Terminado! Envié {archivos_enviados} archivos")
    except Exception as e:
        await status_msg.edit_text(f"Error: {e}")
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)

async def cambiar_calidad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fmt = "flac" if update.message.text == "/flac" else "mp3"
    context.user_data["fmt"] = fmt
    await update.message.reply_text(f"Calidad cambiada a {fmt.upper()}")

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["flac", "mp3"], cambiar_calidad))
    app.add_handler(CallbackQueryHandler(boton_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))

    print("Bot con búsqueda por nombre activo!")
    app.run_polling()

if __name__ == "__main__":
    main()