# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from openerp import fields, models


class AccountPaymentConfig(models.TransientModel):
    _inherit = 'account.config.settings'

    module_payment_paypal = fields.Boolean(
        'Paypal',
        help='-It installs the module payment_paypal.')
    module_payment_ogone = fields.Boolean(
        'Ogone',
        help='-It installs the module payment_ogone.')
    module_payment_adyen = fields.Boolean(
        'Adyen',
        help='-It installs the module payment_adyen.')
    module_payment_buckaroo = fields.Boolean(
        'Buckaroo',
        help='-It installs the module payment_buckaroo.')
    module_payment_authorize = fields.Boolean(
        'Authorize.Net',
        help='-It installs the module payment_authorize.')
