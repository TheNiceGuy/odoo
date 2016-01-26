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


class MrpProduction(models.Model):
    """
    Production Orders / Manufacturing Orders
    """
    _name = 'mrp.production'
    _description = 'Manufacturing Order'
    _date_name = 'date_planned'
    _inherit = ['mail.thread', 'ir.needaction_mixin']
    _order = 'date_planned asc, priority desc'

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

    @api.model
    def _default_picking_type(self):
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get('company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'mrp_operation'), ('warehouse_id.company_id', '=', company_id)])
        if not types:
            types = type_obj.search([('code', '=', 'mrp_operation'), ('warehouse_id', '=', False)])
        return types[0].id if types else False

    @api.multi
    @api.depends('move_line_ids','move_line_ids.state', 'workcenter_line_ids', 'workcenter_line_ids.move_line_ids')
    def _compute_availability(self):
        for order in self:
            if not order.move_line_ids:
                order.availability = 'none'
                continue
            assigned_list = [x.state == 'assigned' for x in order.move_line_ids] #might do partial available moves too
            if order.bom_id.ready_to_produce == 'all_available':
                if all(assigned_list):
                    order.availability = 'assigned'
                else:
                    order.availability = 'waiting'
            else:
                if all(assigned_list):
                    order.availability = 'assigned'
                    continue
                #TODO: We can skip this,but partially available is only possible when field on bom allows it
                if order.workcenter_line_ids and order.workcenter_line_ids[0].move_line_ids:
                    if all([x.state=='assigned' for x in order.move_line_ids]):
                        order.availability = 'partially_available'
                    else:
                        order.availability = 'waiting'
                elif any(assigned_list): #Or should be availability of first work order?
                    order.availability = 'partially_available'
                else:
                    order.availability = 'none'

    @api.multi
    def _inverse_date_planned(self):
        for order in self:
            if order.workcenter_line_ids and order.state != 'confirmed':
                raise UserError(_('You should change the Work Order planning instead!'))
            order.write({'date_planned_start_store': order.date_planned_start,
                         'date_planned_finished_store': order.date_planned_finished})

    @api.multi
    @api.depends('workcenter_line_ids.date_planned_start', 'workcenter_line_ids.date_planned_end', 'date_planned_start_store', 'date_planned_finished_store')
    def _compute_date_planned(self):
        for order in self:
            if order.workcenter_line_ids and order.state != 'confirmed': #It is already planned somehow
                first_planned_start_date = False
                last_planned_end_date = False
                for wo in order.workcenter_line_ids:
                    if wo.date_planned_start and ((not first_planned_start_date) or (fields.Datetime.from_string(wo.date_planned_start) < first_planned_start_date)):
                        first_planned_start_date = fields.Datetime.from_string(wo.date_planned_start)
                    if wo.date_planned_end and ((not last_planned_end_date) or (fields.Datetime.from_string(wo.date_planned_end) > last_planned_end_date)):
                        last_planned_end_date = fields.Datetime.from_string(wo.date_planned_end)
                order.date_planned_start = first_planned_start_date and fields.Datetime.to_string(first_planned_start_date) or False
                order.date_planned_finished = last_planned_end_date and fields.Datetime.to_string(last_planned_end_date) or False
            else:
                order.date_planned_start = order.date_planned_start_store
                order.date_planned_finished = order.date_planned_finished_store

    @api.multi
    @api.depends('workcenter_line_ids')
    def _compute_nb_orders(self):
        for mo in self:
            total_mo = 0
            done_mo = 0
            for wo in mo.workcenter_line_ids:
                total_mo += 1
                if wo.state == 'done':
                    done_mo += 1
            mo.nb_orders = total_mo
            mo.nb_done = done_mo

    @api.depends('move_created_ids2')
    def _check_to_done(self):
        produced_qty = 0
        for production in self:
            for produced_product in production.move_created_ids2:
                if (produced_product.scrapped) or (produced_product.product_id.id != production.product_id.id):
                    continue
                produced_qty += produced_product.product_qty
            production.check_to_done = True if produced_qty >= production.product_qty else False

    @api.multi
    @api.depends('consume_operation_ids', 'produce_operation_ids')
    def _compute_post_visible(self):
        for order in self:
            order.post_visible = any([x.qty_done > 0 for x in order.consume_operation_ids]) and any([x.qty_done > 0 for x in order.produce_operation_ids])

    name = fields.Char(string='Reference', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('mrp.production') or '/')
    origin = fields.Char(string='Source', readonly=True, states={'confirmed': [('readonly', False)]},
                         help="Reference of the document that generated this production order request.", copy=False)
    priority = fields.Selection([('0', 'Not urgent'), ('1', 'Normal'), ('2', 'Urgent'), ('3', 'Very Urgent')], 'Priority',
                                index=True, readonly=True, states=dict.fromkeys(['draft', 'confirmed'], [('readonly', False)]), default='1')
    product_id = fields.Many2one('product.product', string='Product', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, domain=[('type', 'in', ['product', 'consu'])])
    product_qty = fields.Float(string='Quantity to Produce', digits=dp.get_precision('Product Unit of Measure'), required=True, readonly=True, states={'confirmed': [('readonly', False)]}, default=1.0)
    product_uom_id = fields.Many2one('product.uom', string='Product Unit of Measure', required=True, readonly=True, states={'confirmed': [('readonly', False)]}, oldname='product_uom')
    progress = fields.Float(compute='_get_progress', string='Production progress')
    location_src_id = fields.Many2one('stock.location', string='Raw Materials Location', required=True,
                                      readonly=True, states={'confirmed': [('readonly', False)]}, default=_src_id_default,
                                      help="Location where the system will look for components.")
    location_dest_id = fields.Many2one('stock.location', string='Finished Products Location', required=True,
                                       readonly=True, states={'confirmed': [('readonly', False)]}, default=_dest_id_default,
                                       help="Location where the system will stock the finished products.")
    date_planned = fields.Datetime(string='Expected Date', required=True, index=True, readonly=True, states={'confirmed': [('readonly', False)]}, copy=False, default=fields.Datetime.now)
    date_planned_start_store = fields.Datetime(string='Technical Field for planned start')
    date_planned_finished_store = fields.Datetime(string='Technical Field for planned finished')
    date_planned_start = fields.Datetime(string='Scheduled Start Date', compute='_compute_date_planned', inverse='_inverse_date_planned', states={'confirmed': [('readonly', False)]}, readonly=True, store=True, index=True, copy=False)
    date_planned_finished = fields.Datetime(string='Scheduled End Date', compute='_compute_date_planned', inverse='_inverse_date_planned', states={'confirmed': [('readonly', False)]}, readonly=True, store=True, index=True, copy=False)
    date_start = fields.Datetime(string='Start Date', index=True, readonly=True, copy=False)
    date_finished = fields.Datetime(string='End Date', index=True, readonly=True, copy=False)
    bom_id = fields.Many2one('mrp.bom', string='Bill of Material', readonly=True, states={'confirmed': [('readonly', False)]},
                             help="Bill of Materials allow you to define the list of required raw materials to make a finished product.")
    routing_id = fields.Many2one('mrp.routing', string='Routing', related = 'bom_id.routing_id', store=True,
                                 on_delete='set null', readonly=True,
                                 help="The list of operations (list of work centers) to produce the finished product. The routing is mainly used "
                                      "to compute work center costs during operations and to plan future loads on work centers based on production plannification.")
    move_prod_id = fields.Many2one('stock.move', string='Product Move', readonly=True, copy=False)
    move_line_ids = fields.One2many('stock.move', 'raw_material_production_id', string='Products to Consume',
                                    domain=[('state', 'not in', ('done', 'cancel'))], readonly=True, states={'confirmed': [('readonly', False)]}, oldname='move_lines')
    move_line_ids2 = fields.One2many('stock.move', 'raw_material_production_id', string='Consumed Products',
                                     domain=[('state', 'in', ('done', 'cancel'))], readonly=True, oldname='move_lines2')
    move_created_ids = fields.One2many('stock.move', 'production_id', string='Products to Produce',
                                       domain=[('state', 'not in', ('done', 'cancel'))], readonly=True)
    move_created_ids2 = fields.One2many('stock.move', 'production_id', 'Produced Products',
                                        domain=[('state', 'in', ('done', 'cancel'))], readonly=True)
    consume_operation_ids = fields.One2many('stock.pack.operation', 'production_raw_id', string="Consume Operations")
    produce_operation_ids = fields.One2many('stock.pack.operation', 'production_finished_id', string="Produce Operations")
    workcenter_line_ids = fields.One2many('mrp.production.workcenter.line', 'production_id', string='Work Centers Utilisation',
                                          readonly=True, oldname='workcenter_lines')
    nb_orders = fields.Integer('Number of Orders', compute='_compute_nb_orders')
    nb_done = fields.Integer('Number of Orders Done', compute='_compute_nb_orders')
    state = fields.Selection([('confirmed', 'Confirmed'), ('planned', 'Planned'), ('progress', 'In Progress'), ('done', 'Done'), ('cancel', 'Cancelled')], 'State', default='confirmed', copy=False)
    availability = fields.Selection([('assigned', 'Available'), ('partially_available', 'Partially available'), ('none', 'None'), ('waiting', 'Waiting')], compute='_compute_availability', store=True, default="none")
    picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type', default=_default_picking_type, required=True)
    post_visible = fields.Boolean('Inventory Post Visible', compute='_compute_post_visible', help='Technical field to check when we can post')
    

#     state = fields.Selection(
#         [('draft', 'New'), ('cancel', 'Cancelled'), ('confirmed', 'Awaiting Raw Materials'),
#             ('ready', 'Ready to Produce'), ('in_production', 'Production Started'), ('done', 'Done')],
#         string='Status', readonly=True, default='draft',
#         track_visibility='onchange', copy=False,
#         help="When the production order is created the status is set to 'Draft'.\n"
#              "If the order is confirmed the status is set to 'Waiting Goods.\n"
#              "If any exceptions are there, the status is set to 'Picking Exception.\n"
#              "If the stock is available then the status is set to 'Ready to Produce.\n"
#              "When the production gets started then the status is set to 'In Production.\n"
#              "When the production is over, the status is set to 'Done'.")
    hour_total = fields.Float(compute='_production_calc', string='Total Hours', store=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env['res.company']._company_default_get('mrp.production'))
    product_tmpl_id = fields.Many2one('product.template', related='product_id.product_tmpl_id', string='Product')
    categ_id = fields.Many2one('product.category', related='product_tmpl_id.categ_id', string='Product Category', readonly=True, store=True)
    check_to_done = fields.Boolean(compute="_check_to_done", string="Check Produced Qty")
    check_move_state = fields.Boolean(string="Check Move State")

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Reference must be unique per Company!'),
    ]

    @api.multi
    @api.depends('workcenter_line_ids.hour')
    def _production_calc(self):
        """ Calculates total hours for a production order.
        :return: Dictionary of values.
        """
        data = self.env['mrp.production.workcenter.line'].read_group([('production_id', 'in', self.ids)], ['hour', 'production_id'], ['production_id'])
        mapped_data = dict([(m['production_id'][0], {'hour': m['hour']}) for m in data])
        for record in self:
            record.hour_total = mapped_data.get(record.id, {}).get('hour', 0)

    def _get_progress(self):
        """ Return product quantity percentage """
        result = dict.fromkeys(self.ids, 100)
        for mrp_production in self:
            if mrp_production.product_qty:
                done = 0.0
                for move in mrp_production.move_created_ids2:
                    if not move.scrapped and move.product_id == mrp_production.product_id:
                        done += move.product_qty
                result[mrp_production.id] = done / mrp_production.product_qty * 100
        return result

    @api.constrains('product_qty')
    def _check_qty(self):
        if self.product_qty <= 0:
            raise ValueError(_('Order quantity cannot be negative or zero!'))

    @api.model
    def create(self, values):
        if 'product_id' in values and ('product_uom_id' not in values or not values['product_uom_id']):
            values['product_uom_id'] = self.env['product.product'].browse(values.get('product_id')).uom_id.id
        production = super(MrpProduction, self).create(values)
        production.generate_moves(properties=None) #TODO: solutions for properties: procurement.property_ids
        return production

    @api.multi
    def button_plan(self):
        WorkOrder = self.env['mrp.production.workcenter.line']
        for order in self.filtered(lambda x: x.routing_id and x.state == 'confirmed'):
            order.write({'state': 'planned'})
                    # Create work orders
            #TODO: Need to find solutions for properties
            results, results2 = order._prepare_lines(properties=None)
            firsttime = True
            for line in results2:
                if firsttime:
                    firsttime = False
                    line['state'] = 'ready'
                line['production_id'] = order.id
                wo = WorkOrder.create(line)
                moves = self.env['stock.move'].search([('operation_id','=', wo.operation_id.id), ('raw_material_production_id', '=', self.id)])
                if moves:
                    moves.write({'workorder_id': wo.id})
                for move in wo.move_line_ids:
                    self.env['mrp.production.workcenter.line.consume'].create({'product_id': move.product_id.id, 'workorder_id': wo.id})
            #Let us try to plan the order
            order._plan_workorder()

    @api.multi
    def button_mark_done(self):
        self.ensure_one()
        self.write({'state': 'done'})

    @api.multi
    def unlink(self):
        for production in self:
            if production.state not in ('draft', 'cancel'):
                raise UserError(_('Cannot delete a manufacturing order in state \'%s\'.') % production.state)
        return super(MrpProduction, self).unlink()

    @api.onchange('location_src_id')
    def onchange_location_id(self):
        if self.location_dest_id:
            return
        if self.location_src_id:
            self.location_dest_id = self.location_src_id.id

    @api.multi
    @api.onchange('product_id', 'company_id')
    def onchange_product_id(self):
        if not self.product_id:
            self.product_uom_id = False
            self.bom_id = False
            self.routing_id = False
            self.product_tmpl_id = False
        else:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id, properties=[])
            routing_id = False
            if bom_point:
                routing_id = bom_point.routing_id
            self.product_uom_id = self.product_id.uom_id.id
            self.bom_id = bom_point.id
            self.routing_id = routing_id.id
            self.product_tmpl_id = self.product_id.product_tmpl_id.id
            self.date_planned_start = fields.Datetime.to_string(datetime.now())
            date_planned = datetime.now() + relativedelta(days=self.product_id.produce_delay or 0.0) + relativedelta(days=self.company_id.manufacturing_lead)
            self.date_planned = fields.Datetime.to_string(date_planned)
            self.date_planned_finished = date_planned
            return {'domain': {'product_uom_id': [('category_id', '=', self.product_id.uom_id.category_id.id)]}}

    @api.onchange('bom_id')
    def onchange_bom_id(self):
        if not self.bom_id:
            self.routing_id = False
        self.routing_id = self.bom_id.routing_id.id or False

    def _prepare_lines(self, properties=None):
        # search BoM structure and route
        bom_point = self.bom_id
        if not bom_point:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id, properties=properties)
            if bom_point:
                self.write({'bom_id': bom_point.id, 'routing_id': bom_point.routing_id and bom_point.routing_id.id or False})

        if not bom_point:
            raise UserError(_("Cannot find a bill of material for this product."))

        # get components and workcenter_line_ids from BoM structure
        factor = self.product_uom_id._compute_qty(self.product_qty, bom_point.product_uom_id.id)
        # product_line_ids, workcenter_line_ids
        return bom_point.explode(self.product_id, factor / bom_point.product_qty, properties=properties, routing_id=self.routing_id.id)

    @api.multi
    def _plan_workorder(self):
        workorder_obj = self.env['mrp.production.workcenter.line']
        for production in self:
            start_date = fields.datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT)
            for workorder in production.workcenter_line_ids:
                workcenter = workorder.workcenter_id
                capacity = workcenter.capacity
                # Check initial capacity 
                #TODO: check production_state != 'done'
                wos = workorder_obj.search([
                    ('workcenter_id', '=', workcenter.id),
                    ('date_planned_start', '<', start_date), 
                    ('date_planned_end', '>', start_date),
                    ])
                init_cap = sum([x.capacity_planned for x in wos])
                cr = self._cr
                cr.execute("""SELECT date, cap FROM 
                            ((SELECT date_planned_start AS date, capacity_planned AS cap FROM mrp_production_workcenter_line WHERE workcenter_id = %s AND
                                    date_planned_start IS NOT NULL AND date_planned_end IS NOT NULL AND date_planned_start > %s)
                            UNION
                            (SELECT date_planned_end AS date, -capacity_planned AS cap FROM mrp_production_workcenter_line WHERE workcenter_id = %s AND
                                    date_planned_start IS NOT NULL AND date_planned_end IS NOT NULL AND date_planned_end > %s)) AS date_union 
                            ORDER BY date""", (workcenter.id, start_date, workcenter.id, start_date))
                res = cr.fetchall()
                first_date = False
                to_date = False
                between_capacity = init_cap
                intervals = []
                if between_capacity < capacity:
                    first_date = datetime.strptime(start_date, DEFAULT_SERVER_DATETIME_FORMAT)
                    from_capacity = capacity - between_capacity
                    intervals = workcenter.calendar_id.interval_get(first_date, workorder.hour / from_capacity)
                    to_date = intervals[0][-1][1]
                for date, cap in res:
                    between_capacity += cap
                    date_fmt = datetime.strptime(date, DEFAULT_SERVER_DATETIME_FORMAT)
                    if not first_date and (between_capacity < capacity):
                        first_date = date_fmt
                        from_capacity = capacity - between_capacity
                        intervals = workcenter.calendar_id.interval_get(first_date, workorder.hour / from_capacity)
                        to_date = intervals[0][-1][1]
                    elif between_capacity >= capacity:
                        first_date = False
                        to_date = False
                        from_capacity = 0
                        intervals = []
                    elif first_date and (to_date <= date_fmt):
                        break
                    elif first_date: #Change date when minimum capacity is not attained
                        if from_capacity > capacity - between_capacity:
                            from_capacity = capacity - between_capacity
                            intervals = workcenter.calendar_id.interval_get(first_date, workorder.hour / from_capacity)
                            to_date = intervals[0][-1][1]
                workorder.write({'date_planned_start': first_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                 'date_planned_end': to_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                                 'capacity_planned': from_capacity})
                start_date = to_date.strftime(DEFAULT_SERVER_DATETIME_FORMAT)

    @api.multi
    def action_cancel(self):
        """ Cancels the production order and related stock moves.
        :return: True
        """
        ProcurementOrder = self.env['procurement.order']
        for production in self:
            if production.move_created_ids:
                production.move_created_ids.action_cancel()
            procs = ProcurementOrder.search([('move_dest_id', 'in', [record.id for record in production.move_line_ids])])
            if procs:
                procs.cancel()
            production.move_line_ids.action_cancel()
        self.write({'state': 'cancel'})
        # Put related procurements in exception
        procs = ProcurementOrder.search([('production_id', 'in', [self.ids])])
        if procs:
            procs.message_post(body=_('Manufacturing order cancelled.'))
            procs.write({'state': 'exception'})
        return True

    def do_prepare_partial(self):
        pack_operation_obj = self.env['stock.pack.operation']
        pack_lot_obj = self.env['stock.pack.operation.lot']
        #get list of existing operations and delete them
        existing_operation_ids = pack_operation_obj.search([('production_raw_id', 'in', self.ids), ('production_state', '!=', 'done')])
        if existing_operation_ids:
            existing_operation_ids.write({'qty_reserved': 0.0, 'qty_done': 0.0})
            #TODO: put packlots at 0 too
        for production in self:
            # prepare Consume Lines
            forced_qties = {}  # Quantity remaining after calculating reserved quants
            total_quants = self.env['stock.quant']
            total_moves = self.env['stock.move']
            #Calculate packages, reserved quants, qtys of this picking's moves
            for move in production.move_line_ids:
                if move.state not in ('assigned', 'confirmed', 'waiting'):
                    continue
                total_moves |= move
                move_quants = move.reserved_quant_ids
                total_quants |= move_quants
                forced_qty = move.product_qty - sum([x.qty for x in move_quants])
                #if we used force_assign() on the move, or if the move is incoming, forced_qty > 0
                if float_compare(forced_qty, 0, precision_rounding=move.product_id.uom_id.rounding) > 0:
                    if forced_qties.get(move.product_id):
                        forced_qties[move.product_id] += forced_qty
                    else:
                        forced_qties[move.product_id] = forced_qty
            # Existing reservations:
            ops_todo = {}
            ops_reserved = {}
            lots_todo = {}
            lots_reserved = {}
            for quant in total_quants:
                if quant.qty <= 0: 
                    continue
                key = (quant.product_id.id, quant.package_id.id, quant.owner_id.id, quant.location_id.id)
                packops = production.consume_operation_ids.filtered(lambda x: (key == (x.product_id.id, x.package_id.id, x.owner_id.id, x.location_id.id)) and x.production_state != 'done')#x.product_id.id == quant.product_id.id and quant.package_id.id == x.package_id.id and quant.location_id.id == x.location_id.id)
                if packops:
                    # Add to existing packages
                    ops = packops[0]
                else:
                    ops = pack_operation_obj.create({'product_qty': 0,
                                                    'product_id': quant.product_id.id,
                                                    'package_id': quant.package_id.id,
                                                    'owner_id': quant.owner_id.id,
                                                    'location_id': quant.location_id.id,
                                                    'location_dest_id': quant.product_id.property_stock_production.id,
                                                    'product_uom_id': quant.product_id.uom_id.id,
                                                    'production_raw_id': production.id,
                                                    })
                ops_todo.setdefault(ops.id , 0)
                ops_reserved.setdefault(ops.id , 0)
                ops_todo[ops.id] += quant.qty
                ops_reserved[ops.id] += quant.qty
                if quant.lot_id:
                    lots = []#self.env['stock.pack.operation.lot'] #browse record
                    if packops:
                        for pack in packops:
                            lots += [x.id for x in pack.pack_lot_ids if x.lot_id.id == quant.lot_id.id]
                    if lots:
                        lot = lots[0]
                    else:
                        lot = pack_lot_obj.create({'lot_id': quant.lot_id.id, 'qty': 0.0, 'qty_todo': 0, 'operation_id': ops.id})
                    lots_todo.setdefault(lot.id, 0.0)
                    lots_todo[lot.id] += quant.qty
                    lots_reserved.setdefault(lot.id, 0.0)
                    lots_reserved[lot.id] += quant.qty
            
            # Do something with forced quantities
            for product in forced_qties:
                packops = production.consume_operation_ids.filtered(lambda x: (product.id == x.product_id.id) and x.production_state != 'done')#x.product_id.id == quant.product_id.id and quant.package_id.id == x.package_id.id and quant.location_id.id == x.location_id.id)
                if packops:
                    # Add to existing packages
                    ops = packops[0]
                else:
                    ops = pack_operation_obj.create({'product_qty': 0,
                                                    'product_id': product.id,
                                                    'package_id': False,
                                                    #TODO:'owner_id': ops.owner_id.id,
                                                    'location_id': production.location_src_id.id,
                                                    'location_dest_id': product.property_stock_production.id,
                                                    'product_uom_id': product.uom_id.id,
                                                    'production_raw_id': production.id,
                                                    })
                ops_todo.setdefault(ops.id , 0)
                ops_todo[ops.id] += forced_qties[product]

            # Now update all existing pack operations and pack operation lots
            for ops in ops_todo.keys() + ops_reserved.keys():
                ops_rec = pack_operation_obj.browse(ops)
                #TODO: reduce to one write instead
                if ops_todo.get(ops):
                    ops_rec.product_qty = ops_todo[ops]
                if ops_reserved.get(ops):
                    ops_rec.qty_reserved = ops_reserved[ops]
            for lot in lots_todo.keys():
                lot_rec = pack_lot_obj.browse(lot)
                lot_rec.qty_todo = lots_todo[lot]

    def do_prepare_partial_produce(self):
        pack_operation_obj = self.env['stock.pack.operation']
        #get list of existing operations and delete them
        existing_operation_ids = pack_operation_obj.search([('production_finished_id', 'in', self.ids), ('production_state', '!=', 'done')])
        if existing_operation_ids:
            existing_operation_ids.unlink()
        for production in self:
            # prepare Consume Lines
            forced_qties = {}  # Quantity remaining after calculating reserved quants
            total_quants = self.env['stock.quant']
            total_moves = self.env['stock.move']
            #Calculate packages, reserved quants, qtys of this picking's moves
            for move in production.move_created_ids:
                if move.state not in ('assigned', 'confirmed', 'waiting'):
                    continue
                total_moves |= move
                # Nothing is reserved here normally, so we could skip it
                move_quants = move.reserved_quant_ids
                total_quants |= move_quants
                forced_qty = (move.state == 'assigned') and move.product_qty - sum([x.qty for x in move_quants]) or 0
                #if we used force_assign() on the move, or if the move is incoming, forced_qty > 0
                if float_compare(forced_qty, 0, precision_rounding=move.product_id.uom_id.rounding) > 0:
                    if forced_qties.get(move.product_id):
                        forced_qties[move.product_id] += forced_qty
                    else:
                        forced_qties[move.product_id] = forced_qty
            for vals in total_moves._prepare_pack_ops(total_quants, forced_qties):
                vals['fresh_record'] = False
                vals['production_finished_id'] = production.id
                pack_operation_obj.create(vals)


    @api.multi
    def action_production_end(self):
        """ Changes production state to Finish and writes finished date.
        :return: True
        """
        self._costs_generate()
        write_res = self.write({'state': 'done', 'date_finished': fields.datetime.now()})
        # Check related procurements
        self.env["procurement.order"].search([('production_id', 'in', self.ids)]).check()
        return write_res

    def _get_subproduct_factor(self, move=None):
        """ Compute the factor to compute the qty of procucts to produce for the given production_id. By default,
            it's always equal to the quantity encoded in the production order or the production wizard, but if the
            module mrp_subproduct is installed, then we must use the move_id to identify the product to produce
            and its quantity.
        :param production_id: ID of the mrp.order
        :param move_id: ID of the stock move that needs to be produced. Will be used in mrp_subproduct.
        :return: The factor to apply to the quantity that we should produce for the given production order.
        """
        return 1

    def _get_produced_qty(self):
        ''' returns the produced quantity of product 'production.product_id' for the given production, in the product UoM
        '''
        produced_qty = 0
        for produced_product in self.move_created_ids2:
            if (produced_product.scrapped) or (produced_product.product_id.id != self.product_id.id):
                continue
            produced_qty += produced_product.product_qty
        return produced_qty


    def _calculate_qty(self, to_produce_qty=0.0): #Add option to put them partially or not at all
        self.ensure_one()
        consume_dict = {}
        for move in self.move_line_ids:
            if move.reserved_quant_ids:
                for quant in move.reserved_quant_ids:
                    key = (move.workorder_id.id, move.product_id.id, quant.lot_id.id, move.product_uom.id)
                    consume_dict.setdefault(key, 0.0)
                    consume_dict[key] += quant.qty
            elif move.state == 'assigned':
                key = (move.workorder_id.id, move.product_id.id, False, move.product_uom.id)
                consume_dict.setdefault(key, 0.0)
                consume_dict[key] += move.product_qty
        consume_lines=[]
        for key in consume_dict:
            consume_lines.append({'product_id': key[1], 'product_qty': consume_dict[key], 'production_lot_ids': key[2], 'workorder_id': key[0], 'product_uom_id': key[3]})
        return consume_lines

    @api.multi
    def create_lots_for_po(self):
        lot_obj = self.env['stock.production.lot']
        opslot_obj = self.env['stock.pack.operation.lot']
        to_unlink = []
        for production in self:
            for ops in production.produce_operation_ids: #TODO: Need to filter here
                for opslot in ops.pack_lot_ids:
                    if not opslot.lot_id:
                        lot_id = lot_obj.create({'name': opslot.lot_name, 'product_id': ops.product_id.id})
                        opslot.write({'lot_id': lot_id.id})
                #Unlink pack operations where qty = 0
                to_unlink += [x.id for x in ops.pack_lot_ids if x.qty == 0.0]
        opslot_obj.browse(to_unlink).unlink()

    @api.multi
    def do_transfer(self):
        """
            If no pack operation, we do simple action_done of the picking
            Otherwise, do the pack operations
        """
        stock_move_obj = self.env['stock.move']
        #self.create_lots_for_po() --> Normally not necessary for consumption 
        for production in self:
            
            consume_operation_ids = production.consume_operation_ids.filtered(lambda x: x.production_state != 'done')
            #Split pack operations first
            for operation in consume_operation_ids:
                if operation.qty_done < 0:
                    raise UserError(_('No negative quantities allowed'))
                if operation.qty_done > 0:
                    remainder = operation.product_qty - operation.qty_done
                    operation.write({'product_qty': operation.qty_done})
                    if remainder:
                        operation.copy({'product_qty': remainder, 'qty_done': 0.0})
            
            consume_operation_ids = production.consume_operation_ids.filtered(lambda x: x.production_state != 'done' and x.qty_done > 0)
            # Do what would have been done otherwise
            need_rereserve, all_op_processed = production.move_line_ids.recompute_remaining_qty(consume_operation_ids)
            
            #create extra moves in the picking (unexpected product moves coming from pack operations)
            todo_move_ids = []
            if not all_op_processed:
                location_src = production.move_line_ids[0].location_id
                location_dest = production.move_line_ids[0].location_dest_id
                group = production.move_line_ids[0].group_id
                extra_moves = consume_operation_ids._create_extra_moves(location_src, location_dest, group)
                todo_move_ids += extra_moves

            #split move lines if needed
            toassign_move_ids = []
            for move in production.move_line_ids:
                remaining_qty = move.remaining_qty
                if move.state in ('done', 'cancel'):
                    #ignore stock moves cancelled or already done
                    continue
                elif move.state == 'draft':
                    toassign_move_ids.append(move.id)
                if float_compare(remaining_qty, 0,  precision_rounding=move.product_id.uom_id.rounding) == 0:
                    if move.state in ('draft', 'assigned', 'confirmed'):
                        todo_move_ids.append(move.id)
                elif float_compare(remaining_qty,0, precision_rounding=move.product_id.uom_id.rounding) > 0 and \
                            float_compare(remaining_qty, move.product_qty, precision_rounding=move.product_id.uom_id.rounding) < 0:
                    new_move = stock_move_obj.split(move, remaining_qty)
                    todo_move_ids.append(move.id)
                    #Assign move as it was assigned before
                    toassign_move_ids.append(new_move)
            if need_rereserve or not all_op_processed:
                stock_move_obj.browse(todo_move_ids).action_assign()
                need_rereserve, all_op_processed = production.move_line_ids.recompute_remaining_qty(consume_operation_ids)
            self.env['stock.move'].browse(todo_move_ids).action_done()
            consume_operation_ids.write({'production_state': 'done'})
            
            # Need to transfer done moves to finished products for creating the consumed_for link
        return True

    @api.multi
    def do_transfer_finished(self):
        """
            If no pack operation, we do simple action_done of the picking
            Otherwise, do the pack operations
        """
        stock_move_obj = self.env['stock.move']
        self.create_lots_for_po()
        for production in self:
            produce_operation_ids = production.produce_operation_ids.filtered(lambda x: x.production_state != 'done')
            
            #Split pack operations first
            for operation in produce_operation_ids:
                if operation.qty_done < 0:
                    raise UserError(_('No negative quantities allowed'))
                if operation.qty_done > 0:
                    remainder = operation.product_qty - operation.qty_done
                    operation.write({'product_qty': operation.qty_done})
                    if remainder:
                        operation.copy({'product_qty': remainder, 'qty_done': 0.0})
            
            produce_operation_ids = production.produce_operation_ids.filtered(lambda x: x.production_state != 'done' and x.qty_done > 0)
            # Do what would have been done otherwise
            need_rereserve, all_op_processed = production.move_created_ids.recompute_remaining_qty(produce_operation_ids)
            
            #create extra moves in the picking (unexpected product moves coming from pack operations)
            todo_move_ids = []
            if not all_op_processed:
                location_src = production.move_created_ids[0].location_id
                location_dest = production.move_created_ids[0].location_dest_id
                group = production.move_created_ids[0].group_id
                todo_move_ids += produce_operation_ids._create_extra_moves(location_src, location_dest, group)

            #split move lines if needed
            toassign_move_ids = []
            for move in production.move_created_ids:
                remaining_qty = move.remaining_qty
                if move.state in ('done', 'cancel'):
                    #ignore stock moves cancelled or already done
                    continue
                elif move.state == 'draft':
                    toassign_move_ids.append(move.id)
                if float_compare(remaining_qty, 0,  precision_rounding=move.product_id.uom_id.rounding) == 0:
                    if move.state in ('draft', 'assigned', 'confirmed'):
                        todo_move_ids.append(move.id)
                elif float_compare(remaining_qty,0, precision_rounding=move.product_id.uom_id.rounding) > 0 and \
                            float_compare(remaining_qty, move.product_qty, precision_rounding=move.product_id.uom_id.rounding) < 0:
                    new_move = stock_move_obj.split(move, remaining_qty)
                    todo_move_ids.append(move.id)
                    #Assign move as it was assigned before
                    toassign_move_ids.append(new_move)
            if need_rereserve or not all_op_processed:
                stock_move_obj.browse(todo_move_ids).action_assign()
                need_rereserve, all_op_processed = production.move_created_ids.recompute_remaining_qty(produce_operation_ids)
            self.env['stock.move'].browse(todo_move_ids).action_done()
            produce_operation_ids.write({'production_state': 'done'})
        return True

    @api.multi
    def post_inventory(self):
        self.do_transfer() #TODO: Need to give back move_ids done for consumed_for relationship
        self.do_transfer_finished()

    @api.multi
    def action_produce(self, production_qty, wizard=False):
        """ All stock move lines of raw materials will be done/consumed
        and stock move lines of final product will be also done/produced.
        :param production_qty: specify qty to produce in the uom of the production order
        :param wizard: the mrp produce product wizard, which will tell the amount of consumed products needed
        :return: True
        """
        self.ensure_one()
        # Filter produce line, otherwise create one:
        produce_operations = self.produce_operation_ids.filtered(lambda x: x.production_state == 'confirmed' and x.product_id.id == self.product_id.id)
        #TODO: byproducts?
        ratio = 1.0
        if produce_operations:
            produce_operations[0].qty_done += production_qty
            ratio = production_qty / produce_operations[0].product_qty
        else:
            self.env['stock.pack.operation'].create({'product_id': self.product_id.id,
                                                    'product_uom_id': self.product_uom_id.id,
                                                    'product_qty': production_qty,
                                                    'location_id': self.location_src_id.id,
                                                    'location_dest_id': self.location_dest_id.id})
        # TODO: Change consumed products
        # The rounding used can be changed
        consume_operations = self.consume_operation_ids.filtered(lambda x: x.production_state == 'confirmed')
        for operation in consume_operations:
            operation.qty_done += ratio * operation.product_qty
        return True

    def _make_production_produce_line(self):
        procs = self.env['procurement.order'].search([('production_id', '=', self.id)])
        procurement = procs and procs[0]
        data = {
            'name': self.name,
            'date': self.date_planned,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'location_id': self.product_id.property_stock_production.id,
            'location_dest_id': self.location_dest_id.id,
            'move_dest_id': self.move_prod_id.id,
            'procurement_id': procurement and procurement.id,
            'company_id': self.company_id.id,
            'production_id': self.id,
            'origin': self.name,
            'group_id': procurement and procurement.group_id.id,
        }
        move_id = self.env['stock.move'].create(data)
        # a phantom bom cannot be used in mrp order so it's ok to assume the list returned by action_confirm
        # is 1 element long, so we can take the first.
        move_id.action_confirm()
        move_id.action_assign()
        return True

    def _get_raw_material_procure_method(self, product, location=False, location_dest=False):
        '''This method returns the procure_method to use when creating the stock move for the production raw materials
        Besides the standard configuration of looking if the product or product category has the MTO route,
        you can also define a rule e.g. from Stock to Production (which might be used in the future like the sale orders)
        '''
        routes = product.route_ids + product.categ_id.total_route_ids

        if location and location_dest:
            pull = self.env['procurement.rule'].search([('route_id', 'in', routes.ids),
                                                        ('location_id', '=', location_dest.id),
                                                        ('location_src_id', '=', location.id)], limit=1)
            if pull:
                return pull.procure_method

        try:
            mto_route = self.env['stock.warehouse']._get_mto_route()
        except:
            return "make_to_stock"

        if mto_route in routes.ids:
            return "make_to_order"
        return "make_to_stock"

    def _create_previous_move(self, move, source_location, dest_location):
        '''
        When the routing gives a different location than the raw material location of the production order,
        we should create an extra move from the raw material location to the location of the routing, which
        precedes the consumption line (chained).  The picking type depends on the warehouse in which this happens
        and the type of locations.
        '''
        # Need to search for a picking type
        code = move.get_code_from_locs(source_location, dest_location)
        if code == 'outgoing':
            check_loc = source_location
        else:
            check_loc = dest_location
        warehouse = check_loc.get_warehouse()
        domain = [('code', '=', code)]
        if warehouse:
            domain += [('warehouse_id', '=', warehouse)]
        types = self.env['stock.picking.type'].search(domain)
        move = move.copy(default={
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'procure_method': self._get_raw_material_procure_method(move.product_id, location=source_location,
                                                                    location_dest=dest_location),
            'raw_material_production_id': False,
            'move_dest_id': move.id,
            'picking_type_id': types and types[0] or False,
        })
        return move


    def _prepare_consume_line(self, line, source_location, prev_move):
        """
            Prepare consume lines based on BoM 
        """
        self.ensure_one()
        product = self.env['product.product'].browse(line['product_id'])
        WorkOrder = self.env['mrp.production.workcenter.line']
        destination_location = self.product_id.property_stock_production
        vals = {
            'name': self.name,
            'date': self.date_planned,
            'product_id': product.id,
            'product_uom_qty': line['product_uom_qty'],
            'product_uom': line['product_uom_id'],
            'location_id': source_location.id,
            'location_dest_id': destination_location.id,
            'company_id': self.company_id.id,
            'procure_method': prev_move and 'make_to_stock' or self._get_raw_material_procure_method(product, location=source_location,
                                                                                                     location_dest=destination_location),  # Make_to_stock avoids creating procurement
            'raw_material_production_id': self.id,
            'price_unit': product.standard_price,
            'origin': self.name,
            'warehouse_id': self.location_src_id.get_warehouse(),
            'group_id': self.move_prod_id.group_id.id,
            'operation_id': line['operation_id'],
            'workorder_id' : WorkOrder.search([('operation_id', '=', line['operation_id']), ('production_id', '=', self.id)], limit=1).id,
        }
        return vals

    @api.multi
    def generate_moves(self, properties=None):
        """ 
            Generates moves and work orders
        """
        WorkOrder = self.env['mrp.production.workcenter.line']
        for production in self:
            #Produce lines
            production._make_production_produce_line()
            #The weird line
            if production.move_prod_id and production.move_prod_id.location_id.id != production.location_dest_id.id:
                production.move_prod_id.write({'location_id': production.location_dest_id.id})
            production.do_prepare_partial_produce()
            #Consume lines
            results, results2 = production._prepare_lines(properties=properties)
            stock_moves = self.env['stock.move']
            source_location = production.location_src_id
            prev_move = False
            prod_location=source_location
            if production.bom_id.routing_id and production.bom_id.routing_id.location_id and self.bom_id.routing_id.location_id != source_location:
                source_location = production.bom_id.routing_id.location_id
                prev_move=True
            for line in results:
                product = self.env['product.product'].browse(line['product_id'])
                if product.type in ['product', 'consu']:
                    stock_move_vals = production._prepare_consume_line(line, source_location, prev_move)
                    stock_move_vals['raw_material_production_id'] = production.id
                    stock_move = self.env['stock.move'].create(stock_move_vals)
                    stock_moves = stock_moves | stock_move
                    if prev_move:
                        prev_move = self._create_previous_move(stock_move, prod_location, source_location)
                        stock_moves = stock_moves | prev_move
            if stock_moves:
                stock_moves.action_confirm()
        return True

    @api.multi
    def action_assign(self):
        """
        Checks the availability on the consume lines of the production order
        """
        for production in self:
            production.move_line_ids.action_assign()
            production.do_prepare_partial()
            status  = any([x.state != 'assigned' for x in production.move_line_ids])
            if status:
                production.check_move_state = True
        return True

    @api.multi
    def close_warning_message(self):
        self.ensure_one()
        self.check_move_state = False

#     @api.multi
#     def force_assign(self):
#         for order in self:
#             order.move_line_ids.force_assign()
#             order.do_prepare_partial()
#         return True

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
            'context': {'product_ids': self.move_line_ids.mapped('product_id').ids + self.produce_operation_ids.mapped('product_id').ids},
            'target': 'new',
        }


class MrpProductionWorkcenterLine(models.Model):
    _name = 'mrp.production.workcenter.line'
    _description = 'Work Order'
    _order = 'sequence'
    _inherit = ['mail.thread']

    @api.multi
    @api.depends('time_ids')
    def _compute_started(self):
        for workorder in self:
            running = [x.date_start for x in workorder.time_ids if x.state == 'running']
            if running:
                workorder.started_since = running[0]

    @api.multi
    def _compute_delay(self):
        for workorder in self:
            duration = sum(workorder.time_ids.filtered(lambda x: x.state == 'done').mapped('duration'))
            workorder.delay = duration
            workorder.delay_stop = duration

    @api.multi
    @api.depends('consume_operation_ids')
    def _compute_availability(self):
        for workorder in self:
            if workorder.consume_operation_ids:
                if any([x.state != 'assigned' for x in workorder.move_line_ids if not x.scrapped]):
                    workorder.availability = 'waiting'
                else:
                    workorder.availability = 'assigned'
            else:
                workorder.availability = workorder.production_id.availability == 'assigned' and 'assigned' or 'waiting'

    def _check_produce_qty(self):
        for workorder in self:
            if workorder.qty_produced >= workorder.qty:
                workorder.check_produce_qty = True

    @api.depends('production_id', 'workcenter_id', 'production_id.bom_id', 'production_id.picking_type_id')
    def _get_inventory_message(self):
        InventoryMessage = self.env['inventory.message']
        msg = ''
        for workorder in self:
            if workorder.production_id or workorder.workcenter_id:
                domain = [
                    '|', '|', ('picking_type_id', '=', workorder.production_id.picking_type_id.id),
                    ('bom_id', '=', workorder.production_id.bom_id.id),
                    ('workcenter_id', '=', workorder.workcenter_id.id),
                    ('valid_until', '>=', fields.Date.today())
                ]
                messages = InventoryMessage.search(domain)
                for invmessage in messages:
                    msg += "".join(invmessage.message)
                workorder.inv_message = msg
                workorder.inv_message_ids = [(6, 0, messages.ids)]

    name = fields.Char(string='Work Order', required=True)
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center', required=True)
    hour = fields.Float(string='Expected Duration', digits=(16, 2))
    sequence = fields.Integer(required=True, default=1, help="Gives the sequence order when displaying a list of work orders.")
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', track_visibility='onchange', index=True, ondelete='cascade', required=True)
    state = fields.Selection([('pending', 'Pending'), ('ready', 'Ready'), ('progress', 'In Progress'), ('done', 'Finished'), ('cancel', 'Cancelled')], default='pending')
    date_planned_start = fields.Datetime('Scheduled Date Start')
    date_planned_end = fields.Datetime('Scheduled Date Finished')
    capacity_planned = fields.Integer('Capacity Planned')
    date_start = fields.Datetime('Effective Start Date')
    date_finished = fields.Datetime('Effective End Date')
    delay = fields.Float('Real Duration', compute='_compute_delay', readonly=True)
    delay_stop = fields.Float('Stop Duration', compute='_compute_delay', readonly=True)
    qty_produced = fields.Float('Qty Produced', readonly=True, help="The number of products already handled by this work order", default=0.0) #TODO: decimal precision
    operation_id = fields.Many2one('mrp.routing.workcenter', 'Operation') #Should be used differently as BoM can change in the meantime
    move_line_ids = fields.One2many('stock.move', 'workorder_id', 'Moves')
    consume_operation_ids = fields.One2many('stock.pack.operation', 'workorder_id')
    availability = fields.Selection([('waiting', 'Waiting'), ('assigned', 'Available')], 'Stock Availability', store=True, compute='_compute_availability')
    production_state = fields.Selection(related='production_id.state', readonly=True)
    product = fields.Many2one('product.product', related='production_id.product_id', string="Product", readonly=True)
    qty = fields.Float(related='production_id.product_qty', string='Qty', readonly=True, store=True) #store really needed?
    uom = fields.Many2one('product.uom', related='production_id.product_uom_id', string='Unit of Measure')
    started_since = fields.Datetime('Started Since', compute='_compute_started')
    time_ids = fields.One2many('mrp.production.workcenter.line.time', 'workorder_id')
    worksheet = fields.Binary('Worksheet', related='operation_id.worksheet', readonly=True)
    show_state = fields.Boolean(compute='_get_current_state')
    check_produce_qty = fields.Boolean(compute='_check_produce_qty')
    inv_message = fields.Html(compute="_get_inventory_message")
    inv_message_ids = fields.One2many('inventory.message', compute='_get_inventory_message', string='Messages')
    consume_line_ids = fields.One2many('mrp.production.workcenter.line.consume', 'workorder_id', 'Consume Lines')
    active_consume_line_ids = fields.One2many('mrp.production.workcenter.line.consume', 'workorder_id', 'Active Consume Lines', domain=[('processed', '=', False)])
    final_lot_id = fields.Many2one('stock.production.lot', 'Current Final Lot Working On', domain="[('product_id', '=', product_id)]") # Might need to become separate object when doing multiple in parallel
    qty_producing = fields.Float('Qty Producing')


    def _add_qty(self, product_qty):
        '''
            Adds qty to workorder and checks if the next workorder should be put to ready
        '''
        self.ensure_one()
        self.qty_produced += product_qty
        # Next work order becomes available if not already
        workorders = [x.id for x in self.production_id.workcenter_line_ids]
        old_index = workorders.index(self.id)
        new_index = old_index + 1
        if new_index < len(workorders):
            workorder_next = self.env['mrp.production.workcenter.line'].browse(workorders[new_index])
            if workorder_next.state == 'confirmed':
                workorder_next.state = 'ready'
        if self.qty_produced >= self.qty:
            self.button_finish()

    @api.multi
    def record_production(self):
        self.ensure_one()
        if not self.consume_line_ids:
            #TODO: should return action
            data_obj = self.env['ir.model.data']
            action = data_obj.xmlid_to_res_id('mrp.act_mrp_product_produce_wo')
            act_obj = self.env['ir.actions.act_window']
            result = act_obj.read([action])[0]
            return result
            
        if self.qty_producing <= 0:
            raise UserError(_('You should specify a positive quantity you are producing'))
        for consume in self.consume_line_ids:
            # Add quantities to pack operations in production order
            consume.processed = True
            consume_ops = self.production_id.consume_operation_ids.filtered(lambda x: x.product_id.id == consume.product_id.id)
            if not consume_ops:
                # Need to see, we could create it on the fly too
                raise UserError('You deleted something')
            if not consume.lot_id: #maybe need to check tracking of the different products
                consume_ops[0].qty_done += consume.product_qty
            else:
                pack_lots = []
                for ops in consume_ops:
                    # Find ops 
                    pack_lots += [x for x in ops.pack_lot_ids if x.lot_id.id == consume.lot_id.id]
                if pack_lots:
                    pack_lots[0].qty += consume.product_qty
                    pack_lots[0].operation_id.qty_done += consume.product_qty
                    consume.operation_id = pack_lots[0].operation_id.id
                    consume.final_lot_id = self.final_lot_id
                    consume.final_qty = self.qty_producing
                else:
                    oplot = self.env['stock.pack.operation.lot'].create({'operation_id': consume_ops[0].id, 'lot_id': consume.lot_id.id, 'qty': consume.product_qty})
                    consume.operation_id = consume_ops[0].id
                    consume.final_lot_id = self.final_lot_id
                    consume.final_qty = self.qty_producing
        #Recreate consume lines
        for move in self.move_line_ids:
            self.env['mrp.production.workcenter.line.consume'].create({'product_id': move.product_id.id, 'workorder_id': self.id})
        #Augment qty
        self._add_qty(self.qty_producing)
        #Resetting qty (we assume lot stays the same more or less)
        self.qty_producing = 0.0
        
    def _get_current_state(self):
        for order in self:
            if order.time_ids.filtered(lambda x : x.user_id.id == self.env.user.id and x.state == 'running'):
                order.show_state = True
            else:
                order.show_state = False

    # Plan should disappear -> created when doing production
    @api.multi
    def button_plan(self):
        self.ensure_one()
        self.write({'state': 'planned'})

    @api.multi
    def button_start(self):
        timeline = self.env['mrp.production.workcenter.line.time']
        for workorder in self:
            if workorder.production_id.state != 'progress':
                workorder.production_id.state = 'progress'
            timeline.create({'workorder_id': workorder.id,
                             'state': 'running',
                             'date_start': datetime.now(),
                             'user_id': self.env.user.id})
        self.write({'state': 'progress',
                    'date_start': datetime.now(),
                    })

    @api.multi
    def button_finish(self):
        self.ensure_one()
        self.end_all()
        self.write({'state': 'done'})

    @api.multi
    def end_previous(self):
        timeline_obj = self.env['mrp.production.workcenter.line.time']
        for workorder in self:
            timeline = timeline_obj.search([('workorder_id', '=', workorder.id), ('state', '=', 'running'), ('user_id', '=', self.env.user.id)], limit=1)
            timed = datetime.now() - fields.Datetime.from_string(timeline.date_start)
            hours = timed.total_seconds() / 3600.0
            timeline.write({'state': 'done',
                            'duration': hours})

    @api.multi
    def end_all(self):
        timeline_obj = self.env['mrp.production.workcenter.line.time']
        for workorder in self:
            timelines = timeline_obj.search([('workorder_id', '=', workorder.id), ('state', '=', 'running')])
            for timeline in timelines:
                timed = datetime.now() - fields.Datetime.from_string(timeline.date_start)
                hours = timed.total_seconds() / 3600.0
                timeline.write({'state': 'done',
                                'duration': hours})

    @api.multi
    def button_pending(self):
        self.end_previous()

    @api.multi
    def button_cancel(self):
        self.write({'state': 'cancel'})

    @api.multi
    def button_done(self):
        self.end_all()
        self.write({'state': 'done',
                    'date_finished': datetime.now()})

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
            'context': {'default_workorder_id': self.ids[0], 'product_ids': self.move_line_ids.mapped('product_id').ids + [self.product.id]},
            'target': 'new',
        }


class MrpProductionWorkcenterLineTime(models.Model):
    _name='mrp.production.workcenter.line.time'
    _description = 'Work Order Timesheet Line'
    
    workorder_id = fields.Many2one('mrp.production.workcenter.line', 'Work Order')
    date_start = fields.Datetime('Start Date')
    duration = fields.Float('Duration')
    user_id = fields.Many2one('res.users', string="User")
    state = fields.Selection([('running', 'Running'), ('done', 'Done')], string="Status", default="running")


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

    name = fields.Char(string='Reference', required=True, readonly=True, copy=False, default='New')
    product_id = fields.Many2one('product.product', string="Product", required=True, states={'done': [('readonly', True)]})
    product_qty = fields.Float('Quantity', required=True, states={'done': [('readonly', True)]})
    product_uom_id = fields.Many2one('product.uom', string="Unit of Measure", required=True, states={'done': [('readonly', True)]})
    bom_id = fields.Many2one('mrp.bom', 'Bill of Material', required=True, domain=[('product_tmpl_id', '=', 'product_id.product_tmpl_id')], states={'done': [('readonly', True)]})  # Add domain
    mo_id = fields.Many2one('mrp.production', string='Manufacturing Order', states={'done': [('readonly', True)]})
    lot_id = fields.Many2one('stock.production.lot', 'Lot', domain="[('product_id','=', product_id)]", states={'done': [('readonly', True)]})
    location_id = fields.Many2one('stock.location', 'Location', required=True, default=_src_id_default, states={'done': [('readonly', True)]})
    consume_line_ids = fields.One2many('stock.move', 'unbuild_raw_material_id', string="Consume Product", readonly=True)
    produce_line_ids = fields.One2many('stock.move', 'unbuild_id', readonly=True)
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft', index=True)
    location_dest_id = fields.Many2one('stock.location', string='Destination Location', required=True, default=_dest_id_default, states={'done': [('readonly', True)]})

    @api.constrains('product_qty')
    def _check_qty(self):
        if self.product_qty <= 0:
            raise ValueError(_('Unbuild product quantity cannot be negative or zero!'))

    def _prepare_lines(self, properties=None):
        # search BoM structure and route
        bom_point = self.bom_id
        if not bom_point:
            bom_point = self.env['mrp.bom']._bom_find(product=self.product_id, properties=properties)
            if bom_point:
                self.write({'bom_id': bom_point.id})
        if not bom_point:
            raise UserError(_("Cannot find a bill of material for this product."))
        # get components and workcenter_line_ids from BoM structure
        factor = self.product_uom_id._compute_qty(self.product_qty, bom_point.product_uom_id.id)
        # product_line_ids, workcenter_line_ids
        return bom_point.explode(self.product_id, factor / bom_point.product_qty, properties=properties)

    def generate_move_line(self):
        stock_moves = self.env['stock.move']
        for order in self:
            result, results2 = order._prepare_lines()
            for line in result:
                vals = {
                    'name': order.name,
                    'date': order.create_date,
                    'product_id': line['product_id'],
                    'product_uom': line['product_uom_id'],
                    'product_uom_qty': line['product_uom_qty'],
                    'unbuild_id': order.id,
                    'location_id': order.product_id.property_stock_production.id,
                    'location_dest_id': order.location_dest_id.id,
                    'origin': order.name,
                }
                stock_moves = stock_moves | self.env['stock.move'].create(vals)
            if stock_moves:
                self.produce_line_ids = stock_moves
                stock_moves.action_confirm()

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('mrp.unbuild') or 'New'
        unbuild = super(MrpUnbuild, self).create(vals)
        unbuild._make_unbuild_line()
        unbuild.generate_move_line()
        return unbuild

    def _make_unbuild_line(self):
        data = {
            'name': self.name,
            'date': self.create_date,
            'product_id': self.product_id.id,
            'product_uom': self.product_uom_id.id,
            'product_uom_qty': self.product_qty,
            'restrict_lot_id': self.lot_id.id,
            'location_id': self.location_id.id,
            'location_dest_id': self.product_id.property_stock_production.id,
            'unbuild_raw_material_id': self.id,
            'unbuild_id': self.id,
            'origin': self.name
        }
        self.env['stock.move'].create(data).action_confirm()

    @api.onchange('mo_id')
    def onchange_mo_id(self):
        if self.mo_id:
            self.product_id = self.mo_id.product_id.id
            self.product_qty = self.mo_id.product_qty

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.bom_id = self.env['mrp.bom']._bom_find(product=self.product_id, properties=[])
            self.product_uom_id = self.product_id.uom_id.id

    @api.multi
    def button_unbuild(self):
        self.consume_line_ids.action_done()
        self.produce_line_ids.action_done()
        self.write({'state': 'done'})

    @api.multi
    def button_open_move(self):
        stock_moves = self.env['stock.move'].search([('origin', '=', self.name)])
        return {
            'name': _('Stock Moves'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'stock.move',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id', 'in', stock_moves.ids)],
        }

    #TODO: need quants defined here


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
    picking_type_id = fields.Many2one('stock.picking.type', string="Alert on Operation")
    code = fields.Selection(related='picking_type_id.code', store=True)
    product_id = fields.Many2one('product.product', string="Product")
    bom_id = fields.Many2one('mrp.bom', 'Bill of Material')
    workcenter_id = fields.Many2one('mrp.workcenter', string='Work Center')
    valid_until = fields.Date(default=_default_valid_until)

    @api.onchange('product_id')
    def onchange_product_id(self):
        if self.product_id:
            self.bom_id = self.env['mrp.bom']._bom_find(product=self.product_id, properties=[])


class StockScrap(models.Model):
    _inherit = "stock.scrap"

    workorder_id = fields.Many2one('mrp.production.workcenter.line', 'Work Order')
