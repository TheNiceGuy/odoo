# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import datetime
from dateutil.relativedelta import relativedelta
import math

from odoo import api, fields, models, _
from odoo.addons import decimal_precision as dp
from odoo.tools import html2plaintext
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    """ Manufacturing Orders """
    _name = 'mrp.production'
    _description = 'Manufacturing Order'
    _date_name = 'date_planned'
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'date_planned asc,id'

    @api.model
    def _get_default_picking_type(self):
        return self.env['stock.picking.type'].search([
            ('code', '=', 'mrp_operation'),
            ('warehouse_id.company_id', 'in', [self.env.context.get('company_id', self.env.user.company_id.id), False])],
            limit=1).id

    @api.model
    def _get_default_location_src_id(self):
        location_id = False
        if self._context.get('default_picking_type_id'):
            location_id = self.env['stock.picking.type'].browse(self.env.context['default_picking_type_id']).default_location_src_id.id
        if not location_id:
            location_id = self.env.ref('stock.stock_location_stock', raise_if_not_found=False).id
        return location_id

    @api.model
    def _get_default_location_dest_id(self):
        location_id = False
        if self._context.get('default_picking_type_id'):
            location_id = self.env['stock.picking.type'].browse(self.env.context['default_picking_type_id']).default_location_dest_id.id
        if not location_id:
            location_id = self.env.ref('stock.stock_location_stock', raise_if_not_found=False).id
        return location_id

    name = fields.Char(
        'Reference',
        default=lambda self: self.env['ir.sequence'].next_by_code('mrp.production') or '/',
        copy=False, readonly=True)
    origin = fields.Char(
        'Source', copy=False,
        help="Reference of the document that generated this production order request.")

    product_id = fields.Many2one(
        'product.product', 'Product',
        domain=[('type', 'in', ['product', 'consu'])],
        readonly=True, required=True,
        states={'confirmed': [('readonly', False)]})
    product_tmpl_id = fields.Many2one(
        'product.template', 'Product Template',
        related='product_id.product_tmpl_id')
    product_qty = fields.Float(
        'Quantity to Produce',
        default=1.0, digits_compute=dp.get_precision('Product Unit of Measure'),
        readonly=True, required=True,
        states={'confirmed': [('readonly', False)]})
    product_uom_id = fields.Many2one(
        'product.uom', 'Product Unit of Measure',
        oldname='product_uom', readonly=True, required=True,
        states={'confirmed': [('readonly', False)]})

    picking_type_id = fields.Many2one(
        'stock.picking.type', 'Picking Type',
        default=_get_default_picking_type, required=True)
    location_src_id = fields.Many2one(
        'stock.location', 'Raw Materials Location',
        default=_get_default_location_src_id,
        readonly=True,  required=True,  # TDE FIXME: not required anymore ?
        states={'confirmed': [('readonly', False)]},
        help="Location where the system will look for components.")
    location_dest_id = fields.Many2one(
        'stock.location', 'Finished Products Location',
        default=_get_default_location_dest_id,
        readonly=True,  required=True,  # TDE FIXME: not required anymore ?
        states={'confirmed': [('readonly', False)]},
        help="Location where the system will stock the finished products.")
    date_planned = fields.Datetime(
        'Expected Date',
        copy=False, default=fields.Datetime.now,
        index=True, required=True, readonly=True,
        states={'confirmed': [('readonly', False)]})
    date_start = fields.Datetime('Start Date', copy=False, index=True, readonly=True)
    date_finished = fields.Datetime('End Date', copy=False, index=True, readonly=True)

    bom_id = fields.Many2one(
        'mrp.bom', 'Bill of Material',
        readonly=True, states={'confirmed': [('readonly', False)]},
        help="Bill of Materials allow you to define the list of required raw materials to make a finished product.")
    
    # FP Note: what's the goal of this field? -> It is like the destination move of the production move
    move_prod_id = fields.Many2one(
        'stock.move', 'Product Move',
        copy=False, readonly=True)
    move_raw_ids = fields.One2many(
        'stock.move', 'raw_material_production_id', 'Raw Materials',
        oldname='move_lines',
        copy=False, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    move_finished_ids = fields.One2many(
        'stock.move', 'production_id', 'Finished Products',
        copy=False, states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    state = fields.Selection([
        ('confirmed', 'Confirmed'),
        ('planned', 'Planned'),
        ('progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')], string='State',
        copy=False, default='confirmed')  # TDE FIXME: no more track visibility ?
    availability = fields.Selection([
        ('assigned', 'Available'),
        ('partially_available', 'Partially Available'),
        ('none', 'None'),
        ('waiting', 'Waiting')], string='Availability',
        compute='_compute_availability', store=True,
        default="none")  # TDE FIXME: default + store ? weird

    post_visible = fields.Boolean(
        'Inventory Post Visible', compute='_compute_post_visible',
        help='Technical field to check when we can post')

    user_id = fields.Many2one('res.users', 'Responsible', default=lambda self: self._uid)
    company_id = fields.Many2one(
        'res.company', 'Company',
        default=lambda self: self.env['res.company']._company_default_get('mrp.production'))  # TDE FIXME: no more required ?
    check_to_done = fields.Boolean(compute="_get_produced_qty", string="Check Produced Qty")
    qty_produced = fields.Float(compute="_get_produced_qty", string="Quantity Produced")
    procurement_group_id = fields.Many2one(
        'procurement.group', 'Procurement Group',
        copy=False)
    propagate = fields.Boolean(
        'Propagate cancel and split',
        help='If checked, when the previous move of the move (which was generated by a next procurement) is cancelled or split, the move generated by this move will too')
    has_moves = fields.Boolean(compute='_has_moves')
    has_scrap_move = fields.Boolean(compute='_has_scrap_move')

    @api.multi
    @api.depends('move_raw_ids.state')
    def _compute_availability(self):
        for order in self:
            if not order.move_raw_ids:
                order.availability = 'none'
                continue
            if order.bom_id.ready_to_produce == 'all_available':
                assigned_list = [x.state in ('assigned','done','cancel') for x in order.move_raw_ids]
                order.availability = all(assigned_list) and 'assigned' or 'waiting'
            else:
                # TODO: improve this check
                partial_list = [x.partially_available and x.state in ('waiting', 'confirmed', 'assigned') for x in order.move_raw_ids]
                assigned_list = [x.state in ('assigned','done','cancel') for x in order.move_raw_ids]
                order.availability = (all(assigned_list) and 'assigned') or (any(partial_list) and 'partially_available') or 'waiting'

    @api.multi
    @api.depends('move_raw_ids.quantity_done', 'move_finished_ids.quantity_done')
    def _compute_post_visible(self):
        for order in self:
            order.post_visible = any(order.move_raw_ids.filtered(lambda x: (x.quantity_done) > 0 and (x.state not in ['done', 'cancel']))) or \
                any(order.move_finished_ids.filtered(lambda x: (x.quantity_done) > 0 and (x.state not in ['done', 'cancel'])))

    @api.multi
    def _has_moves(self):
        for mo in self:
            mo.has_moves = any(mo.move_raw_ids)

    @api.multi
    def _has_scrap_move(self):
        StockMove = self.env['stock.move']
        for production in self:
            production.has_scrap_move = any(x.scrapped for x in StockMove.search([('production_id', '=', production.id)]))

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Reference must be unique per Company!'),
        ('qty_positive', 'check (product_qty > 0)', 'The quantity to produce must be positive!'),
    ]

    @api.model
    def create(self, values):
        if values.get('product_id') and 'product_uom_id' not in values:
            values['product_uom_id'] = self.env['product.product'].browse(values['product_id']).uom_id.id
        if not values.get('name', False):
            values['name'] = self.env['ir.sequence'].next_by_code('mrp.production') or 'New'
        if not values.get('procurement_group_id'):
            values['procurement_group_id'] = self.env["procurement.group"].create({'name': values['name']}).id
        production = super(MrpProduction, self).create(values)
        production._generate_moves()
        return production

    @api.multi
    def unlink(self):
        if any(production.state != 'cancel' for production in self):
            raise UserError(_('Cannot delete a manufacturing order not in cancel state'))
        return super(MrpProduction, self).unlink()

    @api.onchange('product_id', 'picking_type_id', 'company_id')
    def onchange_product_id(self):
        """ Finds UoM of changed product. """
        # TDE FIXME: check for company_id
        if not self.product_id:
            self.bom_id = False
        else:
            bom = self.env['mrp.bom']._bom_find(product=self.product_id, picking_type=self.picking_type_id)
            self.bom_id = bom.id
            self.product_uom_id = self.product_id.uom_id.id
            return {'domain': {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}}

    @api.onchange('picking_type_id')
    def onchange_picking_type(self):
        location = self.env.ref('stock.stock_location_stock')
        self.location_src_id = self.picking_type_id.default_location_src_id.id or location.id
        self.location_dest_id = self.picking_type_id.default_location_dest_id.id or location.id

    @api.multi
    def action_cancel(self):
        """ Cancels the production order and related stock moves.
        @return: True
        """
        ProcurementOrder = self.env['procurement.order']
        # Cancel confirmed moves
        for production in self:
            finish_moves = production.move_finished_ids.filtered(lambda x : x.state not in ('done', 'cancel'))
            raw_moves = production.move_raw_ids.filtered(lambda x: x.state not in ('done','cancel'))
            if (not finish_moves) and (not raw_moves):
                raise UserError(_('No need to cancel as all moves are done'))
            if finish_moves:
                finish_moves.action_cancel()
            procs = ProcurementOrder.search([('move_dest_id', 'in', finish_moves.ids)])
            if procs:
                procs.cancel()
            for move in raw_moves:
                if move.quantity_done:
                    raise UserError(_("Already consumed material %s , So you can not cancel production."%(move.product_id.name)))
            raw_moves.action_cancel()
            self.write({'state': 'cancel'})
            # Put relatfinish_to_canceled procurements in exception
            procs = ProcurementOrder.search([('production_id', 'in', self.ids)])
            if procs:
                procs.message_post(body=_('Manufacturing order cancelled.'))
                procs.write({'state': 'exception'})
        return True

    @api.multi
    def _cal_price(self, consumed_moves):
        return True

    @api.multi
    def post_inventory(self):
        for order in self:
            moves_to_do = order.move_raw_ids.move_validate()
            #order.move_finished_ids.filtered(lambda x: x.state not in ('done','cancel')).move_validate()
            order._cal_price(moves_to_do)
            moves_to_finish = order.move_finished_ids.move_validate()
            for move in moves_to_finish:
                #Group quants by lots
                lot_quants = {}
                raw_lot_quants = {}
                quants = self.env['stock.quant']
                if move.has_tracking != 'none':
                    for quant in move.quant_ids:
                        lot_quants.setdefault(quant.lot_id.id, self.env['stock.quant'])
                        raw_lot_quants.setdefault(quant.lot_id.id, self.env['stock.quant'])
                        lot_quants[quant.lot_id.id] |= quant
                for move_raw in moves_to_do:
                    if (move.has_tracking != 'none') and (move_raw.has_tracking != 'none'):
                        for lot in lot_quants:
                            lots = move_raw.move_lot_ids.filtered(lambda x: x.lot_produced_id.id == lot).mapped('lot_id')
                            raw_lot_quants[lot] |= move_raw.quant_ids.filtered(lambda x: (x.lot_id in lots) and (x.qty > 0.0))
                    else:
                        quants |= move_raw.quant_ids.filtered(lambda x: x.qty > 0.0)
                if move.has_tracking != 'none':
                    for lot in lot_quants:
                        lot_quants[lot].write({'consumed_quant_ids': [(6, 0, [x.id for x in raw_lot_quants[lot] | quants])]})
                else:
                    move.quant_ids.write({'consumed_quant_ids': [(6, 0, [x.id for x in quants])]})
            order.action_assign()
        return True

    @api.multi
    def button_mark_done(self):
        self.ensure_one()
        self.post_inventory()
        moves_to_cancel = (self.move_raw_ids | self.move_finished_ids).filtered(lambda x: x.state not in ('done', 'cancel'))
        moves_to_cancel.action_cancel()
        # self._costs_generate()
        self.write({'state': 'done', 'date_finished': fields.datetime.now()})
        self.env["procurement.order"].search([('production_id', 'in', self.ids)]).check()
        self.write({'state': 'done'})

    @api.multi
    def _get_produced_qty(self):
        for production in self:
            done_moves = production.move_finished_ids.filtered(lambda x: x.state != 'cancel' and x.product_id.id == production.product_id.id)
            qty_produced = sum(done_moves.mapped('quantity_done'))
            production.check_to_done = done_moves and (qty_produced >= production.product_qty) and (production.state not in ('done', 'cancel'))
            production.qty_produced = qty_produced
        return True

    def _make_production_produce_line(self):
        procs = self.env['procurement.order'].search([('production_id', '=', self.id)])
        procurement = procs and procs[0]
        data = {
            'name': self.name,
            'date': self.date_planned,
            'date_expected': self.date_planned,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'location_id': self.product_id.property_stock_production.id,
            'location_dest_id': self.location_dest_id.id,
            'move_dest_id': self.move_prod_id.id,
            'procurement_id': procurement and procurement.id or False,
            'company_id': self.company_id.id,
            'production_id': self.id,
            'origin': self.name,
            'group_id': self.procurement_group_id.id,
        }
        move_id = self.env['stock.move'].create(data)
        move_id.action_confirm()
        return True

    @api.multi
    def _update_move(self, bom_line, quantity, **kw):
        self.ensure_one()
        move = self.move_raw_ids.filtered(lambda x: x.bom_line_id.id == bom_line.id and x.state not in ('done', 'cancel'))
        if move:
            move.write({'product_uom_qty': quantity})
            return move
        else:
            self._generate_move(bom_line, quantity, **kw)



    @api.multi
    def _generate_move_data(self, bom_line, quantity, **kw):
        source_location = self.location_src_id
        if bom_line.product_id.type not in ['product', 'consu']:
            return False
        if 'original_quantity' in kw:
            original_quantity = kw['original_quantity']
        else:
            original_quantity = 1.0
        data = {
            'name': self.name,
            'date': self.date_planned,
            'bom_line_id': bom_line.id,
            'product_id': bom_line.product_id.id,
            'product_uom_qty': quantity,
            'product_uom': bom_line.product_uom_id.id,
            'location_id': source_location.id,
            'location_dest_id': self.product_id.property_stock_production.id,
            'raw_material_production_id': self.id,
            'company_id': self.company_id.id,
            'price_unit': bom_line.product_id.standard_price,
            'procure_method': 'make_to_stock',
            'origin': self.name,
            'warehouse_id': source_location.get_warehouse().id,
            'group_id': self.procurement_group_id.id,
            'propagate': self.propagate,
            'unit_factor': quantity / original_quantity,
        }
        return data

    @api.multi
    def _generate_move(self, bom_line, quantity, **kw):
        self.ensure_one()
        data = self._generate_move_data(bom_line, quantity, result=kw)
        return self.env['stock.move'].create(data)

    @api.multi
    def _adjust_procure_method(self):
        try:
            mto_route = self.env['stock.warehouse']._get_mto_route()
        except:
            mto_route = False
        for move in self.move_raw_ids:
            product = move.product_id
            routes = product.route_ids + product.categ_id.route_ids
            # TODO: optimize with read_group?
            pull = self.env['procurement.rule'].search([('route_id', 'in', [x.id for x in routes]), ('location_src_id', '=', move.location_id.id),
                                                        ('location_id', '=', move.location_dest_id.id)], limit=1)
            if pull and (pull.procure_method == 'make_to_order'):
                move.procure_method = pull.procure_method
            elif not pull:
                if mto_route and mto_route in [x.id for x in routes]:
                    move.procure_method = 'make_to_order'

    @api.multi
    def _generate_moves(self):
        for production in self:
            production._make_production_produce_line()
            factor = self.env['product.uom']._compute_qty(production.product_uom_id.id, production.product_qty, production.bom_id.product_uom_id.id)
            production.bom_id.explode(production.product_id, factor, method=self._generate_move)
            # Check for all draft moves whether they are mto or not
            self._adjust_procure_method()
            self.move_raw_ids.action_confirm()
        return True

    @api.multi
    def action_assign(self):
        for production in self:
            move_to_assign = production.move_raw_ids.filtered(lambda x: x.state in ('confirmed', 'waiting', 'assigned'))
            move_to_assign.action_assign()
        return True

    @api.multi
    def do_unreserve(self):
        for production in self:
            production.move_raw_ids.filtered(lambda x: x.state not in ('done', 'cancel')).do_unreserve()

    @api.multi
    def button_unreserve(self):
        self.ensure_one()
        self.do_unreserve()

    @api.multi
    def button_scrap(self):
        self.ensure_one()
        return {
            'name': _('Scrap'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.scrap',
            'view_id': self.env.ref('stock.stock_scrap_form_view2').id,
            'type': 'ir.actions.act_window',
            'context': {'product_ids': (self.move_raw_ids | self.move_finished_ids.filtered(lambda x: x.state == 'done')).mapped('product_id').ids},
            'target': 'new',
        }

    @api.multi
    def button_scrapped_moves(self):
        self.ensure_one()
        action_rec = self.env.ref('stock.action_move_form2')
        scrap_moves = self.env['stock.move'].search([('production_id', '=', self.id), ('scrapped', '=', True), ('state', '=', 'done')])
        if action_rec:
            action = action_rec.read([])[0]
            action['domain'] = [('id', 'in', scrap_moves.ids)]
            action_context = eval(action['context'])
            action_context['scrap_move'] = True
            action['context'] = str(action_context)
            return action
