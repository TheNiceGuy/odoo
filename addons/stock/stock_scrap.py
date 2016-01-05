# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models


class StockScrap(models.Model):
    _name = 'stock.scrap'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('stock.scrap') or '/')
    product_id = fields.Many2one('product.product', 'Product')
    product_uom_id = fields.Many2one('product.uom', string='Product UoM')
    lot_id = fields.Many2one('stock.production.lot', 'Lot')
    picking_id = fields.Many2one('stock.picking', 'Picking', default=(lambda x: (x.env.context.get('active_id'))))
    location_id = fields.Many2one('stock.location', 'Source Location')
    scrap_location_id = fields.Many2one('stock.location', domain="[('scrap_location', '=', True)]", string="Scrap Location", default=(lambda x: x.env['stock.location'].search([('scrap_location', '=', True)], limit=1)))
    scrap_qty = fields.Float('Qty To Scrap')
    state = fields.Selection([('confirmed', 'Confirmed'), ('done', 'Done')], default="confirmed")
