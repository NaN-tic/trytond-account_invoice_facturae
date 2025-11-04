
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.pyson import Bool, Eval


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    # Número d'expedient (Invoice Issue Data Type)
    file_reference = fields.Char('File Reference', size=20)
    # Número de contracte (Inovice Issue Data Type)
    receiver_contract_reference = fields.Char('Receiver Contract Reference',
        size=20)
    # Operació (Invoice Issue Data Type)
    receiver_transaction_reference = fields.Char(
        'Receiver Transaction Reference', size=20)
    # Observacions (Invoice Issue Data Type)
    invoice_description = fields.Text('Invoice Description', size=2500,
        states={
            'readonly': Bool(Eval('invoices')),
        }, depends=['invoices'])

    def create_invoice(self):
        invoice = super(Sale, self).create_invoice()

        if invoice:
            invoice_description = []
            for line in invoice.lines:
                if (not line.origin or line.origin.__name__ != 'sale.line'
                        or not line.origin.sale):
                    continue
                if line.origin.sale.invoice_description:
                    invoice_description.append(
                        line.origin.sale.invoice_description)
            invoice.file_reference = (self.file_reference or (
                    invoice.invoice_address
                    and invoice.invoice_address.file_reference or None))
            invoice.receiver_contract_reference = (
                self.receiver_contract_reference or (invoice.invoice_address
                    and invoice.invoice_address.receiver_contract_reference
                    or None))
            if invoice_description:
                invoice.invoice_description = "\n".join(invoice_description)
            invoice.save()
        return invoice

    @fields.depends('invoice_address', 'receiver_contract_reference',
        'file_reference')
    def on_change_invoice_address(self):
        if self.invoice_address:
            self.file_reference = (self.invoice_address.file_reference or None)
            self.receiver_contract_reference = (
                self.invoice_address.receiver_contract_reference or None)
        else:
            self.file_reference = None
            self.receiver_contract_reference = None


class ModifyHeader(metaclass=PoolMeta):
    __name__ = 'sale.modify_header'

    def value_start(self, fields):
        values = super().value_start(fields)
        for field in ['receiver_transaction_reference', 'invoice_description']:
            if values.get(field):
                values[field] = None
        return values
