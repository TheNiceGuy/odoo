# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    can_be_expensed = fields.Boolean(help="Specify whether the product can be selected in an HR expense.", string="Can be Expensed")

     
    @api.onchange('can_be_expensed')
    def onchange_can_be_expensed(self):
        if hasattr(self, 'available_in_pos'):
            if self.can_be_expensed:
                self.available_in_pos = False
