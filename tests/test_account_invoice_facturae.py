# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
# import doctest
import os.path
import unittest
from decimal import Decimal
import trytond.tests.test_tryton
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.tests.test_tryton import ModuleTestCase, with_transaction
from trytond.modules.account.tests import get_fiscalyear, create_chart
from trytond.modules.company.tests import create_company, set_company
from trytond.modules.account_invoice.tests import set_invoice_sequences
from trytond.modules.currency.tests import create_currency, add_currency_rate
CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))


class TestAccountInvoiceFacturaeCase(ModuleTestCase):
    'Test account_invoice_facturae module'
    module = 'account_invoice_facturae'

    @with_transaction()
    def test_invoice_generation(self):
        'Test invoice generation'

        pool = Pool()
        Account = pool.get('account.account')
        FiscalYear = pool.get('account.fiscalyear')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')
        Party = pool.get('party.party')
        PaymentTerm = pool.get('account.invoice.payment_term')
        ProductUom = pool.get('product.uom')
        ProductCategory = pool.get('product.category')
        ProductTemplate = pool.get('product.template')
        Product = pool.get('product.product')
        Tax = pool.get('account.tax')
        Address = pool.get('party.address')
        PartyIdentifier = pool.get('party.identifier')
        Country = pool.get('country.country')
        Subdivision = pool.get('country.subdivision')
        PaymentType = pool.get('account.payment.type')

        country = Country(name='Country', code='ES', code3='ESP')
        country.save()
        subdivision = Subdivision(
            name='Subdivision', country=country, code='SUB', type='area')
        subdivision.save()

        company = create_company()
        currency = create_currency('EUR')
        add_currency_rate(currency, 1.0)

        tax_identifier = PartyIdentifier()
        tax_identifier.type = 'eu_vat'
        tax_identifier.code = 'BE0897290877'
        company.header = 'Report Header'
        company.party.name = 'Seller'
        company.party.identifiers = [tax_identifier]
        company.party.facturae_person_type = 'J'
        company.party.facturae_residence_type = 'R'
        company.party.save()
        company.save()

        # Save certificate into company
        with open(os.path.join(
                    CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
            company.facturae_certificate = cert_file.read()

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

            payment_receivable, = PaymentType.create([{
                    'name': 'Payment Receivable',
                    'kind': 'receivable',
                    'company': company.id,
                    'facturae_type': '01',
                    }])
            revenue, = Account.search([('type.revenue', '=', True)])
            expense, = Account.search([('type.expense', '=', True)])
            tax_account, = Account.search([
                    ('name', '=', 'Main Tax'),
                    ])
            with Transaction().set_user(0):
                vat21 = Tax()
                vat21.name = vat21.description = '21% VAT'
                vat21.type = 'percentage'
                vat21.rate = Decimal('0.21')
                vat21.invoice_account = tax_account
                vat21.report_type = '05'
                vat21.credit_note_account = tax_account

            vat21.save()

            company_address, = company.party.addresses
            company_address.street = 'street'
            company_address.zip = '08201'
            company_address.city = 'City'
            company_address.subdivision = subdivision
            company_address.country = country
            company_address.save()
            party = Party(name='Buyer')
            party.facturae_person_type = 'J'
            party.facturae_residence_type = 'R'
            tax_identifier = PartyIdentifier()
            tax_identifier.type = 'eu_vat'
            tax_identifier.code = 'BE0897290877'
            party.identifiers = [tax_identifier]
            party.save()

            address_dict = {
                'party': party.id,
                'street': 'St sample, 15',
                'city': 'City',
                'zip': '08201',
                'subdivision': subdivision.id,
                'country': country.id,
                }

            address, = Address.create([address_dict])

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


            account_category = ProductCategory()
            account_category.name = 'Account Category'
            account_category.accounting = True
            account_category.account_expense = expense
            account_category.account_revenue = revenue
            account_category.customer_taxes = [vat21]
            account_category.save()

            unit, = ProductUom.search([('name', '=', 'Unit')])
            template = ProductTemplate()
            template.name = 'product'
            template.default_uom = unit
            template.type = 'service'
            template.list_price = Decimal('40')
            template.account_category = account_category
            template.save()
            product = Product()
            product.template = template
            product.save()

            currency = create_currency('Eur')
            add_currency_rate(currency, 1)

            with Transaction().set_user(0):
                invoice = Invoice()
                invoice.type = 'out'
                invoice.on_change_type()
                invoice.party = party
                invoice.on_change_party()
                invoice.payment_type = payment_receivable
                invoice.payment_term = term
                invoice.currency = currency
                invoice.company = company

                line1 = InvoiceLine()
                line1.product = product
                line1.on_change_product()
                line1.on_change_account()
                line1.quantity = 5
                line1.unit_price = Decimal('40')

                line2 = InvoiceLine()
                line2.account = revenue
                line2.on_change_account()
                line2.product = product
                line2.on_change_product()
                line2.description = 'Test'
                line2.quantity = 1
                line2.unit_price = Decimal(20)

                invoice.lines = [line1, line2]
                invoice.on_change_lines()

                invoice.save()
                Invoice.post([invoice])

            Invoice.generate_facturae_default([invoice], 'privatepassword')


def suite():
    suite = trytond.tests.test_tryton.suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            TestAccountInvoiceFacturaeCase))
    return suite
