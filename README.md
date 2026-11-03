# ControlStock

Aplicacion de escritorio para Windows destinada al control de inventario de una empresa de telecomunicaciones. Permite administrar articulos reutilizables y consumibles, entregas y devoluciones por cuadrilla, recuentos fisicos, informes, seguimiento administrativo de IClass y copias de seguridad locales.

La aplicacion funciona **100% sin conexion a Internet** y almacena toda la informacion en el equipo donde se ejecuta.

## Caracteristicas

- Inicio de sesion con un unico administrador y contrasena protegida mediante PBKDF2-HMAC-SHA256.
- Inventario con categorias, marcas, stock minimo, estados y baja/reactivacion de articulos.
- Stock separado por estados: disponible, asignado, reparacion, danado, extraviado y fuera de servicio.
- Entregas a cuadrillas con control de stock disponible y trazabilidad de consumibles.
- Devoluciones FIFO contra entregas pendientes, con estado del material devuelto.
- Recuento fisico con borrador, confirmacion y ajustes auditables.
- Historial de movimientos no eliminable, con anulaciones compensatorias y motivos.
- Seguimiento IClass sin modificar el stock.
- Informes diarios, semanales, mensuales e historicos, exportables a Excel.
- Copias de seguridad manuales y automaticas, restauracion con copia previa de seguridad.
- Interfaz completa en espanol.

## Requisitos

- Windows 10 u 11 de 64 bits.
- Python 3.11 o superior para ejecutar desde el codigo fuente.
- Dependencias de `requirements.txt`.

## Instalacion desde el codigo fuente

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python run.py
```

En el primer inicio la aplicacion solicita crear el usuario administrador. La contrasena debe tener al menos 8 caracteres y el usuario al menos 3.

## Ejecutable

El ejecutable se genera con PyInstaller:

```powershell
.\build.ps1
```

El resultado queda en `dist\ControlStock.exe`. Es un ejecutable independiente: no requiere Python instalado en el equipo de destino.

## Uso rapido

1. **Inventario**: cree los articulos, indique categoria, tipo y stock minimo. Puede registrar stock inicial al crear el articulo o usar **Ingresos de stock**.
2. **Entregas**: seleccione la cuadrilla, el tecnico y los articulos. Los consumibles se descuentan del stock; los reutilizables quedan asignados a la cuadrilla.
3. **Devoluciones**: devuelva material reutilizable indicando cantidad y estado. El sistema aplica la devolucion a las entregas pendientes mas antiguas.
4. **Cuadrillas**: consulte saldos pendientes, entregas, devoluciones e historial.
5. **Recuento fisico**: inicie un recuento, guarde un borrador y confirmelo para ajustar el stock con trazabilidad.
6. **Informes**: seleccione el periodo y exporte el informe a Excel.
7. **Pendientes de IClass**: marque las entregas cargadas en IClass o revierta la marca con un motivo. Esta operacion no modifica el stock.
8. **Configuracion**: administre copias de seguridad, categorias y la contrasena del administrador.

## Reglas de negocio principales

- No se permite stock negativo ni cantidades cero o negativas.
- No se puede entregar mas cantidad que el stock disponible.
- No se puede devolver mas material del pendiente de la cuadrilla.
- Una entrega no puede anularse si tiene devoluciones asociadas o si ya esta cargada en IClass.
- Los consumibles no generan devoluciones pendientes.
- Los movimientos no se eliminan: se anulan con movimientos compensatorios y motivo.
- El cierre de una entrega en IClass no modifica cantidades de stock.

## Datos, copias y registros

- Base de datos: `%LOCALAPPDATA%\ControlStock\database\control_stock.db`
- Copias de seguridad por defecto: `Documentos\ControlStock\Copias de seguridad`
- Registros: `%LOCALAPPDATA%\ControlStock\logs\control_stock.log`

Las copias automaticas pueden configurarse en **Configuracion > Copias de seguridad**. Al restaurar una copia se crea automaticamente una copia previa de la base actual. Despues de restaurar se recomienda reiniciar la aplicacion.

## Pruebas

```powershell
python -m pytest tests -q
```

Las pruebas cubren autenticacion, ingresos, ajustes, entregas, devoluciones FIFO, anulaciones, recuentos, IClass, informes, exportacion Excel, cuadrillas y copias de seguridad.

## Estructura del proyecto

```text
app/
  db/          Modelos, base de datos, migraciones y datos iniciales
  services/    Reglas de negocio y consultas
  ui/          Ventanas, paginas, dialogos, tema e iconos
  utils/       Fechas, numeros y exportacion Excel
tests/         Pruebas automatizadas
run.py         Punto de entrada
build.ps1      Generacion del ejecutable
```
