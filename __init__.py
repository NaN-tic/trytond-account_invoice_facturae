# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool

import company
import invoice
import party
import payment_type
import account


def register():
    Pool.register(
        account.TaxTemplate,
        account.Tax,
        company.Company,
        invoice.Invoice,
        invoice.InvoiceLine,
        invoice.CreditInvoiceStart,
        invoice.GenerateSignedFacturaeAskPassword,
        party.Party,
        payment_type.PaymentType,
        module='account_invoice_facturae', type_='model')
    Pool.register(
        invoice.CreditInvoice,
        invoice.GenerateSignedFacturae,
        module='account_invoice_facturae', type_='wizard')
