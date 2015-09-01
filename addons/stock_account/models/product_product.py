# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.onchange('type')
    def onchange_type_valuation(self):
        if self.type != 'product':
            self.valuation = 'manual_periodic'
        return {}
