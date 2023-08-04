# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account, invoice, party, company, payment_type
from .invoice import FACTURAE_SCHEMA_VERSION

__all__ = [FACTURAE_SCHEMA_VERSION]


def register():
    Pool.register(
        account.Configuration,
        account.ConfigurationFacturae,
        account.TaxTemplate,
        account.Tax,
        invoice.Invoice,
        invoice.InvoiceLine,
        invoice.CreditInvoiceStart,
        invoice.GenerateFacturaeStart,
        party.Address,
        payment_type.PaymentType,
        company.Company,
        module='account_invoice_facturae', type_='model')
    Pool.register(
        invoice.CreditInvoice,
        invoice.GenerateFacturae,
        module='account_invoice_facturae', type_='wizard')
