# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError
from openerp.tools import float_compare


class StockPackOperation(models.Model):
    _inherit = 'stock.pack.operation'
    
    @api.multi
    @api.depends('picking_id', 'production_raw_id', 'production_finished_id')
    def _compute_lots_visible(self):
        for pack in self:
            picking_type = False
            product_requires = (pack.product_id.tracking != 'none')
            state=''
            if pack.picking_id:
                picking_type = pack.picking_id.picking_type_id
                state = pack.picking_id.state
            if pack.production_raw_id:
                picking_type = pack.production_raw_id.picking_type_id
                state = pack.production_raw_id.state
            if pack.production_finished_id:
                picking_type = pack.production_finished_id.picking_type_id
                state = pack.production_finished_id.state
            if picking_type:
                pack.lots_visible = (picking_type.use_existing_lots or picking_type.use_create_lots) and product_requires
                pack.state = state
            if pack.pack_lot_ids:
                pack.lots_visible=True
    
    picking_id = fields.Many2one('stock.picking', 'Picking', required=False)
    production_raw_id = fields.Many2one('mrp.production', 'Manufacturing Order')
    production_finished_id = fields.Many2one('mrp.production', 'Manufacturing Order')
    workorder_id = fields.Many2one('mrp.production.workcenter.line', 'Work Order')
    production_state = fields.Selection([('confirmed', 'Confirmed'), ('done', 'Done')], default='confirmed', string='Production State', copy=False)
    lots_visible = fields.Boolean('Lots visible', compute='_compute_lots_visible')
    state = fields.Char('State', compute='_compute_lots_visible')
    qty_reserved = fields.Float('Qty Reserved', readonly=True)

    def _prepare_values_extra_move(self, product, remaining_qty):
        """
        Creates an extra move when there is no corresponding original move to be copied
        """
        self.ensure_one()
        uom_obj = self.env["product.uom"]
        uom_id = product.uom_id.id
        qty = remaining_qty
        if self.product_id and self.product_uom_id and self.product_uom_id.id != product.uom_id.id:
            if self.product_uom_id.factor > product.uom_id.factor:  # If the pack operation's is a smaller unit
                uom_id = self.product_uom_id.id
                #HALF-UP rounding as only rounding errors will be because of propagation of error from default UoM
                qty = uom_obj._compute_qty_obj(product.uom_id, remaining_qty, self.product_uom_id, rounding_method='HALF-UP')
        ref = product.default_code
        name = '[' + ref + ']' + ' ' + product.name if ref else product.name
        res = {
            'product_id': product.id,
            'product_uom': uom_id,
            'product_uom_qty': qty,
            'name': _('Extra Move: ') + name,
            'state': 'draft',
            'restrict_partner_id': self.owner_id,
            }
        return res

    def _create_extra_moves(self, location_id, location_dest_id, group_id):
        '''This function creates move lines on a picking, at the time of do_transfer, based on
        unexpected product transfers (or exceeding quantities) found in the pack operations.
        '''
        move_obj = self.env['stock.move']
        operation_obj = self.env['stock.pack.operation']
        moves = []
        for op in self:
            for product, remaining_qty in operation_obj._get_remaining_prod_quantities(op).items():
                if float_compare(remaining_qty, 0, precision_rounding=product.uom_id.rounding) > 0:
                    vals = op._prepare_values_extra_move(product, remaining_qty)
                    vals['location_id'] = location_id.id
                    vals['location_dest_id'] = location_dest_id.id
                    vals['group_id'] = group_id.id
                    moves.append(move_obj.create(vals).id)
        if moves:
            move_list = move_obj.browse(moves)
            move_list.action_confirm()
        return moves


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    manufacture_to_resupply = fields.Boolean(string='Manufacture in this Warehouse', default=True, help="When products are manufactured, they can be manufactured in this warehouse.")
    manufacture_pull_id = fields.Many2one('procurement.rule', string='Manufacture Rule')
    manu_type_id = fields.Many2one('stock.picking.type', domain=[('code', '=', 'mrp_operation')], string='Manufacturing Picking Type')

    def _get_manufacture_pull_rule(self):
        try:
            manufacture_route = self.env.ref('mrp.route_warehouse0_manufacture')
        except:
            manufacture_route = self.env['stock.location.route'].search([('name', 'like', _('Manufacture'))])
            manufacture_route = manufacture_route and manufacture_route[0] or False
        if not manufacture_route:
            raise UserError(_('Can\'t find any generic Manufacture route.'))

        return {
            'name': self._format_routename(self, _(' Manufacture')),
            'location_id': self.lot_stock_id.id,
            'route_id': manufacture_route.id,
            'action': 'manufacture',
            'picking_type_id': self.int_type_id.id,
            'propagate': False,
            'warehouse_id': self.id,
        }

    @api.multi
    def create_routes(self, warehouse):
        res = super(StockWarehouse, self).create_routes(warehouse)
        if warehouse.manufacture_to_resupply:
            manufacture_pull_vals = warehouse._get_manufacture_pull_rule()
            self.manufacture_pull_id = self.env['procurement.rule'].create(manufacture_pull_vals)
        return res
    
    def _create_manufacturing_picking_type(self):
        picking_type_obj = self.env['stock.picking.type']
        seq_obj = self.env['ir.sequence']
        for warehouse in self:
            #man_seq_id = seq_obj.sudo().create('name': warehouse.name + _(' Sequence Manufacturing'), 'prefix': warehouse.code + '/MANU/', 'padding')
            wh_stock_loc = warehouse.lot_stock_id
            seq = seq_obj.search([('code', '=', 'mrp.production')], limit=1)
            other_pick_type = picking_type_obj.search([('warehouse_id', '=', warehouse.id)], order = 'sequence desc', limit=1)
            color = other_pick_type and other_pick_type.color or 0
            max_sequence = other_pick_type and other_pick_type.sequence or 0
            manu_type = picking_type_obj.create({
                'name': _('Manufacturing'),
                'warehouse_id': warehouse.id,
                'code': 'mrp_operation',
                'use_create_lots': True,
                'use_existing_lots': False,
                'sequence_id': seq.id,
                'default_location_src_id': wh_stock_loc.id,
                'default_location_dest_id': wh_stock_loc.id,
                'sequence': max_sequence + 1,
                'color': color})
            warehouse.write({'manu_type_id': manu_type.id})

    @api.v7
    def create_sequences_and_picking_types(self, cr, uid, warehouse, context=None):
        res = super(StockWarehouse, self).create_sequences_and_picking_types(cr, uid, warehouse, context=context)
        warehouse._create_manufacturing_picking_type()
        return res

    @api.multi
    def write(self, vals):
        if 'manufacture_to_resupply' in vals:
            if vals.get("manufacture_to_resupply"):
                for warehouse in self:
                    if not warehouse.manufacture_pull_id:
                        manufacture_pull_vals = warehouse._get_manufacture_pull_rule()
                        warehouse.manufacture_pull_id = self.env['procurement.rule'].create(manufacture_pull_vals)
                    if not warehouse.manu_type_id:
                        warehouse._create_manufacturing_picking_type()
                    warehouse.manu_type_id.active = True
            else:
                for warehouse in self:
                    if warehouse.manu_type_id:
                        warehouse.manu_type_id.active = False
                    if warehouse.manufacture_pull_id:
                        warehouse.manufacture_pull_id.unlink()
        return super(StockWarehouse, self).write(vals)

    @api.multi
    def get_all_routes_for_wh(self):
        all_routes = super(StockWarehouse, self).get_all_routes_for_wh()
        if self.manufacture_to_resupply and self.manufacture_pull_id and self.manufacture_pull_id.route_id:
            all_routes += [self.manufacture_pull_id.route_id.id]
        return all_routes

    @api.multi
    def _handle_renaming(self, name, code):
        res = super(StockWarehouse, self)._handle_renaming(name, code)
        # change the manufacture procurement rule name
        if self.manufacture_pull_id:
            self.manufacture_pull_id.write({'name': self.manufacture_pull_id.name.replace(self.name, name, 1)})
        return res

    def _get_all_products_to_resupply(self):
        ProductProduct = self.env['product.product']
        res = super(StockWarehouse, self)._get_all_products_to_resupply()
        if self.manufacture_pull_id and self.manufacture_pull_id.route_id:
            for product_id in res:
                for route in ProductProduct.browse(product_id).route_ids:
                    if route.id == self.manufacture_pull_id.route_id.id:
                        res.remove(product_id)
                        break
        return res