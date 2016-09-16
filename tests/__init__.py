# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
try:
    from trytond.modules.analytic_invoice_balance.tests\
        .test_account_invoice_facturae import suite
except ImportError:
    from .test_account_invoice_facturae import suite

__all__ = ['suite']
