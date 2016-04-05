# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import models, fields, api


class AccountTax(models.Model):
    _inherit = 'account.tax'


    type_tax_use = fields.Selection(selection_add=[('tax_adjustments', 'Tax Adjustments')])
