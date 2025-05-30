# -*- coding: utf-8 -*-
# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import logging
import os
import base64
import random
import xmlsig
import hashlib
import datetime
import math
from decimal import Decimal
from jinja2 import Environment, FileSystemLoader
from lxml import etree
from operator import attrgetter
from trytond.model import ModelView, fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Bool, Eval
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond import backend
from trytond.i18n import gettext
from trytond.exceptions import UserError, UserWarning
from trytond.modules.certificate_manager.certificate_manager import (
    ENCODING_DER)
from trytond.tools import slugify

FACTURAE_SCHEMA_VERSION = '3.2.2'

# Get from XSD scheme of Facturae 3.2.2
# http://www.facturae.gob.es/formato/Versiones/Facturaev3_2_2.xml
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

DEFAULT_FACTURAE_TEMPLATE = 'template_facturae_3.2.2.xml'
DEFAULT_FACTURAE_SCHEMA = 'Facturaev3_2_2-offline.xml'


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
            })
    invoice_facturae = fields.Binary('Factura-e',
        filename='invoice_facturae_filename')
    invoice_facturae_filename = fields.Function(fields.Char(
        'Factura-e filename'), 'get_invoice_facturae_filename')
    invoice_facturae_sent = fields.Boolean('Factura-e Sent')
    file_reference = fields.Char('File Reference', size=20, states={
            'readonly': (Eval('state') != 'draft'),
        }, depends=['state'])
    receiver_contract_reference = fields.Char('Receiver Contract Reference',
        size=20, states={'readonly': (Eval('state') != 'draft'),},
        depends=['state'])
    invoice_description = fields.Text('Invoice Description', size=2500,
        states={'readonly': (Eval('state') != 'draft'),}, depends=['state'])

    @classmethod
    def __setup__(cls):
        super(Invoice, cls).__setup__()
        cls._check_modify_exclude |= {'invoice_facturae', 'invoice_facturae_sent'}
        cls._buttons.update({
                'generate_facturae_wizard': {
                    'invisible': ((Eval('type') != 'out')
                        | ~Eval('state').in_(['posted', 'paid'])),
                    'readonly': Bool(Eval('invoice_facturae_sent')),
                    }
                })

    @classmethod
    def copy(cls, invoices, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default.setdefault('invoice_facturae', None)
        default.setdefault('rectificative_reason_code', None)
        default.setdefault('invoice_facturae_sent', None)
        return super(Invoice, cls).copy(invoices, default=default)

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

    @classmethod
    def draft(cls, invoices):
        invoice_facturae_sends = [invoice for invoice in invoices if invoice.invoice_facturae_sent]
        if invoice_facturae_sends:
            names = ', '.join(m.rec_name for m in invoice_facturae_sends[:5])
            if len(invoice_facturae_sends) > 5:
                names += '...'
            raise UserError(gettext('account_invoice_facturae.msg_draft_invoice_facturae_sent',
                invoices=names))

        cls.write(invoices, {
            'invoice_facturae': None,
            })
        super(Invoice, cls).draft(invoices)

    @classmethod
    def post(cls, invoices):
        super(Invoice, cls).post(invoices)

        for invoice in invoices:
            cls.__queue__.generate_facturae(invoice)

    def _credit(self, **values):
        credit = super(Invoice, self)._credit(**values)
        rectificative_reason_code = Transaction().context.get(
            'rectificative_reason_code')
        if rectificative_reason_code:
            credit.rectificative_reason_code = rectificative_reason_code
        return credit

    @classmethod
    @ModelView.button_action(
        'account_invoice_facturae.wizard_generate_signed_facturae')
    def generate_facturae_wizard(cls, invoices):
        pass

    def generate_facturae(self, certificate=None, service=None):
        pool = Pool()
        Configuration = pool.get('account.configuration')
        Invoice = pool.get('account.invoice')

        config = Configuration(1)
        transaction = Transaction()

        if self.type != 'out' or self.state not in ('posted', 'paid'):
            return
        # send facturae to service
        if not service and config.facturae_service:
            service = config.facturae_service
        if service:
            if not self.invoice_facturae:
                lang = (self.party.lang and self.party.lang.code
                    or Transaction().language)
                with Transaction().set_context(language=lang):
                    invoice = Invoice(self.id)
                    facturae_content = invoice.get_facturae()
                self._validate_facturae(facturae_content, service=service)
                if backend.name != 'sqlite' and certificate:
                    invoice_facturae = self._sign_facturae(facturae_content,
                        'default', certificate)
                else:
                    invoice_facturae = facturae_content
                self.invoice_facturae = invoice_facturae
                self.save()

            if self.invoice_facturae and service != 'only_file':
                with transaction.set_context(
                        queue_scheduled_at=config.invoice_facturae_after):
                    Invoice.__queue__.send_facturae(self, service)

    def send_facturae(self, service):
        Invoice = Pool().get('account.invoice')

        method = 'send_facturae_%s' % service
        getattr(Invoice, method)(self)

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
        Invoice = pool.get('account.invoice')
        Date = pool.get('ir.date')
        Rate = pool.get('currency.currency.rate')
        Warning = pool.get('res.user.warning')

        # These are an assert because it shouldn't happen
        assert len(self.credited_invoices) < 2, (
            "Too much credited invoices for invoice %s" % self.id)
        assert not self.credited_invoices or self.rectificative_reason_code, (
            "Missing rectificative_reason_code for invoice %s with credited "
            "invoices" % self.id)
        assert len(self.taxes_outputs) > 0, (
            "Missing some tax in invoice %s" % self.id)

        if self.invoice_date > Date.today():
            key = Warning.format('future_facturae', [self.id])
            if Warning.check(key):
                raise UserWarning(key, gettext(
                    'account_invoice_facturae.msg_future_facturae_warning',
                    id=self.id))

        for field in FACe_REQUIRED_FIELDS:
            if (not getattr(self.invoice_address, field)
                    or not getattr(self.company, field)):
                raise UserError(gettext(
                        'account_invoice_facturae.party_facturae_fields',
                        party=self.party.rec_name,
                        invoice=self.rec_name,
                        field=field))
        if (not self.company.party.tax_identifier
                or len(self.company.party.tax_identifier.code) < 3
                or len(self.company.party.tax_identifier.code) > 30):
            raise UserError(gettext(
                    'account_invoice_facturae.company_vat_identifier',
                    party=self.company.party.rec_name))

        company_address = self.company.party.address_get(type='invoice')
        if (not company_address
                or not company_address.street
                or not company_address.postal_code
                or not company_address.city
                or not company_address.subdivision
                or not company_address.country):
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
        if (self.invoice_address.facturae_person_type == 'F'
                and len(self.party.name.split(' ', 2)) < 2):
            raise UserError(gettext(
                    'account_invoice_facturae.party_name_surname',
                    party=self.party.rec_name,
                    invoice=self.rec_name))
        if (not self.invoice_address.street
                or not self.invoice_address.postal_code
                or not self.invoice_address.city
                or not self.invoice_address.subdivision
                or not self.invoice_address.country):
            raise UserError(gettext(
                    'account_invoice_facturae.invoice_address_fields',
                    invoice=self.rec_name))

        euro, = Currency.search([('code', '=', 'EUR')], limit=1)
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
                        'account_invoice_facturae.'
                        'missing_payment_type_facturae_type',
                        payment_type=move_line.payment_type.rec_name,
                        invoice=self.rec_name))
            if move_line.payment_type.facturae_type in ('02', '04'):
                if not hasattr(move_line, 'account_bank'):
                    raise UserError(gettext(
                            'account_invoice_facturae.'
                            'missing_account_bank_module',
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
                'Invoice': Invoice,
                'euro': euro,
                'exchange_rate': exchange_rate,
                'exchange_rate_date': exchange_rate_date,
                'UOM_CODE2TYPE': UOM_CODE2TYPE,
                }

    def _validate_facturae(self, xml_string, schema_file_path=None, service=None):
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

    def _sign_facturae(self, xml_string, service='default', certificate=None):
        """
        Inspired by https://github.com/pedrobaeza/l10n-spain/blob/d01d049934db55130471e284012be7c860d987eb/l10n_es_facturae/wizard/create_facturae.py
        """
        pool = Pool()
        Configuration = pool.get('account.configuration')

        if not certificate:
            certificate = Configuration(1).facturae_certificate
            if not certificate:
                raise UserError(gettext(
                        'account_invoice_facturae.msg_missing_certificate'))

        logger = logging.getLogger('account_invoice_facturae')

        def _sign_file(cert, request):
            key = cert.load_pem_key()
            pem = cert.load_pem_certificate()

            # DER is an ASN.1 encoding type
            crt = pem.public_bytes(ENCODING_DER)

            # Set variables values
            rand_min = 1
            rand_max = 99999
            signature_id = "Signature%05d" % random.randint(rand_min, rand_max)
            signed_properties_id = (
                signature_id
                + "-SignedProperties%05d" % random.randint(rand_min, rand_max)
                )
            key_info_id = "KeyInfo%05d" % random.randint(rand_min, rand_max)
            reference_id = "Reference%05d" % random.randint(rand_min, rand_max)
            object_id = "Object%05d" % random.randint(rand_min, rand_max)
            etsi = "http://uri.etsi.org/01903/v1.3.2#"
            sig_policy_identifier = (
                "http://www.facturae.es/"
                "politica_de_firma_formato_facturae/"
                "politica_de_firma_formato_facturae_v3_1"
                ".pdf"
                )
            sig_policy_hash_value = "Ohixl6upD6av8N7pEvDABhEL6hM="

            # Get XML file to edit
            root = etree.fromstring(request)

            # Create a signature template for RSA-SHA1 enveloped signature.
            sign = xmlsig.template.create(
                c14n_method=xmlsig.constants.TransformInclC14N,
                sign_method=xmlsig.constants.TransformRsaSha1,
                name=signature_id,
                ns="ds",
                )
            assert sign is not None

            # Add the <ds:Signature/> node to the document.
            root.append(sign)

            # Add the <ds:Reference/> node to the signature template.
            ref = xmlsig.template.add_reference(
                sign, xmlsig.constants.TransformSha1, name=reference_id, uri=""
                )

            # Add the enveloped transform descriptor.
            xmlsig.template.add_transform(ref,
                xmlsig.constants.TransformEnveloped)

            # Add 2 new <ds:Reference/> node to the signature template.
            xmlsig.template.add_reference(
                sign,
                xmlsig.constants.TransformSha1,
                uri="#" + signed_properties_id,
                uri_type="http://uri.etsi.org/01903#SignedProperties",
                )
            xmlsig.template.add_reference(
                sign, xmlsig.constants.TransformSha1, uri="#" + key_info_id
                )

            # Add the <ds:KeyInfo/> and <ds:KeyName/> nodes.
            key_info = xmlsig.template.ensure_key_info(sign, name=key_info_id)
            x509_data = xmlsig.template.add_x509_data(key_info)
            xmlsig.template.x509_data_add_certificate(x509_data)

            # Set the certificate values
            ctx = xmlsig.SignatureContext()
            ctx.private_key = key
            ctx.x509 = pem
            ctx.public_key = pem.public_key()

            # Set the footer validation
            object_node = etree.SubElement(
                sign,
                etree.QName(xmlsig.constants.DSigNs, "Object"),
                nsmap={"etsi": etsi},
                attrib={xmlsig.constants.ID_ATTR: object_id},
                )
            qualifying_properties = etree.SubElement(
                object_node,
                etree.QName(etsi, "QualifyingProperties"),
                attrib={"Target": "#" + signature_id},
                )
            signed_properties = etree.SubElement(
                qualifying_properties,
                etree.QName(etsi, "SignedProperties"),
                attrib={xmlsig.constants.ID_ATTR: signed_properties_id},
                )
            signed_signature_properties = etree.SubElement(
                signed_properties, etree.QName(etsi,
                    "SignedSignatureProperties")
                )
            now = datetime.datetime.now()
            etree.SubElement(
                signed_signature_properties, etree.QName(etsi, "SigningTime")
                ).text = now.isoformat()
            signing_certificate = etree.SubElement(
                signed_signature_properties, etree.QName(etsi,
                    "SigningCertificate")
                )
            signing_certificate_cert = etree.SubElement(
                signing_certificate, etree.QName(etsi, "Cert")
                )
            cert_digest = etree.SubElement(
                signing_certificate_cert, etree.QName(etsi, "CertDigest")
                )
            etree.SubElement(
                cert_digest,
                etree.QName(xmlsig.constants.DSigNs, "DigestMethod"),
                attrib={"Algorithm": "http://www.w3.org/2000/09/xmldsig#sha1"},
                )

            hash_cert = hashlib.sha1(crt)
            etree.SubElement(
                cert_digest, etree.QName(xmlsig.constants.DSigNs,
                    "DigestValue")
                ).text = base64.b64encode(hash_cert.digest())

            issuer_serial = etree.SubElement(
                signing_certificate_cert, etree.QName(etsi, "IssuerSerial")
                )
            etree.SubElement(
                issuer_serial, etree.QName(xmlsig.constants.DSigNs,
                    "X509IssuerName")
                ).text = xmlsig.utils.get_rdns_name(pem.issuer.rdns)
            etree.SubElement(
                issuer_serial, etree.QName(xmlsig.constants.DSigNs,
                    "X509SerialNumber")
                ).text = str(pem.serial_number)

            signature_policy_identifier = etree.SubElement(
                signed_signature_properties,
                etree.QName(etsi, "SignaturePolicyIdentifier"),
                )
            signature_policy_id = etree.SubElement(
                signature_policy_identifier, etree.QName(etsi,
                    "SignaturePolicyId")
                )
            sig_policy_id = etree.SubElement(
                signature_policy_id, etree.QName(etsi, "SigPolicyId")
                )
            etree.SubElement(
                sig_policy_id, etree.QName(etsi, "Identifier")
                ).text = sig_policy_identifier
            etree.SubElement(
                sig_policy_id, etree.QName(etsi, "Description")
                ).text = "Política de Firma FacturaE v3.1"
            sig_policy_hash = etree.SubElement(
                signature_policy_id, etree.QName(etsi, "SigPolicyHash")
                )
            etree.SubElement(
                sig_policy_hash,
                etree.QName(xmlsig.constants.DSigNs, "DigestMethod"),
                attrib={"Algorithm": "http://www.w3.org/2000/09/xmldsig#sha1"},
                )
            hash_value = sig_policy_hash_value
            etree.SubElement(
                sig_policy_hash, etree.QName(xmlsig.constants.DSigNs,
                    "DigestValue")
                ).text = hash_value
            signer_role = etree.SubElement(
                signed_signature_properties, etree.QName(etsi, "SignerRole")
                )
            claimed_roles = etree.SubElement(
                signer_role, etree.QName(etsi, "ClaimedRoles")
                )
            etree.SubElement(
                claimed_roles, etree.QName(etsi, "ClaimedRole")
                ).text = "supplier"
            signed_data_object_properties = etree.SubElement(
                signed_properties, etree.QName(etsi,
                    "SignedDataObjectProperties")
                )
            data_object_format = etree.SubElement(
                signed_data_object_properties,
                etree.QName(etsi, "DataObjectFormat"),
                attrib={"ObjectReference": "#" + reference_id},
                )
            etree.SubElement(
                data_object_format, etree.QName(etsi, "Description")
                ).text = "Factura"
            data_object_format_identifier = etree.SubElement(
                data_object_format, etree.QName(etsi, "ObjectIdentifier")
                )
            etree.SubElement(
                data_object_format_identifier,
                etree.QName(etsi, "Identifier"),
                attrib={"Qualifier": "OIDAsURN"}
                ).text = "urn:oid:1.2.840.10003.5.109.10"
            etree.SubElement(
                data_object_format_identifier, etree.QName(etsi, "Description")
                )
            etree.SubElement(
                data_object_format, etree.QName(etsi, "MimeType")
                ).text = "text/xml"

            # Sign the file and verify the sign.
            ctx.sign(sign)
            ctx.verify(sign)

            return etree.tostring(root, xml_declaration=True, encoding="UTF-8")

        signed_file_content = _sign_file(certificate, xml_string)

        logger.info("Factura-e for invoice %s (%s) generated and signed",
            self.rec_name, self.id)

        return signed_file_content

    @classmethod
    def double_up_to_eight(cls, value):
        # return max 8 digits in DoubleUpToEightDecimalType
        _TOTAL_DIGITS = 8
        def digits_decimal(value):
            num_str = str(value)
            if '.' in num_str:
                num_digits = num_str[::-1].find('.')
            else:
                num_digits = 0

            return num_digits

        if digits_decimal(value) > _TOTAL_DIGITS:
            precision = 10 ** -_TOTAL_DIGITS
            return math.floor(float(value) / precision) * precision
        return value


class InvoiceLine(metaclass=PoolMeta):
    __name__ = 'account.invoice.line'

    @property
    def facturae_article_code(self):
        return self.product and self.product.code or ''

    @property
    def facturae_item_description(self):
        return (
            (self.description and self.description)
            or (self.product and self.product.rec_name)
            or '#'+str(self.id)
            )

    @property
    def facturae_receiver_transaction_reference(self):
        # TODO Issuer/ReceiverTransactionDate (sale, contract...)
        return ''

    @property
    def facturae_start_date(self):
        try:
            pool = Pool()
            Consumption = pool.get('contract.consumption')
        except:
            Consumption = None

        if (self.origin and Consumption
                and isinstance(self.origin, Consumption)):
            return self.origin.start_date
        return None

    @property
    def facturae_end_date(self):
        try:
            pool = Pool()
            Consumption = pool.get('contract.consumption')
        except:
            Consumption = None

        if (self.origin and Consumption
                and isinstance(self.origin, Consumption)):
            return self.origin.end_date
        elif self.facturae_start_date:
            return self.facturae_start_date
        return None

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
            (None, 'None'),
            ('only_file', 'Only Generate Facturae'),
            ], 'Factura-e Service')
    certificate = fields.Many2One('certificate', 'Factura-e Certificate')


class GenerateFacturae(Wizard):
    'Generate Factura-e file'
    __name__ = 'account.invoice.generate_facturae'
    start = StateView('account.invoice.generate_facturae.start',
        'account_invoice_facturae.generate_facturae_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generate', 'generate', 'tryton-launch', default=True),
            ])
    generate = StateTransition()

    def default_start(self, fields):
        pool = Pool()
        Configuration = pool.get('account.configuration')

        default = {
            'service': None,
            'certificate': None,
            }

        config = Configuration(1)
        if config.facturae_service:
            default['service'] = config.facturae_service
        if config.facturae_certificate:
            default['certificate'] = config.facturae_certificate.id

        return default

    def transition_generate(self):
        Invoice = Pool().get('account.invoice')

        invoices = Invoice.browse(Transaction().context['active_ids'])
        for invoice in invoices:
            invoice.generate_facturae(certificate=getattr(self.start,
                'certificate', None), service=self.start.service)
        return 'end'
