# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    production_id = fields.Many2one(
        'mrp.production', 'Manufacturing Order',
        states={'done': [('readonly', True)]})

    @api.multi
    def do_scrap(self):
        self.ensure_one()
        StockMove = self.env['stock.move']
        production_id = False
        picking_id = False
        origin = ''
        if self.env.context.get('active_model') == 'mrp.production':
            production_id = self.env.context.get('active_id')
            origin = self.env['mrp.production'].browse(self.env.context.get('active_id')).name
        if self.env.context.get('active_model') == 'stock.picking':
            picking_id = self.env.context.get('active_id')
            origin = self.env['stock.picking'].browse(self.env.context.get('active_id')).name
        default_val = {
            'name': self.name,
            'origin': origin,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.scrap_qty,
            'location_id': self.location_id.id,
            'scrapped': True,
            'location_dest_id': self.scrap_location_id.id,
            'production_id': production_id,
            'picking_id': picking_id,
        }
        move = StockMove.create(default_val)
        new_move = move.action_scrap(self.scrap_qty, self.scrap_location_id.id)
        self.write({'move_id': move.id, 'state': 'done'})
        return True