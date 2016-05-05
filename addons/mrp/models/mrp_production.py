# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from collections import OrderedDict
from openerp import api, fields, models, _
from openerp.exceptions import AccessError, UserError, Warning
from openerp.tools import float_compare, float_is_zero, DEFAULT_SERVER_DATETIME_FORMAT, html2plaintext
import openerp.addons.decimal_precision as dp
from datetime import datetime
from dateutil.relativedelta import relativedelta
import time
import math

class MrpProduction(models.Model):
    """ Manufacturing Orders """
    _name = 'mrp.production'
    _description = 'Manufacturing Order'
    _date_name = 'date_planned'
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'date_planned asc,id'

    @api.model
    def _default_picking_type(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'mrp_operation'), ('warehouse_id.company_id', 'in', [company_id, False])])
        return types[0].id if types else False

    def _location_src_default(self):
        location=False
        if self.env.context.get('default_picking_type_id'):
            location = self.env['stock.picking_type'].browse(self.env.context['default_picking_type_id']).default_location_src_id.id
        if not location:
            try:
                location = self.env.ref('stock.stock_location_stock')
                location.check_access_rule('read')
            except (AccessError, ValueError):
                location = False
        return location

    def _location_dest_default(self):
        location=False
        if self.env.context.get('default_picking_type_id'):
            location = self.env['stock.picking_type'].browse(self.env.context['default_picking_type_id']).default_location_dest_id.id
        if not location:
            try:
                location = self.env.ref('stock.stock_location_stock')
                location.check_access_rule('read')
            except (AccessError, ValueError):
                location = False
        return location

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

    name = fields.Char(string='Reference', readonly=True, copy=False, default='New')
    origin = fields.Char(string='Source', help="Reference of the document that generated this manufacturing order.", copy=False)
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, domain=[('type', 'in', ['product', 'consu'])])
    product_tmpl_id = fields.Many2one('product.template', string='Product Template', related='product_id.product_tmpl_id')
    product_qty = fields.Float(string='Quantity to Produce', digits=dp.get_precision('Product Unit of Measure'), required=True, readonly=True, states={'confirmed': [('readonly', False)]}, default=1.0)
    product_uom_id = fields.Many2one('product.uom', string='Product Unit of Measure', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, oldname='product_uom')

    picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type', default=_default_picking_type, required=True)
    location_src_id = fields.Many2one('stock.location', string='Raw Materials Location', default=_location_src_default,
                                      readonly=True, states={'confirmed': [('readonly', False)]})
    location_dest_id = fields.Many2one('stock.location', string='Finished Products Location', default=_location_dest_default,
                                       readonly=True, states={'confirmed': [('readonly', False)]})
    date_planned = fields.Datetime(string='Expected Date', required=True, index=True, readonly=True, states={'confirmed': [('readonly', False)]}, copy=False, default=fields.Datetime.now)

    date_start = fields.Datetime(string='Start Date', readonly=True, copy=False)
    date_finished = fields.Datetime(string='End Date', readonly=True, copy=False)

    bom_id = fields.Many2one('mrp.bom', string='Bill of Material', readonly=True, states={'confirmed': [('readonly', False)]})
    # FP Note: what's the goal of this field? -> It is like the destination move of the production move
    move_prod_id = fields.Many2one('stock.move', string='Product Move', readonly=True, copy=False)
    move_raw_ids = fields.One2many('stock.move', 'raw_material_production_id', string='Raw Materials', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, copy=False)
    move_finished_ids = fields.One2many('stock.move', 'production_id', string='Finished Products', states={'done': [('readonly', True)], 'cancel': [('readonly', True)]}, copy=False)

    state = fields.Selection([('confirmed', 'Confirmed'), ('planned', 'Planned'), ('progress', 'In Progress'), ('done', 'Done'), ('cancel', 'Cancelled')], 'State', default='confirmed', copy=False)

    availability = fields.Selection([('assigned', 'Available'), ('partially_available', 'Partially Available'), ('none', 'None'), ('waiting', 'Waiting')], compute='_compute_availability', store=True, default="none")

    post_visible = fields.Boolean('Inventory Post Visible', compute='_compute_post_visible', help='Technical field to check when we can post')

    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env['res.company']._company_default_get('mrp.production'))
    check_to_done = fields.Boolean(compute="_get_produced_qty", string="Check Produced Qty")
    qty_produced = fields.Float(compute="_get_produced_qty", string="Quantity Produced")
    procurement_group_id = fields.Many2one('procurement.group', 'Procurement Group', copy=False)
    propagate = fields.Boolean(string='Propagate cancel and split', help='If checked, when the previous move of the move (which was generated by a next procurement) is cancelled or split, the move generated by this move will too')
    has_moves = fields.Boolean(compute='_has_moves')
    has_scrap_move = fields.Boolean(compute='_has_scrap_move')

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Reference must be unique per Company!'),
        ('qty_positive', 'check (product_qty > 0)', 'The quantity to produce must be positive!'),
    ]

    @api.model
    def create(self, values):
        if not values.get('name', False):
            values['name'] = self.env['ir.sequence'].next_by_code('mrp.production') or 'New'
        if not values.get('procurement_group_id'):
            values['procurement_group_id'] = self.env["procurement.group"].create({'name': values['name']}).id
        production = super(MrpProduction, self).create(values)
        production._generate_moves()
        return production

    @api.multi
    def _has_scrap_move(self):
        StockMove = self.env['stock.move']
        for production in self:
            production.has_scrap_move = any(x.scrapped for x in StockMove.search([('production_id', '=', production.id)]))

    @api.multi
    def unlink(self):
        for production in self:
            if production.state != 'cancel':
                raise UserError(_('Cannot delete a manufacturing order in state \'%s\'.') % production.state)
        return super(MrpProduction, self).unlink()

    @api.onchange('picking_type_id')
    def onchange_picking_type(self):
        location = self.env.ref('stock.stock_location_stock')
        self.location_src_id = self.picking_type_id.default_location_src_id.id or location.id
        self.location_dest_id = self.picking_type_id.default_location_dest_id.id or location.id

    @api.multi
    @api.onchange('product_id', 'company_id', 'picking_type_id')
    def onchange_product_id(self):
        if not self.product_id:
            self.product_uom_id = False
            self.bom_id = False
        else:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id, picking_type=self.picking_type_id)
            self.product_uom_id = self.product_id.uom_id.id
            self.bom_id = bom_point.id
            return {'domain': {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}}


    @api.multi
    def action_cancel(self):
        """ Cancels the production order and related stock moves.
        :return: True
        """
        ProcurementOrder = self.env['procurement.order']
        # Cancel confirmed moves
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
        write_res = self.write({'state': 'done', 'date_finished': fields.datetime.now()})
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
        move = self.move_raw_ids.filtered(lambda x:x.bom_line_id.id == bom_line.id and x.state not in ('done', 'cancel'))
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
            #'operation_id': bom_line.operation_id.id,
            'price_unit': bom_line.product_id.standard_price,
            'procure_method': 'make_to_stock',
            'origin': self.name,
            'warehouse_id': source_location.get_warehouse(),
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
            #TODO: optimize with read_group?
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
            #Check for all draft moves whether they are mto or not
            self._adjust_procure_method()
            self.move_raw_ids.action_confirm()
        return True

    @api.multi
    def action_assign(self):
        lots = self.env['stock.move.lots']
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
            'context': {'product_ids': (self.move_raw_ids | self.move_finished_ids).mapped('product_id').ids},
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

class MrpUnbuild(models.Model):
    _name = "mrp.unbuild"
    _description = "Unbuild Order"
    _inherit = ['mail.thread']
    _order = 'id desc'

    def _src_id_default(self):
        try:
            location = self.env.ref('stock.stock_location_stock')
            location.check_access_rule('read')
        except (AccessError, ValueError):
            location = False
        return location

    def _dest_id_default(self):
        try:
            location = self.env.ref('stock.stock_location_stock')
            location.check_access_rule('read')
        except (AccessError, ValueError):
            location = False
        return location

    name = fields.Char(string='Reference', readonly=True, copy=False, default=False)
    product_id = fields.Many2one('product.product', string="Product", required=True, states={'done': [('readonly', True)]})
    product_qty = fields.Float('Quantity', required=True, states={'done': [('readonly', True)]})
    product_uom_id = fields.Many2one('product.uom', string="Unit of Measure", required=True, states={'done': [('readonly', True)]})
    bom_id = fields.Many2one('mrp.bom', 'Bill of Material', required=True, domain=[('product_tmpl_id', '=', 'product_id.product_tmpl_id')], states={'done': [('readonly', True)]})  # Add domain
    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order', states={'done': [('readonly', True)]}, domain="[('product_id', '=', product_id), ('state', 'in', ['done', 'cancel'])]")
    lot_id = fields.Many2one('stock.production.lot', 'Lot', domain="[('product_id','=', product_id)]", states={'done': [('readonly', True)]})
    location_id = fields.Many2one('stock.location', 'Location', required=True, default=_src_id_default, states={'done': [('readonly', True)]})
    consume_line_id = fields.Many2one('stock.move', readonly=True)
    produce_line_ids = fields.One2many('stock.move', 'unbuild_id', readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft', index=True)
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', required=True, default=_dest_id_default, states={'done': [('readonly', True)]})

    @api.constrains('product_qty')
    def _check_qty(self):
        if self.product_qty <= 0:
            raise ValueError(_('Unbuild product quantity cannot be negative or zero!'))

    def _get_bom(self):
        # search BoM structure and route
        bom_point = self.bom_id
        if not bom_point:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id)
            if bom_point:
                self.write({'bom_id': bom_point.id})
        if not bom_point:
            raise UserError(_("Cannot find a bill of material for this product."))
        return bom_point

    @api.multi
    def _generate_moves(self):
        for unbuild in self:
            bom = unbuild._get_bom()
            factor = self.env['product.uom']._compute_qty(unbuild.product_uom_id.id, unbuild.product_qty, bom.product_uom_id.id)
            bom.explode(unbuild.product_id, factor / bom.product_qty, method=self._generate_move)
            unbuild.consume_line_id.action_confirm()
        return True

    @api.model
    def create(self, vals):
        if not vals.get('name', False):
            vals['name'] = self.env['ir.sequence'].next_by_code('mrp.unbuild') or 'New'
        unbuild = super(MrpUnbuild, self).create(vals)
        return unbuild

    def _make_unbuild_consume_line(self):
        data = {
            'name': self.name,
            'date': self.create_date,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'restrict_lot_id': self.lot_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.product_id.property_stock_production.id,
            'raw_material_unbuild_id': self.id,
            'origin': self.name
        }
        rec = self.env['stock.move'].create(data).action_confirm()
        return rec

    @api.multi
    def _generate_move(self, bom_line, quantity, **kw):
        self.ensure_one()
        data = {
            'name': self.name,
            'date': self.create_date,
            'bom_line_id': bom_line.id,
            'product_id': bom_line.product_id.id,
            'product_uom_qty': quantity,
            'product_uom': bom_line.product_uom_id.id,
            'procure_method': 'make_to_stock',
            'location_dest_id': self.location_dest_id.id,
            'location_id': self.product_id.property_stock_production.id,
            'unbuild_id': self.id,
        }
        return self.env['stock.move'].create(data)


    @api.onchange('mo_id')
    def onchange_mo_id(self):
        if self.mo_id:
            self.product_id = self.mo_id.product_id.id
            self.product_qty = self.mo_id.product_qty

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.bom_id = self.env['mrp.bom']._bom_find(product=self.product_id)
            self.product_uom_id = self.product_id.uom_id.id

    @api.multi
    def button_unbuild(self):
        self.ensure_one()
        self._make_unbuild_consume_line()
        self._generate_moves()
        #Search quants that passed production order
        move = self.consume_line_id
        if self.mo_id:
            main_finished_moves = self.mo_id.move_finished_ids.filtered(lambda x: x.product_id.id == self.mo_id.product_id.id)
            domain = [('qty', '>', 0), ('history_ids', 'in', [x.id for x in main_finished_moves])]
            qty = self.product_qty # Convert to qty on product UoM
            quants = self.env['stock.quant'].quants_get_preferred_domain(qty, move, domain=domain, preferred_domain_list=[], lot_id=self.lot_id.id)
        else:
            quants = self.env['stock.quant'].quants_get_preferred_domain(qty, move, domain=domain, preferred_domain_list=[], lot_id=self.lot_id.id)
        self.env['stock.quant'].quants_reserve(quants, move)
#        self.consume_line_id.action_done()
        if move.has_tracking != 'none':
            if not self.lot_id.id:
                raise UserError(_('Should have a lot for the finished product'))
            self.env['stock.move.lots'].create({'move_id': move.id,
                                                'lot_id': self.lot_id.id,
                                                'quantity_done': move.product_uom_qty,
                                                'quantity': move.product_uom_qty})
        self.consume_line_id.move_validate()
        original_quants = self.env['stock.quant']
        for quant in self.consume_line_id.quant_ids:
            original_quants |= quant.consumed_quant_ids
        for produce_move in self.produce_line_ids:
            if produce_move.has_tracking != 'none':
                original = original_quants.filtered(lambda x: x.product_id.id == produce_move.product_id.id)
                self.env['stock.move.lots'].create({'move_id': produce_move.id,
                                                    'lot_id': original.lot_id.id,
                                                    'quantity_done': produce_move.product_uom_qty,
                                                    'quantity': produce_move.product_uom_qty,})
        self.produce_line_ids.move_validate()
        produced_quant_ids = self.env['stock.quant']
        for move in self.produce_line_ids:
            produced_quant_ids |= move.quant_ids
        self.consume_line_id.quant_ids.write({'produced_quant_ids': [(6, 0, produced_quant_ids)]})
        # TODO : Need to assign quants which consumed at build product.
        #self.quant_move_rel()
        self.write({'state': 'done'})


    @api.multi
    def button_open_move(self):
        stock_moves = self.env['stock.move'].search(['|', ('unbuild_id', '=', self.id), ('raw_material_unbuild_id', '=', self.id)])
        return {
            'name': _('Stock Moves'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'stock.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', stock_moves.ids)],
        }

    @api.multi
    def _get_consumed_quants(self):
        self.ensure_one()
        quants = self.env['stock.quant']
        for quant in self.consume_line_id.reserved_quant_ids:
            quants = quants | quant.consumed_quant_ids
        return quants

    
    #TODO: need quants defined here
    @api.multi
    def quant_move_rel(self):
        self.ensure_one()
        todo_moves = self.env['stock.move']
        consumed_quants = self._get_consumed_quants()
        if consumed_quants:
            for move in self.produce_line_ids:
                res = []
                quants = consumed_quants.filtered(lambda x: x.product_id == move.product_id)
                if quants:
                    for quant in quants:
                        res += [(quant, quant.qty)]
                    self.env['stock.quant'].quants_move(res, move, move.location_dest_id)
                else:
                    todo_moves = todo_moves | move
        assigned_moves = self.produce_line_ids - todo_moves
        assigned_moves.write({'state': 'done'})
        todo_moves.action_done()


class InventoryMessage(models.Model):
    _name = "inventory.message"
    _description = "Inventory Message"

    @api.depends('message')
    def _get_note_first_line(self):
        for invmessage in self:
            invmessage.name = (invmessage.message and html2plaintext(invmessage.message) or "").strip().replace('*', '').split("\n")[0]

    @api.model
    def _default_valid_until(self):
        return datetime.today() + relativedelta(days=7)

    name = fields.Text(compute='_get_note_first_line', store=True)
    message = fields.Html(required=True)
    picking_type_id = fields.Many2one('stock.picking.type', string="Alert on Operation", required=True)
    code = fields.Selection(related='picking_type_id.code', store=True)
    product_id = fields.Many2one('product.product', string="Product")
    bom_id = fields.Many2one('mrp.bom', 'Bill of Material', domain="[('product_id', '=', product_id)]")
    valid_until = fields.Date(default=_default_valid_until, required=True)

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.bom_id = self.env['mrp.bom']._bom_find(product=self.product_id)
