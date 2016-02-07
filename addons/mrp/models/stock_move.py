# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError
from openerp.tools import float_compare
from datetime import datetime
import openerp.addons.decimal_precision as dp

class StockMoveLots(models.Model):
    _name = 'stock.move.lots'
    _description = "Quantities to Process by lots"

    move_id = fields.Many2one('stock.move', string='Inventory Move', required=True)
    workorder_id = fields.Many2one('mrp.production.work.order', string='Work Order')
    lot_id = fields.Many2one('stock.production.lot', string='Lot')
    quantity = fields.Float('Quantity', default=1.0)
    product_id = fields.Many2one('product.product', related="move_id.product_id")

class StockMove(models.Model):
    _inherit = 'stock.move'

    production_id = fields.Many2one('mrp.production', string='Production Order for finished products')
    raw_material_production_id = fields.Many2one('mrp.production', string='Production Order for raw materials')

    unbuild_id = fields.Many2one('mrp.unbuild', "Unbuild Order")

    operation_id = fields.Many2one('mrp.routing.workcenter', string="Operation To Consume")
    workorder_id = fields.Many2one('mrp.production.work.order', string="Work Order To Consume")

    has_tracking = fields.Selection(related='product_id.tracking', string='Product with Tracking')

    # Not sure we need this?
    consumed_for_id = fields.Many2one('stock.move', string='Consumed for', help='Technical field used to make the traceability of produced products', oldname='consumed_for')

    # Quantities to process, in normalized UoMs
    quantity_done = fields.Float('Quantity', digits_compute=dp.get_precision('Product Unit of Measure'), states={'done': [('readonly', True)]})
    quantity_lots = fields.One2many('stock.move.lots', 'move_id', string='Lots')
    bom_line_id = fields.Many2one('mrp.bom.line', string="BoM Line")

    @api.multi
    def move_validate(self):
        self.do_unreserve()
        quant_obj = self.env['stock.quant']
        for move in self:
            if move.has_tracking == 'none':
                quants = quant_obj.quants_get_preferred_domain(move.product_qty, move)
                quant_obj.quants_reserve(quants, move)
            else:
                for lot in move.quantity_lots:
                    quants = quant_obj.quants_get_preferred_domain(lot.quantity, move, lot_id=lot.lot_id.id)
                    quant_obj.quants_reserve(quants, move)
            if move.quantity_done < move.product_qty:
                new_move = move.split(move.product_qty- move.quantity_done)
            move.action_done()
        return True

    @api.multi
    def split_move_lot(self):
        self.ensure_one()
        view = self.env['ir.model.data'].xmlid_to_res_id('stock.view_stock_move_lots')
        serial = (self.has_tracking == 'serial')
        only_create = self.picking_type_id.use_create_lots and not self.picking_type_id.use_existing_lots
        ctx = {
            'serial': serial,
            'only_create': only_create,
            'create_lots': self.picking_type_id.use_create_lots,
            'state_done': self.picking_id.state == 'done',
        }
        result = {
             'name': _('Register Lots'),
             'type': 'ir.actions.act_window',
             'view_type': 'form',
             'view_mode': 'form',
             'res_model': 'stock.move',
             'views': [(view, 'form')],
             'view_id': view,
             'target': 'new',
             'res_id': self.id,
             'context': ctx,
        }
        return result


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    def _get_mo_count(self):
        MrpProduction = self.env['mrp.production']
        for picking in self:
            if picking.code == 'mrp_operation':
                picking.count_mo_waiting = MrpProduction.search_count([('availability', '=', 'waiting')])
                picking.count_mo_todo = MrpProduction.search_count([('state', '=', 'confirmed')])
                picking.count_mo_late = MrpProduction.search_count(['&', ('date_planned', '<', datetime.now().strftime('%Y-%m-%d')), ('state', 'in', ['draft', 'confirmed', 'ready'])])

    code = fields.Selection(selection_add=[('mrp_operation', 'Manufacturing Operation')])
    count_mo_todo = fields.Integer(compute='_get_mo_count')
    count_mo_waiting = fields.Integer(compute='_get_mo_count')
    count_mo_late = fields.Integer(compute='_get_mo_count')
