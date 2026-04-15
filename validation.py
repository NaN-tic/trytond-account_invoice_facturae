# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.exceptions import UserError
from trytond.i18n import gettext


DIR3_FIELDS = (
    'oficina_contable',
    'organo_gestor',
    'unidad_tramitadora',
    'organo_proponente',
    )


def validate_dir3_values(model, values):
    for field_name in DIR3_FIELDS:
        value = values.get(field_name)
        if value is None:
            continue
        if value != value.strip() or not value.isalnum():
            raise UserError(gettext(
                    'account_invoice_facturae.msg_invalid_dir3_code',
                    field=model._fields[field_name].string))
