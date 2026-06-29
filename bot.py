import os
import json
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, ConversationHandler, filters,
    JobQueue
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Caracas")
DATA_FILE = "pendientes.json"
USERS_FILE = "usuarios.json"

# ── Almacenamiento ──────────────────────────────────────────────────────────────
def cargar():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def guardar(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_items(user_id: str):
    return cargar().get(user_id, [])

def set_user_items(user_id: str, items: list):
    data = cargar()
    data[user_id] = items
    guardar(data)

def cargar_usuarios():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def registrar_usuario(user_id: str, chat_id: int, nombre: str):
    usuarios = cargar_usuarios()
    usuarios[user_id] = {"chat_id": chat_id, "nombre": nombre}
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(usuarios, f, ensure_ascii=False, indent=2)

# ── Estados ─────────────────────────────────────────────────────────────────────
TITULO, CATEGORIA, PRIORIDAD, FECHA, DESCRIPCION = range(5)

# ── Etiquetas ───────────────────────────────────────────────────────────────────
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

def esta_vencido(item):
    """Retorna True si el item tiene fecha y ya pasó."""
    if not item.get("fecha") or item.get("done"):
        return False
    try:
        partes = item["fecha"].replace("-", "/").split("/")
        if len(partes) == 3:
            # Soporta dd/mm/yyyy y yyyy-mm-dd
            if len(partes[0]) == 4:
                anio, mes, dia = int(partes[0]), int(partes[1]), int(partes[2])
            else:
                dia, mes, anio = int(partes[0]), int(partes[1]), int(partes[2])
            fecha_item = datetime(anio, mes, dia, tzinfo=TZ)
            return datetime.now(TZ) > fecha_item
    except:
        pass
    return False

def menu_principal():
    return InlineKeyboardMarkup([
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
    ])

# ── Recordatorios ────────────────────────────────────────────────────────────────
async def recordatorio_manana(context: ContextTypes.DEFAULT_TYPE):
    """Recordatorio matutino 8 AM — resumen completo de activos."""
    usuarios = cargar_usuarios()
    for uid, info in usuarios.items():
        items = get_user_items(uid)
        activos = [i for i in items if not i["done"]]
        if not activos:
            continue
        orden = {"alta": 0, "media": 1, "baja": 2}
        activos.sort(key=lambda x: orden.get(x["prioridad"], 9))
        hoy = datetime.now(TZ).strftime("%d/%m/%Y")
        texto = f"☀️ *Buenos días, {info['nombre']}!*\n📅 {hoy}\n\n"
        texto += f"Tienes *{len(activos)} pendiente(s)* activo(s):\n\n"
        for idx, it in enumerate(activos):
            pri = PRIORIDAD_EMOJI.get(it["prioridad"], "")
            cat = CATEGORIA_EMOJI.get(it["categoria"], "")
            fecha = f" — 📆 {it['fecha']}" if it.get("fecha") else ""
            venc = " ⚠️ *VENCIDO*" if esta_vencido(it) else ""
            texto += f"{pri}{cat} *{it['titulo']}*{fecha}{venc}\n"
        texto += "\n_Usa /menu para gestionar tus pendientes._"
        try:
            await context.bot.send_message(
                chat_id=info["chat_id"],
                text=texto,
                parse_mode="Markdown",
                reply_markup=menu_principal()
            )
        except Exception as e:
            logger.error(f"Error enviando recordatorio matutino a {uid}: {e}")

async def recordatorio_tarde(context: ContextTypes.DEFAULT_TYPE):
    """Recordatorio vespertino 3 PM — solo pendientes sin completar."""
    usuarios = cargar_usuarios()
    for uid, info in usuarios.items():
        items = get_user_items(uid)
        activos = [i for i in items if not i["done"]]
        if not activos:
            continue
        orden = {"alta": 0, "media": 1, "baja": 2}
        activos.sort(key=lambda x: orden.get(x["prioridad"], 9))
        texto = f"🕒 *Recordatorio de tarde, {info['nombre']}*\n\n"
        texto += f"Aún tienes *{len(activos)} pendiente(s)* sin completar:\n\n"
        for it in activos:
            pri = PRIORIDAD_EMOJI.get(it["prioridad"], "")
            cat = CATEGORIA_EMOJI.get(it["categoria"], "")
            venc = " ⚠️ *VENCIDO*" if esta_vencido(it) else ""
            texto += f"{pri}{cat} {it['titulo']}{venc}\n"
        texto += "\n_¿Lograste avanzar hoy? Marca los completados con /menu_"
        try:
            await context.bot.send_message(
                chat_id=info["chat_id"],
                text=texto,
                parse_mode="Markdown",
                reply_markup=menu_principal()
            )
        except Exception as e:
            logger.error(f"Error enviando recordatorio vespertino a {uid}: {e}")

async def recordatorio_alta_prioridad(context: ContextTypes.DEFAULT_TYPE):
    """Alerta cada hora si hay items de alta prioridad vencidos."""
    usuarios = cargar_usuarios()
    for uid, info in usuarios.items():
        items = get_user_items(uid)
        vencidos_alta = [i for i in items if not i["done"] and i["prioridad"] == "alta" and esta_vencido(i)]
        if not vencidos_alta:
            continue
        texto = f"🚨 *¡ALERTA! Tienes {len(vencidos_alta)} pendiente(s) de ALTA prioridad vencido(s):*\n\n"
        for it in vencidos_alta:
            texto += f"🔴🔧 *{it['titulo']}*\n   📆 Fecha: {it.get('fecha','Sin fecha')}\n\n"
        texto += "_Atiéndelos cuanto antes o márcalos como completados._"
        try:
            await context.bot.send_message(
                chat_id=info["chat_id"],
                text=texto,
                parse_mode="Markdown",
                reply_markup=menu_principal()
            )
        except Exception as e:
            logger.error(f"Error enviando alerta alta prioridad a {uid}: {e}")

# ── /start ───────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    registrar_usuario(str(user.id), update.effective_chat.id, user.first_name)
    texto = (
        f"👋 ¡Hola *{user.first_name}*! Soy tu asistente de pendientes para *TMS, C.A.* 🛠️\n\n"
        "Puedo ayudarte a gestionar:\n"
        "🔧 Actividades de campo | 📅 Reuniones\n"
        "📋 Tareas admin | 🎫 Tickets FTTH\n\n"
        "🔔 *Recibirás recordatorios automáticos:*\n"
        "   ☀️ 8:00 AM — Resumen matutino\n"
        "   🕒 3:00 PM — Recordatorio vespertino\n"
        "   🚨 Alerta si tienes alta prioridad vencida\n\n"
        "✅ Marca pendientes como *completados* para sacarlos de los recordatorios sin perder el historial.\n\n"
        "¿Qué hacemos hoy?"
    )
    await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=menu_principal())

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📌 Menú principal:", reply_markup=menu_principal())

# ── Flujo nuevo pendiente ────────────────────────────────────────────────────────
async def nuevo_pendiente_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📝 *¿Cuál es el título del pendiente?*\n\nEj: Revisión splitter zona norte", parse_mode="Markdown")
    return TITULO

async def nuevo_pendiente_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        "creado": datetime.now(TZ).strftime("%d/%m/%Y %H:%M"),
    }
    items.append(nuevo)
    set_user_items(uid, items)
    pri = PRIORIDAD_EMOJI[nuevo["prioridad"]]
    cat = CATEGORIA_EMOJI[nuevo["categoria"]]
    await update.message.reply_text(
        f"✅ *Pendiente guardado!*\n\n{pri}{cat} *{nuevo['titulo']}*\n\n"
        f"_Se incluirá en tus recordatorios automáticos hasta que lo marques como completado._",
        parse_mode="Markdown", reply_markup=menu_principal()
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

    orden = {"alta": 0, "media": 1, "baja": 2}
    vis_sorted = sorted(vis, key=lambda x: (x["done"], orden.get(x["prioridad"], 9)))
    activos = [i for i in vis_sorted if not i["done"]]

    texto = f"*{titulo}* — {len(activos)} activo(s)\n\n"
    texto += "\n\n".join(formatear_item(i, idx) for idx, i in enumerate(vis_sorted))

    teclado = []
    for it in vis_sorted:
        if not it["done"]:
            teclado.append([InlineKeyboardButton(f"✅ Completar: {it['titulo'][:26]}", callback_data=f"done_{it['id']}")])
        else:
            teclado.append([InlineKeyboardButton(f"↩ Reabrir: {it['titulo'][:28]}", callback_data=f"reopen_{it['id']}")])
        teclado.append([InlineKeyboardButton(f"🗑 Eliminar: {it['titulo'][:26]}", callback_data=f"del_{it['id']}")])
    teclado.append([InlineKeyboardButton("🏠 Menú", callback_data="inicio")])

    await query.message.reply_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(teclado))

# ── Resumen ──────────────────────────────────────────────────────────────────────
async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    items = get_user_items(uid)
    hoy = datetime.now(TZ).strftime("%d/%m/%Y")
    total = len(items)
    activos = len([i for i in items if not i["done"]])
    completados = len([i for i in items if i["done"]])
    altas = len([i for i in items if i["prioridad"] == "alta" and not i["done"]])
    vencidos = len([i for i in items if esta_vencido(i)])

    texto = (
        f"📊 *Resumen — {hoy}*\n\n"
        f"📌 Total registrados: {total}\n"
        f"⬜ Activos: {activos}\n"
        f"✅ Completados: {completados}\n"
        f"🔴 Alta prioridad activa: {altas}\n"
        f"⚠️ Vencidos: {vencidos}\n\n"
    )
    por_cat = {}
    for i in items:
        if not i["done"]:
            c = i["categoria"]
            por_cat[c] = por_cat.get(c, 0) + 1
    if por_cat:
        texto += "*Por categoría (activos):*\n"
        for cat, cnt in por_cat.items():
            texto += f"  {CATEGORIA_EMOJI.get(cat,'')} {CATEGORIA_LABEL.get(cat,cat)}: {cnt}\n"

    await query.message.reply_text(texto, parse_mode="Markdown", reply_markup=menu_principal())

# ── Acciones ─────────────────────────────────────────────────────────────────────
async def accion_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = str(update.effective_user.id)
    items = get_user_items(uid)

    if data.startswith("done_") or data.startswith("reopen_"):
        item_id = int(data.split("_", 1)[1])
        titulo, estado = "", ""
        for it in items:
            if it["id"] == item_id:
                it["done"] = not it["done"]
                titulo = it["titulo"]
                if it["done"]:
                    it["completado_en"] = datetime.now(TZ).strftime("%d/%m/%Y %H:%M")
                    estado = "completado ✅\n\n_Ya no aparecerá en tus recordatorios, pero quedará en tu historial._"
                else:
                    estado = "reabierto ↩\n\n_Volverá a aparecer en tus recordatorios._"
                break
        set_user_items(uid, items)
        await query.message.reply_text(f"*{titulo}* marcado como {estado}", parse_mode="Markdown", reply_markup=menu_principal())

    elif data.startswith("del_"):
        item_id = int(data.split("_")[1])
        titulo = next((i["titulo"] for i in items if i["id"] == item_id), "")
        items = [i for i in items if i["id"] != item_id]
        set_user_items(uid, items)
        await query.message.reply_text(f"🗑 *{titulo}* eliminado permanentemente.", parse_mode="Markdown", reply_markup=menu_principal())

    elif data == "inicio":
        await query.message.reply_text("📌 Menú principal:", reply_markup=menu_principal())
    elif data == "ver_todos":   await ver_pendientes(update, context, None)
    elif data == "ver_alta":    await ver_pendientes(update, context, "alta")
    elif data == "ver_campo":   await ver_pendientes(update, context, "campo")
    elif data == "ver_reunion": await ver_pendientes(update, context, "reunion")
    elif data == "ver_admin":   await ver_pendientes(update, context, "admin")
    elif data == "ver_ticket":  await ver_pendientes(update, context, "ticket")
    elif data == "resumen":     await resumen(update, context)

# ── Main ─────────────────────────────────────────────────────────────────────────
def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise ValueError("Falta la variable de entorno TELEGRAM_TOKEN")

    app = ApplicationBuilder().token(token).build()

    # Programar recordatorios
    jq: JobQueue = app.job_queue

    # ☀️ 8:00 AM hora Venezuela (UTC-4)
    jq.run_daily(recordatorio_manana, time=time(8, 0, tzinfo=TZ), name="manana")

    # 🕒 3:00 PM hora Venezuela
    jq.run_daily(recordatorio_tarde, time=time(15, 0, tzinfo=TZ), name="tarde")

    # 🚨 Alerta alta prioridad vencida — cada hora en jornada laboral (8 AM - 5 PM)
    for hora in range(8, 18):
        jq.run_daily(
            recordatorio_alta_prioridad,
            time=time(hora, 0, tzinfo=TZ),
            name=f"alta_prioridad_{hora}"
        )

    conv = ConversationHandler(
        entry_points=[
            CommandHandler("nuevo", nuevo_pendiente_cmd),
            CallbackQueryHandler(nuevo_pendiente_cb, pattern="^nuevo$"),
        ],
        states={
            TITULO:      [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_titulo)],
            CATEGORIA:   [CallbackQueryHandler(recibir_categoria, pattern="^cat_")],
            PRIORIDAD:   [CallbackQueryHandler(recibir_prioridad, pattern="^pri_")],
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

    print("🤖 Bot TMS con recordatorios iniciado...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
