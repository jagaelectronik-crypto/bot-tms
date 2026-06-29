import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Almacenamiento ──────────────────────────────────────────────────────────────
DATA_FILE = "pendientes.json"

def cargar():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_items(user_id: str):
    data = cargar()
    return data.get(user_id, [])

def set_user_items(user_id: str, items: list):
    data = cargar()
    data[user_id] = items
    guardar(data)

# ── Estados de conversación ─────────────────────────────────────────────────────
TITULO, CATEGORIA, PRIORIDAD, FECHA, DESCRIPCION = range(5)

# ── Emojis y etiquetas ──────────────────────────────────────────────────────────
PRIORIDAD_EMOJI = {"alta": "🔴", "media": "🟡", "baja": "🟢"}
CATEGORIA_EMOJI = {"campo": "🔧", "reunion": "📅", "admin": "📋", "ticket": "🎫"}
PRIORIDAD_LABEL = {"alta": "Alta", "media": "Media", "baja": "Baja"}
CATEGORIA_LABEL = {"campo": "Campo/Técnica", "reunion": "Reunión", "admin": "Admin", "ticket": "Ticket"}

# ── Helpers ─────────────────────────────────────────────────────────────────────
def formatear_item(i, idx):
    done = "✅" if i.get("done") else "⬜"
    pri = PRIORIDAD_EMOJI.get(i["prioridad"], "")
    cat = CATEGORIA_EMOJI.get(i["categoria"], "")
    fecha = f"\n   📆 {i['fecha']}" if i.get("fecha") else ""
    desc = f"\n   💬 {i['descripcion']}" if i.get("descripcion") else ""
    tachado = "~" if i.get("done") else ""
    return f"{done} *{tachado}{idx+1}. {i['titulo']}{tachado}*  {pri}{cat}{fecha}{desc}"

def menu_principal():
    teclado = [
        [InlineKeyboardButton("➕ Nuevo pendiente", callback_data="nuevo")],
        [
            InlineKeyboardButton("📋 Ver todos", callback_data="ver_todos"),
            InlineKeyboardButton("🔴 Alta prioridad", callback_data="ver_alta"),
        ],
        [
            InlineKeyboardButton("🔧 Campo", callback_data="ver_campo"),
            InlineKeyboardButton("📅 Reuniones", callback_data="ver_reunion"),
        ],
        [
            InlineKeyboardButton("📋 Admin", callback_data="ver_admin"),
            InlineKeyboardButton("🎫 Tickets", callback_data="ver_ticket"),
        ],
        [InlineKeyboardButton("📊 Resumen del día", callback_data="resumen")],
    ]
    return InlineKeyboardMarkup(teclado)

# ── Comando /start ───────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nombre = update.effective_user.first_name
    texto = (
        f"👋 ¡Hola *{nombre}*\\! Soy tu asistente de pendientes para *TMS, C\\.A\\.* 🛠️\n\n"
        "Puedo ayudarte a gestionar:\n"
        "🔧 Actividades de campo \\| 📅 Reuniones\n"
        "📋 Tareas admin \\| 🎫 Tickets FTTH\n\n"
        "¿Qué hacemos hoy\\?"
    )
    await update.message.reply_text(texto, parse_mode="MarkdownV2", reply_markup=menu_principal())

# ── Comando /menu ────────────────────────────────────────────────────────────────
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Menú principal:", reply_markup=menu_principal())

# ── Flujo: agregar pendiente ─────────────────────────────────────────────────────
async def nuevo_pendiente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.reply_text("📝 *¿Cuál es el título del pendiente?*\n\nEj: Revisión splitter zona norte", parse_mode="Markdown")
    return TITULO

async def recibir_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["titulo"] = update.message.text.strip()
    teclado = [[
        InlineKeyboardButton("🔧 Campo", callback_data="cat_campo"),
        InlineKeyboardButton("📅 Reunión", callback_data="cat_reunion"),
    ], [
        InlineKeyboardButton("📋 Admin", callback_data="cat_admin"),
        InlineKeyboardButton("🎫 Ticket", callback_data="cat_ticket"),
    ]]
    await update.message.reply_text("📂 *¿Categoría?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(teclado))
    return CATEGORIA

async def recibir_categoria(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["categoria"] = query.data.replace("cat_", "")
    teclado = [[
        InlineKeyboardButton("🔴 Alta", callback_data="pri_alta"),
        InlineKeyboardButton("🟡 Media", callback_data="pri_media"),
        InlineKeyboardButton("🟢 Baja", callback_data="pri_baja"),
    ]]
    await query.message.reply_text("⚡ *¿Prioridad?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(teclado))
    return PRIORIDAD

async def recibir_prioridad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["prioridad"] = query.data.replace("pri_", "")
    teclado = [[InlineKeyboardButton("⏭ Sin fecha", callback_data="sin_fecha")]]
    await query.message.reply_text(
        "📆 *¿Fecha?* Escríbela así: `25/07/2025`\nO pulsa el botón para omitirla.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(teclado)
    )
    return FECHA

async def recibir_fecha_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fecha"] = update.message.text.strip()
    await update.message.reply_text("💬 *¿Alguna descripción o nota?* (o escribe `no`)", parse_mode="Markdown")
    return DESCRIPCION

async def recibir_fecha_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["fecha"] = ""
    await query.message.reply_text("💬 *¿Alguna descripción o nota?* (o escribe `no`)", parse_mode="Markdown")
    return DESCRIPCION

async def recibir_descripcion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    context.user_data["descripcion"] = "" if texto.lower() == "no" else texto

    uid = str(update.effective_user.id)
    items = get_user_items(uid)
    nuevo = {
        "id": int(datetime.now().timestamp() * 1000),
        "titulo": context.user_data["titulo"],
        "categoria": context.user_data["categoria"],
        "prioridad": context.user_data["prioridad"],
        "fecha": context.user_data.get("fecha", ""),
        "descripcion": context.user_data.get("descripcion", ""),
        "done": False,
        "creado": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }
    items.append(nuevo)
    set_user_items(uid, items)

    pri = PRIORIDAD_EMOJI[nuevo["prioridad"]]
    cat = CATEGORIA_EMOJI[nuevo["categoria"]]
    await update.message.reply_text(
        f"✅ *Pendiente guardado\\!*\n\n{pri}{cat} *{nuevo['titulo']}*",
        parse_mode="MarkdownV2", reply_markup=menu_principal()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.", reply_markup=menu_principal())
    return ConversationHandler.END

# ── Ver pendientes ───────────────────────────────────────────────────────────────
async def ver_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE, filtro=None):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    items = get_user_items(uid)

    if filtro == "alta":
        vis = [i for i in items if i["prioridad"] == "alta" and not i["done"]]
        titulo = "🔴 Alta prioridad"
    elif filtro in ("campo", "reunion", "admin", "ticket"):
        vis = [i for i in items if i["categoria"] == filtro]
        titulo = f"{CATEGORIA_EMOJI[filtro]} {CATEGORIA_LABEL[filtro]}"
    else:
        vis = items
        titulo = "📋 Todos los pendientes"

    if not vis:
        await query.message.reply_text(f"{titulo}\n\n_Sin pendientes en esta categoría._", parse_mode="Markdown", reply_markup=menu_principal())
        return

    # Ordenar: no completados primero, luego por prioridad
    orden = {"alta": 0, "media": 1, "baja": 2}
    vis_sorted = sorted(vis, key=lambda x: (x["done"], orden.get(x["prioridad"], 9)))
    pendientes_reales = [i for i in vis_sorted if not i["done"]]

    texto = f"*{titulo}* — {len(pendientes_reales)} activo(s)\n\n"
    texto += "\n\n".join(formatear_item(i, idx) for idx, i in enumerate(vis_sorted))

    # Botones de acción
    teclado = []
    for idx, it in enumerate(vis_sorted):
        if not it["done"]:
            lbl = f"✅ Completar: {it['titulo'][:25]}"
            teclado.append([InlineKeyboardButton(lbl, callback_data=f"done_{it['id']}")])
        else:
            lbl = f"↩ Reabrir: {it['titulo'][:25]}"
            teclado.append([InlineKeyboardButton(lbl, callback_data=f"reopen_{it['id']}")])
        teclado.append([InlineKeyboardButton(f"🗑 Eliminar: {it['titulo'][:22]}", callback_data=f"del_{it['id']}")])

    teclado.append([InlineKeyboardButton("🏠 Menú", callback_data="inicio")])

    await query.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(teclado))

# ── Resumen del día ──────────────────────────────────────────────────────────────
async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    items = get_user_items(uid)
    total = len(items)
    activos = len([i for i in items if not i["done"]])
    completados = len([i for i in items if i["done"]])
    altas = len([i for i in items if i["prioridad"] == "alta" and not i["done"]])
    hoy = datetime.now().strftime("%d/%m/%Y")

    texto = (
        f"📊 *Resumen — {hoy}*\n\n"
        f"📌 Total: {total} pendientes\n"
        f"⬜ Activos: {activos}\n"
        f"✅ Completados: {completados}\n"
        f"🔴 Alta prioridad activa: {altas}\n\n"
    )

    por_cat = {}
    for i in items:
        if not i["done"]:
            c = i["categoria"]
            por_cat[c] = por_cat.get(c, 0) + 1
    if por_cat:
        texto += "*Por categoría (activos):*\n"
        for cat, cnt in por_cat.items():
            texto += f"  {CATEGORIA_EMOJI.get(cat,'')} {CATEGORIA_LABEL.get(cat, cat)}: {cnt}\n"

    await query.message.reply_text(texto, parse_mode="Markdown", reply_markup=menu_principal())

# ── Acciones sobre items ─────────────────────────────────────────────────────────
async def accion_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = str(update.effective_user.id)
    items = get_user_items(uid)

    if data.startswith("done_") or data.startswith("reopen_"):
        item_id = int(data.split("_", 1)[1])
        for it in items:
            if it["id"] == item_id:
                it["done"] = not it["done"]
                break
        set_user_items(uid, items)
        estado = "completado ✅" if next((i["done"] for i in items if i["id"] == item_id), False) else "reabierto ↩"
        titulo = next((i["titulo"] for i in items if i["id"] == item_id), "")
        await query.message.reply_text(f"*{titulo}* marcado como {estado}.", parse_mode="Markdown", reply_markup=menu_principal())

    elif data.startswith("del_"):
        item_id = int(data.split("_")[1])
        titulo = next((i["titulo"] for i in items if i["id"] == item_id), "")
        items = [i for i in items if i["id"] != item_id]
        set_user_items(uid, items)
        await query.message.reply_text(f"🗑 *{titulo}* eliminado.", parse_mode="Markdown", reply_markup=menu_principal())

    elif data == "inicio":
        await query.message.reply_text("📌 Menú principal:", reply_markup=menu_principal())

    elif data == "nuevo":
        context.user_data.clear()
        await query.message.reply_text("📝 *¿Cuál es el título del pendiente?*", parse_mode="Markdown")
        return TITULO

    elif data == "ver_todos":
        await ver_pendientes(update, context, None)
    elif data == "ver_alta":
        await ver_pendientes(update, context, "alta")
    elif data == "ver_campo":
        await ver_pendientes(update, context, "campo")
    elif data == "ver_reunion":
        await ver_pendientes(update, context, "reunion")
    elif data == "ver_admin":
        await ver_pendientes(update, context, "admin")
    elif data == "ver_ticket":
        await ver_pendientes(update, context, "ticket")
    elif data == "resumen":
        await resumen(update, context)

# ── Main ─────────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("Falta la variable de entorno TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(nuevo_pendiente, pattern="^nuevo$")],
        states={
            TITULO: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_titulo)],
            CATEGORIA: [CallbackQueryHandler(recibir_categoria, pattern="^cat_")],
            PRIORIDAD: [CallbackQueryHandler(recibir_prioridad, pattern="^pri_")],
            FECHA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_fecha_texto),
                CallbackQueryHandler(recibir_fecha_skip, pattern="^sin_fecha$"),
            ],
            DESCRIPCION: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_descripcion)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(accion_item))

    print("🤖 Bot TMS iniciado...")
    app.run_polling()

if __name__ == "__main__":
    main()
