# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError

class StockPickingScrap(models.TransientModel):
    _name = 'stock.scrap'

    picking_id = fields.Many2one('stock.picking', 'Picking', default=(lambda x: (x.env.context.get('active_id'))), readonly=True) #x.env.context.get('active_model') == 'mrp.production.workcenter.line') and 
    location_id = fields.Many2one('stock.location', 'Source Location')
    scrap_location_id = fields.Many2one('stock.location', domain="[('scrap_location', '=', True)]", 
                                        default=(lambda x: x.env['stock.location'].search([('scrap_location', '=', True)], limit=1)))
    type = fields.Selection([('reserved', 'Reserved or Done'), ('demand', 'Useful for Picking'), ('location', 'Everything in Source Location')], default='reserved')
    line_ids = fields.One2many('stock.scrap.line', 'scrap_id')

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
            scrap_lines += [(0, 0, {'location_id': key[0],
                                    'product_id': key[1],
                                    'package_id': key[2],
                                    'lot_id': key[3],
                                    'owner_id': key[4],
                                    'product_qty': grouped_quants[key]})]
        return scrap_lines

    @api.onchange('picking_id', 'location_id', 'type')
    def onchange_type(self):
        if self.picking_id and self.type == 'reserved':
            quants = self.env['stock.quant']
            for move in self.picking_id.move_lines:
                if self.picking_id.state == 'done':
                    quants |= move.quant_ids
                else:
                    quants |= move.reserved_quant_ids
            scrap_lines = self._translate_quants_to_lines(quants)
            self.line_ids = scrap_lines

    @api.multi
    def do_scrap(self):
        self.ensure_one()
        # Create stock move in picking to put these quants to scrap
        return True


class StockPickingScrapLine(models.TransientModel):
    _name = 'stock.scrap.line'

    scrap_id = fields.Many2one('stock.scrap', 'Wizard', readonly=True)
    location_id = fields.Many2one('stock.location', 'Location', readonly=True)
    product_id = fields.Many2one('product.product', 'Product', readonly=True)
    package_id = fields.Many2one('stock.quant.package', 'Package', readonly=True)
    lot_id = fields.Many2one('stock.production.lot', 'Lot', readonly=True)
    owner_id = fields.Many2one('res.partner', 'Owner', readonly=True)
    product_qty = fields.Float('Qty In Stock', readonly=True)
    scrap_qty = fields.Float('Qty To Scrap')
    