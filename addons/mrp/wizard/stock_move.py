# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models
from openerp.tools import float_compare
import openerp.addons.decimal_precision as dp


class StockPickingScrap(models.TransientModel):
    _inherit = "stock.scrap"
    
    workorder_id = fields.Many2one('mrp.production.workcenter.line', 'Work Order')
    
    @api.model
    def default_get(self, fields):
        res = super(StockPickingScrap, self).default_get(fields)
        if self.env.context.get('active_model') == 'mrp.production.workcenter.line':
            res.update({'workorder_id': self.env.context.get("active_id"),})
        return res
    
    @api.onchange('picking_id', 'workorder_id', 'location_id', 'type')
    def onchange_type(self):
        if (self.env.context.get('active_model') == 'stock.picking') and self.picking_id:
            return super(StockPickingScrap, self).onchange_type()
        if (self.env.context.get('active_model') == 'mrp.production.workcenter.line') and self.workorder_id and (self.type == 'reserved'):
            quants = self.env['stock.quant']
            for move in self.workorder_id.move_line_ids:
                if move.state == 'done':
                    quants |= move.quant_ids
                else:
                    quants |= move.reserved_quant_ids
            scrap_lines = self._translate_quants_to_lines(quants)
            self.line_ids = scrap_lines


class StockMoveConsume(models.TransientModel):
    _name = "stock.move.consume"
    _description = "Consume Products"

    product_id = fields.Many2one('product.product', string='Product', required=True, index=True)
    product_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom = fields.Many2one('product.uom', string='Product Unit of Measure', required=True)
    location_id = fields.Many2one('stock.location', string='Location', required=True)
    restrict_lot_id = fields.Many2one('stock.production.lot', string='Lot')

    #TOFIX: product_uom should not have different category of default UOM of product. Qty should be convert into UOM of original move line before going in consume and scrap
    @api.model
    def default_get(self, fields):
        res = super(StockMoveConsume, self).default_get(fields)
        move = self.env['stock.move'].browse(self._context['active_id'])
        if 'product_id' in fields:
            res.update({'product_id': move.product_id.id})
        if 'product_uom_id' in fields:
            res.update({'product_uom': move.product_uom.id})
        if 'product_qty' in fields:
            res.update({'product_qty': move.product_uom_qty})
        if 'location_id' in fields:
            res.update({'location_id': move.location_id.id})
        return res

    @api.multi
    def do_move_consume(self):
        StockMove = self.env['stock.move']
        move_ids = self._context['active_ids']
        move = StockMove.browse(move_ids[0])
        production_id = move.raw_material_production_id.id
        production = self.env['mrp.production'].browse(production_id)
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        for data in self:
            qty = data['product_uom_id']._compute_qty(data.product_qty, data.product_id.uom_id.id)
            remaining_qty = move.product_qty - qty
            #check for product quantity is less than previously planned
            if float_compare(remaining_qty, 0, precision_digits=precision) >= 0:
                StockMove.action_consume(move_ids, qty, data.location_id.id, restrict_lot_id=data.restrict_lot_id.id)
            else:
                consumed_qty = min(move.product_qty, qty)
                StockMove.action_consume(move_ids, consumed_qty, data.location_id.id, restrict_lot_id=data.restrict_lot_id.id)
                #consumed more in wizard than previously planned
                extra_more_qty = qty - consumed_qty
                #create new line for a remaining qty of the product
                extra_move_id = production._make_consume_line_from_data(data.product_id, data.product_id.uom_id.id, extra_more_qty)
                extra_move_id.write({'restrict_lot_id': data.restrict_lot_id.id})
                extra_move_id.action_done()
        return {'type': 'ir.actions.act_window_close'}
