# Chiarita Store

App para controlar el stock y las finanzas del emprendimiento: registrar productos con su costo y precio de venta, registrar ventas con cliente y medio de pago, emitir el comprobante de venta en PDF con la garantía de 10 días corridos, y ver qué ventas siguen dentro de la garantía.

## Uso local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

La app se abre en `http://localhost:8501`. Los datos se guardan en `chiarita.db` (SQLite, no se sube al repo).

## Secciones

- **Dashboard**: valor del stock, ganancia potencial, ventas y ganancia del mes, alertas de stock bajo.
- **Stock**: alta, edición y baja de productos (nombre, costo, precio de venta, stock, stock mínimo).
- **Nueva venta**: arma un comprobante con uno o varios productos, carga el cliente y el medio de pago, descuenta stock y genera el comprobante en PDF.
- **Historial**: todas las ventas realizadas, con reimpresión del PDF y estado de la garantía.
- **Garantías**: listado de comprobantes con garantía vigente y días restantes.
- **Configuración**: nombre, teléfono, dirección del negocio y días de garantía (10 por defecto), usados en el comprobante.

## Nota sobre el hosting

Si se despliega en un servicio con almacenamiento efímero (por ejemplo Streamlit Community Cloud gratuito), la base `chiarita.db` puede reiniciarse en cada redeploy. Para producción conviene un hosting con disco persistente (Render, Railway, etc.).
