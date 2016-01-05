# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError

class StockScrapWizard(models.TransientModel):
    _name = 'stock.scrap.wizard'

    product_id = fields.Many2one('product.product', 'Product')
    product_qty = fields.Float('Qty In Stock', readonly=True)
    scrap_qty = fields.Float('Qty To Scrap')
    lot_id = fields.Many2one('stock.production.lot', 'Lot')
    scrap_location_id = fields.Many2one('stock.location', domain="[('scrap_location', '=', True)]", string="Scrap Location", default=(lambda x: x.env['stock.location'].search([('scrap_location', '=', True)], limit=1)))
