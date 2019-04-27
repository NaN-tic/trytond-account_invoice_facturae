# -*- coding: utf-8 -*-
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import glob
import logging
import os
import re
from decimal import Decimal
from jinja2 import Environment, FileSystemLoader
from lxml import etree
from operator import attrgetter
from subprocess import Popen, PIPE
from tempfile import NamedTemporaryFile

from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond import backend
from trytond.i18n import gettext
from trytond.exceptions import UserError

__all__ = ['Invoice', 'InvoiceLine', 'CreditInvoiceStart', 'CreditInvoice',
    'GenerateFacturaeStart', 'GenerateFacturae']

# Get from XSD scheme of Facturae 3.2.1
# http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_1.xml
RECTIFICATIVE_REASON_CODES = [
    ("01", "Invoice number", "Número de la factura"),
    ("02", "Invoice serial number", "Serie de la factura"),
    ("03", "Issue date", "Fecha expedición"),
    ("04", "Name and surnames/Corporate name-Issuer (Sender)",
        "Nombre y apellidos/Razón Social-Emisor"),
    ("05", "Name and surnames/Corporate name-Receiver",
        "Nombre y apellidos/Razón Social-Receptor"),
    ("06", "Issuer's Tax Identification Number",
        "Identificación fiscal Emisor/obligado"),
    ("07", "Receiver's Tax Identification Number",
        "Identificación fiscal Receptor"),
    ("08", "Issuer's address", "Domicilio Emisor/Obligado"),
    ("09", "Receiver's address", "Domicilio Receptor"),
    ("10", "Item line", "Detalle Operación"),
    ("11", "Applicable Tax Rate", "Porcentaje impositivo a aplicar"),
    ("12", "Applicable Tax Amount", "Cuota tributaria a aplicar"),
    ("13", "Applicable Date/Period", "Fecha/Periodo a aplicar"),
    ("14", "Invoice Class", "Clase de factura"),
    ("15", "Legal literals", "Literales legales"),
    ("16", "Taxable Base", "Base imponible"),
    ("80", "Calculation of tax outputs", "Cálculo de cuotas repercutidas"),
    ("81", "Calculation of tax inputs", "Cálculo de cuotas retenidas"),
    ("82",
        "Taxable Base modified due to return of packages and packaging "
        "materials",
        "Base imponible modificada por devolución de envases / embalajes"),
    ("83", "Taxable Base modified due to discounts and rebates",
        "Base imponible modificada por descuentos y bonificaciones"),
    ("84",
        "Taxable Base modified due to firm court ruling or administrative "
        "decision",
        "Base imponible modificada por resolución firme, judicial o "
        "administrativa"),
    ("85",
        "Taxable Base modified due to unpaid outputs where there is a "
        "judgement opening insolvency proceedings",
        "Base imponible modificada cuotas repercutidas no satisfechas. Auto "
        "de declaración de concurso"),
    ]
# UoM Type from UN/CEFACT
UOM_CODE2TYPE = {
    'u': '01',
    'h': '02',
    'kg': '03',
    'g': '21',
    's': '34',
    'm': '25',
    'km': '22',
    'cm': '16',
    'mm': '26',
    'm³': '33',
    'l': '04',
    }
# Missing types in product/uom.xml
# "06", Boxes-BX
# "07", Trays, one layer no cover, plastic-DS
# "08", Barrels-BA
# "09", Jerricans, cylindrical-JY
# "10", Bags-BG
# "11", Carboys, non-protected-CO
# "12", Bottles, non-protected, cylindrical-BO
# "13", Canisters-CI
# "14", Tetra Briks
# "15", Centiliters-CLT
# "17", Bins-BI
# "18", Dozens
# "19", Cases-CS
# "20", Demijohns, non-protected-DJ
# "23", Cans, rectangular-CA
# "24", Bunches-BH
# "27", 6-Packs
# "28", Packages-PK
# "29", Portions
# "30", Rolls-RO
# "31", Envelopes-EN
# "32", Tubs-TB
# "35", Watt-WTT
FACe_REQUIRED_FIELDS = ['facturae_person_type', 'facturae_residence_type']

_slugify_strip_re = re.compile(r'[^\w\s-]')
_slugify_hyphenate_re = re.compile(r'[-\s]+')

DEFAULT_FACTURAE_TEMPLATE = 'template_facturae_3.2.1.xml'
DEFAULT_FACTURAE_SCHEMA = 'Facturaev3_2_1-offline.xsd'


def slugify(value):
    if not isinstance(value, str):
        value = str(value)
    value = str(_slugify_strip_re.sub('', value).strip().lower())
    return _slugify_hyphenate_re.sub('-', value)


def module_path():
    return os.path.dirname(os.path.abspath(__file__))


class Invoice(metaclass=PoolMeta):
    __name__ = 'account.invoice'
    credited_invoices = fields.Function(fields.One2Many('account.invoice',
            None, 'Credited Invoices'),
        'get_credited_invoices', searcher='search_credited_invoices')
    rectificative_reason_code = fields.Selection(
        [(None, "")] + [(x[0], x[1]) for x in RECTIFICATIVE_REASON_CODES],
        'Rectificative Reason Code', sort=False,
        states={
            'invisible': ~Bool(Eval('credited_invoices')),
            'required': (Bool(Eval('credited_invoices'))
                & (Eval('state').in_(['posted', 'paid']))),
            }, depends=['credited_invoices'])
    invoice_facturae = fields.Binary('Factura-e',
        filename='invoice_facturae_filename', readonly=True)
    invoice_facturae_filename = fields.Function(fields.Char(
        'Factura-e filename'), 'get_invoice_facturae_filename')

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._check_modify_exclude.append('invoice_facturae')
        cls._buttons.update({
                'generate_facturae_wizard': {
                    'invisible': ((Eval('type') != 'out')
                        | ~Eval('state').in_(['posted', 'paid'])),
                    'readonly': Bool(Eval('invoice_facturae')),
                    }
                })

    def get_credited_invoices(self, name):
        pool = Pool()
        InvoiceLine = pool.get('account.invoice.line')
        invoices = set()
        for line in self.lines:
            if isinstance(line.origin, InvoiceLine) and line.origin.invoice:
                invoices.add(line.origin.invoice.id)
        return list(invoices)

    @classmethod
    def search_credited_invoices(cls, name, clause):
        return [('lines.origin.invoice',) + tuple(clause[1:3])
            + ('account.invoice.line',) + tuple(clause[3:])]

    def get_invoice_facturae_filename(self, name):
        return 'facturae-%s.xsig' % slugify(self.number)

    @property
    def rectificative_reason_spanish_description(self):
        if self.rectificative_reason_code:
            for code, _, spanish_description in RECTIFICATIVE_REASON_CODES:
                if code == self.rectificative_reason_code:
                    return spanish_description

    @property
    def taxes_outputs(self):
        """Return list of 'impuestos repecutidos'"""
        return [inv_tax for inv_tax in self.taxes
            if inv_tax.tax and inv_tax.tax.rate >= Decimal(0)]

    @property
    def taxes_withheld(self):
        """Return list of 'impuestos retenidos'"""
        return [inv_tax for inv_tax in self.taxes
            if inv_tax.tax and inv_tax.tax.rate < Decimal(0)]

    @property
    def payment_details(self):
        return sorted([ml for ml in self.move.lines
                if ml.account.type.receivable],
            key=attrgetter('maturity_date'))

    def _credit(self):
        invoice_vals = super(Invoice, self)._credit()
        rectificative_reason_code = Transaction().context.get(
            'rectificative_reason_code')
        if rectificative_reason_code:
            invoice_vals['rectificative_reason_code'] = (
                rectificative_reason_code)
        return invoice_vals

    @classmethod
    @ModelView.button_action(
        'account_invoice_facturae.wizard_generate_signed_facturae')
    def generate_facturae_wizard(cls, invoices):
        pass

    @classmethod
    def generate_facturae_default(cls, invoices, certificate_password):
        to_write = ([],)
        for invoice in invoices:
            if invoice.invoice_facturae:
                continue
            facturae_content = invoice.get_facturae()
            invoice._validate_facturae(facturae_content)
            if backend.name() != 'sqlite':
                invoice_facturae = invoice._sign_facturae(
                    facturae_content, certificate_password)
            else:
                invoice_facturae = facturae_content
            to_write[0].append(invoice)
            to_write += ({'invoice_facturae': invoice_facturae},)
        if to_write:
            cls.write(*to_write)

    def get_facturae(self):
        jinja_env = Environment(
            loader=FileSystemLoader(module_path()),
            trim_blocks=True,
            lstrip_blocks=True,
            )
        template = DEFAULT_FACTURAE_TEMPLATE
        return self._get_jinja_template(jinja_env, template).render(
            self._get_content_to_render(), ).encode('utf-8')

    def _get_jinja_template(self, jinja_env, template):
        return jinja_env.get_template(template)

    def _get_content_to_render(self):
        """Return the content to render in factura-e XML file"""
        pool = Pool()
        Currency = pool.get('currency.currency')
        Date = pool.get('ir.date')
        Rate = pool.get('currency.currency.rate')

        if self.type != 'out':
            return
        if self.state not in ('posted', 'paid'):
            return

        # These are an assert because it shouldn't happen
        assert self.invoice_date <= Date.today(), (
            "Invoice date of invoice %s is in the future" % self.id)
        assert len(self.credited_invoices) < 2, (
            "Too much credited invoices for invoice %s" % self.id)
        assert not self.credited_invoices or self.rectificative_reason_code, (
            "Missing rectificative_reason_code for invoice %s with credited "
            "invoices" % self.id)
        assert len(self.taxes_outputs) > 0, (
            "Missing some tax in invoice %s" % self.id)

        for field in FACe_REQUIRED_FIELDS:
            for party in [self.party, self.company.party]:
                if not getattr(party, field):
                    raise UserError(gettext(
                        'account_invoice_facturae.party_facturae_fields',
                            party=party.rec_name,
                            invoice=self.rec_name,
                            field=field))
        if (not self.company.party.tax_identifier
                or len(self.company.party.tax_identifier.code) < 3
                or len(self.company.party.tax_identifier.code) > 30):
            raise UserError(gettext(
                'account_invoice_facturae.company_vat_identifier',
                    party=self.company.party.rec_name))

        if (not self.company.party.addresses
                or not self.company.party.addresses[0].street
                or not self.company.party.addresses[0].zip
                or not self.company.party.addresses[0].city
                or not self.company.party.addresses[0].subdivision
                or not self.company.party.addresses[0].country):
            raise UserError(gettext(
                'account_invoice_facturae.company_address_fields',
                    party=self.company.party.rec_name))

        if (not self.party.tax_identifier
                or len(self.party.tax_identifier.code) < 3
                or len(self.party.tax_identifier.code) > 30):
            raise UserError(gettext(
                'account_invoice_facturae.party_vat_identifier',
                    party=self.party.rec_name,
                    invoice=self.rec_name))
        if (self.party.facturae_person_type == 'F'
                and len(self.party.name.split(' ', 2)) < 2):
            raise UserError(gettext(
                'account_invoice_facturae.party_name_surname',
                    party=self.party.rec_name,
                    invoice=self.rec_name))
        if (not self.invoice_address.street
                or not self.invoice_address.zip
                or not self.invoice_address.city
                or not self.invoice_address.subdivision
                or not self.invoice_address.country):
            raise UserError(gettext(
                'account_invoice_facturae.invoice_address_fields',
                    invoice=self.rec_name))

        euro, = Currency.search([('code', '=', 'EUR')])
        if self.currency != euro:
            assert (euro.rate == Decimal(1)
                or self.currency.rate == Decimal(1)), (
                "Euro currency or the currency of invoice %s must to be the "
                "base currency" % self.id)
            if euro.rate == Decimal(1):
                rates = Rate.search([
                        ('currency', '=', self.currency),
                        ('date', '<=', self.invoice_date),
                        ], limit=1, order=[('date', 'DESC')])
                if not rates:
                    raise UserError(gettext(
                        'account_invoice_facturae.no_rate',
                            currency=self.currenc.name,
                            date=self.invoice_date.strftime('%d/%m/%Y')))
                exchange_rate = rates[0].rate
                exchange_rate_date = rates[0].date
            else:
                rates = Rate.search([
                        ('currency', '=', euro),
                        ('date', '<=', self.invoice_date),
                        ], limit=1, order=[('date', 'DESC')])
                if not rates:
                    raise UserError(gettext(
                        'account_invoice_facturae.no_rate',
                            currency=euro.name,
                            date=self.invoice_date.strftime('%d/%m/%Y')))
                exchange_rate = Decimal(1) / rates[0].rate
                exchange_rate_date = rates[0].date
        else:
            exchange_rate = exchange_rate_date = None

        for invoice_tax in self.taxes:
            assert invoice_tax.tax, 'Empty tax in invoice %s' % self.id
            assert (invoice_tax.tax.type == 'percentage'), (
                'Unsupported non percentage tax %s of invoice %s'
                % (invoice_tax.tax.id, self.id))

        for move_line in self.payment_details:
            if not move_line.payment_type:
                raise UserError(gettext(
                    'account_invoice_facturae.missing_payment_type',
                    invoice=self.rec_name))
            if not move_line.payment_type.facturae_type:
                raise UserError(gettext(
                    'account_invoice_facturae.missing_payment_type_facturae_type',
                        payment_type=move_line.payment_type.rec_name,
                        invoice=self.rec_name))
            if move_line.payment_type.facturae_type in ('02', '04'):
                if not hasattr(move_line, 'account_bank'):
                    raise UserError(gettext(
                        'account_invoice_facturae.missing_account_bank_module',
                            payment_type=move_line.payment_type.rec_name,
                            invoice=self.rec_name))
                if not move_line.bank_account:
                    raise UserError(gettext(
                        'account_invoice_facturae.missing_bank_account',
                            invoice=self.rec_name))
                if not [n for n in move_line.bank_account.numbers
                        if n.type == 'iban']:
                    raise UserError(gettext(
                        'account_invoice_facturae.missing_iban',
                        bank_account=move_line.bank_account.rec_name,
                        invoice=self.rec_name))

        return {
                'invoice': self,
                'Decimal': Decimal,
                'Currency': Currency,
                'euro': euro,
                'exchange_rate': exchange_rate,
                'exchange_rate_date': exchange_rate_date,
                'invoice': self,
                'Decimal': Decimal,
                'Currency': Currency,
                'euro': euro,
                'exchange_rate': exchange_rate,
                'exchange_rate_date': exchange_rate_date,
                'UOM_CODE2TYPE': UOM_CODE2TYPE,
                }

    def _validate_facturae(self, xml_string, schema_file_path=None):
        """
        Inspired by https://github.com/pedrobaeza/l10n-spain/blob/d01d049934db55130471e284012be7c860d987eb/l10n_es_facturae/wizard/create_facturae.py
        """
        logger = logging.getLogger('account_invoice_facturae')

        if not schema_file_path:
            schema_file_path = os.path.join(
                module_path(),
                DEFAULT_FACTURAE_SCHEMA)
        with open(schema_file_path, encoding='utf-8') as schema_file:
            facturae_schema = etree.XMLSchema(file=schema_file)
            logger.debug("%s loaded" % schema_file_path)
        try:
            facturae_schema.assertValid(etree.fromstring(xml_string))
            logger.debug("Factura-e XML of invoice %s validated",
                self.rec_name)
        except Exception as e:
            logger.warning("Error validating generated Factura-e file",
                exc_info=True)
            logger.debug(xml_string)
            raise UserError(gettext(
                'account_invoice_facturae.invalid_factura_xml_file',
                    invoice=self.rec_name, message=e))
        return True


    def _sign_facturae(self, xml_string, certificate_password):
        """
        Inspired by https://github.com/pedrobaeza/l10n-spain/blob/d01d049934db55130471e284012be7c860d987eb/l10n_es_facturae/wizard/create_facturae.py
        """
        if not self.company.facturae_certificate:
            raise UserError(gettext(
                'account_invoice_facturae.missing_certificate',
                company=self.company.rec_name))

        logger = logging.getLogger('account_invoice_facturae')

        unsigned_file = NamedTemporaryFile(suffix='.xml', delete=False)
        unsigned_file.write(xml_string)
        unsigned_file.close()

        cert_file = NamedTemporaryFile(suffix='.pfx', delete=False)
        cert_file.write(self.company.facturae_certificate)
        cert_file.close()

        signed_file = NamedTemporaryFile(suffix='.xsig', delete=False)

        env = {}
        env.update(os.environ)
        libs = os.path.join(module_path(), 'java', 'lib', '*.jar')
        env['CLASSPATH'] = ':'.join(glob.glob(libs))

        # TODO: implement Signer with python
        # http://www.pyopenssl.org/en/stable/api/crypto.html#OpenSSL.crypto.load_pkcs12
        signature_command = [
            'java',
            '-Djava.awt.headless=true',
            'com.nantic.facturae.Signer',
            '0',
            unsigned_file.name,
            signed_file.name,
            'facturae31',
            cert_file.name,
            certificate_password
            ]
        signature_process = Popen(signature_command,
            stdout=PIPE,
            stderr=PIPE,
            env=env,
            cwd=os.path.join(module_path(), 'java'))
        output, err = signature_process.communicate()
        rc = signature_process.returncode
        if rc != 0:
            logger.warning('Error %s signing invoice "%s" with command '
                '"%s <password>": %s %s', rc, self.id,
                signature_command[:-1], output, err)
            raise UserError(gettext(
                'account_invoice_factura.error_signing',
                    invoice=self.rec_name,
                    process_output=output))

        logger.info("Factura-e for invoice %s (%s) generated and signed",
            self.rec_name, self.id)

        signed_file_content = signed_file.read()
        signed_file.close()

        os.unlink(unsigned_file.name)
        os.unlink(cert_file.name)
        os.unlink(signed_file.name)

        return signed_file_content


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'

    @property
    def taxes_outputs(self):
        """Return list of 'impuestos repecutidos'"""
        return [inv_tax for inv_tax in self.invoice_taxes
            if inv_tax.tax and inv_tax.tax.rate >= Decimal(0)]

    @property
    def taxes_withheld(self):
        """Return list of 'impuestos retenidos'"""
        return [inv_tax for inv_tax in self.invoice_taxes
            if inv_tax.tax and inv_tax.tax.rate < Decimal(0)]

    @property
    def taxes_additional_line_item_information(self):
        res = {}
        for inv_tax in self.invoice_taxes:
            if inv_tax.tax and (not inv_tax.tax.report_type
                    or inv_tax.tax.report_type == '05'):
                key = (inv_tax.tax.rate * 100, inv_tax.base, inv_tax.amount)
                res.setdefault('05', []).append((key, inv_tax.description))
            elif inv_tax.tax and inv_tax.tax.report_description:
                res[inv_tax.tax.report_type] = inv_tax.tax.report_description
        if '05' in res:
            if len(res['05']) == 1:
                res['05'] = res['05'][0]
            else:
                for key, tax_description in res['05']:
                    res['05 %s %s %s' % key] = tax_description
                del res['05']
        return res


class CreditInvoiceStart(metaclass=PoolMeta):
    __name__ = 'account.invoice.credit.start'
    rectificative_reason_code = fields.Selection(
        [(x[0], x[1]) for x in RECTIFICATIVE_REASON_CODES],
        'Rectificative Reason Code', required=True, sort=False)


class CreditInvoice(metaclass=PoolMeta):
    __name__ = 'account.invoice.credit'

    def do_credit(self, action):
        with Transaction().set_context(
                rectificative_reason_code=self.start.rectificative_reason_code
                ):
            return super(CreditInvoice, self).do_credit(action)


class GenerateFacturaeStart(ModelView):
    'Generate Factura-e file - Start'
    __name__ = 'account.invoice.generate_facturae.start'
    service = fields.Selection([
        ('default', 'Default'),
        ], 'Service', required=True)
    certificate_password = fields.Char('Certificate Password',
        states={
            'required': Eval('service') == 'default',
            'invisible': Eval('service') != 'default',
        }, depends=['service'])

    @staticmethod
    def default_service():
        return 'default'


class GenerateFacturae(Wizard):
    'Generate Factura-e file'
    __name__ = 'account.invoice.generate_facturae'
    start = StateView('account.invoice.generate_facturae.start',
        'account_invoice_facturae.generate_facturae_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generate', 'generate', 'tryton-executable', default=True),
            ])
    generate = StateTransition()

    def transition_generate(self):
        Invoice = Pool().get('account.invoice')

        invoices = Invoice.browse(Transaction().context['active_ids'])
        service = 'generate_facturae_%s' % self.start.service
        getattr(Invoice, service)(invoices, self.start.certificate_password)
        return 'end'
