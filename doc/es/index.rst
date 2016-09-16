Facturación - Generación de factura electrónica Factura-e
=========================================================

Añade la posibilidad de generar una factura electrónica firmada digitalmente
siguiendo el formato Factura-e requerido en España.

Como configuración previa, hay que subir el certificado PKCS12 de cada empresa
(el su formulario) y habrá que seleccionar el campo *Tipo informes" de los
impuestos que se quieran usar y el campo *Tipo Factura-e* de los tipos de pago.

Si se van a emitir facturas con tipo de pago *Transferencia* o *Recibo
domiciliado*, habrá que tener instalado el módulo *account_bank*, y las cuentas
que se usen deberán tener IBAN.

Los terceros de las empresas y de los destinatarios de las facturas deberán
tener los campos de la pestaña *Factura-e* rellenados.

Todas estas condiciones se comprueban al generar el fichero Factura-e y se
muestran avisos al usuario explicando exáctamente que falta en caso necesario.

Para generar el fichero Factura-e se dispone de un botón en el formulario y en
la vista listado, pudiendo seleccionar varias facturas. Se habrirá un asistente
que pide la contraseña del certificado y se genera un fichero individual para
cada factura que se almacena en un campo propio de la factura, disponible
también desde el formulario.
