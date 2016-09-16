# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
# import doctest
import os.path
import unittest
from decimal import Decimal

import trytond.tests.test_tryton
from trytond.pool import Pool
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
# from trytond.tests.test_tryton import doctest_setup, doctest_teardown
# from trytond.tests.test_tryton import doctest_checker

from trytond.modules.account.tests import get_fiscalyear
from trytond.modules.account_es.tests import create_chart
from trytond.modules.company.tests import create_company, set_company
from trytond.modules.account_invoice.tests import set_invoice_sequences

CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))


class TestCase(ModuleTestCase):
    'Test account_invoice_facturae module'
    module = 'account_invoice_facturae'

    @with_transaction()
    def test_invoice_generation(self):
        'Test invoice generation'
        pool = Pool()
        Account = pool.get('account.account')
        FiscalYear = pool.get('account.fiscalyear')
        GenerateSignedFacturae = pool.get('account.invoice.generate_facturae',
            type='wizard')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')
        ModelData = pool.get('ir.model.data')
        Party = pool.get('party.party')
        PaymentTerm = pool.get('account.invoice.payment_term')
        ProductUom = pool.get('product.uom')
        ProductTemplate = pool.get('product.template')
        Product = pool.get('product.product')
        Tax = pool.get('account.tax')

        revenue_template_id = ModelData.get_id('account_es', 'pgc_7000_child')
        expense_template_id = ModelData.get_id('account_es', 'pgc_600_child')
        vat21_template_id = ModelData.get_id('account_es', 'iva_rep_21')

        company = create_company()
        # Save certificate into company
        with open(os.path.join(
                    CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
            company.facturae_certificate = cert_file.read()
        company.save()

        payment_term, = PaymentTerm.create([{
                    'name': '20 days, 40 days',
                    'lines': [
                        ('create', [{
                                    'sequence': 0,
                                    'type': 'percent',
                                    'divisor': 2,
                                    'ratio': Decimal('.5'),
                                    'relativedeltas': [('create', [{
                                                    'days': 20,
                                                    },
                                                ]),
                                        ],
                                    }, {
                                    'sequence': 1,
                                    'type': 'remainder',
                                    'relativedeltas': [('create', [{
                                                    'days': 40,
                                                    },
                                                ]),
                                        ],
                                    }])]
                    }])

        with set_company(company):
            create_chart(company, tax=True)

            fiscalyear = set_invoice_sequences(get_fiscalyear(company))
            fiscalyear.save()
            FiscalYear.create_period([fiscalyear])

            revenue, = Account.search([('template', '=', revenue_template_id)])
            expense, = Account.search([('template', '=', expense_template_id)])
            vat21, = Tax.search([('template', '=', vat21_template_id)])

            party = Party(name='Party')
            party.save()

            term, = PaymentTerm.create([{
                        'name': 'Payment term',
                        'lines': [
                            ('create', [{
                                        'type': 'remainder',
                                        'relativedeltas': [
                                            ('create', [{
                                                        'sequence': 0,
                                                        'days': 0,
                                                        'months': 0,
                                                        'weeks': 0,
                                                        }])],
                                        }])],
                        }])

            unit, = ProductUom.search([('name', '=', 'Unit')])
            template = ProductTemplate()
            template.name = 'product'
            template.default_uom = unit
            template.type = 'service'
            template.list_price = Decimal('40')
            template.cost_price = Decimal('25')
            template.account_expense = expense
            template.account_revenue = revenue
            template.customer_taxes = [vat21]
            template.save()
            product = Product()
            product.template = template
            product.save()

            invoice = Invoice()
            invoice.type = 'out'
            invoice.on_change_type()
            invoice.party = party
            invoice.on_change_party()
            invoice.payment_term = term

            line1 = InvoiceLine()
            line1.product = product
            line1.on_change_product()
            line1.on_change_account()
            line1.quantity = 5
            line1.unit_price = Decimal('40')

            line2 = InvoiceLine()
            line2.account = revenue
            line2.on_change_account()
            line2.description = 'Test'
            line2.quantity = 1
            line2.unit_price = Decimal(20)

            invoice.lines = [line1, line2]
            invoice.on_change_lines()
            invoice.save()
            # invoice.untaxed_amount == Decimal('220.00')
            # invoice.tax_amount == Decimal('20.00')
            # invoice.total_amount == Decimal('240.00')

            Invoice.post([invoice])

            session_id, _, _ = GenerateSignedFacturae.create()
            generate_signed_facturae = GenerateSignedFacturae(session_id)
            generate_signed_facturae.account.certificate_password = (
                'privatepassword')
            generate_signed_facturae.transition_generate()

            self.assertIsNotNone(invoice.invoice_facturae)


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestCase))
    # suite.addTests(doctest.DocFileSuite(
    #         'scenario_account_invoice_facturae.rst',
    #         setUp=doctest_setup, tearDown=doctest_teardown, encoding='utf-8',
    #         checker=doctest_checker,
    #         optionflags=doctest.REPORT_ONLY_FIRST_FAILURE))
    return suite
