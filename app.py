import sqlite3
import warnings
from datetime import datetime, timedelta, timezone

import libsql
import pandas as pd
import streamlit as st
from fpdf import FPDF

try:
    from zoneinfo import ZoneInfo
    TZ_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")
except Exception:
    TZ_ARGENTINA = timezone(timedelta(hours=-3))

DB_PATH = "chiarita.db"
MEDIOS_PAGO = [
    "Efectivo", "Transferencia", "Tarjeta de débito", "Tarjeta de crédito",
    "Fiado / Cuenta corriente", "Otro",
]

st.set_page_config(page_title="Chiarita Store - Stock y Finanzas", layout="wide", page_icon="🧺")

warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")


def ahora():
    return datetime.now(TZ_ARGENTINA).replace(tzinfo=None)


def _turso_credentials():
    try:
        url = st.secrets.get("TURSO_DATABASE_URL")
        token = st.secrets.get("TURSO_AUTH_TOKEN")
    except Exception:
        return None, None
    return url, token


def get_conn():
    turso_url, turso_token = _turso_credentials()
    if turso_url and turso_token:
        conn = libsql.connect(database=turso_url, auth_token=turso_token)
    else:
        conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
    except Exception:
        pass
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        nombre_negocio TEXT,
        telefono TEXT,
        direccion TEXT,
        dias_garantia INTEGER NOT NULL DEFAULT 10,
        ultimo_comprobante INTEGER NOT NULL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        categoria TEXT,
        costo REAL NOT NULL,
        precio_venta REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        stock_minimo INTEGER NOT NULL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_comprobante TEXT UNIQUE,
        fecha TEXT NOT NULL,
        cliente_nombre TEXT NOT NULL,
        cliente_telefono TEXT,
        medio_pago TEXT,
        total REAL NOT NULL,
        ganancia_total REAL NOT NULL,
        garantia_hasta TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS venta_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL REFERENCES ventas(id),
        producto_id INTEGER,
        nombre_producto TEXT NOT NULL,
        cantidad INTEGER NOT NULL,
        precio_unitario REAL NOT NULL,
        costo_unitario REAL NOT NULL,
        subtotal REAL NOT NULL,
        ganancia REAL NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venta_id INTEGER NOT NULL REFERENCES ventas(id),
        fecha TEXT NOT NULL,
        monto REAL NOT NULL,
        medio_pago TEXT,
        nota TEXT
    )""")

    columnas_ventas = {row[1] for row in c.execute("PRAGMA table_info(ventas)").fetchall()}
    if "monto_pagado" not in columnas_ventas:
        c.execute("ALTER TABLE ventas ADD COLUMN monto_pagado REAL NOT NULL DEFAULT 0")
        c.execute("UPDATE ventas SET monto_pagado = total")
    if "saldo_pendiente" not in columnas_ventas:
        c.execute("ALTER TABLE ventas ADD COLUMN saldo_pendiente REAL NOT NULL DEFAULT 0")
    if "estado_pago" not in columnas_ventas:
        c.execute("ALTER TABLE ventas ADD COLUMN estado_pago TEXT NOT NULL DEFAULT 'Pagado'")
    if "nota" not in columnas_ventas:
        c.execute("ALTER TABLE ventas ADD COLUMN nota TEXT")

    c.execute("SELECT COUNT(*) FROM config")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO config (id, nombre_negocio, telefono, direccion, dias_garantia, ultimo_comprobante) "
            "VALUES (1, 'Chiarita Store', '', '', 10, 0)"
        )
    conn.commit()
    conn.close()


def get_config():
    conn = get_conn()
    row = conn.execute("SELECT * FROM config WHERE id = 1").fetchone()
    conn.close()
    cols = ["id", "nombre_negocio", "telefono", "direccion", "dias_garantia", "ultimo_comprobante"]
    return dict(zip(cols, row))


def formato_moneda(valor):
    texto = f"{valor:,.2f}"
    texto = texto.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"


def siguiente_numero_comprobante(conn):
    cur = conn.execute("UPDATE config SET ultimo_comprobante = ultimo_comprobante + 1 WHERE id = 1")
    numero = conn.execute("SELECT ultimo_comprobante FROM config WHERE id = 1").fetchone()[0]
    return f"{numero:06d}"


def generar_pdf_comprobante(venta, items, config):
    pdf = FPDF(format="A5")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 8, config["nombre_negocio"] or "Comprobante de venta", ln=True)
    pdf.set_font("Helvetica", "", 10)
    if config["direccion"]:
        pdf.cell(0, 5, config["direccion"], ln=True)
    if config["telefono"]:
        pdf.cell(0, 5, f"Tel: {config['telefono']}", ln=True)
    pdf.ln(3)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 7, "COMPROBANTE DE VENTA", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, f"N.° {venta['numero_comprobante']}", ln=True)
    pdf.cell(0, 5, f"Fecha: {venta['fecha']}", ln=True)
    pdf.ln(2)
    pdf.cell(0, 5, f"Cliente: {venta['cliente_nombre']}", ln=True)
    if venta.get("cliente_telefono"):
        pdf.cell(0, 5, f"Teléfono: {venta['cliente_telefono']}", ln=True)
    pdf.cell(0, 5, f"Medio de pago: {venta['medio_pago']}", ln=True)
    pdf.ln(4)

    col_widths = (70, 20, 25, 25)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_widths[0], 6, "Producto", border=1)
    pdf.cell(col_widths[1], 6, "Cant.", border=1, align="C")
    pdf.cell(col_widths[2], 6, "P. Unit.", border=1, align="C")
    pdf.cell(col_widths[3], 6, "Subtotal", border=1, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for item in items:
        pdf.cell(col_widths[0], 6, item["nombre_producto"][:38], border=1)
        pdf.cell(col_widths[1], 6, str(item["cantidad"]), border=1, align="C")
        pdf.cell(col_widths[2], 6, formato_moneda(item["precio_unitario"]), border=1, align="C")
        pdf.cell(col_widths[3], 6, formato_moneda(item["subtotal"]), border=1, align="C")
        pdf.ln()

    pdf.set_font("Helvetica", "B", 11)
    pdf.ln(2)
    pdf.cell(0, 7, f"TOTAL: {formato_moneda(venta['total'])}", ln=True, align="R")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Pagado: {formato_moneda(venta.get('monto_pagado', venta['total']))}", ln=True, align="R")
    if venta.get("saldo_pendiente", 0) > 0:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, f"Saldo pendiente: {formato_moneda(venta['saldo_pendiente'])}", ln=True, align="R")

    pdf.ln(6)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0, 4,
        f"Garantía: {config['dias_garantia']} días corridos a partir de la fecha de compra "
        f"(válida hasta el {venta['garantia_hasta']}). Conserve este comprobante para hacer "
        f"válida la garantía.",
    )

    return bytes(pdf.output(dest="S"))


def tab_dashboard():
    conn = get_conn()
    productos = pd.read_sql_query("SELECT * FROM productos", conn)
    ventas = pd.read_sql_query("SELECT * FROM ventas", conn)
    costo_vendido_historico = conn.execute(
        "SELECT COALESCE(SUM(costo_unitario * cantidad), 0) FROM venta_items"
    ).fetchone()[0]
    por_cobrar = conn.execute("SELECT COALESCE(SUM(saldo_pendiente), 0) FROM ventas").fetchone()[0]
    conn.close()

    valor_stock_costo = (productos["costo"] * productos["stock"]).sum() if not productos.empty else 0
    ganancia_potencial = (
        ((productos["precio_venta"] - productos["costo"]) * productos["stock"]).sum()
        if not productos.empty else 0
    )
    total_invertido = valor_stock_costo + costo_vendido_historico

    hoy = ahora().date()
    inicio_mes = hoy.replace(day=1)
    if not ventas.empty:
        ventas["fecha_dt"] = pd.to_datetime(ventas["fecha"]).dt.date
        ventas_mes = ventas[ventas["fecha_dt"] >= inicio_mes]
    else:
        ventas_mes = ventas

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Productos activos", len(productos))
    col2.metric("Valor stock (costo)", formato_moneda(valor_stock_costo))
    col3.metric("Total invertido (histórico)", formato_moneda(total_invertido))
    col4.metric("Ganancia potencial en stock", formato_moneda(ganancia_potencial))
    col5.metric("Ventas del mes", len(ventas_mes))

    col5, col6, col7 = st.columns(3)
    col5.metric("Ingresos del mes", formato_moneda(ventas_mes["total"].sum() if not ventas_mes.empty else 0))
    col6.metric("Ganancia del mes", formato_moneda(ventas_mes["ganancia_total"].sum() if not ventas_mes.empty else 0))
    col7.metric("Por cobrar", formato_moneda(por_cobrar))

    bajo_stock = productos[productos["stock"] <= productos["stock_minimo"]] if not productos.empty else productos
    if not bajo_stock.empty:
        st.warning("Productos con stock bajo o agotado:")
        st.dataframe(bajo_stock[["nombre", "stock", "stock_minimo"]], hide_index=True, use_container_width=True)

    if not ventas.empty:
        ultimos_30 = hoy - timedelta(days=30)
        recientes = ventas[ventas["fecha_dt"] >= ultimos_30].copy()
        if not recientes.empty:
            resumen_diario = recientes.groupby("fecha_dt")[["total", "ganancia_total"]].sum()
            st.subheader("Últimos 30 días")
            st.bar_chart(resumen_diario)


def tab_stock():
    st.subheader("Productos")
    conn = get_conn()
    productos = pd.read_sql_query("SELECT * FROM productos ORDER BY nombre", conn)
    conn.close()

    if not productos.empty:
        tabla = productos.copy()
        tabla["margen"] = tabla["precio_venta"] - tabla["costo"]
        tabla["costo"] = tabla["costo"].map(formato_moneda)
        tabla["precio_venta"] = tabla["precio_venta"].map(formato_moneda)
        tabla["margen"] = tabla["margen"].map(formato_moneda)
        st.dataframe(
            tabla[["nombre", "categoria", "costo", "precio_venta", "margen", "stock", "stock_minimo"]],
            hide_index=True, use_container_width=True,
        )
    else:
        st.info("Todavía no cargaste productos.")

    with st.expander("➕ Agregar producto nuevo"):
        with st.form("form_nuevo_producto", clear_on_submit=True):
            nombre = st.text_input("Nombre del producto")
            categoria = st.text_input("Categoría (opcional)")
            c1, c2 = st.columns(2)
            costo = c1.number_input("Costo (lo que te salió)", min_value=0.0, step=0.01)
            precio_venta = c2.number_input("Precio de venta", min_value=0.0, step=0.01)
            c3, c4 = st.columns(2)
            stock = c3.number_input("Stock inicial", min_value=0, step=1)
            stock_minimo = c4.number_input("Alertar cuando el stock sea menor o igual a", min_value=0, step=1)
            if st.form_submit_button("Guardar producto"):
                if not nombre:
                    st.error("El nombre es obligatorio.")
                else:
                    conn = get_conn()
                    conn.execute(
                        "INSERT INTO productos (nombre, categoria, costo, precio_venta, stock, stock_minimo) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (nombre, categoria, costo, precio_venta, stock, stock_minimo),
                    )
                    conn.commit()
                    conn.close()
                    st.success(f"Producto '{nombre}' agregado.")
                    st.rerun()

    if not productos.empty:
        with st.expander("✏️ Editar producto o ajustar stock"):
            opciones = {f"{row.nombre} (stock: {row.stock})": row.id for row in productos.itertuples()}
            seleccion = st.selectbox("Producto", list(opciones.keys()))
            producto_id = opciones[seleccion]
            actual = productos[productos["id"] == producto_id].iloc[0]

            with st.form("form_editar_producto"):
                nombre = st.text_input("Nombre", value=actual["nombre"])
                categoria = st.text_input("Categoría", value=actual["categoria"] or "")
                c1, c2 = st.columns(2)
                costo = c1.number_input("Costo", min_value=0.0, step=0.01, value=float(actual["costo"]))
                precio_venta = c2.number_input("Precio de venta", min_value=0.0, step=0.01, value=float(actual["precio_venta"]))
                c3, c4 = st.columns(2)
                stock = c3.number_input("Stock", min_value=0, step=1, value=int(actual["stock"]))
                stock_minimo = c4.number_input("Stock mínimo", min_value=0, step=1, value=int(actual["stock_minimo"]))
                col_guardar, col_borrar = st.columns(2)
                guardar = col_guardar.form_submit_button("Guardar cambios")
                borrar = col_borrar.form_submit_button("Eliminar producto")

                if guardar:
                    conn = get_conn()
                    conn.execute(
                        "UPDATE productos SET nombre=?, categoria=?, costo=?, precio_venta=?, stock=?, stock_minimo=? "
                        "WHERE id=?",
                        (nombre, categoria, costo, precio_venta, stock, stock_minimo, producto_id),
                    )
                    conn.commit()
                    conn.close()
                    st.success("Producto actualizado.")
                    st.rerun()

                if borrar:
                    conn = get_conn()
                    conn.execute("DELETE FROM productos WHERE id=?", (producto_id,))
                    conn.commit()
                    conn.close()
                    st.success("Producto eliminado.")
                    st.rerun()


def tab_nueva_venta():
    st.subheader("Registrar venta")
    conn = get_conn()
    productos = pd.read_sql_query("SELECT * FROM productos WHERE stock > 0 ORDER BY nombre", conn)
    conn.close()

    if "carrito" not in st.session_state:
        st.session_state.carrito = []

    if productos.empty:
        st.info("No hay productos con stock disponible para vender.")
        return

    en_carrito = {}
    for item in st.session_state.carrito:
        en_carrito[item["producto_id"]] = en_carrito.get(item["producto_id"], 0) + item["cantidad"]

    opciones = {f"{row.nombre} (disponible: {row.stock})": row.id for row in productos.itertuples()}
    c1, c2, c3 = st.columns([3, 1, 1])
    seleccion = c1.selectbox("Producto", list(opciones.keys()), key="sel_producto_venta")
    producto_id = opciones[seleccion]
    producto = productos[productos["id"] == producto_id].iloc[0]
    disponible = producto["stock"] - en_carrito.get(producto_id, 0)
    cantidad = c2.number_input("Cantidad", min_value=1, max_value=max(int(disponible), 1), step=1, key="cant_venta")
    c3.write("")
    c3.write("")
    if c3.button("Agregar"):
        if cantidad > disponible:
            st.error(f"Solo hay {disponible} unidades disponibles.")
        else:
            st.session_state.carrito.append({
                "producto_id": producto_id,
                "nombre_producto": producto["nombre"],
                "cantidad": cantidad,
                "precio_unitario": producto["precio_venta"],
                "costo_unitario": producto["costo"],
                "subtotal": cantidad * producto["precio_venta"],
                "ganancia": cantidad * (producto["precio_venta"] - producto["costo"]),
            })
            st.rerun()

    if st.session_state.carrito:
        st.markdown("**Comprobante en curso:**")
        for i, item in enumerate(st.session_state.carrito):
            colp, colc, colu, cols, colx = st.columns([3, 1, 1.2, 1.2, 0.6])
            colp.write(item["nombre_producto"])
            colc.write(item["cantidad"])
            colu.write(formato_moneda(item["precio_unitario"]))
            cols.write(formato_moneda(item["subtotal"]))
            if colx.button("✕", key=f"quitar_{i}"):
                st.session_state.carrito.pop(i)
                st.rerun()

        total = sum(i["subtotal"] for i in st.session_state.carrito)
        ganancia_total = sum(i["ganancia"] for i in st.session_state.carrito)
        colt, colg = st.columns(2)
        colt.metric("Total", formato_moneda(total))
        colg.metric("Ganancia estimada", formato_moneda(ganancia_total))

        with st.form("form_confirmar_venta"):
            cliente_nombre = st.text_input("Nombre del cliente *")
            cliente_telefono = st.text_input("Teléfono del cliente (opcional)")
            medio_pago = st.selectbox("Medio de pago", MEDIOS_PAGO)
            monto_pagado = st.number_input(
                "Monto pagado ahora", min_value=0.0, max_value=float(total), value=float(total), step=0.01,
            )
            confirmar = st.form_submit_button("Confirmar venta y generar comprobante")

            if confirmar:
                if not cliente_nombre:
                    st.error("El nombre del cliente es obligatorio.")
                else:
                    saldo_pendiente = round(total - monto_pagado, 2)
                    if monto_pagado <= 0:
                        estado_pago = "Pendiente"
                    elif monto_pagado >= total:
                        estado_pago = "Pagado"
                    else:
                        estado_pago = "Parcial"

                    conn = get_conn()
                    config = get_config()
                    numero_comprobante = siguiente_numero_comprobante(conn)
                    fecha = ahora().strftime("%Y-%m-%d %H:%M")
                    garantia_hasta = (ahora() + timedelta(days=config["dias_garantia"])).strftime("%d/%m/%Y")

                    cur = conn.execute(
                        "INSERT INTO ventas (numero_comprobante, fecha, cliente_nombre, cliente_telefono, "
                        "medio_pago, total, ganancia_total, garantia_hasta, monto_pagado, saldo_pendiente, "
                        "estado_pago) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (numero_comprobante, fecha, cliente_nombre, cliente_telefono, medio_pago,
                         total, ganancia_total, garantia_hasta, monto_pagado, saldo_pendiente, estado_pago),
                    )
                    venta_id = cur.lastrowid

                    for item in st.session_state.carrito:
                        conn.execute(
                            "INSERT INTO venta_items (venta_id, producto_id, nombre_producto, cantidad, "
                            "precio_unitario, costo_unitario, subtotal, ganancia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (venta_id, item["producto_id"], item["nombre_producto"], item["cantidad"],
                             item["precio_unitario"], item["costo_unitario"], item["subtotal"], item["ganancia"]),
                        )
                        conn.execute(
                            "UPDATE productos SET stock = stock - ? WHERE id = ?",
                            (item["cantidad"], item["producto_id"]),
                        )

                    if monto_pagado > 0:
                        conn.execute(
                            "INSERT INTO pagos (venta_id, fecha, monto, medio_pago, nota) VALUES (?, ?, ?, ?, ?)",
                            (venta_id, fecha, monto_pagado, medio_pago, "Pago al momento de la venta"),
                        )
                    conn.commit()

                    venta = {
                        "numero_comprobante": numero_comprobante,
                        "fecha": fecha,
                        "cliente_nombre": cliente_nombre,
                        "cliente_telefono": cliente_telefono,
                        "medio_pago": medio_pago,
                        "total": total,
                        "garantia_hasta": garantia_hasta,
                        "monto_pagado": monto_pagado,
                        "saldo_pendiente": saldo_pendiente,
                    }
                    pdf_bytes = generar_pdf_comprobante(venta, st.session_state.carrito, config)
                    conn.close()

                    st.session_state.ultimo_pdf = pdf_bytes
                    st.session_state.ultimo_pdf_nombre = f"comprobante_{numero_comprobante}.pdf"
                    st.session_state.carrito = []
                    st.success(f"Venta registrada. Comprobante N.° {numero_comprobante}")
                    st.rerun()

    if st.session_state.get("ultimo_pdf"):
        st.download_button(
            "📄 Descargar comprobante en PDF",
            data=st.session_state.ultimo_pdf,
            file_name=st.session_state.ultimo_pdf_nombre,
            mime="application/pdf",
        )


def tab_historial():
    st.subheader("Historial de ventas")
    conn = get_conn()
    ventas = pd.read_sql_query("SELECT * FROM ventas ORDER BY id DESC", conn)
    config = get_config()

    if ventas.empty:
        st.info("Todavía no registraste ventas.")
        conn.close()
        return

    hoy = ahora().date()
    ventas["vigente"] = pd.to_datetime(ventas["garantia_hasta"], format="%d/%m/%Y").dt.date >= hoy

    filtro_cliente = st.text_input("Buscar por cliente")
    filtradas = ventas
    if filtro_cliente:
        filtradas = ventas[ventas["cliente_nombre"].str.contains(filtro_cliente, case=False, na=False)]

    for venta in filtradas.itertuples():
        estado = "🟢 Garantía vigente" if venta.vigente else "⚪ Garantía vencida"
        estado_pago_txt = venta.estado_pago
        if venta.saldo_pendiente > 0:
            estado_pago_txt += f" (debe {formato_moneda(venta.saldo_pendiente)})"
        titulo_expander = (
            f"N.° {venta.numero_comprobante} · {venta.fecha} · {venta.cliente_nombre} · "
            f"{formato_moneda(venta.total)} · {estado} · {estado_pago_txt}"
        ).replace("$", "\\$")
        with st.expander(titulo_expander):
            items = pd.read_sql_query(
                "SELECT nombre_producto, cantidad, precio_unitario, subtotal, ganancia FROM venta_items "
                "WHERE venta_id = ?", conn, params=(venta.id,),
            )
            items_mostrar = items.copy()
            items_mostrar["precio_unitario"] = items_mostrar["precio_unitario"].map(formato_moneda)
            items_mostrar["subtotal"] = items_mostrar["subtotal"].map(formato_moneda)
            items_mostrar["ganancia"] = items_mostrar["ganancia"].map(formato_moneda)
            st.dataframe(items_mostrar, hide_index=True, use_container_width=True)
            st.write(f"Medio de pago: {venta.medio_pago}")
            st.write(f"Ganancia de la venta: {formato_moneda(venta.ganancia_total)}")
            st.write(f"Garantía válida hasta: {venta.garantia_hasta}")
            st.write(f"Estado de pago: {venta.estado_pago}")
            st.write(f"Pagado: {formato_moneda(venta.monto_pagado)}")
            st.write(f"Saldo pendiente: {formato_moneda(venta.saldo_pendiente)}")
            if venta.nota:
                st.write(f"Nota: {venta.nota}")

            venta_dict = {
                "numero_comprobante": venta.numero_comprobante,
                "fecha": venta.fecha,
                "cliente_nombre": venta.cliente_nombre,
                "cliente_telefono": venta.cliente_telefono,
                "medio_pago": venta.medio_pago,
                "total": venta.total,
                "garantia_hasta": venta.garantia_hasta,
                "monto_pagado": venta.monto_pagado,
                "saldo_pendiente": venta.saldo_pendiente,
            }
            pdf_bytes = generar_pdf_comprobante(venta_dict, items.to_dict("records"), config)
            st.download_button(
                "📄 Descargar comprobante",
                data=pdf_bytes,
                file_name=f"comprobante_{venta.numero_comprobante}.pdf",
                mime="application/pdf",
                key=f"pdf_{venta.id}",
            )

            if venta.saldo_pendiente > 0:
                if st.button("✅ Marcar como pagado", key=f"marcar_pagado_{venta.id}"):
                    diferencia = round(venta.total - venta.monto_pagado, 2)
                    conn_edit = get_conn()
                    if diferencia > 0:
                        conn_edit.execute(
                            "INSERT INTO pagos (venta_id, fecha, monto, medio_pago, nota) VALUES (?, ?, ?, ?, ?)",
                            (venta.id, ahora().strftime("%Y-%m-%d %H:%M"), diferencia, venta.medio_pago,
                             "Cobro posterior (marcado como pagado)"),
                        )
                    conn_edit.execute(
                        "UPDATE ventas SET monto_pagado = total, saldo_pendiente = 0, estado_pago = 'Pagado' "
                        "WHERE id = ?",
                        (venta.id,),
                    )
                    conn_edit.commit()
                    conn_edit.close()
                    st.success("Venta marcada como pagada.")
                    st.rerun()

            if st.checkbox("✏️ Editar venta", key=f"toggle_editar_{venta.id}"):
                with st.form(f"form_editar_venta_{venta.id}"):
                    edit_cliente_nombre = st.text_input(
                        "Nombre del cliente", value=venta.cliente_nombre, key=f"edit_nombre_{venta.id}",
                    )
                    edit_cliente_telefono = st.text_input(
                        "Teléfono", value=venta.cliente_telefono or "", key=f"edit_tel_{venta.id}",
                    )
                    medio_idx = MEDIOS_PAGO.index(venta.medio_pago) if venta.medio_pago in MEDIOS_PAGO else 0
                    edit_medio_pago = st.selectbox(
                        "Medio de pago", MEDIOS_PAGO, index=medio_idx, key=f"edit_medio_{venta.id}",
                    )
                    edit_monto_pagado = st.number_input(
                        "Monto pagado", min_value=0.0, max_value=float(venta.total),
                        value=float(venta.monto_pagado), step=0.01, key=f"edit_pagado_{venta.id}",
                    )
                    edit_nota = st.text_area(
                        "Nota / observación (opcional)", value=venta.nota or "", key=f"edit_nota_{venta.id}",
                    )
                    if st.form_submit_button("Guardar cambios"):
                        if not edit_cliente_nombre:
                            st.error("El nombre del cliente es obligatorio.")
                        else:
                            nuevo_saldo = round(venta.total - edit_monto_pagado, 2)
                            if edit_monto_pagado <= 0:
                                nuevo_estado = "Pendiente"
                            elif edit_monto_pagado >= venta.total:
                                nuevo_estado = "Pagado"
                            else:
                                nuevo_estado = "Parcial"

                            conn_edit = get_conn()
                            diferencia = round(edit_monto_pagado - venta.monto_pagado, 2)
                            if diferencia > 0:
                                conn_edit.execute(
                                    "INSERT INTO pagos (venta_id, fecha, monto, medio_pago, nota) "
                                    "VALUES (?, ?, ?, ?, ?)",
                                    (venta.id, ahora().strftime("%Y-%m-%d %H:%M"), diferencia, edit_medio_pago,
                                     edit_nota or "Cobro posterior"),
                                )
                            conn_edit.execute(
                                "UPDATE ventas SET cliente_nombre=?, cliente_telefono=?, medio_pago=?, "
                                "monto_pagado=?, saldo_pendiente=?, estado_pago=?, nota=? WHERE id=?",
                                (edit_cliente_nombre, edit_cliente_telefono, edit_medio_pago, edit_monto_pagado,
                                 nuevo_saldo, nuevo_estado, edit_nota, venta.id),
                            )
                            conn_edit.commit()
                            conn_edit.close()
                            st.success("Venta actualizada.")
                            st.rerun()
    conn.close()


def tab_garantias():
    st.subheader("Garantías vigentes")
    conn = get_conn()
    ventas = pd.read_sql_query("SELECT * FROM ventas ORDER BY id DESC", conn)
    conn.close()

    if ventas.empty:
        st.info("Todavía no hay ventas registradas.")
        return

    hoy = ahora().date()
    ventas["garantia_hasta_dt"] = pd.to_datetime(ventas["garantia_hasta"], format="%d/%m/%Y").dt.date
    vigentes = ventas[ventas["garantia_hasta_dt"] >= hoy].copy()

    if vigentes.empty:
        st.info("No hay comprobantes con garantía vigente en este momento.")
        return

    vigentes["días restantes"] = vigentes["garantia_hasta_dt"].apply(lambda d: (d - hoy).days)
    vigentes = vigentes.sort_values("días restantes")
    vigentes["total"] = vigentes["total"].map(formato_moneda)
    st.dataframe(
        vigentes[["numero_comprobante", "cliente_nombre", "cliente_telefono", "fecha",
                  "garantia_hasta", "días restantes", "total"]]
        .rename(columns={
            "numero_comprobante": "N.° comprobante", "cliente_nombre": "Cliente",
            "cliente_telefono": "Teléfono", "fecha": "Fecha de venta", "garantia_hasta": "Vence",
        }),
        hide_index=True, use_container_width=True,
    )


def tab_cuentas():
    st.subheader("Cuentas y deudas")
    conn = get_conn()
    ventas = pd.read_sql_query(
        "SELECT * FROM ventas WHERE saldo_pendiente > 0 ORDER BY fecha", conn,
    )
    conn.close()

    if ventas.empty:
        st.success("No hay saldos pendientes. Todo cobrado ✅")
        return

    st.metric("Total adeudado por clientes", formato_moneda(ventas["saldo_pendiente"].sum()))

    filtro_cliente = st.text_input("Buscar por cliente", key="filtro_cuentas")
    filtradas = ventas
    if filtro_cliente:
        filtradas = ventas[ventas["cliente_nombre"].str.contains(filtro_cliente, case=False, na=False)]

    for venta in filtradas.itertuples():
        with st.expander(
            f"N.° {venta.numero_comprobante} · {venta.cliente_nombre} · {venta.fecha} · "
            f"Debe {formato_moneda(venta.saldo_pendiente)} · {venta.estado_pago}"
        ):
            st.write(f"Teléfono: {venta.cliente_telefono or '-'}")
            st.write(f"Total de la venta: {formato_moneda(venta.total)}")
            st.write(f"Pagado hasta ahora: {formato_moneda(venta.monto_pagado)}")
            st.write(f"Saldo pendiente: {formato_moneda(venta.saldo_pendiente)}")

            with st.form(f"form_cobro_{venta.id}"):
                monto_cobro = st.number_input(
                    "Monto a cobrar", min_value=0.01, max_value=float(venta.saldo_pendiente),
                    value=float(venta.saldo_pendiente), step=0.01, key=f"monto_cobro_{venta.id}",
                )
                medio_pago_cobro = st.selectbox("Medio de pago", MEDIOS_PAGO, key=f"medio_cobro_{venta.id}")
                nota_cobro = st.text_input("Nota (opcional)", key=f"nota_cobro_{venta.id}")
                if st.form_submit_button("Registrar cobro"):
                    conn = get_conn()
                    fecha_cobro = ahora().strftime("%Y-%m-%d %H:%M")
                    conn.execute(
                        "INSERT INTO pagos (venta_id, fecha, monto, medio_pago, nota) VALUES (?, ?, ?, ?, ?)",
                        (venta.id, fecha_cobro, monto_cobro, medio_pago_cobro, nota_cobro),
                    )
                    nuevo_pagado = round(venta.monto_pagado + monto_cobro, 2)
                    nuevo_saldo = round(max(venta.total - nuevo_pagado, 0), 2)
                    nuevo_estado = "Pagado" if nuevo_saldo <= 0 else "Parcial"
                    conn.execute(
                        "UPDATE ventas SET monto_pagado = ?, saldo_pendiente = ?, estado_pago = ? WHERE id = ?",
                        (nuevo_pagado, nuevo_saldo, nuevo_estado, venta.id),
                    )
                    conn.commit()
                    conn.close()
                    st.success("Cobro registrado.")
                    st.rerun()


def tab_configuracion():
    st.subheader("Datos del negocio")
    config = get_config()
    with st.form("form_config"):
        nombre_negocio = st.text_input("Nombre del negocio", value=config["nombre_negocio"] or "")
        telefono = st.text_input("Teléfono", value=config["telefono"] or "")
        direccion = st.text_input("Dirección", value=config["direccion"] or "")
        dias_garantia = st.number_input("Días de garantía", min_value=0, step=1, value=int(config["dias_garantia"]))
        if st.form_submit_button("Guardar"):
            conn = get_conn()
            conn.execute(
                "UPDATE config SET nombre_negocio=?, telefono=?, direccion=?, dias_garantia=? WHERE id=1",
                (nombre_negocio, telefono, direccion, dias_garantia),
            )
            conn.commit()
            conn.close()
            st.success("Configuración guardada.")
            st.rerun()


init_db()
st.title("🧺 Chiarita Store")
st.caption("Control de stock, ventas, ganancias y garantías")

tabs = st.tabs([
    "📊 Dashboard", "📦 Stock", "🧾 Nueva venta", "📜 Historial", "🛡️ Garantías",
    "💰 Cuentas / Deudas", "⚙️ Configuración",
])
with tabs[0]:
    tab_dashboard()
with tabs[1]:
    tab_stock()
with tabs[2]:
    tab_nueva_venta()
with tabs[3]:
    tab_historial()
with tabs[4]:
    tab_garantias()
with tabs[5]:
    tab_cuentas()
with tabs[6]:
    tab_configuracion()
