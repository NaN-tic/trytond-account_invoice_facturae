
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval
from trytond.i18n import gettext
from trytond.exceptions import UserWarning


class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    # Número d'expedient (Invoice Issue Data Type)
    file_reference = fields.Char('File Reference', size=20, states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    # Número de contracte (Inovice Issue Data Type)
    receiver_contract_reference = fields.Char('Receiver Contract Reference',
        size=20, states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    # Operació (Invoice Issue Data Type)
    receiver_transaction_reference = fields.Char(
        'Receiver Transaction Reference', size=20, states={
            'readonly': (Eval('state') != 'draft')
        }, depends=['state'])
    # Observacions (Invoice Issue Data Type)
    invoice_description = fields.Text('Invoice Description', size=2500,
        states={
            'readonly': (Eval('state') != 'draft')
        }, depends=['state'])

    def create_invoice(self):
        invoice = super(Sale, self).create_invoice()

        if invoice:
            for line in invoice.lines:
                if (line.origin and line.origin.__name__ == 'sale.line' and
                        line.origin.sale):
                    if line.origin.sale.file_reference:
                        invoice.file_reference = line.origin.sale.file_reference
                    if line.origin.sale.receiver_contract_reference:
                        invoice.receiver_contract_reference = (
                            line.origin.sale.receiver_contract_reference)
                    if line.origin.sale.receiver_transaction_reference:
                        invoice.receiver_transaction_reference = (
                            line.origin.sale.receiver_transaction_reference)
                    if line.origin.sale.invoice_description:
                        invoice.invoice_description = (
                            line.origin.sale.invoice_description)
            invoice.save()
        return invoice

    @fields.depends('party', 'invoice_address', 'receiver_contract_reference',
        'file_reference')
    def on_change_party(self):
        super(Sale, self).on_change_party()
        if self.party and self.invoice_address:
            if self.invoice_address.file_reference:
                self.file_reference = self.invoice_address.file_reference
            if self.invoice_address.receiver_contract_reference:
                self.receiver_contract_reference = (
                    self.invoice_address.receiver_contract_reference)

    @classmethod
    def quote(cls, sales):
        for sale in sales:
            sale.check_facturae_fields()


    def check_facturae_fields(self):
        pool = Pool()
        Sale = pool.get('sale.sale')
        Warning = pool.get('res.user.warning')

        sales = Sale.search([
            ('state', 'in', ['processing', 'done']),
            ['OR',
                ('file_reference', '=', self.file_reference),
                ('receiver_contract_reference', '=',
                    self.receiver_contract_reference)
             ]], limit=1)

        if sales:
            key = 'sale_facturae_duplicated_%s' % sales[0].id
            if Warning.check(key):
                raise UserWarning(key, gettext(
                    'account_invoice_facturae.msg_duplicated_sale_facturae_fields',
                    sale=sales[0].rec_name))
