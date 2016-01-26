# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models
import openerp.addons.decimal_precision as dp


class MrpProductProduceWo(models.TransientModel):
    _name = "mrp.product.produce.wo"
    _description = "Product Produce Work Order"
    
    @api.model
    def _get_product_qty(self):
        """ To obtain product quantity
        :param self: The object pointer.
        :param cr: A database cursor
        :param uid: ID of the user currently logged in
        :param context: A standard dictionary
        :return: Quantity
        """
        workorder = self.env['mrp.production.workcenter.line'].browse(self._context.get('active_id'))
        
        return workorder.qty - workorder.qty_produced

    @api.model
    def _get_product_id(self):
        """ To obtain product id
        :return: id
        """
        workorder = self.env['mrp.production.workcenter.line'].browse(self._context.get('active_id'))
        return workorder.production_id.product_id.id

    @api.model
    def _get_uom_id(self):
        """ To obtain product id
        :return: id
        """
        workorder = self.env['mrp.production.workcenter.line'].browse(self._context.get('active_id'))
        return workorder.production_id.product_uom_id.id

    product_id = fields.Many2one('product.product', readonly=True, string='Product', default=_get_product_id)
    product_qty = fields.Float(string='Quantity Manufactured', digits=dp.get_precision('Product Unit of Measure'), required=True, default=_get_product_qty)
    product_uom_id = fields.Many2one('product.uom', readonly=True, string='Unit of Measure', default=_get_uom_id)
    operation_ids = fields.Many2many('stock.pack.operation', 'mrp_product_produce_wo_stock_operation_rel')
    #lot_id = fields.Many2one('stock.production.lot', string='Lot')  # Should only be visible when it is consume and produce mode
    #consume_lines = fields.One2many('mrp.product.produce.line', 'produce_id', string='Products Consumed')
    #tracking = fields.Selection(related='product_id.tracking', selection=[('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')], default=_get_track)
    _sql_constraints = [('product_qty_greater', 'check(product_qty > 0)', 'Quantity should be bigger than 0')] 
    

    @api.multi
    def do_produce(self):
        self.ensure_one()
        workorder = self.env['mrp.production.workcenter.line'].browse(self._context.get('active_id'))
        prod_qty = {}
        for move in workorder.move_line_ids:
            # Raise the qty that would have been consumed
            # Check qty for each product
            prod_qty.setdefault(move.product_id.id, 0.0)
            prod_qty[move.product_id.id] += move.product_qty
        
        # Now go through all operations and add them here:
        
        
        workorder._add_qty(self.product_qty)
        # Calculate
        # Add quantity to workorder
        return {}
