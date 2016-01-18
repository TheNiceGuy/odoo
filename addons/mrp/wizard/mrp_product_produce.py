# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models
import openerp.addons.decimal_precision as dp


# class MrpProductProduceLine(models.TransientModel):
#     _name="mrp.product.produce.line"
#     _description = "Product Produce Consume lines"
# 
#     product_id = fields.Many2one('product.product', string='Product')
#     product_qty = fields.Float(string='Quantity (in default UoM)', digits=dp.get_precision('Product Unit of Measure'))
#     lot_id = fields.Many2one('stock.production.lot', string='Lot')
#     produce_id = fields.Many2one('mrp.product.produce', string='Produce')


class MrpProductProduce(models.TransientModel):
    _name = "mrp.product.produce"
    _description = "Product Produce"

    @api.model
    def _get_product_qty(self):
        """ To obtain product quantity
        :param self: The object pointer.
        :param cr: A database cursor
        :param uid: ID of the user currently logged in
        :param context: A standard dictionary
        :return: Quantity
        """
        production = self.env['mrp.production'].browse(self._context['active_id'])
        done = 0.0
        produce_operations = production.produce_operation_ids.filtered(lambda x: x.production_state != 'done' and x.product_id.id == production.product_id.id)
        result = 0.0
        if produce_operations:
            result = produce_operations[0].qty_done or produce_operations[0].product_qty
        return result

    @api.model
    def _get_product_id(self):
        """ To obtain product id
        :return: id
        """
        production = False
        if self._context and self._context.get("active_id"):
            production = self.env['mrp.production'].browse(self._context['active_id'])
        return production and production.product_id.id or False

    @api.model
    def _get_production_uom(self):
        """ To obtain product id
        :return: id
        """
        production = False
        if self._context and self._context.get("active_id"):
            production = self.env['mrp.production'].browse(self._context['active_id'])
        return production and production.product_uom_id.id or False

    @api.model
    def _get_track(self):
        production = self._get_product_id()
        return production and self.env['product.product'].browse(production).tracking or False

    product_id = fields.Many2one('product.product', default=_get_product_id)
    product_qty = fields.Float(string='Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True, default=_get_product_qty)
    product_uom_id = fields.Many2one('product.uom', 'Unit of Measure', default=_get_production_uom)
    lot_id = fields.Many2one('stock.production.lot', string='Lot')  # Should only be visible when it is consume and produce mode
#    consume_lines = fields.One2many('mrp.product.produce.line', 'produce_id', string='Products Consumed')
    tracking = fields.Selection(related='product_id.tracking', selection=[('serial', 'By Unique Serial Number'), ('lot', 'By Lots'), ('none', 'No Tracking')], default=_get_track)

    @api.multi
    def do_produce(self):
        production_id = self._context.get('active_id', False)
        assert production_id, "Production Id should be specified in context as a Active ID."
        self.env['mrp.production'].browse(production_id).action_produce(self.product_qty, self)
        return {}
