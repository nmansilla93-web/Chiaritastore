# Chiarita Store

App para controlar el stock y las finanzas del emprendimiento: registrar productos con su costo y precio de venta, registrar ventas con cliente y medio de pago, emitir el comprobante de venta en PDF con la garantía de 10 días corridos, y ver qué ventas siguen dentro de la garantía.

## Uso local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

La app se abre en `http://localhost:8501`. Sin configurar Turso, los datos se guardan en `chiarita.db` (SQLite local, no se sube al repo).

## Secciones

- **Dashboard**: valor del stock, ganancia potencial, ventas y ganancia del mes, alertas de stock bajo.
- **Stock**: alta, edición y baja de productos (nombre, costo, precio de venta, stock, stock mínimo).
- **Nueva venta**: arma un comprobante con uno o varios productos, carga el cliente y el medio de pago, descuenta stock y genera el comprobante en PDF.
- **Historial**: todas las ventas realizadas, con reimpresión del PDF y estado de la garantía.
- **Garantías**: listado de comprobantes con garantía vigente y días restantes.
- **Configuración**: nombre, teléfono, dirección del negocio y días de garantía (10 por defecto), usados en el comprobante.

## Hosting gratis para siempre: Streamlit Community Cloud + Turso

Streamlit Community Cloud aloja la app gratis sin límite de tiempo, pero borra el disco local en cada reinicio. Por eso la app usa [Turso](https://turso.tech) (SQLite en la nube, plan gratuito permanente) como base de datos cuando hay credenciales configuradas, y cae automáticamente a `chiarita.db` local si no las encuentra (para desarrollo).

1. Creá una cuenta gratis en [turso.tech](https://turso.tech) y una base de datos (`turso db create chiarita` con la CLI, o desde el dashboard).
2. Obtené la URL de conexión (`turso db show chiarita --url`, empieza con `libsql://...`) y un token (`turso db tokens create chiarita`).
3. En Streamlit Community Cloud, andá a **Settings → Secrets** de la app y agregá:
   ```toml
   TURSO_DATABASE_URL = "libsql://tu-base.turso.io"
   TURSO_AUTH_TOKEN = "tu-token"
   ```
4. Para probarlo en local con Turso, creá `.streamlit/secrets.toml` (ya está en `.gitignore`, no se sube) con las mismas dos claves.

Sin esas dos claves configuradas, la app sigue funcionando igual pero con SQLite local (`chiarita.db`), útil para desarrollo.
