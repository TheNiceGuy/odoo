# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from openerp import api, fields, models, _
from openerp.exceptions import UserError
from openerp.tools import float_compare
from datetime import datetime


class StockMove(models.Model):
    _inherit = 'stock.move'

    production_id = fields.Many2one('mrp.production', string='Production Order for Produced Products', index=True, copy=False)
    raw_material_production_id = fields.Many2one('mrp.production', string='Production Order for Raw Materials', index=True)
    unbuild_raw_material_id = fields.Many2one('mrp.unbuild', "Raw Materials for Unbuild Order")
    consumed_for_id = fields.Many2one('stock.move', string='Consumed for', help='Technical field used to make the traceability of produced products', oldname='consumed_for')
    operation_id = fields.Many2one('mrp.routing.workcenter', string="Operation To Consume")
    workorder_id = fields.Many2one('mrp.production.workcenter.line', string="Work Order To Consume")
    unbuild_id = fields.Many2one('mrp.unbuild', "Unbuild Order")

    @api.model
    def check_tracking(self, move, lot_id):
        super(StockMove, self).check_tracking(move, lot_id)
        if move.raw_material_production_id and move.product_id.tracking != 'none' and move.location_dest_id.usage == 'production' and move.raw_material_production_id.product_id.tracking != 'none' and not move.consumed_for_id:
            raise UserError(_("Because the product %s requires it, you must assign a serial number to your raw material %s to proceed further in your production. Please use the 'Produce' button to do so.") % (move.raw_material_production_id.product_id.name, move.product_id.name))

    def _action_explode(self):
        """ Explodes pickings.
        :return: True
        """
        ProductProduct = self.env['product.product']
        ProcurementOrder = self.env['procurement.order']
        to_explode_again_ids = self - self
        properties = self.env.context.get('properties') or None
        bom_point = self.env['mrp.bom'].sudo()._bom_find(product=self.product_id, properties=properties)
        if bom_point and bom_point.bom_type == 'phantom':
            processed_ids = self - self
            factor = self.product_uom.sudo()._compute_qty(self.product_uom_qty, bom_point.product_uom_id.id) / bom_point.product_qty
            res = bom_point.sudo().explode(self.product_id, factor, properties)

            for line in res[0]:
                product = ProductProduct.browse(line['product_id'])
                if product.type in ['product', 'consu']:
                    valdef = {
                        'picking_id': self.picking_id.id if self.picking_id else False,
                        'product_id': line['product_id'],
                        'product_uom': line['product_uom_id'],
                        'product_uom_qty': line['product_uom_qty'],
                        'state': 'draft',  # will be confirmed below
                        'name': line['name'],
                        'procurement_id': self.procurement_id.id,
                        'split_from': self.id,  # Needed in order to keep sale connection, but will be removed by unlink
                    }
                    mid = self.copy(default=valdef)
                    to_explode_again_ids = to_explode_again_ids | mid
                else:
                    if product.type in ('consu', 'product'):
                        valdef = {
                            'name': self.rule_id and self.rule_id.name or "/",
                            'origin': self.origin,
                            'company_id': self.company_id and self.company_id.id or False,
                            'date_planned': self.date,
                            'product_id': line['product_id'],
                            'product_qty': line['product_uom_qty'],
                            'product_uom_id': line['product_uom_id'],
                            'group_id': self.group_id.id,
                            'priority': self.priority,
                            'partner_dest_id': self.partner_id.id,
                        }
                        if self.procurement_id:
                            procurement = self.procurement_id.copy(default=valdef)
                        else:
                            procurement = ProcurementOrder.create(valdef)
                        procurement.run()  # could be omitted

            # check if new moves needs to be exploded
            if to_explode_again_ids:
                for new_move in to_explode_again_ids:
                    processed_ids = processed_ids | new_move._action_explode()

            if not self.split_from and self.procurement_id:
                # Check if procurements have been made to wait for
                moves = self.procurement_id.move_ids
                if len(moves) == 1:
                    self.procurement_id.write({'state': 'done'})

            if processed_ids and self.state == 'assigned':
                # Set the state of resulting moves according to 'assigned' as the original move is assigned
                processed_ids.write({'state': 'assigned'})

            # delete the move with original product which is not relevant anymore
            self.sudo().unlink()
            # return list of newly created move
            return processed_ids

        return self

    @api.multi
    def action_confirm(self):
        moves = self - self
        for move in self:
            # in order to explode a move, we must have a picking_type_id on that move because otherwise the move
            # won't be assigned to a picking and it would be weird to explode a move into several if they aren't
            # all grouped in the same picking.
            if move.picking_type_id:
                moves = moves | move._action_explode()
            else:
                moves = moves | move

        # we go further with the list of ids potentially changed by action_explode
        return super(StockMove, moves).action_confirm()

    def action_consume(self, product_qty, location_id=False, restrict_lot_id=False, restrict_partner_id=False, consumed_for_id=False):
        """ Consumed product with specific quantity from specific source location.
        :param product_qty: Consumed/produced product quantity (= in quantity of UoM of product)
        :param location_id: Source location
        :param restrict_lot_id: optional parameter that allows to restrict the choice of quants on this specific lot
        :param restrict_partner_id: optional parameter that allows to restrict the choice of quants to this specific partner
        :param consumed_for_id: optional parameter given to this function to make the link between raw material consumed and produced product, for a better traceability
        :return: New lines created if not everything was consumed for this line
        """
        res = self - self  # creates empty recordset

        if product_qty <= 0:
            raise UserError(_('Please provide proper quantity.'))
        # because of the action_confirm that can create extra moves in case of phantom bom, we need to make 2 loops
        ids2 = []
        for move in self:
            if move.state == 'draft':
                ids2.extend(move.action_confirm())
            else:
                ids2.append(move.id)

        prod_orders = self.env['mrp.production']
        for move in self.browse(ids2):
            prod_orders = prod_orders | move.raw_material_production_id or move.production_id
            move_qty = move.product_qty
            if move_qty <= 0:
                raise UserError(_('Cannot consume a move with negative or zero quantity.'))
            quantity_rest = move_qty - product_qty
            # Compare with numbers of move uom as we want to avoid a split with 0 qty
            quantity_rest_uom = move.product_uom_qty - self.env['product.uom']._compute_qty_obj(move.product_id.uom_id, product_qty, move.product_uom)
            if float_compare(quantity_rest_uom, 0, precision_rounding=move.product_uom.rounding) != 0:
                new_mov = self.browse(self.split(move, quantity_rest))
                if move.production_id:
                    new_mov.write({'production_id': move.production_id.id})
                res = res | new_mov
            vals = {'restrict_lot_id': restrict_lot_id,
                    'restrict_partner_id': restrict_partner_id,
                    'consumed_for_id': consumed_for_id}
            if location_id:
                vals.update({'location_id': location_id})
            move.write(vals)
        # Original moves will be the quantities consumed, so they need to be done
        self.browse(ids2).action_done()
        if res:
            res.action_assign()
        if prod_orders:
            prod_orders.signal_workflow('button_produce')
        return res

    @api.multi
    def action_scrap(self, product_qty, location_id, restrict_lot_id=False, restrict_partner_id=False):
        """ Move the scrap/damaged product into scrap location
        :param product_qty: Scraped product quantity
        :param location_id: Scrap location
        :return: Scraped lines
        """
        MrpProduction = self.env['mrp.production']
        Stock_Move = self.env['stock.move']
        res = self - self
        for move in self:
            new_move_ids = super(StockMove, move).action_scrap(product_qty, location_id, restrict_lot_id=restrict_lot_id, restrict_partner_id=restrict_partner_id)
            # If we are not scrapping our whole move, tracking and lot references must not be removed
            new_moves = Stock_Move.browse(new_move_ids)
            production_ids = MrpProduction.search([('move_line_ids', 'in', [move.id])])
            for prod_id in production_ids:
                prod_id.signal_workflow('button_produce')
            if move.production_id.id:
                new_moves.write({'production_id': move.production_id.id})
            res = res | new_moves
        return res
    
    
    
    
    
    def _prepare_pack_ops(self, quants, forced_qties, entire_packages=False, owner_id=False, context=None):
        """ returns a list of dict, ready to be used in create() of stock.pack.operation.

        :param picking: browse record (stock.picking)
        :param quants: browse record list (stock.quant). List of quants associated to the picking
        :param forced_qties: dictionary showing for each product (keys) its corresponding quantity (value) that is not covered by the quants associated to the picking
        """
        def _picking_putaway_apply(product):
            location = False
            # Search putaway strategy
            if product_putaway_strats.get(product.id):
                location = product_putaway_strats[product.id]
            else:
                loc = self.env['stock.location'].browse(location_dest_id)
                location = self.env['stock.location'].get_putaway_strategy(loc, product, context=context)
                product_putaway_strats[product.id] = location
            return location or location_dest_id

        # If we encounter an UoM that is smaller than the default UoM or the one already chosen, use the new one instead.
        product_uom = {} # Determines UoM used in pack operations
        location_dest_id = None
        location_id = None
        for move in self:
            # UoMs in manufacturing order should maybe be the same instead of searching the lowest total
            if not product_uom.get(move.product_id.id):
                product_uom[move.product_id.id] = move.product_id.uom_id
            if move.product_uom.id != move.product_id.uom_id.id and move.product_uom.factor > product_uom[move.product_id.id].factor:
                product_uom[move.product_id.id] = move.product_uom
            if not move.scrapped:
                if location_dest_id and move.location_dest_id.id != location_dest_id:
                    raise UserError(_('The destination location must be the same for all the moves of the picking.')) #TODO: manufacturing order
                location_dest_id = move.location_dest_id.id
                if location_id and move.location_id.id != location_id:
                    raise UserError(_('The source location must be the same for all the moves of the picking.'))
                location_id = move.location_id.id

        pack_obj = self.pool.get("stock.quant.package")
        quant_obj = self.pool.get("stock.quant")
        vals = []
        qtys_grouped = {}
        lots_grouped = {}
        #for each quant of the picking, find the suggested location
        quants_suggested_locations = {}
        product_putaway_strats = {}
        for quant in quants:
            if quant.qty <= 0:
                continue
            suggested_location_id = _picking_putaway_apply(quant.product_id)
            quants_suggested_locations[quant] = suggested_location_id

        #find the packages we can movei as a whole
        if entire_packages:
            top_lvl_packages = self._get_top_level_packages(quants_suggested_locations)
            # and then create pack operations for the top-level packages found
            for pack in top_lvl_packages:
                pack_quant_ids = pack.get_content()
                pack_quants = quant_obj.browse(pack_quant_ids)
                vals.append({
                        'package_id': pack.id,
                        'product_qty': 1.0,
                        'location_id': pack.location_id.id,
                        'location_dest_id': quants_suggested_locations[pack_quants[0]],
                        'owner_id': pack.owner_id.id,
                    })
                #remove the quants inside the package so that they are excluded from the rest of the computation
                for quant in pack_quants:
                    del quants_suggested_locations[quant]
        # Go through all remaining reserved quants and group by product, package, owner, source location and dest location
        # Lots will go into pack operation lot object
        for quant, dest_location_id in quants_suggested_locations.items():
            key = (quant.product_id.id, quant.package_id.id, quant.owner_id.id, quant.location_id.id, dest_location_id)
            if qtys_grouped.get(key):
                qtys_grouped[key] += quant.qty
            else:
                qtys_grouped[key] = quant.qty
            if quant.product_id.tracking != 'none' and quant.lot_id:
                lots_grouped.setdefault(key, {}).setdefault(quant.lot_id.id, 0.0)
                lots_grouped[key][quant.lot_id.id] += quant.qty

        # Do the same for the forced quantities (in cases of force_assign or incomming shipment for example)
        for product, qty in forced_qties.items():
            if qty <= 0:
                continue
            suggested_location_id = _picking_putaway_apply(product)
            key = (product.id, False, owner_id, location_id, suggested_location_id)
            if qtys_grouped.get(key):
                qtys_grouped[key] += qty
            else:
                qtys_grouped[key] = qty

        # Create the necessary operations for the grouped quants and remaining qtys
        uom_obj = self.env['product.uom']
        prevals = {}
        for key, qty in qtys_grouped.items():
            product = self.env["product.product"].browse(key[0])
            uom_id = product.uom_id.id
            qty_uom = qty
            if product_uom.get(key[0]):
                uom_id = product_uom[key[0]].id
                qty_uom = product.uom_id._compute_qty(qty, uom_id)
            pack_lot_ids = []
            if lots_grouped.get(key):
                for lot in lots_grouped[key].keys():
                    pack_lot_ids += [(0, 0, {'lot_id': lot, 'qty': 0.0, 'qty_todo': lots_grouped[key][lot]})]
            val_dict = {
                'product_qty': qty_uom,
                'product_id': key[0],
                'package_id': key[1],
                'owner_id': key[2],
                'location_id': key[3],
                'location_dest_id': key[4],
                'product_uom_id': uom_id,
                'pack_lot_ids': pack_lot_ids,
            }
            if key[0] in prevals:
                prevals[key[0]].append(val_dict)
            else:
                prevals[key[0]] = [val_dict]
                
        #prevals var holds the operations in order to create them in the same order than the picking stock moves if possible
        processed_products = set()
        for move in self:
            if move.product_id.id not in processed_products:
                vals += prevals.get(move.product_id.id, [])
                processed_products.add(move.product_id.id)
        return vals

    def recompute_remaining_qty(self, pack_operation_ids, done_qtys=False):
        def _create_link_for_index(operation_id, index, product_id, qty_to_assign, quant_id=False):
            move_dict = prod2move_ids[product_id][index]
            qty_on_link = min(move_dict['remaining_qty'], qty_to_assign)
            self.env['stock.move.operation.link'].create({'move_id': move_dict['move'].id, 'operation_id': operation_id, 'qty': qty_on_link, 'reserved_quant_id': quant_id})
            if move_dict['remaining_qty'] == qty_on_link:
                prod2move_ids[product_id].pop(index)
            else:
                move_dict['remaining_qty'] -= qty_on_link
            return qty_on_link

        def _create_link_for_quant(operation_id, quant, qty):
            """create a link for given operation and reserved move of given quant, for the max quantity possible, and returns this quantity"""
            if not quant.reservation_id.id:
                return _create_link_for_product(operation_id, quant.product_id.id, qty)
            qty_on_link = 0
            for i in range(0, len(prod2move_ids[quant.product_id.id])):
                if prod2move_ids[quant.product_id.id][i]['move'].id != quant.reservation_id.id:
                    continue
                qty_on_link = _create_link_for_index(operation_id, i, quant.product_id.id, qty, quant_id=quant.id)
                break
            return qty_on_link

        def _create_link_for_product(operation_id, product_id, qty):
            '''method that creates the link between a given operation and move(s) of given product, for the given quantity.
            Returns True if it was possible to create links for the requested quantity (False if there was not enough quantity on stock moves)'''
            qty_to_assign = qty
            prod_obj = self.env["product.product"]
            product = prod_obj.browse(product_id)
            rounding = product.uom_id.rounding
            qtyassign_cmp = float_compare(qty_to_assign, 0.0, precision_rounding=rounding)
            if prod2move_ids.get(product_id):
                while prod2move_ids[product_id] and qtyassign_cmp > 0:
                    qty_on_link = _create_link_for_index(operation_id, 0, product_id, qty_to_assign, quant_id=False)
                    qty_to_assign -= qty_on_link
                    qtyassign_cmp = float_compare(qty_to_assign, 0.0, precision_rounding=rounding)
            return qtyassign_cmp == 0

        uom_obj = self.env['product.uom']
        package_obj = self.env['stock.quant.package']
        quant_obj = self.env['stock.quant']
        link_obj = self.env['stock.move.operation.link']
        quants_in_package_done = set()
        prod2move_ids = {}
        still_to_do = []
        #make a dictionary giving for each product, the moves and related quantity that can be used in operation links
        for move in [x for x in self if x.state not in ('done', 'cancel')]:
            if not prod2move_ids.get(move.product_id.id):
                prod2move_ids[move.product_id.id] = [{'move': move, 'remaining_qty': move.product_qty}]
            else:
                prod2move_ids[move.product_id.id].append({'move': move, 'remaining_qty': move.product_qty})

        need_rereserve = False
        #sort the operations in order to give higher priority to those with a package, then a serial number
        operations = pack_operation_ids
        operations = sorted(operations, key=lambda x: ((x.package_id and not x.product_id) and -4 or 0) + (x.package_id and -2 or 0) + (x.pack_lot_ids and -1 or 0))
        #delete existing operations to start again from scratch
        links = link_obj.search([('operation_id', 'in', [x.id for x in operations])])
        if links:
            links.unlink()
        #1) first, try to create links when quants can be identified without any doubt
        for ops in operations:
            lot_qty = {}
            for packlot in ops.pack_lot_ids:
                lot_qty[packlot.lot_id.id] = uom_obj._compute_qty_obj(ops.product_uom_id, packlot.qty, ops.product_id.uom_id)
            #for each operation, create the links with the stock move by seeking on the matching reserved quants,
            #and deffer the operation if there is some ambiguity on the move to select
            if ops.package_id and not ops.product_id and (not done_qtys or ops.qty_done):
                #entire package
                quant_ids = ops.package_id.get_content()
                for quant in quant_obj.browse(quant_ids):
                    remaining_qty_on_quant = quant.qty
                    if quant.reservation_id:
                        #avoid quants being counted twice
                        quants_in_package_done.add(quant.id)
                        qty_on_link = _create_link_for_quant(ops.id, quant, quant.qty)
                        remaining_qty_on_quant -= qty_on_link
                    if remaining_qty_on_quant:
                        still_to_do.append((ops, quant.product_id.id, remaining_qty_on_quant))
                        need_rereserve = True
            elif ops.product_id.id:
                #Check moves with same product
                product_qty = ops.qty_done if done_qtys else ops.product_qty
                qty_to_assign = uom_obj._compute_qty_obj(ops.product_uom_id, product_qty, ops.product_id.uom_id)
                for move_dict in prod2move_ids.get(ops.product_id.id, []):
                    move = move_dict['move']
                    for quant in move.reserved_quant_ids:
                        if not qty_to_assign > 0:
                            break
                        if quant.id in quants_in_package_done:
                            continue

                        #check if the quant is matching the operation details
                        if ops.package_id:
                            flag = quant.package_id and bool(package_obj.search([('id', 'child_of', [ops.package_id.id])])) or False
                        else:
                            flag = not quant.package_id.id
                        flag = flag and (ops.owner_id.id == quant.owner_id.id)
                        if flag:
                            if not lot_qty:
                                max_qty_on_link = min(quant.qty, qty_to_assign)
                                qty_on_link = _create_link_for_quant(ops.id, quant, max_qty_on_link)
                                qty_to_assign -= qty_on_link
                            else:
                                if lot_qty.get(quant.lot_id.id):  # if there is still some qty left
                                    max_qty_on_link = min(quant.qty, qty_to_assign, lot_qty[quant.lot_id.id])
                                    qty_on_link = _create_link_for_quant(ops.id, quant, max_qty_on_link)
                                    qty_to_assign -= qty_on_link
                                    lot_qty[quant.lot_id.id] -= qty_on_link

                qty_assign_cmp = float_compare(qty_to_assign, 0, precision_rounding=ops.product_id.uom_id.rounding)
                if qty_assign_cmp > 0:
                    #qty reserved is less than qty put in operations. We need to create a link but it's deferred after we processed
                    #all the quants (because they leave no choice on their related move and needs to be processed with higher priority)
                    still_to_do += [(ops, ops.product_id.id, qty_to_assign)]
                    need_rereserve = True

        #2) then, process the remaining part
        all_op_processed = True
        for ops, product_id, remaining_qty in still_to_do:
            all_op_processed = _create_link_for_product(ops.id, product_id, remaining_qty) and all_op_processed
        return (need_rereserve, all_op_processed)



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
