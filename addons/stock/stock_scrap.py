# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models


class StockScrap(models.Model):
    _name = 'stock.scrap'

    name = fields.Char(required=True, readonly=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('stock.scrap') or '/')
    product_id = fields.Many2one('product.product', 'Product')
    product_uom_id = fields.Many2one('product.uom', string='Product UoM')
    lot_id = fields.Many2one('stock.production.lot', 'Lot')
    picking_id = fields.Many2one('stock.picking', 'Picking')
    location_id = fields.Many2one('stock.location', 'Source Location')
    scrap_location_id = fields.Many2one('stock.location', domain="[('scrap_location', '=', True)]", string="Scrap Location", default=(lambda x: x.env['stock.location'].search([('scrap_location', '=', True)], limit=1)))
    scrap_qty = fields.Float('Qty To Scrap')
    state = fields.Selection([('confirmed', 'Confirmed'), ('done', 'Done')], default="confirmed")

    def _translate_quants_to_lines(self, quants):
        grouped_quants = {}
        for quant in quants:
            key = (quant.location_id.id, quant.product_id.id, quant.package_id.id, quant.lot_id.id, quant.owner_id.id)
            if grouped_quants.get(key):
                grouped_quants[key] += quant.qty
            else:
                grouped_quants[key] = quant.qty
        scrap_lines = []
        for key in grouped_quants:
            scrap_lines += [{
                'location_id': key[0],
                'product_id': key[1],
                'package_id': key[2],
                'lot_id': key[3],
                'owner_id': key[4],
                'product_qty': grouped_quants[key]
            }]
            return scrap_lines

    @api.multi
    def do_scrap(self):
        self.ensure_one()
        return True
