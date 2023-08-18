# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import ModelSQL, fields
from trytond.pool import Pool, PoolMeta
from trytond.modules.company.model import CompanyValueMixin

REPORT_TYPES = [
    (None, ""),
    ("01", "Value-Added Tax"),
    ("02", "Taxes on production, services and imports in Ceuta and Melilla"),
    ("03", "IGIC:Canaries General Indirect Tax"),
    ("04", "IRPF:Personal Income Tax"),
    ("05", "Other"),
    ("06", "ITPAJD:Tax on wealth transfers and stamp duty"),
    ("07", "IE: Excise duties and consumption taxes"),
    ("08", "Ra: Customs duties"),
    ("09", "IGTECM: Sales tax in Ceuta and Melilla"),
    ("10", "IECDPCAC: Excise duties on oil derivates in Canaries"),
    ("11", "IIIMAB: Tax on premises that affect the environment in the "
        "Balearic Islands"),
    ("12", "ICIO: Tax on construction, installation and works"),
    ("13", "IMVDN: Local tax on unoccupied homes in Navarre"),
    ("14", "IMSN: Local tax on building plots in Navarre"),
    ("15", "IMGSN: Local sumptuary tax in Navarre"),
    ("16", "IMPN: Local tax on advertising in Navarre"),
    ("17", "REIVA: Special VAT for travel agencies"),
    ("18", "REIGIC: Special IGIC: for travel agencies"),
    ("19", "REIPSI: Special IPSI for travel agencies"),
    ("20", "IPS: Insurance premiums Tax"),
    ("21", "SWUA: Surcharge for Winding Up Activity"),
    ("22", "IVPEE: Tax on the value of electricity generation"),
    ("23", "Tax on the production of spent nuclear fuel and radioactive waste "
        "from the generation of nuclear electric power"),
    ("24", "Tax on the storage of spent nuclear energy and radioactive waste "
        "in centralised facilities"),
    ("25", "IDEC: Tax on bank deposits"),
    ("26", "Excise duty applied to manufactured tobacco in Canaries"),
    ("27", "IGFEI: Tax on Fluorinated Greenhouse Gases"),
    ("28", "IRNR: Non-resident Income Tax"),
    ("29", "Corporation Tax"),
    ]


class Configuration(metaclass=PoolMeta):
    __name__ = 'account.configuration'
    facturae_certificate = fields.MultiValue(
        fields.Many2One('certificate', "Factura-e Certificate",
        help='Certificate to sign Factura-e'))
    facturae_service = fields.MultiValue(
        fields.Selection('get_facturae_service', "Factura-e Service",
        help='Service to be used when post the invoice'))
    invoice_facturae_after = fields.TimeDelta("Send Factura-e after",
        help="Grace period after which the invoice will be sent to the facturae "
        "service. Applies only if a worker queue is activated.")

    @classmethod
    def default_facturae_service(cls, **pattern):
        return cls.multivalue_model('facturae_service').default_facturae_service()

    @classmethod
    def get_facturae_service(cls):
        pool = Pool()
        ConfigurationFacturae = pool.get('account.configuration.facturae')
        return ConfigurationFacturae.fields_get(['facturae_service'])['facturae_service']['selection']

    @classmethod
    def multivalue_model(cls, field):
        pool = Pool()
        if field in {'facturae_certificate', 'facturae_service'}:
            return pool.get('account.configuration.facturae')
        return super().multivalue_model(field)


class ConfigurationFacturae(ModelSQL, CompanyValueMixin):
    "Account Configuration Factura-e"
    __name__ = 'account.configuration.facturae'
    facturae_certificate = fields.Many2One('certificate', "Factura-e Certificate",
        help='Certificate to sign Factura-e')
    facturae_service =  fields.Selection([
        (None, 'None'),
        ('only_file', 'Only Generate Facturae'),
        ], "Factura-e Service")

    @staticmethod
    def default_facturae_service():
        return None


class TaxTemplate(metaclass=PoolMeta):
    __name__ = 'account.tax.template'

    report_type = fields.Selection(REPORT_TYPES, 'Report Type', sort=False)

    def _get_tax_value(self, tax=None):
        res = super(TaxTemplate, self)._get_tax_value(tax)

        if not tax or tax.report_type != self.report_type:
            res['report_type'] = self.report_type

        return res


class Tax(metaclass=PoolMeta):
    __name__ = 'account.tax'

    report_type = fields.Selection(REPORT_TYPES, 'Report Type', sort=False)
