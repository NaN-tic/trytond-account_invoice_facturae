# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['Company']


class Company(metaclass=PoolMeta):
    __name__ = 'company.company'
    facturae_certificate = fields.Binary('Factura-e Certificate',
        help='The certificate to generate the XAdES electronic firm for '
        'invoices.')

