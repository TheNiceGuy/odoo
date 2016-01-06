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
    location_id = fields.Many2one('stock.location', 'Source Location', default=lambda self: self.env.ref('stock.warehouse0').lot_stock_id.id or False,)
    scrap_location_id = fields.Many2one('stock.location', domain="[('scrap_location', '=', True)]", string="Scrap Location", default=(lambda x: x.env['stock.location'].search([('scrap_location', '=', True)], limit=1)))
    scrap_qty = fields.Float('Qty To Scrap')
    state = fields.Selection([('confirmed', 'Confirmed'), ('done', 'Done')], default="confirmed")
    move_id = fields.Many2one('stock.move', 'Stock Move')

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id.id

    @api.multi
    def do_scrap(self):
        self.ensure_one()
        StockMove = self.env['stock.move']
        default_val = {
            'name': self.name,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.scrap_qty,
            'location_id': self.location_id.id,
            'scrapped': True,
            'location_dest_id': self.scrap_location_id.id,
        }
        move = StockMove.create(default_val)
        new_move = move.action_scrap(self.scrap_qty, self.scrap_location_id.id)
        self.write({'move_id': new_move.id, 'state': 'done'})
        return True
