# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta
from trytond.i18n import gettext
from trytond.exceptions import UserError

__all__ = ['PaymentType']


class PaymentType(metaclass=PoolMeta):
    __name__ = 'account.payment.type'
    facturae_type = fields.Selection([
            (None, ''),
            ('01', 'In cash'),
            ('02', 'Direct debit'),
            ('03', 'Receipt'),
            ('04', 'Credit transfer'),
            ('05', 'Accepted bill of exchange'),
            ('06', 'Documentary credit'),
            ('07', 'Contract award'),
            ('08', 'Bill of exchange'),
            ('09', 'Transferable promissory note'),
            ('10', 'Non transferable promissory note'),
            ('11', 'Cheque'),
            ('12', 'Open account reimbursement'),
            ('13', 'Special payment'),
            ('14', 'Set-off by reciprocal credits'),
            ('15', 'Payment by postgiro'),
            ('16', 'Certified cheque'),
            ('17', 'Banker\'s draft'),
            ('18', 'Cash on delivery'),
            ('19', 'Payment by card'),
            ], 'Factura-e Type', sort=False)



    @classmethod
    def validate(cls, payment_types):
        super(PaymentType, cls).validate(payment_types)
        for payment_type in payment_types:
            payment_type.check_facturae_type()

    def check_facturae_type(self):
        if not hasattr(self, 'account_bank'):
            # account_bank module not installed
            return
        if (self.facturae_type and self.facturae_type == '02'
                and self.account_bank != 'party'
                or self.facturae_type and self.facturae_type == '04'
                and self.account_bank != 'company'):
            raise UserError(gettext(
                'account_invoice_facturae.incompatible_facturae_type_account_bank',
                payment_type=self.rec_name))
