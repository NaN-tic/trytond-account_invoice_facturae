# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.

import os.path
import secrets
import xml.etree.ElementTree as ET
from decimal import Decimal
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.tests.test_tryton import (ModuleTestCase, with_transaction,
    activate_module)
from trytond.modules.account.tests import get_fiscalyear, create_chart
from trytond.modules.company.tests import (create_company, set_company,
    CompanyTestMixin)
from trytond.modules.account_invoice.tests import set_invoice_sequences
from trytond.modules.currency.tests import create_currency, add_currency_rate
from trytond.exceptions import UserError
CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))


class AccountInvoiceFacturaeTestCase(CompanyTestMixin, ModuleTestCase):
    'Test AccountInvoiceFacturae module'
    module = 'account_invoice_facturae'
    depends = ['party_zip']

    @staticmethod
    def _find_xml_element(root, name):
        for element in root.iter():
            if element.tag == name or element.tag.endswith('}%s' % name):
                return element
        return None

    @classmethod
    def _find_xml_text(cls, root, *names):
        element = root
        for name in names:
            element = cls._find_xml_element(element, name)
            if element is None:
                return None
        return element.text

    @staticmethod
    def _valid_dir3_values():
        return {
            'oficina_contable': 'ABC123',
            'organo_gestor': 'DEF456',
            'unidad_tramitadora': 'GHI789',
            'organo_proponente': 'JKL012',
            }

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        activate_module('account_invoice_facturae')
        activate_module('account_invoice_discount')
        activate_module('sale')
        activate_module('sale_invoice_grouping')
        activate_module('party_zip')

    @with_transaction()
    def test_dir3_code_validation(self):
        pool = Pool()
        Company = pool.get('company.company')
        Party = pool.get('party.party')
        Address = pool.get('party.address')

        company = create_company()
        company.party.name = 'Seller'
        company.party.save()

        Company.write([company], self._valid_dir3_values())
        self.assertEqual(company.oficina_contable, 'ABC123')

        with self.assertRaises(UserError):
            Company.write([company], {
                    'oficina_contable': ' ABC123 ',
                    })

        party = Party(name='Buyer')
        party.save()

        address, = Address.create([{
                    'party': party.id,
                    **self._valid_dir3_values(),
                    }])
        self.assertEqual(address.organo_proponente, 'JKL012')

        with self.assertRaises(UserError):
            Address.create([{
                        'party': party.id,
                        'organo_gestor': 'ABC-123',
                        }])

        with self.assertRaises(UserError):
            Address.write([address], {
                    'unidad_tramitadora': 'XYZ 999',
                    })

    @with_transaction()
    def test_invoice_generation(self):
        'Test invoice generation'

        pool = Pool()
        Configuration = pool.get('account.configuration')
        Certificate = pool.get('certificate')
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
            name='Subdivision', country=country, code='SUB', type='province')
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
        company.facturae_person_type = 'J'
        company.facturae_residence_type = 'R'
        company.party.save()
        company.save()

        with set_company(company):
            certificate = Certificate()
            certificate.name = 'dummy Certificate'
            # Save certificate
            with open(os.path.join(
                        CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
                certificate.pem_certificate = cert_file.read()
            certificate.save()

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
            revenue, = Account.search([
                    ('type.revenue', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            expense, = Account.search([
                    ('type.expense', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            tax_account, = Account.search([
                    ('code', '=', '6.3.6'), # Main Tax
                    ('closed', '=', False),
                    ], limit=1)
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
            company_address.postal_code = '08201'
            company_address.city = 'City'
            company_address.subdivision = subdivision
            company_address.country = country
            company_address.save()
            party = Party(name='Buyer')
            tax_identifier = PartyIdentifier()
            tax_identifier.type = 'eu_vat'
            tax_identifier.code = 'BE0897290877'
            party.identifiers = [tax_identifier]
            party.save()

            address_dict = {
                'party': party.id,
                'street': 'St sample, 15',
                'city': 'City',
                'postal_code': '08201',
                'subdivision': subdivision.id,
                'country': country.id,
                'facturae_person_type': 'J',
                'facturae_residence_type': 'R',
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

            configuration = Configuration(1)
            configuration.facturae_service = 'only_file'
            configuration.save()

            with Transaction().set_user(0):
                invoice = Invoice()
                invoice.type = 'out'
                invoice.party = party
                invoice.on_change_party()
                invoice.payment_type = payment_receivable
                invoice.payment_term = term
                invoice.currency = currency
                invoice.company = company
                invoice.file_reference = 'FileReference'
                invoice.receiver_contract_reference = 'ReceiverContract'
                invoice.invoice_description = 'InvoiceDescription'
                invoice.set_journal()
                invoice._update_account()

                line1 = InvoiceLine()
                line1.company = company
                line1.currency = currency
                line1.product = product
                line1.on_change_product()
                line1.on_change_account()
                line1.quantity = 5
                line1.unit_price = Decimal('40')

                line2 = InvoiceLine()
                line2.company = company
                line2.currency = currency
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

            invoice.generate_facturae()
            self.assertNotEqual(invoice.invoice_facturae, None)
            self.assertEqual(invoice.invoice_facturae_filename, 'facturae-1.xml')

    @with_transaction()
    def test_attachment_small(self):
        'Test attachment less than 100KB'
        pool = Pool()
        Configuration = pool.get('account.configuration')
        Certificate = pool.get('certificate')
        Account = pool.get('account.account')
        FiscalYear = pool.get('account.fiscalyear')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')
        InvoiceAttachment = pool.get('account.invoice.facturae.attachment')
        IrAttachment = pool.get('ir.attachment')
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
            name='Subdivision', country=country, code='SUB', type='province')
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
        company.facturae_person_type = 'J'
        company.facturae_residence_type = 'R'
        company.party.save()
        company.save()

        with set_company(company):
            certificate = Certificate()
            certificate.name = 'dummy Certificate'
            with open(os.path.join(
                        CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
                certificate.pem_certificate = cert_file.read()
            certificate.save()

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
            revenue, = Account.search([
                    ('type.revenue', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            expense, = Account.search([
                    ('type.expense', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            tax_account, = Account.search([
                    ('code', '=', '6.3.6'), # Main Tax
                    ('closed', '=', False),
                    ], limit=1)
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
            company_address.postal_code = '08201'
            company_address.city = 'City'
            company_address.subdivision = subdivision
            company_address.country = country
            company_address.save()
            party = Party(name='Buyer')
            tax_identifier = PartyIdentifier()
            tax_identifier.type = 'eu_vat'
            tax_identifier.code = 'BE0897290877'
            party.identifiers = [tax_identifier]
            party.save()

            address_dict = {
                'party': party.id,
                'street': 'St sample, 15',
                'city': 'City',
                'postal_code': '08201',
                'subdivision': subdivision.id,
                'country': country.id,
                'facturae_person_type': 'J',
                'facturae_residence_type': 'R',
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

            configuration = Configuration(1)
            configuration.facturae_service = 'only_file'
            configuration.save()

            with Transaction().set_user(0):
                invoice = Invoice()
                invoice.type = 'out'
                invoice.party = party
                invoice.on_change_party()
                invoice.payment_type = payment_receivable
                invoice.payment_term = term
                invoice.currency = currency
                invoice.company = company
                invoice.file_reference = 'FileReference'
                invoice.receiver_contract_reference = 'ReceiverContract'
                invoice.invoice_description = 'InvoiceDescription'
                invoice.set_journal()
                invoice._update_account()

                line1 = InvoiceLine()
                line1.company = company
                line1.currency = currency
                line1.product = product
                line1.on_change_product()
                line1.on_change_account()
                line1.quantity = 5
                line1.unit_price = Decimal('40')

                line2 = InvoiceLine()
                line2.company = company
                line2.currency = currency
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

                # Create small attachment
                attachment_data = secrets.token_bytes(50 * 1024) # random 50 KB
                attachment = IrAttachment()
                attachment.name = 'test.pdf'
                attachment.type = 'data'
                attachment.data = attachment_data
                attachment.resource = invoice
                attachment.save()

                invoice_attachment = InvoiceAttachment()
                invoice_attachment.invoice = invoice
                invoice_attachment.attachment = attachment
                invoice_attachment.attachment_format = (
                    invoice_attachment.on_change_with_attachment_format())
                invoice_attachment.description = 'Test attachment'
                invoice_attachment.save()
                self.assertNotEqual(
                    invoice_attachment.attachment_format, 'NONE')

            invoice.generate_facturae()
            self.assertNotEqual(invoice.invoice_facturae, None)
            self.assertEqual(invoice.invoice_facturae_filename, 'facturae-1.xml')

    @with_transaction()
    def test_invoice_generation_with_line_discount(self):
        'Test invoice generation with line discount'

        pool = Pool()
        Configuration = pool.get('account.configuration')
        Certificate = pool.get('certificate')
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
            name='Subdivision', country=country, code='SUB', type='province')
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
        company.facturae_person_type = 'J'
        company.facturae_residence_type = 'R'
        company.party.save()
        company.save()

        with set_company(company):
            certificate = Certificate()
            certificate.name = 'dummy Certificate'
            with open(os.path.join(
                        CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
                certificate.pem_certificate = cert_file.read()
            certificate.save()

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
            revenue, = Account.search([
                    ('type.revenue', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            tax_account, = Account.search([
                    ('code', '=', '6.3.6'),
                    ('closed', '=', False),
                    ], limit=1)
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
            company_address.postal_code = '08201'
            company_address.city = 'City'
            company_address.subdivision = subdivision
            company_address.country = country
            company_address.save()
            party = Party(name='Buyer')
            tax_identifier = PartyIdentifier()
            tax_identifier.type = 'eu_vat'
            tax_identifier.code = 'BE0897290877'
            party.identifiers = [tax_identifier]
            party.save()

            address_dict = {
                'party': party.id,
                'street': 'St sample, 15',
                'city': 'City',
                'postal_code': '08201',
                'facturae_person_type': 'J',
                'facturae_residence_type': 'R',
                'country': country.id,
                'subdivision': subdivision.id,
                }
            address, = Address.create([address_dict])
            party.addresses = [address]
            party.save()

            unit, = ProductUom.search([('name', '=', 'Unit')])
            product_category = ProductCategory(name='Product Category')
            product_category.accounting = True
            product_category.account_revenue = revenue
            product_category.customer_taxes = [vat21]
            product_category.save()

            template = ProductTemplate()
            template.name = 'Product'
            template.default_uom = unit
            template.type = 'service'
            template.list_price = Decimal('20')
            template.account_category = product_category
            template.save()
            product = Product()
            product.template = template
            product.save()

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

            configuration = Configuration(1)
            configuration.facturae_service = 'only_file'
            configuration.save()

            with Transaction().set_user(0):
                invoice = Invoice()
                invoice.type = 'out'
                invoice.party = party
                invoice.on_change_party()
                invoice.invoice_address = address
                invoice.payment_type = payment_receivable
                invoice.payment_term = term
                invoice.currency = currency
                invoice.company = company
                invoice.set_journal()
                invoice._update_account()

                line = InvoiceLine()
                line.company = company
                line.currency = currency
                line.account = revenue
                line.on_change_account()
                line.product = product
                line.on_change_product()
                line.description = 'Test'
                line.quantity = 1
                line.base_price = Decimal('10.0000')
                line.discount_rate = Decimal('0.1')
                line.on_change_discount_rate()

                invoice.lines = [line]
                invoice.on_change_lines()

                invoice.save()
                Invoice.post([invoice])

            invoice.generate_facturae()
            self.assertIsNotNone(invoice.invoice_facturae)

            root = ET.fromstring(invoice.invoice_facturae)
            invoice_line = self._find_xml_element(root, 'InvoiceLine')
            self.assertIsNotNone(invoice_line)
            self.assertEqual(
                Decimal(self._find_xml_text(invoice_line, 'UnitPriceWithoutTax')),
                Decimal('10.0000'))
            self.assertEqual(
                Decimal(self._find_xml_text(invoice_line, 'TotalCost')),
                Decimal('10.0000'))
            self.assertEqual(
                self._find_xml_text(
                    invoice_line, 'DiscountsAndRebates', 'Discount',
                    'DiscountReason'),
                'Discount 10%')
            self.assertEqual(
                Decimal(self._find_xml_text(
                    invoice_line, 'DiscountsAndRebates', 'Discount',
                    'DiscountRate')),
                Decimal('10'))
            self.assertEqual(
                Decimal(self._find_xml_text(
                    invoice_line, 'DiscountsAndRebates', 'Discount',
                    'DiscountAmount')),
                Decimal('1.0000'))
            self.assertEqual(
                Decimal(self._find_xml_text(invoice_line, 'GrossAmount')),
                Decimal('9.0000'))

    @with_transaction()
    def test_attachment_mixed_sizes(self):
        'Test attachments with one small and one large'
        pool = Pool()
        Configuration = pool.get('account.configuration')
        Certificate = pool.get('certificate')
        Account = pool.get('account.account')
        FiscalYear = pool.get('account.fiscalyear')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')
        InvoiceAttachment = pool.get('account.invoice.facturae.attachment')
        IrAttachment = pool.get('ir.attachment')
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
            name='Subdivision', country=country, code='SUB', type='province')
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
        company.facturae_person_type = 'J'
        company.facturae_residence_type = 'R'
        company.party.save()
        company.save()

        with set_company(company):
            certificate = Certificate()
            certificate.name = 'dummy Certificate'
            with open(os.path.join(
                        CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
                certificate.pem_certificate = cert_file.read()
            certificate.save()

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
            revenue, = Account.search([
                    ('type.revenue', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            expense, = Account.search([
                    ('type.expense', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            tax_account, = Account.search([
                    ('code', '=', '6.3.6'), # Main Tax
                    ('closed', '=', False),
                    ], limit=1)
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
            company_address.postal_code = '08201'
            company_address.city = 'City'
            company_address.subdivision = subdivision
            company_address.country = country
            company_address.save()
            party = Party(name='Buyer')
            tax_identifier = PartyIdentifier()
            tax_identifier.type = 'eu_vat'
            tax_identifier.code = 'BE0897290877'
            party.identifiers = [tax_identifier]
            party.save()

            address_dict = {
                'party': party.id,
                'street': 'St sample, 15',
                'city': 'City',
                'postal_code': '08201',
                'subdivision': subdivision.id,
                'country': country.id,
                'facturae_person_type': 'J',
                'facturae_residence_type': 'R',
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

            configuration = Configuration(1)
            configuration.facturae_service = 'only_file'
            configuration.save()

            with Transaction().set_user(0):
                invoice = Invoice()
                invoice.type = 'out'
                invoice.party = party
                invoice.on_change_party()
                invoice.payment_type = payment_receivable
                invoice.payment_term = term
                invoice.currency = currency
                invoice.company = company
                invoice.file_reference = 'FileReference'
                invoice.receiver_contract_reference = 'ReceiverContract'
                invoice.invoice_description = 'InvoiceDescription'
                invoice.set_journal()
                invoice._update_account()

                line1 = InvoiceLine()
                line1.company = company
                line1.currency = currency
                line1.product = product
                line1.on_change_product()
                line1.on_change_account()
                line1.quantity = 5
                line1.unit_price = Decimal('40')

                line2 = InvoiceLine()
                line2.company = company
                line2.currency = currency
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

                # Create small attachment
                attachment_data_small = secrets.token_bytes(50 * 1024) # random 50 KB
                attachment_small = IrAttachment()
                attachment_small.name = 'test_small.pdf'
                attachment_small.type = 'data'
                attachment_small.data = attachment_data_small
                attachment_small.resource = invoice
                attachment_small.save()

                invoice_attachment_small = InvoiceAttachment()
                invoice_attachment_small.invoice = invoice
                invoice_attachment_small.attachment = attachment_small
                invoice_attachment_small.attachment_format = (
                    invoice_attachment_small.on_change_with_attachment_format())
                invoice_attachment_small.description = 'Test small attachment'
                invoice_attachment_small.save()
                self.assertNotEqual(
                    invoice_attachment_small.attachment_format, 'NONE')

                # Create large attachment
                attachment_data_large = secrets.token_bytes(150 * 1024) # random 150 KB
                attachment_large = IrAttachment()
                attachment_large.name = 'test_large.pdf'
                attachment_large.type = 'data'
                attachment_large.data = attachment_data_large
                attachment_large.resource = invoice
                attachment_large.save()

                invoice_attachment_large = InvoiceAttachment()
                invoice_attachment_large.invoice = invoice
                invoice_attachment_large.attachment = attachment_large
                invoice_attachment_large.attachment_format = (
                    invoice_attachment_large.on_change_with_attachment_format())
                invoice_attachment_large.description = 'Test large attachment'
                invoice_attachment_large.save()
                self.assertNotEqual(
                    invoice_attachment_large.attachment_format, 'ZIP')

            invoice.generate_facturae()
            self.assertNotEqual(invoice.invoice_facturae, None)

    @with_transaction()
    def test_attachment_unsupported_format(self):
        'Test attachment with unsupported format'
        pool = Pool()
        Configuration = pool.get('account.configuration')
        Certificate = pool.get('certificate')
        Account = pool.get('account.account')
        FiscalYear = pool.get('account.fiscalyear')
        Invoice = pool.get('account.invoice')
        InvoiceLine = pool.get('account.invoice.line')
        InvoiceAttachment = pool.get('account.invoice.facturae.attachment')
        IrAttachment = pool.get('ir.attachment')
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
            name='Subdivision', country=country, code='SUB', type='province')
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
        company.facturae_person_type = 'J'
        company.facturae_residence_type = 'R'
        company.party.save()
        company.save()

        with set_company(company):
            certificate = Certificate()
            certificate.name = 'dummy Certificate'
            with open(os.path.join(
                        CURRENT_PATH, 'certificate.pfx'), 'rb') as cert_file:
                certificate.pem_certificate = cert_file.read()
            certificate.save()

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
            revenue, = Account.search([
                    ('type.revenue', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            expense, = Account.search([
                    ('type.expense', '=', True),
                    ('closed', '=', False),
                    ], limit=1)
            tax_account, = Account.search([
                    ('code', '=', '6.3.6'), # Main Tax
                    ('closed', '=', False),
                    ], limit=1)
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
            company_address.postal_code = '08201'
            company_address.city = 'City'
            company_address.subdivision = subdivision
            company_address.country = country
            company_address.save()
            party = Party(name='Buyer')
            tax_identifier = PartyIdentifier()
            tax_identifier.type = 'eu_vat'
            tax_identifier.code = 'BE0897290877'
            party.identifiers = [tax_identifier]
            party.save()

            address_dict = {
                'party': party.id,
                'street': 'St sample, 15',
                'city': 'City',
                'postal_code': '08201',
                'subdivision': subdivision.id,
                'country': country.id,
                'facturae_person_type': 'J',
                'facturae_residence_type': 'R',
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

            configuration = Configuration(1)
            configuration.facturae_service = 'only_file'
            configuration.save()

            with Transaction().set_user(0):
                invoice = Invoice()
                invoice.type = 'out'
                invoice.party = party
                invoice.on_change_party()
                invoice.payment_type = payment_receivable
                invoice.payment_term = term
                invoice.currency = currency
                invoice.company = company
                invoice.file_reference = 'FileReference'
                invoice.receiver_contract_reference = 'ReceiverContract'
                invoice.invoice_description = 'InvoiceDescription'
                invoice.set_journal()
                invoice._update_account()

                line1 = InvoiceLine()
                line1.company = company
                line1.currency = currency
                line1.product = product
                line1.on_change_product()
                line1.on_change_account()
                line1.quantity = 5
                line1.unit_price = Decimal('40')

                line2 = InvoiceLine()
                line2.company = company
                line2.currency = currency
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

                # Create unsupported attachment
                attachment_data = secrets.token_bytes(50 * 1024) # random 50 KB
                attachment = IrAttachment()
                attachment.name = 'test.exe'
                attachment.type = 'data'
                attachment.data = attachment_data
                attachment.resource = invoice
                attachment.save()

                invoice_attachment = InvoiceAttachment()
                invoice_attachment.invoice = invoice
                invoice_attachment.attachment = attachment
                with self.assertRaises(UserError):
                    invoice_attachment.attachment_format = (
                        invoice_attachment.on_change_with_attachment_format())

del ModuleTestCase
